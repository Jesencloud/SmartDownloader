#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能，支持重试机制、进度显示和错误处理
"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeRemainingColumn,
    DownloadColumn, TransferSpeedColumn, TaskID
)

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
    """网络管理器。
    
    负责处理网络连接检查、熔断器状态管理等网络相关功能。
    
    Attributes:
        connectivity_test_host (str): 用于连接测试的主机地址。
        connectivity_test_port (int): 用于连接测试的端口。
        connectivity_timeout (int): 连接测试超时时间。
    """
    
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
        """异步检查网络连接状态。
        
        Returns:
            bool: 如果网络连接正常返回True，否则返回False。
        """
        try:
            await asyncio.wait_for(
                asyncio.open_connection(self.connectivity_test_host, self.connectivity_test_port),
                timeout=self.connectivity_timeout
            )
            return True
        except (OSError, asyncio.TimeoutError, ConnectionError):
            return False

    def check_circuit_breaker(self):
        """检查熔断器状态，并根据需要转换状态。
        
        Raises:
            DownloaderException: 当熔断器处于OPEN状态时。
        """
        if self._circuit_breaker_state == CircuitBreakerState.OPEN:
            elapsed_time = time.time() - self._last_failure_timestamp
            if elapsed_time > self.circuit_breaker_timeout:
                self._circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                log.info('熔断器从 OPEN 转换为 HALF-OPEN 状态。')
            else:
                raise DownloaderException('熔断器处于 OPEN 状态，快速失败。')
        elif self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            log.info('熔断器处于 HALF-OPEN 状态，允许一次尝试。')

    def record_failure(self):
        """记录一次失败，并根据阈值转换熔断器状态。
        
        当失败次数达到阈值时，将熔断器从CLOSED状态转换为OPEN状态。
        """
        self._failure_count += 1
        if self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            self._failure_count = 0
            log.warning('熔断器从 HALF-OPEN 转换为 OPEN 状态。')
        elif self._circuit_breaker_state == CircuitBreakerState.CLOSED and self._failure_count >= self.circuit_breaker_failure_threshold:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            log.warning(f'连续失败 {self._failure_count} 次，熔断器从 CLOSED 转换为 OPEN 状态。')

    def reset_circuit_breaker(self):
        """重置熔断器到CLOSED状态。
        
        清除失败计数和时间戳，将熔断器重置为正常状态。
        """
        if self._circuit_breaker_state != CircuitBreakerState.CLOSED:
            log.info('熔断器重置为 CLOSED 状态。')
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0


class RetryManager:
    """重试管理器。
    
    负责计算重试延迟时间，实现指数退避算法。
    
    Attributes:
        base_delay (int): 基础延迟时间。
        max_delay (int): 最大延迟时间。
        backoff_factor (float): 退避因子。
    """
    
    def __init__(self):
        self.base_delay = config.downloader.base_delay
        self.max_delay = config.downloader.max_delay
        self.backoff_factor = config.downloader.backoff_factor

    def calculate_delay(self, attempt: int) -> int:
        """计算指数退避延迟时间。
        
        Args:
            attempt (int): 当前重试次数。
            
        Returns:
            int: 计算得出的延迟时间（秒）。
        """
        delay = self.base_delay * (self.backoff_factor ** attempt)
        jitter = random.uniform(0.5, 1.5)
        delay = min(delay * jitter, self.max_delay)
        return int(delay)


