# core/subprocess_progress_handler.py

import asyncio
import json
import logging
import re
import time
from typing import Optional

from rich.progress import Progress, TaskID

from config_manager import config
from .exceptions import DownloadStalledException

log = logging.getLogger(__name__)


class SubprocessProgressHandler:
    """处理子进程的进度跟踪和输出解析"""
    
    def __init__(self):
        self.network_timeout = config.downloader.network_timeout

    def _parse_size_to_bytes(self, size_str: str) -> int:
        """将 yt-dlp 输出中的大小字符串（例如 '10.5MiB'）转换为字节数。"""
        if not size_str:
            return 0
        size_str = size_str.replace('~', '').strip()
        units = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4, "PiB": 1024**5,
                 "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4, "PB": 1000**5}
        
        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    value = float(size_str[:-len(unit)])
                    return int(value * multiplier)
                except ValueError:
                    log.warning(f"无法解析大小字符串: {size_str}")
                    return 0
        log.warning(f"未知大小单位或格式: {size_str}")
        return 0

    def _handle_json_progress_data(self, progress_data: dict, progress: Progress, task_id: TaskID) -> bool:
        """
        处理JSON格式的进度数据
        
        Returns:
            bool: 是否成功处理了进度数据
        """
        if progress_data.get('status') == 'downloading':
            percentage = progress_data.get('_percent')
            total_bytes = progress_data.get('total_bytes')
            downloaded_bytes = progress_data.get('downloaded_bytes')

            if percentage is not None and total_bytes is not None and downloaded_bytes is not None:
                # 确保任务可见后再更新进度
                if not progress.tasks[task_id].visible:
                    progress.update(task_id, visible=True)
                progress.update(task_id, completed=downloaded_bytes, total=total_bytes)
                return True
                
        elif progress_data.get('status') == 'finished':
            # 确保任务可见后再更新进度
            if not progress.tasks[task_id].visible:
                progress.update(task_id, visible=True)
            progress.update(task_id, completed=progress.tasks[task_id].total or 1, 
                          total=progress.tasks[task_id].total or 1)
            return True
        return False

    def _handle_text_progress_data(self, line: str, progress: Progress, task_id: TaskID) -> bool:
        """
        处理文本格式的进度数据
        
        Returns:
            bool: 是否成功处理了进度数据
        """
        if '[download]' not in line:
            return False
            
        # 尝试匹配下载进度的正则表达式
        match = re.search(r'(\d+\.\d+)%\s+of\s+(~?\d+\.\d+[KMGTP]?i?B)(?:\s+at\s+(\d+\.\d+[KMGTP]?i?B/s|\d+\.\d+[KMGTP]?i?B/s|unknown\s+speed))?(?:\s+ETA\s+(\d{2}:\d{2}|unknown))?', line)
        
        if match:
            percentage = float(match.group(1))
            total_size_str = match.group(2)
            total_bytes = self._parse_size_to_bytes(total_size_str)
            completed_bytes = int(total_bytes * (percentage / 100.0))
            
            # 确保任务可见后再更新进度
            if not progress.tasks[task_id].visible:
                progress.update(task_id, visible=True)
            progress.update(task_id, completed=completed_bytes, total=total_bytes)
            return True
            
        elif 'Destination' in line or 'already has best quality' in line:
            # 确保任务可见后再更新进度
            if not progress.tasks[task_id].visible:
                progress.update(task_id, visible=True)
            progress.update(task_id, completed=progress.tasks[task_id].total or 1, 
                          total=progress.tasks[task_id].total or 1)
            return True
            
        return False

    def _process_line(self, line: str, progress: Progress, task_id: TaskID) -> bool:
        """
        处理单行输出
        
        Returns:
            bool: 是否成功处理了进度数据
        """
        # 首先尝试解析为JSON
        try:
            progress_data = json.loads(line)
            return self._handle_json_progress_data(progress_data, progress, task_id)
        except json.JSONDecodeError:
            # 如果不是JSON，尝试解析文本格式
            return self._handle_text_progress_data(line, progress, task_id)

    async def _read_process_output(self, process: asyncio.subprocess.Process, 
                                 progress: Progress, task_id: TaskID) -> str:
        """
        读取并处理进程输出
        
        Returns:
            str: 累积的错误输出
        """
        error_output = ""
        
        while True:
            if process.stdout is None:
                break
                
            try:
                line_bytes = await asyncio.wait_for(
                    process.stdout.readline(), 
                    self.network_timeout
                )
                if not line_bytes:
                    break
                
                line = line_bytes.decode('utf-8', errors='ignore')
                error_output += line
                
                # 处理这一行的进度数据
                self._process_line(line, progress, task_id)
                
            except asyncio.TimeoutError:
                raise DownloadStalledException(f"下载超时 ({self.network_timeout}s 无进度更新)")
        
        return error_output

    def _finalize_progress(self, process: asyncio.subprocess.Process, 
                          progress: Progress, task_id: TaskID) -> None:
        """
        完成进度处理
        """
        if process.returncode == 0:
            progress.update(task_id, completed=progress.tasks[task_id].total or 100)

    async def handle_subprocess_with_progress(self, process: asyncio.subprocess.Process,
                                            progress: Progress, task_id: TaskID) -> str:
        """
        处理带进度显示的子进程
        
        Args:
            process: 子进程对象
            progress: Rich进度条对象
            task_id: 任务ID
            
        Returns:
            str: 累积的错误输出
            
        Raises:
            DownloadStalledException: 当下载超时时
        """
        error_output = await self._read_process_output(process, progress, task_id)
        
        # 等待进程完成
        await process.wait()
        
        # 完成进度处理
        self._finalize_progress(process, progress, task_id)
        
        return error_output