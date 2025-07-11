# downloader.py

import asyncio
import json
import logging
import re
import random
import socket
import time
from pathlib import Path
from typing import Optional, List, Generator, Dict, Any, AsyncGenerator

import aiofiles
from rich.console import Console
from rich.progress import (Progress, BarColumn, TextColumn, TimeRemainingColumn,
                           DownloadColumn, TransferSpeedColumn, TaskID)

from config_manager import config
from core import (
    CircuitBreakerState, DownloaderException, MaxRetriesExceededException,
    NetworkException, ProxyException, DownloadStalledException,
    NonRecoverableErrorException, FFmpegException,
    SubprocessProgressHandler, ErrorHandler, CommandBuilder
)

log = logging.getLogger(__name__)
console = Console()

# 全局进度条信号量，确保同时只有一个进度条活动
_progress_semaphore = asyncio.Semaphore(1)


class NetworkManager:
    def __init__(self):
        self.connectivity_test_host = config.advanced.connectivity_test_host
        self.connectivity_test_port = config.advanced.connectivity_test_port
        self.connectivity_timeout = config.advanced.connectivity_timeout
        self.circuit_breaker_failure_threshold = config.downloader.circuit_breaker_failure_threshold
        self.circuit_breaker_timeout = config.downloader.circuit_breaker_timeout
        
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0

    async def check_connectivity(self) -> bool:
        """异步的网络连接检查"""
        try:
            await asyncio.wait_for(
                asyncio.open_connection(self.connectivity_test_host, self.connectivity_test_port),
                timeout=self.connectivity_timeout
            )
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    def check_circuit_breaker(self):
        """检查熔断器状态，并根据需要转换状态。"""
        if self._circuit_breaker_state == CircuitBreakerState.OPEN:
            elapsed_time = time.time() - self._last_failure_timestamp
            if elapsed_time > self.circuit_breaker_timeout:
                self._circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                log.info("熔断器从 OPEN 转换为 HALF-OPEN 状态。")
            else:
                raise DownloaderException("熔断器处于 OPEN 状态，快速失败。")
        elif self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            log.info("熔断器处于 HALF-OPEN 状态，允许一次尝试。")

    def record_failure(self):
        """记录一次失败，并根据阈值转换熔断器状态。"""
        self._failure_count += 1
        if self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            self._failure_count = 0
            log.warning("熔断器从 HALF-OPEN 转换为 OPEN 状态。")
        elif self._circuit_breaker_state == CircuitBreakerState.CLOSED and self._failure_count >= self.circuit_breaker_failure_threshold:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            log.warning(f"连续失败 {self._failure_count} 次，熔断器从 CLOSED 转换为 OPEN 状态。")

    def reset_circuit_breaker(self):
        """重置熔断器到 CLOSED 状态。"""
        if self._circuit_breaker_state != CircuitBreakerState.CLOSED:
            log.info("熔断器重置为 CLOSED 状态。")
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0