class FileProcessor:
    """文件处理器。
    
    负责处理文件合并、音频提取、临时文件清理等文件相关操作。
    
    Attributes:
        download_folder (Path): 下载文件夹路径。
    """
    
    def __init__(self, download_folder: Path):
        self.download_folder = download_folder

    async def merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Path:
        """将视频和音频文件合并为MP4格式。
        
        Args:
            video_part (Path): 视频文件路径。
            audio_part (Path): 音频文件路径。
            file_prefix (str): 输出文件前缀。
            
        Returns:
            Path: 合并后的MP4文件路径。
            
        Raises:
            FFmpegException: 当合并过程失败时。
        """
        console.print('🔧 正在合并视频和音频...', style='bold yellow')
        final_path = self.download_folder / f'{file_prefix}.mp4'
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()),
               '-c', 'copy', str(final_path.resolve())]

        try:
            await self._run_subprocess(cmd)
            console.print(f'✅ 视频合并成功: {final_path.name}', style='bold green')
            return final_path
        except (OSError, IOError, PermissionError) as e:
            raise FFmpegException(f'视频合并操作失败，无法访问文件: {e}') from e
        except Exception as e:
            raise FFmpegException(f'视频合并时发生未知错误: {e}') from e

    async def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Path:
        console.print(f'🎥 正在提取音频: {video_path.name}', style='bold blue')
        mp3_path = self.download_folder / f'{file_prefix}.mp3'
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]

        try:
            await self._run_subprocess(cmd)
            console.print(f'✅ 音频提取成功: {mp3_path.name}', style='bold green')
            return mp3_path
        except (OSError, IOError, PermissionError) as e:
            raise FFmpegException(f'音频提取操作失败，无法访问文件: {e}') from e
        except Exception as e:
            raise FFmpegException(f'音频提取时发生未知错误: {e}') from e

    async def cleanup_temp_files(self, file_prefix: str) -> None:
        loop = asyncio.get_running_loop()
        def _cleanup():
            for p in self.download_folder.glob(f'{file_prefix}.f*'): 
                p.unlink(missing_ok=True)
            for p in self.download_folder.glob(f'{file_prefix}_*.tmp.*'): 
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
                    except (OSError, PermissionError) as e:
                        log.error(f'清理文件 {file_path.name} 时权限不足: {e}')
                    except Exception as e:
                        log.error(f'清理文件 {file_path.name} 时发生未知错误: {e}', exc_info=True)
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _cleanup)

        if cleaned_files:
            console.print(f'🧹 已清理 {len(cleaned_files)} 个未完成文件', style='bold yellow')

    async def _run_subprocess(self, cmd: List[str]) -> None:
        """Helper method for running subprocess commands"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode('utf-8', errors='ignore') if stderr else ''
            raise FFmpegException(f'Command failed: {" ".join(cmd)}\nError: {error_output}')


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
                    console.print(f'♾️ 第 {attempt + 1} 次尝试，等待 {delay} 秒...', style='bold yellow')
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

                log.info(f'子进程成功创建: {cmd[0]}')
                return process

            except (DownloadStalledException, ProxyException, NetworkException) as e:
                log.warning(f'操作中遇到问题: {e}')
                self.network_manager.record_failure()
                if process and process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        # 进程已经结束
                        pass
                
                attempt += 1
                if attempt > self.max_retries:
                    raise MaxRetriesExceededException(f'操作在 {self.max_retries + 1} 次尝试后失败。')
                continue

            except KeyboardInterrupt:
                log.warning('用户中断操作')
                if process and process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        # 进程已经结束
                        pass
                raise
            except Exception as e:
                log.error(f'未知子进程错误: {e}', exc_info=True)
                if process and process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        # 进程已经结束
                        pass
                raise DownloaderException(f'未知子进程错误: {e}') from e

        raise MaxRetriesExceededException(f'操作在 {self.max_retries + 1} 次尝试后失败。')

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
            log.error(f'无法获取 {url} 的 stdout 流。')
            return

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                log.debug(f'JSON解析失败，跳过该行: {e}')
                continue

        retcode = await process.wait()
        if retcode != 0:
            error = b''
            if process.stderr is not None:
                try:
                    error = await process.stderr.read()
                except Exception as e:
                    log.warning(f'读取错误输出时失败: {e}')
            error_message = error.decode('utf-8', errors='ignore') if error else '未知错误'
            log.error(f'解析URL \'{url}\' 时出错: {error_message}')

    async def download_and_merge(self, video_url: str, file_prefix: str) -> Path:
        # 使用信号量确保同时只有一个进度条活动
        async with _progress_semaphore:
            # 检查是否使用auto_best模式进行合并下载
            if (config.downloader.video_quality == 'auto_best' and 
                config.downloader.audio_quality == 'auto_best'):
                
                # 使用auto_best模式：直接下载合并文件
                # 构建合并下载命令
                combined_cmd, format_combo = await self.command_builder.build_combined_download_cmd(
                    f'{self.download_folder / file_prefix}.%(ext)s', video_url
                )
                
                # 检查是否是x.com链接，显示特殊提示
                if video_url.startswith('https://x.com'):
                    console.print(f'🐦 x.com链接使用auto_best模式: {file_prefix} ({format_combo})', style='bold blue')
                else:
                    console.print(f'🎬 正在准备下载 (auto_best模式): {file_prefix} ({format_combo})', style='bold blue')
                
                # 创建进度条对象
                with Progress(
                    TextColumn('[bold blue]⬇️ {task.description}'), BarColumn(bar_width=None),
                    '[progress.percentage]{task.percentage:>3.1f}%', '|', DownloadColumn(), '|',
                    TransferSpeedColumn(), '|', TimeRemainingColumn(), console=console, expand=True
                ) as progress:
                    
                    # 创建隐藏的任务，只有在真正有进度数据时才显示
                    if video_url.startswith('https://x.com'):
                        download_task = progress.add_task(f'下载x.com合并视频 ({format_combo})', total=None, visible=False)
                    else:
                        download_task = progress.add_task(f'下载合并视频 ({format_combo})', total=None, visible=False)
                    await self._run_subprocess_with_progress(combined_cmd, progress, download_task)
                
                # 查找下载的文件
                merged_file = next((p for p in self.download_folder.glob(f'{file_prefix}.*') 
                                  if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                
                if merged_file:
                    console.print(f'✅ 自动合并下载完成: {merged_file.name}', style='bold green')
                    return merged_file
                else:
                    raise NonRecoverableErrorException('未找到下载的合并文件')
            
            else:
                # 传统模式：分别下载视频和音频然后合并
                video_part_base, audio_part_base = f'{file_prefix}_video.tmp', f'{file_prefix}_audio.tmp'
                
                # 先准备命令
                vid_cmd = await self.command_builder.build_video_download_cmd(
                    f"{self.download_folder / video_part_base}.%(ext)s", video_url
                )
                aud_cmd = await self.command_builder.build_audio_download_cmd(
                    f"{self.download_folder / audio_part_base}.%(ext)s", video_url
                )
                
                # 创建进度条对象
                with Progress(
                    TextColumn('[bold blue]⬇️ {task.description}'), BarColumn(bar_width=None),
                    '[progress.percentage]{task.percentage:>3.1f}%', '|', DownloadColumn(), '|',
                    TransferSpeedColumn(), '|', TimeRemainingColumn(), console=console, expand=True
                ) as progress:
                    
                    # 创建隐藏的任务，只有在真正有进度数据时才显示
                    video_task = progress.add_task('下载视频', total=None, visible=False)
                    await self._run_subprocess_with_progress(vid_cmd, progress, video_task)

                    audio_task = progress.add_task('下载音频', total=None, visible=False)
                    await self._run_subprocess_with_progress(aud_cmd, progress, audio_task)

                # 检查下载的文件
                vid_part = next(self.download_folder.glob(f'{video_part_base}.*'), None)
                aud_part = next(self.download_folder.glob(f'{audio_part_base}.*'), None)

                if not (vid_part and aud_part):
                    merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") 
                                      if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                    if merged_file:
                        console.print('✅ 检测到媒体源已合并', style='bold green')
                        return merged_file
                    raise NonRecoverableErrorException('未找到下载的视频或音频文件')

                return await self.file_processor.merge_to_mp4(vid_part, aud_part, file_prefix)

    async def download_metadata(self, url: str, file_prefix: str) -> None:
        cmd = self.command_builder.build_metadata_download_cmd(str(self.download_folder / file_prefix), url)
        await self._run_subprocess(cmd)

    async def download_audio_directly(self, video_url: str, file_prefix: str) -> Path:
        """直接从URL下载音频文件（用于audio_extraction_mode = direct_download）"""
        # 使用信号量确保同时只有一个进度条活动
        async with _progress_semaphore:
            console.print(f'🎵 正在直接下载音频: {file_prefix}', style='bold blue')
            
            # 构建音频下载命令
            audio_cmd = await self.command_builder.build_audio_download_cmd(
                f"{self.download_folder / file_prefix}.%(ext)s", video_url
            )
            
            # 创建进度条对象
            with Progress(
                TextColumn("[bold blue]⬇️ {task.description}"), BarColumn(bar_width=None),
                "[progress.percentage]{task.percentage:>3.1f}%", "|", DownloadColumn(), "|",
                TransferSpeedColumn(), "|", TimeRemainingColumn(), console=console, expand=True
            ) as progress:
                
                # 创建隐藏的任务，只有在真正有进度数据时才显示
                audio_task = progress.add_task("下载音频", total=None, visible=False)
                await self._run_subprocess_with_progress(audio_cmd, progress, audio_task)
            
            # 查找下载的音频文件
            audio_file = next((p for p in self.download_folder.glob(f'{file_prefix}.*') 
                             if p.suffix in ['.mp3', '.m4a', '.opus', '.aac', '.webm']), None)
            
            if audio_file:
                console.print(f'✅ 音频下载完成: {audio_file.name}', style='bold green')
                return audio_file
            else:
                raise NonRecoverableErrorException('未找到下载的音频文件')

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