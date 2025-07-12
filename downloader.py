#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能，重构后的版本使用核心模块组件
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeRemainingColumn,
    DownloadColumn, TransferSpeedColumn, TaskID
)

from config_manager import config
from core import (
    DownloaderException, FFmpegException, with_retries,
    CommandBuilder, SubprocessManager, FileProcessor
)

log = logging.getLogger(__name__)
console = Console()

# 全局进度条信号量，确保同时只有一个进度条活动
_progress_semaphore = asyncio.Semaphore(1)


class Downloader:
    """
    简化的下载器，主要负责下载流程编排。
    
    重构后专注于业务流程，具体的执行逻辑委托给核心模块。
    """
    
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        """
        初始化下载器。
        
        Args:
            download_folder: 下载文件夹路径
            cookies_file: cookies文件路径（可选）
            proxy: 代理服务器地址（可选）
        """
        self.download_folder = Path(download_folder)
        self.cookies_file = cookies_file
        self.proxy = proxy
        
        # 组合各种专门的处理器
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.subprocess_manager = SubprocessManager()
        self.file_processor = FileProcessor(self.subprocess_manager, self.command_builder)
        
        log.info(f'初始化下载器，目标文件夹: {self.download_folder}')
        if cookies_file:
            log.info(f'使用cookies文件: {cookies_file}')
        if proxy:
            log.info(f'使用代理: {proxy}')
    
    async def stream_playlist_info(self, url: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式获取播放列表信息。
        
        Args:
            url: 视频或播放列表URL
            
        Yields:
            包含视频信息的字典
            
        Raises:
            DownloaderException: 获取信息失败
        """
        try:
            # 构建获取信息的命令
            info_cmd = self.command_builder.build_playlist_info_cmd(url)
            
            # 执行命令获取信息
            return_code, stdout, stderr = await self.subprocess_manager.execute_simple(
                info_cmd, timeout=60, check_returncode=True
            )
            
            # 解析JSON输出
            for line in stdout.strip().split('\n'):
                if line.strip():
                    try:
                        video_info = json.loads(line)
                        yield video_info
                    except json.JSONDecodeError as e:
                        log.warning(f'解析视频信息JSON失败: {e}')
                        continue
                        
        except Exception as e:
            raise DownloaderException(f'获取播放列表信息失败: {e}') from e
    
    @with_retries(max_retries=3)
    async def download_and_merge(self, video_url: str, file_prefix: str) -> Optional[Path]:
        """
        下载视频和音频并合并为MP4格式。
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            
        Returns:
            合并后的文件路径，失败返回None
            
        Raises:
            DownloaderException: 下载或合并失败
        """
        try:
            log.info(f'开始下载并合并: {file_prefix}')
            
            # 构建下载命令
            download_cmd, file_prefix_used = await self.command_builder.build_combined_download_cmd(
                str(self.download_folder), video_url
            )
            
            # 创建进度条
            async with _progress_semaphore:
                with Progress(
                    TextColumn('[progress.description]{task.description}'),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    
                    # 创建进度任务
                    task_id = progress.add_task(
                        f'⬇️ 下载合并视频', total=None
                    )
                    
                    # 执行下载命令
                    return_code, stdout, stderr = await self.subprocess_manager.execute_with_progress(
                        download_cmd, progress, task_id, timeout=1800  # 30分钟超时
                    )
            
            # 查找生成的文件 - 支持多种视频格式
            output_file = await self._find_output_file(file_prefix, ('.mp4', '.webm', '.mkv', '.avi'))
            if output_file and await self.file_processor.verify_file_integrity(output_file):
                log.info(f'下载合并成功: {output_file.name}')
                return output_file
            else:
                raise DownloaderException(f'下载合并失败，未找到有效的输出文件')
                
        except Exception as e:
            log.error(f'下载合并过程失败: {e}', exc_info=True)
            # 清理可能的临时文件
            await self.file_processor.cleanup_temp_files(
                str(self.download_folder / file_prefix)
            )
            raise
    
    @with_retries(max_retries=3)
    async def download_audio_directly(self, video_url: str, file_prefix: str) -> Optional[Path]:
        """
        直接下载音频文件。
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            
        Returns:
            下载的音频文件路径，失败返回None
            
        Raises:
            DownloaderException: 下载失败
        """
        try:
            log.info(f'开始直接下载音频: {file_prefix}')
            
            # 构建音频下载命令
            audio_cmd = await self.command_builder.build_audio_download_cmd(
                str(self.download_folder), video_url, file_prefix
            )
            
            # 创建进度条
            async with _progress_semaphore:
                with Progress(
                    TextColumn('[progress.description]{task.description}'),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    
                    # 创建进度任务
                    task_id = progress.add_task(
                        f'⬇️ 下载音频', total=None
                    )
                    
                    # 执行下载命令
                    return_code, stdout, stderr = await self.subprocess_manager.execute_with_progress(
                        audio_cmd, progress, task_id, timeout=1800  # 30分钟超时
                    )
            
            # 查找生成的文件 - 支持多种音频格式
            output_file = await self._find_output_file(file_prefix, ('.mp3', '.m4a', '.opus', '.aac', '.webm'))
            if output_file and await self.file_processor.verify_file_integrity(output_file):
                log.info(f'音频下载成功: {output_file.name}')
                return output_file
            else:
                raise DownloaderException(f'音频下载失败，未找到有效的输出文件')
                
        except Exception as e:
            log.error(f'音频下载过程失败: {e}', exc_info=True)
            # 清理可能的临时文件
            await self.file_processor.cleanup_temp_files(
                str(self.download_folder / file_prefix)
            )
            raise
    
    async def download_metadata(self, video_url: str, file_prefix: str) -> bool:
        """
        下载视频元数据信息。
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            
        Returns:
            bool: 下载是否成功
            
        Raises:
            DownloaderException: 下载失败
        """
        try:
            log.info(f'开始下载元数据: {file_prefix}')
            
            # 构建元数据下载命令
            metadata_cmd = self.command_builder.build_metadata_download_cmd(
                str(self.download_folder), video_url
            )
            
            # 执行命令获取元数据
            return_code, stdout, stderr = await self.subprocess_manager.execute_simple(
                metadata_cmd, timeout=60, check_returncode=True
            )
            
            log.info(f'元数据下载成功: {file_prefix}')
            return True
                
        except Exception as e:
            log.error(f'元数据下载失败: {e}', exc_info=True)
            raise DownloaderException(f'元数据下载失败: {e}') from e
    
    async def extract_audio_from_video(self, video_file: Path, audio_file: Path) -> bool:
        """
        从已下载的视频文件提取音频。
        
        Args:
            video_file: 源视频文件路径
            audio_file: 目标音频文件路径
            
        Returns:
            bool: 提取是否成功
            
        Raises:
            FFmpegException: 音频提取失败
        """
        try:
            return await self.file_processor.extract_audio_from_local_file(
                video_file, audio_file
            )
        except Exception as e:
            log.error(f'音频提取失败: {e}', exc_info=True)
            raise
    
    async def cleanup_all_incomplete_files(self):
        """
        清理所有未完成的下载文件。
        
        通常在程序异常退出时调用。
        """
        try:
            log.info('开始清理未完成的下载文件...')
            
            # 清理所有正在运行的进程
            await self.subprocess_manager.cleanup_all_processes()
            
            # 清理临时文件
            cleanup_patterns = config.file_processing.cleanup_patterns
            for pattern in cleanup_patterns:
                matching_files = list(self.download_folder.glob(pattern))
                for file_path in matching_files:
                    try:
                        if file_path.exists():
                            file_path.unlink()
                            log.debug(f'清理临时文件: {file_path.name}')
                    except OSError as e:
                        log.warning(f'清理文件失败 {file_path}: {e}')
            
            log.info('临时文件清理完成')
            
        except Exception as e:
            log.error(f'清理过程中出错: {e}', exc_info=True)
    
    async def _find_output_file(self, file_prefix: str, extensions) -> Optional[Path]:
        """
        查找指定前缀和扩展名的输出文件。
        
        Args:
            file_prefix: 文件前缀
            extensions: 文件扩展名（字符串或元组）
            
        Returns:
            找到的文件路径，未找到返回None
        """
        if isinstance(extensions, str):
            extensions = (extensions,)
        
        # 首先尝试精确匹配
        for ext in extensions:
            exact_file = self.download_folder / f'{file_prefix}{ext}'
            if exact_file.exists():
                return exact_file
        
        # 如果精确匹配失败，尝试在下载文件夹中查找最新的匹配文件
        all_files = []
        for ext in extensions:
            pattern = f'*{ext}'
            matching_files = list(self.download_folder.glob(pattern))
            all_files.extend(matching_files)
        
        if all_files:
            # 返回最新修改的文件
            latest_file = max(all_files, key=lambda f: f.stat().st_mtime)
            log.info(f'找到下载文件: {latest_file.name}')
            return latest_file
        
        return None
    
    async def cleanup_temp_files(self, file_prefix: str):
        """
        清理指定前缀的临时文件。
        
        Args:
            file_prefix: 文件前缀
        """
        try:
            await self.file_processor.cleanup_temp_files(file_prefix)
        except Exception as e:
            log.warning(f'清理临时文件时出错: {e}', exc_info=True)
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取下载器当前状态。
        
        Returns:
            包含状态信息的字典
        """
        return {
            'download_folder': str(self.download_folder),
            'cookies_file': self.cookies_file,
            'proxy': self.proxy,
            'running_processes': self.subprocess_manager.get_running_process_count()
        }