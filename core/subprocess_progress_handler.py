# core/subprocess_progress_handler.py

import asyncio
import json
import logging
import re

from rich.progress import Progress, TaskID

from config_manager import config
from .exceptions import DownloadStalledException

log = logging.getLogger(__name__)


class SubprocessProgressHandler:
    """处理子进程的进度跟踪和输出解析"""

    def __init__(self):
        self.network_timeout = config.downloader.network_timeout
        # 用于跟踪组合下载的进度
        self.combined_download_state = {
            "video_total": 0,
            "video_completed": 0,
            "audio_total": 0,
            "audio_completed": 0,
            "current_file_type": None,
            "is_combined_download": False,
        }

    def _parse_size_to_bytes(self, size_str: str) -> int:
        """将 yt-dlp 输出中的大小字符串（例如 '10.5MiB'）转换为字节数。"""
        if not size_str:
            return 0
        size_str = size_str.replace("~", "").strip()
        units = {
            "B": 1,
            "KiB": 1024,
            "MiB": 1024**2,
            "GiB": 1024**3,
            "TiB": 1024**4,
            "PiB": 1024**5,
            "KB": 1000,
            "MB": 1000**2,
            "GB": 1000**3,
            "TB": 1000**4,
            "PB": 1000**5,
        }

        for unit, multiplier in units.items():
            if size_str.endswith(unit):
                try:
                    value = float(size_str[: -len(unit)])
                    return int(value * multiplier)
                except ValueError:
                    log.warning(f"无法解析大小字符串: {size_str}")
                    return 0
        log.warning(f"未知大小单位或格式: {size_str}")
        return 0

    def _handle_json_progress_data(
        self, progress_data: dict, progress: Progress, task_id: TaskID
    ) -> bool:
        """
        处理JSON格式的进度数据

        Returns:
            bool: 是否成功处理了进度数据
        """
        if progress_data.get("status") == "downloading":
            percentage = progress_data.get("_percent")
            total_bytes = progress_data.get("total_bytes")
            downloaded_bytes = progress_data.get("downloaded_bytes")
            filename = progress_data.get("filename", "")

            if (
                percentage is not None
                and total_bytes is not None
                and downloaded_bytes is not None
            ):
                # 检测是否是组合下载（文件名包含不同格式）
                self._detect_combined_download(filename, total_bytes, downloaded_bytes)

                # 计算显示的进度
                display_total, display_completed = self._calculate_combined_progress(
                    total_bytes, downloaded_bytes
                )

                # 确保任务可见后再更新进度
                if not progress.tasks[task_id].visible:
                    progress.update(task_id, visible=True)
                progress.update(
                    task_id, completed=display_completed, total=display_total
                )
                return True

        elif progress_data.get("status") == "finished":
            filename = progress_data.get("filename", "")
            self._mark_file_finished(filename)

            # 确保任务可见后再更新进度
            if not progress.tasks[task_id].visible:
                progress.update(task_id, visible=True)

            # 如果是组合下载，显示总进度
            if self.combined_download_state["is_combined_download"]:
                total_combined = (
                    self.combined_download_state["video_total"]
                    + self.combined_download_state["audio_total"]
                )
                completed_combined = (
                    self.combined_download_state["video_completed"]
                    + self.combined_download_state["audio_completed"]
                )
                progress.update(
                    task_id, completed=completed_combined, total=total_combined
                )
            else:
                progress.update(
                    task_id,
                    completed=progress.tasks[task_id].total or 1,
                    total=progress.tasks[task_id].total or 1,
                )
            return True
        return False

    def _detect_combined_download(
        self, filename: str, total_bytes: int, downloaded_bytes: int
    ):
        """检测组合下载并更新状态"""
        if not filename:
            return

        # 更智能的检测逻辑
        filename_lower = filename.lower()

        # 添加调试日志
        log.debug(f"检测文件类型: filename={filename}, size={total_bytes}bytes")

        # 检测音频格式标识符 - 优先检测，因为有些音频文件也是webm格式
        is_audio_format = (
            any(
                indicator in filename_lower
                for indicator in [
                    "audio",
                    "Audio",
                    "AUDIO",
                    ".m4a",
                    ".opus",
                    ".mp3",
                    ".aac",
                ]
            )
            or ("hls-audio" in filename_lower)
            or ("f251" in filename_lower)
            or ("f140" in filename_lower)
        )

        # 检测视频格式标识符（hls-, webm-, mp4-等）- 但排除音频标识符
        is_video_format = any(
            indicator in filename_lower
            for indicator in [
                "hls-",
                "dash-",
                "webm-",
                "mp4-",
                ".mp4",
                ".webm",
                ".mkv",
                "f398",
                "f137",
            ]
        ) and not any(
            audio_indicator in filename_lower
            for audio_indicator in ["audio", "Audio", "AUDIO", "f251", "f140"]
        )

        # 基于文件名和大小的综合判断
        if is_audio_format:
            # 明确的音频标识
            log.debug(f"检测为音频文件: {filename} ({total_bytes}bytes)")
            self.combined_download_state["audio_total"] = total_bytes
            self.combined_download_state["audio_completed"] = downloaded_bytes
            self.combined_download_state["current_file_type"] = "audio"
            self.combined_download_state["is_combined_download"] = True
        elif is_video_format or total_bytes > 5 * 1024 * 1024:  # >5MB 可能是视频
            # 明确的视频标识或较大文件
            log.debug(f"检测为视频文件: {filename} ({total_bytes}bytes)")
            self.combined_download_state["video_total"] = total_bytes
            self.combined_download_state["video_completed"] = downloaded_bytes
            self.combined_download_state["current_file_type"] = "video"
            self.combined_download_state["is_combined_download"] = True
        else:
            # 基于文件大小的备用判断
            if total_bytes < 5 * 1024 * 1024:  # <5MB，可能是音频
                log.debug(f"基于大小检测为音频文件: {filename} ({total_bytes}bytes)")
                self.combined_download_state["audio_total"] = total_bytes
                self.combined_download_state["audio_completed"] = downloaded_bytes
                self.combined_download_state["current_file_type"] = "audio"
                self.combined_download_state["is_combined_download"] = True

    def _calculate_combined_progress(self, total_bytes: int, downloaded_bytes: int):
        """计算组合下载的显示进度"""
        if not self.combined_download_state["is_combined_download"]:
            return total_bytes, downloaded_bytes

        # 更新当前文件的进度
        current_type = self.combined_download_state["current_file_type"]
        if current_type == "video":
            self.combined_download_state["video_completed"] = downloaded_bytes
        elif current_type == "audio":
            self.combined_download_state["audio_completed"] = downloaded_bytes

        # 计算总进度 - 智能显示逻辑
        video_total = self.combined_download_state["video_total"]
        video_completed = self.combined_download_state["video_completed"]
        audio_total = self.combined_download_state["audio_total"]
        audio_completed = self.combined_download_state["audio_completed"]

        # 如果两个文件大小都已知，根据当前下载的文件类型显示对应大小
        if video_total > 0 and audio_total > 0:
            if current_type == "video":
                return video_total, video_completed
            elif current_type == "audio":
                return audio_total, audio_completed
            else:
                # 如果当前类型未知，显示总大小
                return video_total + audio_total, video_completed + audio_completed
        elif video_total > 0:
            # 只有视频大小已知，显示视频进度
            return video_total, video_completed
        elif audio_total > 0:
            # 只有音频大小已知，显示音频进度
            return audio_total, audio_completed
        else:
            # 都未知，显示当前文件进度
            return total_bytes, downloaded_bytes

    def _mark_file_finished(self, filename: str):
        """标记文件下载完成"""
        if not filename:
            return

        # 使用与检测相同的逻辑判断文件类型
        filename_lower = filename.lower()

        # 检测音频格式标识符
        is_audio_format = any(
            indicator in filename_lower
            for indicator in [
                "audio",
                "Audio",
                "AUDIO",
                ".m4a",
                ".opus",
                ".mp3",
                ".aac",
            ]
        ) or ("hls-audio" in filename_lower)

        # 检测视频格式标识符
        is_video_format = any(
            indicator in filename_lower
            for indicator in ["hls-", "dash-", "webm-", "mp4-", ".mp4", ".webm", ".mkv"]
        ) and not any(
            audio_indicator in filename_lower
            for audio_indicator in ["audio", "Audio", "AUDIO"]
        )

        if is_audio_format:
            self.combined_download_state["audio_completed"] = (
                self.combined_download_state["audio_total"]
            )
        elif is_video_format:
            self.combined_download_state["video_completed"] = (
                self.combined_download_state["video_total"]
            )

    def _handle_text_progress_data(
        self, line: str, progress: Progress, task_id: TaskID
    ) -> bool:
        """
        处理文本格式的进度数据

        Returns:
            bool: 是否成功处理了进度数据
        """
        if "[download]" not in line:
            return False

        # 尝试匹配下载进度的正则表达式
        match = re.search(
            r"(\d+\.\d+)%\s+of\s+(~?\d+\.\d+[KMGTP]?i?B)(?:\s+at\s+(\d+\.\d+[KMGTP]?i?B/s|\d+\.\d+[KMGTP]?i?B/s|unknown\s+speed))?(?:\s+ETA\s+(\d{2}:\d{2}|unknown))?",
            line,
        )

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

        elif "Destination" in line or "already has best quality" in line:
            # 确保任务可见后再更新进度
            if not progress.tasks[task_id].visible:
                progress.update(task_id, visible=True)
            progress.update(
                task_id,
                completed=progress.tasks[task_id].total or 1,
                total=progress.tasks[task_id].total or 1,
            )
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

    async def _read_process_output(
        self, process: asyncio.subprocess.Process, progress: Progress, task_id: TaskID
    ) -> str:
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
                    process.stdout.readline(), self.network_timeout
                )
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="ignore")

                # Only add error lines to error_output
                if (
                    "error" in line.lower()
                    or "failed" in line.lower()
                    or "exception" in line.lower()
                ):
                    error_output += line

                # 处理这一行的进度数据
                self._process_line(line, progress, task_id)

            except asyncio.TimeoutError:
                raise DownloadStalledException(
                    f"下载超时 ({self.network_timeout}s 无进度更新)"
                )

        return error_output

    def _finalize_progress(
        self, process: asyncio.subprocess.Process, progress: Progress, task_id: TaskID
    ) -> None:
        """
        完成进度处理
        """
        if process.returncode == 0:
            progress.update(task_id, completed=progress.tasks[task_id].total or 100)

    async def handle_subprocess_with_progress(
        self, process: asyncio.subprocess.Process, progress: Progress, task_id: TaskID
    ) -> str:
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
        # 重置组合下载状态
        self.combined_download_state = {
            "video_total": 0,
            "video_completed": 0,
            "audio_total": 0,
            "audio_completed": 0,
            "current_file_type": None,
            "is_combined_download": False,
        }

        error_output = await self._read_process_output(process, progress, task_id)

        # 等待进程完成
        await process.wait()

        # 完成进度处理
        self._finalize_progress(process, progress, task_id)

        return error_output
