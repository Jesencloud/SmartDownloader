#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能，重构后的版本使用核心模块组件
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator, Tuple

from rich.console import Console
from rich.progress import (
    Progress, BarColumn, TextColumn, TimeRemainingColumn, TimeElapsedColumn,
    DownloadColumn, TransferSpeedColumn, TaskID, Task
)
from rich.text import Text

from auto_cookies import main as refresh_cookies
from config_manager import config
from core import (
    DownloaderException, FFmpegException, with_retries,
    CommandBuilder, SubprocessManager, FileProcessor, AuthenticationException
)
from core.cookies_manager import CookiesManager

log = logging.getLogger(__name__)
console = Console()

# 全局进度条信号量，确保同时只有一个进度条活动
_progress_semaphore = asyncio.Semaphore(1)


class CustomSpeedColumn(TransferSpeedColumn):
    """自定义速度列，下载完成时显示✅"""
    
    def render(self, task: Task) -> Text:
        if task.finished:
            return Text("✅", style="bold green", justify="right")
        # ��保显示速度而不是?
        speed = task.get_time() and task.completed / task.get_time() or 0
        if speed > 0:
            return Text(f"{self._format_speed(speed)}", style="progress.data.speed", justify="right")
        return Text("--", style="progress.data.speed", justify="right")
    
    def _format_speed(self, speed: float) -> str:
        """格式化速度显示"""
        units = ["B/s", "KB/s", "MB/s", "GB/s"]
        for unit in units:
            if speed < 1024:
                return f"{speed:.1f} {unit}"
            speed /= 1024
        return f"{speed:.1f} TB/s"


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
        
        # 组合��种专门的处理器
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.subprocess_manager = SubprocessManager()
        self.file_processor = FileProcessor(self.subprocess_manager, self.command_builder)
        
        # 初始化cookies管理器
        if cookies_file:
            self.cookies_manager = CookiesManager(cookies_file)
        else:
            self.cookies_manager = None
        
        log.info(f'初始化下载器，目标文件夹: {self.download_folder}')
        if cookies_file:
            log.info(f'使用cookies文件: {cookies_file}')
        if proxy:
            log.info(f'使用代理: {self.proxy}')

    async def _get_available_formats(self, url: str) -> str:
        """
        获取可用格式列表，并在需要时自动刷新cookies。
        """
        max_retries = 1
        for attempt in range(max_retries + 1):
            cmd = self.command_builder.build_list_formats_cmd(url)
            _, stdout, stderr = await self.subprocess_manager.execute_simple(cmd, check_returncode=False)
            
            output = stdout + stderr
            if "become a premium member" in output.lower():
                log.warning("检测到'become a premium member'提示���尝试刷新cookies...")
                try:
                    # 调用auto_cookies.py中的main函数刷新cookies
                    refresh_cookies()
                    log.info("Cookies已刷新，重试获取格式列表...")
                    # 更新CommandBuilder中的cookies文件路径
                    if self.cookies_manager:
                        refreshed_path = self.cookies_manager.get_cookies_file_path()
                        self.command_builder.update_cookies_file(refreshed_path)
                    continue
                except Exception as e:
                    log.error(f"刷新cookies失败: {e}")
                    raise DownloaderException("自动刷新cookies失败，无法获取高级会员内容。")
            
            if "error" in output.lower() and "premium" in output.lower():
                 raise DownloaderException("获取格式列表时出错，可能需要有效的cookies。")

            return stdout

        raise DownloaderException("刷新cookies后仍无法获取格式列表。")

    def _extract_best_formats(self, format_output: str, log_video_format: bool = True) -> Tuple[Optional[str], Optional[str]]:
        """
        从yt-dlp格式输出中提取最佳视频和音频格式ID
        """
        lines = format_output.split('\n')
        video_formats = []
        audio_formats = []
        
        in_table = False
        for line in lines:
            line = line.strip()
            
            if 'ID' in line and 'EXT' in line and 'RESOLUTION' in line:
                in_table = True
                continue
            if not in_table or not line or line.startswith('-'):
                continue
            
            parts = line.split()
            if len(parts) < 3:
                continue
                
            format_id = parts[0]
            ext = parts[1]
            resolution = parts[2]
            
            if 'mhtml' in ext or 'storyboard' in line:
                continue
            
            if 'audio only' not in line and 'x' in resolution:
                height_match = re.search(r'(\d+)x(\d+)', resolution)
                if height_match:
                    height = int(height_match.group(2))
                    video_formats.append((format_id, height, ext, line))
            
            elif 'audio only' in line:
                filesize_bytes = 0
                bitrate = 0
                is_original_default = 'original (default)' in line.lower()
                
                filesize_match = re.search(r'(\d+\.?\d*)(MiB|GiB|KiB|MB|GB|KB)', line)
                if filesize_match:
                    size_value = float(filesize_match.group(1))
                    size_unit = filesize_match.group(2)
                    
                    if size_unit in ['MiB', 'MB']:
                        filesize_bytes = int(size_value * 1024 * 1024)
                    elif size_unit in ['GiB', 'GB']:
                        filesize_bytes = int(size_value * 1024 * 1024 * 1024)
                    elif size_unit in ['KiB', 'KB']:
                        filesize_bytes = int(size_value * 1024)
                
                if filesize_bytes == 0:
                    bitrate_matches = re.findall(r'(\d+)k', line)
                    if bitrate_matches:
                        bitrate = int(bitrate_matches[-1])
                        filesize_bytes = bitrate * 1000 * 300 // 8
                
                audio_formats.append((format_id, filesize_bytes, bitrate, ext, line, is_original_default))
        
        best_video_id = None
        best_audio_id = None
        
        if video_formats:
            video_formats.sort(key=lambda x: x[1])
            best_video_id = video_formats[-1][0]
            if log_video_format:
                log.info(f"选择最佳视频格式: {video_formats[-1][0]} ({video_formats[-1][1]}p, {video_formats[-1][2]})")
        
        if audio_formats:
            original_default_formats = [fmt for fmt in audio_formats if fmt[5]]
            
            if original_default_formats:
                original_default_formats.sort(key=lambda x: x[1])
                selected_format = original_default_formats[-1]
                log.info(f"优先选择 original (default) 音轨: {selected_format[0]}")
            else:
                audio_formats.sort(key=lambda x: x[1])
                selected_format = audio_formats[-1]
                log.info(f"未找到 original (default) 音轨，选择最大文件大小的音轨: {selected_format[0]}")
            
            best_audio_id = selected_format[0]
            best_audio_filesize = selected_format[1]
            best_audio_bitrate = selected_format[2]
            best_audio_ext = selected_format[3]
            
            if best_audio_filesize > 1024 * 1024:
                size_display = f"{best_audio_filesize / (1024 * 1024):.2f}MB"
            else:
                size_display = f"{best_audio_filesize / 1024:.2f}KB"
                
            log.info(f"选择最佳音频格式: {best_audio_id} ({size_display}, {best_audio_bitrate}k, {best_audio_ext})")
        
        return best_video_id, best_audio_id

    async def _execute_info_cmd_with_auth_retry(self, url: str, info_cmd: list, timeout: int = 60):
        """
        执行信���获取命令，支持认证错误自动重试
        
        Args:
            url: 视频URL
            info_cmd: 信息获取命令
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
        """
        max_auth_retries = 1
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_simple(
                    info_cmd, timeout=timeout, check_returncode=True
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 获取视频信息认证错误，尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建信息获取命令
                        info_cmd = self.command_builder.build_playlist_info_cmd(url)
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新，重试获取���频信息...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies，获取视频信息失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器，无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

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
            
            # 执行命令获取信息（带认证重试支持）
            return_code, stdout, stderr = await self._execute_info_cmd_with_auth_retry(
                url, info_cmd, timeout=60
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
    async def _execute_download_with_auth_retry(self, video_url: str, download_cmd: list, progress, task_id: TaskID, timeout: int = 1800):
        """
        执行下载命令，支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            download_cmd: 下载命令
            progress: 进度条对象
            task_id: 任务ID
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
            
        Raises:
            各种下载相关异常
        """
        max_auth_retries = 1  # 最多重试1次认证错误
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_with_progress(
                    download_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误，尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    # 尝试自动刷新cookies
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        # 更新命令构建器的cookies文件
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建下载命令
                        download_cmd, _ = self.command_builder.build_combined_download_cmd(
                            str(self.download_folder), video_url
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新，重试下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies，下载失败")
                        raise e
                else:
                    # ���到最大重试次数或没有cookies管理器
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器，无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                # 其他类型的错误，直接抛出
                raise e

    async def _execute_audio_download_with_auth_retry(self, video_url: str, audio_cmd: list, progress, task_id: TaskID, file_prefix: str, timeout: int = 1800):
        """
        执行音频下载命令，支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            audio_cmd: 音频下载命令
            progress: 进度条对象
            task_id: 任务ID
            file_prefix: 文件前缀
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
        """
        max_auth_retries = 1
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_with_progress(
                    audio_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 音频下载认证错误，尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建音频下载命令
                        audio_cmd = self.command_builder.build_audio_download_cmd(
                            str(self.download_folder), video_url, file_prefix
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新，重试音频下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies，音频下载失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器，无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

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
            
            video_id, audio_id = None, None
            if (config.downloader.video_quality == "auto_best" and 
                config.downloader.audio_quality == "auto_best"):
                format_output = await self._get_available_formats(video_url)
                video_id, audio_id = self._extract_best_formats(format_output)

            download_cmd, _ = self.command_builder.build_combined_download_cmd(
                str(self.download_folder), video_url, video_id, audio_id
            )
            
            async with _progress_semaphore:
                with Progress(
                    TextColumn('[progress.description]{task.description}'),
                    BarColumn(),
                    DownloadColumn(),
                    TimeElapsedColumn(),
                    CustomSpeedColumn(),
                    console=console
                ) as progress:
                    
                    task_id = progress.add_task(
                        f'⬇️ 下载合并视频', total=None
                    )
                    
                    await self._execute_download_with_auth_retry(
                        video_url, download_cmd, progress, task_id, timeout=1800
                    )
            
            output_file = await self._find_output_file(file_prefix, ('.mp4', '.webm', '.mkv', '.avi'))
            if output_file and await self.file_processor.verify_file_integrity(output_file):
                log.info(f'下载合并成功: {output_file.name}')
                return output_file
            else:
                raise DownloaderException(f'下载合并失败，未找到有效的输出文件')
                
        except Exception as e:
            log.error(f'下载合并过程失败: {e}', exc_info=True)
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
            
            audio_id = None
            if config.downloader.audio_quality == "auto_best":
                format_output = await self._get_available_formats(video_url)
                _, audio_id = self._extract_best_formats(format_output, log_video_format=False)

            audio_cmd = self.command_builder.build_audio_download_cmd(
                str(self.download_folder), video_url, file_prefix, audio_id
            )
            
            async with _progress_semaphore:
                with Progress(
                    TextColumn('[progress.description]{task.description}'),
                    BarColumn(),
                    DownloadColumn(),
                    TimeElapsedColumn(),
                    CustomSpeedColumn(),
                    console=console
                ) as progress:
                    
                    task_id = progress.add_task(
                        f'⬇️ 下载音频', total=None
                    )
                    
                    await self._execute_audio_download_with_auth_retry(
                        video_url, audio_cmd, progress, task_id, file_prefix, timeout=1800
                    )
            
            output_file = await self._find_output_file(file_prefix, ('.mp3', '.m4a', '.opus', '.aac', '.webm'))
            if output_file and await self.file_processor.verify_file_integrity(output_file):
                log.info(f'音频下载成功: {output_file.name}')
                return output_file
            else:
                raise DownloaderException(f'音频下载失败，未找到有效的输出文件')
                
        except Exception as e:
            log.error(f'音频下载过程失败: {e}', exc_info=True)
            await self.file_processor.cleanup_temp_files(
                str(self.download_folder / file_prefix)
            )
            raise
    
    async def download_metadata(self, video_url: str, file_prefix: str) -> bool:
        """
        下载视频元数据信息。
        
        Args:
            video_url: 视频URL
            file_prefix: 文件���缀
            
        Returns:
            bool: 下载是否成功
            
        Raises:
            DownloaderException: 下载失败
        """
        try:
            log.info(f'开始下载元数据: {file_prefix}')
            
            metadata_cmd = self.command_builder.build_metadata_download_cmd(
                str(self.download_folder), video_url
            )
            
            await self.subprocess_manager.execute_simple(
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
            
            await self.subprocess_manager.cleanup_all_processes()
            
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
        
        for ext in extensions:
            exact_file = self.download_folder / f'{file_prefix}{ext}'
            if exact_file.exists():
                return exact_file
        
        all_files = []
        for ext in extensions:
            pattern = f'*{ext}'
            matching_files = list(self.download_folder.glob(pattern))
            all_files.extend(matching_files)
        
        if all_files:
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

    async def close(self):
        """
        安全关闭下载器，清理所有正在运行的进程。
        """
        log.info('正在关闭下载器并清理资源...')
        await self.subprocess_manager.cleanup_all_processes()
        log.info('下载器已安全关闭')