class RetryManager:
    def __init__(self):
        self.base_delay = config.downloader.base_delay
        self.max_delay = config.downloader.max_delay
        self.backoff_factor = config.downloader.backoff_factor

    def calculate_delay(self, attempt: int) -> int:
        """计算指数退避延迟时间"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        jitter = random.uniform(0.5, 1.5)
        delay = min(delay * jitter, self.max_delay)
        return int(delay)


class FileProcessor:
    def __init__(self, download_folder: Path):
        self.download_folder = download_folder

    async def merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Path:
        console.print("🔧 正在合并视频和音频...", style="bold yellow")
        final_path = self.download_folder / f"{file_prefix}.mp4"
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()),
               '-c', 'copy', str(final_path.resolve())]

        try:
            await self._run_subprocess(cmd)
            console.print(f"✅ 视频合并成功: {final_path.name}", style="bold green")
            return final_path
        except Exception as e:
            raise FFmpegException(f"视频合并失败: {e}")

    async def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Path:
        console.print(f"🎥 正在提取音频: {video_path.name}", style="bold blue")
        mp3_path = self.download_folder / f"{file_prefix}.mp3"
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]

        try:
            await self._run_subprocess(cmd)
            console.print(f"✅ 音频提取成功: {mp3_path.name}", style="bold green")
            return mp3_path
        except Exception as e:
            raise FFmpegException(f"音频提取失败: {e}")

    async def cleanup_temp_files(self, file_prefix: str) -> None:
        loop = asyncio.get_running_loop()
        def _cleanup():
            for p in self.download_folder.glob(f"{file_prefix}.f*"): 
                p.unlink(missing_ok=True)
            for p in self.download_folder.glob(f"{file_prefix}_*.tmp.*"): 
                p.unlink(missing_ok=True)
        await loop.run_in_executor(None, _cleanup)

    async def cleanup_all_incomplete_files(self) -> None:
        patterns = config.file_processing.cleanup_patterns
        cleaned_files = []
        
        def _cleanup():
            for pattern in patterns:
                for file_path in self.download_folder.glob(pattern):
                    try:
                        file_path.unlink()
                        cleaned_files.append(file_path.name)
                    except Exception as e:
                        log.error(f"清理文件 {file_path.name} 失败: {e}")
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _cleanup)

        if cleaned_files:
            console.print(f"🧹 已清理 {len(cleaned_files)} 个未完成文件", style="bold yellow")

    async def _run_subprocess(self, cmd: List[str]) -> None:
        """Helper method for running subprocess commands"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode('utf-8', errors='ignore') if stderr else ""
            raise FFmpegException(f"Command failed: {' '.join(cmd)}\nError: {error_output}")


