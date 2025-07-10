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

log = logging.getLogger(__name__)
console = Console()

# --- Custom Exceptions ---
class DownloaderException(Exception):
    """下载器模块的基础异常。"""
    pass

class MaxRetriesExceededException(DownloaderException):
    """当操作在所有重试后仍然失败时抛出。"""
    pass

class NetworkException(DownloaderException):
    """针对可能是临时性的网络相关错误。"""
    pass

class ProxyException(NetworkException):
    """针对代理特定的连接错误。"""
    pass

class DownloadStalledException(NetworkException):
    """当下载似乎停滞时抛出。"""
    pass

class NonRecoverableErrorException(DownloaderException):
    """针对不应重试的错误，例如 404 Not Found。"""
    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details

class FFmpegException(DownloaderException):
    """当 ffmpeg 处理文件失败时抛出。"""
    pass

# --- Circuit Breaker States ---
from enum import Enum

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

# --- End of Custom Exceptions ---


class Downloader:
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        self.download_folder = download_folder
        self.cookies_file = cookies_file
        self.proxy = proxy

        # 从 Pydantic 模型直接获取配置
        self.max_retries = config.downloader.max_retries
        self.base_delay = config.downloader.base_delay
        self.max_delay = config.downloader.max_delay
        self.backoff_factor = config.downloader.backoff_factor
        self.network_timeout = config.downloader.network_timeout
        self.stall_detection_time = config.downloader.stall_detection_time
        self.stall_check_interval = config.downloader.stall_check_interval
        self.stall_threshold_count = config.downloader.stall_threshold_count
        self.proxy_retry_base_delay = config.downloader.proxy_retry_base_delay
        self.proxy_retry_increment = config.downloader.proxy_retry_increment
        self.proxy_retry_max_delay = config.downloader.proxy_retry_max_delay

        self.connectivity_test_host = config.advanced.connectivity_test_host
        self.connectivity_test_port = config.advanced.connectivity_test_port
        self.connectivity_timeout = config.advanced.connectivity_timeout
        self.proxy_test_url = config.advanced.proxy_test_url
        self.proxy_test_timeout = config.advanced.proxy_test_timeout

        self.circuit_breaker_failure_threshold = config.downloader.circuit_breaker_failure_threshold
        self.circuit_breaker_timeout = config.downloader.circuit_breaker_timeout

        # Circuit Breaker state
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0

        console.print(f"🔄 重试机制已启用: 最多 {self.max_retries} 次重试，基础延迟 {self.base_delay}s", style="bold blue")
        console.print(f"🌐 网络中断处理: 将持续重试直到网络恢复（最多50次）", style="bold cyan")

    async def _check_network_connectivity(self) -> bool:
        """异步的网络连接检查"""
        try:
            await asyncio.wait_for(
                asyncio.open_connection(self.connectivity_test_host, self.connectivity_test_port),
                timeout=self.connectivity_timeout
            )
            return True
        except (OSError, asyncio.TimeoutError):
            return False

    def _calculate_delay(self, attempt: int) -> int:
        """计算指数退避延迟时间"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        jitter = random.uniform(0.5, 1.5)
        delay = min(delay * jitter, self.max_delay)
        return int(delay)

    def _should_retry(self, error_output: str) -> bool:
        error_lower = error_output.lower()
        return any(re.search(p.lower(), error_lower) for p in config.downloader.retry_patterns)

    def _is_proxy_error(self, error_output: str) -> bool:
        error_lower = error_output.lower()
        return any(p.lower() in error_lower for p in config.downloader.proxy_patterns)

    def _check_circuit_breaker(self):
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

    def _record_failure(self):
        """记录一次失败，并根据阈值转换熔断器状态。"""
        self._failure_count += 1
        if self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            self._failure_count = 0  # Reset failure count for OPEN state
            log.warning("熔断器从 HALF-OPEN 转换为 OPEN 状态。")
        elif self._circuit_breaker_state == CircuitBreakerState.CLOSED and self._failure_count >= self.circuit_breaker_failure_threshold:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            log.warning(f"连续失败 {self._failure_count} 次，熔断器从 CLOSED 转换为 OPEN 状态。")

    def _reset_circuit_breaker(self):
        """重置熔断器到 CLOSED 状态。"""
        if self._circuit_breaker_state != CircuitBreakerState.CLOSED:
            log.info("熔断器重置为 CLOSED 状态。")
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0

    def _build_base_yt_dlp_cmd(self) -> List[str]:
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings']
        if self.proxy: cmd.extend(['--proxy', self.proxy])
        if self.cookies_file:
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        return cmd

    async def _execute_subprocess_with_retries(self, cmd: List[str], stdout_pipe: Any, stderr_pipe: Any) -> asyncio.subprocess.Process:
        attempt = 0
        while attempt <= self.max_retries:
            self._check_circuit_breaker()
            process = None
            try:
                if attempt > 0:
                    delay = self._calculate_delay(attempt - 1)
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
                self._record_failure()
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
        cmd = self._build_base_yt_dlp_cmd() + ['--flat-playlist', '--print-json', '--skip-download', url]
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

        with Progress(
            TextColumn("[bold blue]⬇️ {task.description}"), BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%", "|", DownloadColumn(), "|",
            TransferSpeedColumn(), "|", TimeRemainingColumn(), console=console, expand=True
        ) as progress:
            console.print("📥 正在下载视频部分...", style="bold green")
            video_task = progress.add_task("下载视频", total=100)
            vid_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestvideo[ext=mp4]/bestvideo',
                     '--newline', '-o', f"{self.download_folder / video_part_base}.%(ext)s", video_url]
            await self._run_subprocess_with_progress(vid_cmd, progress, video_task)

            console.print("🔊 正在下载音频部分...", style="bold green")
            audio_task = progress.add_task("下载音频", total=100)
            aud_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestaudio[ext=m4a]/bestaudio',
                     '--newline', '-o', f"{self.download_folder / audio_part_base}.%(ext)s", video_url]
            await self._run_subprocess_with_progress(aud_cmd, progress, audio_task)

            vid_part = next(self.download_folder.glob(f"{video_part_base}.*"), None)
            aud_part = next(self.download_folder.glob(f"{audio_part_base}.*"), None)

            if not (vid_part and aud_part):
                merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                if merged_file:
                    console.print("✅ 检测到媒体源已合并", style="bold green")
                    return merged_file
                raise NonRecoverableErrorException("未找到下载的视频或音频文件")

            console.print("✅ 视频/音频下载完成", style="bold green")

        return await self.merge_to_mp4(vid_part, aud_part, file_prefix)

    async def merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Path:
        console.print("🔧 正在合并视频和音频...", style="bold yellow")
        final_path = self.download_folder / f"{file_prefix}.mp4"
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()),
               '-c', 'copy', str(final_path.resolve())]

        try:
            await self._run_subprocess(cmd, True)
            console.print(f"✅ 视频合并成功: {final_path.name}", style="bold green")
            return final_path
        except Exception as e:
            raise FFmpegException(f"视频合并失败: {e}")

    async def download_metadata(self, url: str, file_prefix: str) -> None:
        cmd = self._build_base_yt_dlp_cmd() + ['--skip-download', '--write-info-json', '--write-thumbnail',
                                             '--convert-thumbnails', 'png', '-o', str(self.download_folder / file_prefix), url]
        await self._run_subprocess(cmd)

    async def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Path:
        console.print(f"🎥 正在提取音频: {video_path.name}", style="bold blue")
        mp3_path = self.download_folder / f"{file_prefix}.mp3"
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]

        try:
            await self._run_subprocess(cmd, True)
            console.print(f"✅ 音频提取成功: {mp3_path.name}", style="bold green")
            return mp3_path
        except Exception as e:
            raise FFmpegException(f"音频提取失败: {e}")

    async def cleanup_temp_files(self, file_prefix: str) -> None:
        # Using asyncio.to_thread for synchronous glob and unlink
        loop = asyncio.get_running_loop()
        def _cleanup():
            for p in self.download_folder.glob(f"{file_prefix}.f*"): p.unlink(missing_ok=True)
            for p in self.download_folder.glob(f"{file_prefix}_*.tmp.*"): p.unlink(missing_ok=True)
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

    async def _run_subprocess_with_progress(self, cmd: List[str], progress: Progress, task_id: TaskID) -> None:
        process = await self._execute_subprocess_with_retries(cmd, asyncio.subprocess.PIPE, asyncio.subprocess.STDOUT)

        error_output = ""
        last_progress_time = time.time()

        while True:
            if process.stdout is None:
                break
            try:
                line_bytes = await asyncio.wait_for(process.stdout.readline(), self.network_timeout)
                if not line_bytes:
                    break
                
                line = line_bytes.decode('utf-8', errors='ignore')
                error_output += line
                last_progress_time = time.time()

                if '[download]' in line and '%' in line:
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        percentage = float(percent_match.group(1))
                        progress.update(task_id, completed=percentage)
            
            except asyncio.TimeoutError:
                raise DownloadStalledException(f"下载超时 ({self.network_timeout}s 无进度更新)")

        retcode = await process.wait()
        if retcode == 0:
            progress.update(task_id, completed=progress.tasks[task_id].total or 100)
            self._reset_circuit_breaker() # Reset circuit breaker on success
            return

        if process.stderr is None:
            error_output = ""
        else:
            error_output = (await process.stderr.read()).decode('utf-8', errors='ignore')

        if self._is_proxy_error(error_output):
            raise ProxyException(f"代理连接失败: {error_output[:200]}")
        elif self._should_retry(error_output):
            raise NetworkException(f"可重试的网络错误: {error_output[:200]}")
        else:
            raise NonRecoverableErrorException("发生不可重试的错误", details=error_output)

    async def _run_subprocess(self, cmd: List[str], capture_output: bool = False) -> None:
        process = await self._execute_subprocess_with_retries(cmd, asyncio.subprocess.PIPE, asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            self._reset_circuit_breaker() # Reset circuit breaker on success
            return

        if stderr is None:
            error_output = ""
        else:
            error_output = stderr.decode('utf-8', errors='ignore')

        if self._is_proxy_error(error_output):
            raise ProxyException(f"代理连接失败: {error_output[:200]}")
        elif self._should_retry(error_output):
            raise NetworkException(f"可重试的网络错误: {error_output[:200]}")
        else:
            raise DownloaderException(f"命令 '{cmd[0]}' 执行失败: {error_output}")