class Downloader:
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        self.download_folder = download_folder
        self.cookies_file = cookies_file
        self.proxy = proxy

        # 初始化专门的处理器
        self.progress_handler = SubprocessProgressHandler()
        self.error_handler = ErrorHandler()
        self.network_manager = NetworkManager()
        self.retry_manager = RetryManager()
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.file_processor = FileProcessor(download_folder)

        # 从 Pydantic 模型直接获取配置
        self.max_retries = config.downloader.max_retries
        self.network_timeout = config.downloader.network_timeout
        self.stall_detection_time = config.downloader.stall_detection_time
        self.stall_check_interval = config.downloader.stall_check_interval
        self.stall_threshold_count = config.downloader.stall_threshold_count
        self.proxy_retry_base_delay = config.downloader.proxy_retry_base_delay
        self.proxy_retry_increment = config.downloader.proxy_retry_increment
        self.proxy_retry_max_delay = config.downloader.proxy_retry_max_delay

        self.proxy_test_url = config.advanced.proxy_test_url
        self.proxy_test_timeout = config.advanced.proxy_test_timeout


    async def _execute_subprocess_with_retries(self, cmd: List[str], stdout_pipe: Any, stderr_pipe: Any) -> asyncio.subprocess.Process:
        attempt = 0
        while attempt <= self.max_retries:
            self.network_manager.check_circuit_breaker()
            process = None
            try:
                if attempt > 0:
                    delay = self.retry_manager.calculate_delay(attempt - 1)
                    console.print(f"♾️ 第 {attempt + 1} 次尝试，等待 {delay} 秒...", style="bold yellow")
                    await asyncio.sleep(delay)

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=stdout_pipe,
                    stderr=stderr_pipe
                )
                
                # For mypy type narrowing
                if stdout_pipe == asyncio.subprocess.PIPE:
                    assert process.stdout is not None
                if stderr_pipe == asyncio.subprocess.PIPE:
                    assert process.stderr is not None

                log.info(f"子进程成功创建: {cmd[0]}")
                return process

            except (DownloadStalledException, ProxyException, NetworkException) as e:
                log.warning(f"操作中遇到问题: {e}", exc_info=True)
                self.network_manager.record_failure()
                if process and process.returncode is None: process.kill()
                
                attempt += 1
                if attempt > self.max_retries:
                    raise MaxRetriesExceededException(f"操作在 {self.max_retries + 1} 次尝试后失败。")
                continue

            except KeyboardInterrupt:
                if process and process.returncode is None: process.kill()
                raise
            except Exception as e:
                log.error(f"未知子进程错误: {e}", exc_info=True)
                if process and process.returncode is None: process.kill()
                raise DownloaderException(f"未知子进程错误: {e}")

        raise MaxRetriesExceededException(f"操作在 {self.max_retries + 1} 次尝试后失败。")

    async def stream_playlist_info(self, url: str) -> AsyncGenerator[Dict[str, Any], None]:
        cmd = self.command_builder.build_playlist_info_cmd(url)
        limit = 2 * 1024 * 1024 # 2MB limit
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=limit
        )

        if process.stdout is None:
            log.error(f"无法获取 {url} 的 stdout 流。")
            return

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

        retcode = await process.wait()
        if retcode != 0:
            error = b""
            if process.stderr is not None:
                error = await process.stderr.read()
            log.error(f"解析URL '{url}' 时出错: {error.decode()}")

    async def download_and_merge(self, video_url: str, file_prefix: str) -> Path:
        video_part_base, audio_part_base = f"{file_prefix}_video.tmp", f"{file_prefix}_audio.tmp"

        # 使用信号量确保同时只有一个进度条活动
        async with _progress_semaphore:
            # 先准备命令
            vid_cmd = self.command_builder.build_video_download_cmd(
                f"{self.download_folder / video_part_base}.%(ext)s", video_url
            )
            aud_cmd = self.command_builder.build_audio_download_cmd(
                f"{self.download_folder / audio_part_base}.%(ext)s", video_url
            )
            
            # 创建进度条对象
            with Progress(
                TextColumn("[bold blue]⬇️ {task.description}"), BarColumn(bar_width=None),
                "[progress.percentage]{task.percentage:>3.1f}%", "|", DownloadColumn(), "|",
                TransferSpeedColumn(), "|", TimeRemainingColumn(), console=console, expand=True
            ) as progress:
                
                # 创建隐藏的任务，只有在真正有进度数据时才显示
                video_task = progress.add_task("下载视频", total=None, visible=False)
                await self._run_subprocess_with_progress(vid_cmd, progress, video_task)

                audio_task = progress.add_task("下载音频", total=None, visible=False)
                await self._run_subprocess_with_progress(aud_cmd, progress, audio_task)

            # 检查下载的文件
            vid_part = next(self.download_folder.glob(f"{video_part_base}.*"), None)
            aud_part = next(self.download_folder.glob(f"{audio_part_base}.*"), None)

            if not (vid_part and aud_part):
                merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                if merged_file:
                    console.print("✅ 检测到媒体源已合并", style="bold green")
                    return merged_file
                raise NonRecoverableErrorException("未找到下载的视频或音频文件")

        return await self.file_processor.merge_to_mp4(vid_part, aud_part, file_prefix)

    async def download_metadata(self, url: str, file_prefix: str) -> None:
        cmd = self.command_builder.build_metadata_download_cmd(str(self.download_folder / file_prefix), url)
        await self._run_subprocess(cmd)

    async def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Path:
        return await self.file_processor.extract_audio_from_local_file(video_path, file_prefix)

    async def cleanup_temp_files(self, file_prefix: str) -> None:
        await self.file_processor.cleanup_temp_files(file_prefix)

    async def cleanup_all_incomplete_files(self) -> None:
        await self.file_processor.cleanup_all_incomplete_files()

    async def _run_subprocess_with_progress(self, cmd: List[str], progress: Progress, task_id: TaskID) -> None:
        """简化的进度处理函数，使用专门的处理器"""
        process = await self._execute_subprocess_with_retries(cmd, asyncio.subprocess.PIPE, asyncio.subprocess.STDOUT)
        
        # 使用专门的进度处理器
        error_output = await self.progress_handler.handle_subprocess_with_progress(process, progress, task_id)
        
        # 处理成功的情况
        if process.returncode == 0:
            self.network_manager.reset_circuit_breaker()
            return
        
        # 处理错误情况
        exception = self.error_handler.handle_subprocess_error(process.returncode, error_output, cmd[0])
        if exception:
            raise exception

    async def _run_subprocess(self, cmd: List[str]) -> None:
        """简化的子进程执行函数，使用专门的错误处理器"""
        process = await self._execute_subprocess_with_retries(cmd, asyncio.subprocess.PIPE, asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()

        if process.returncode == 0:
            self.network_manager.reset_circuit_breaker()
            return

        error_output = stderr.decode('utf-8', errors='ignore') if stderr else ""
        exception = self.error_handler.handle_subprocess_error(process.returncode, error_output, cmd[0])
        if exception:
            raise exception