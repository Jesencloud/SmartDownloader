#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能,重构后的版本使用核心模块组件
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
import os
import shutil
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, DownloadColumn, ProgressColumn,
    TextColumn, TimeElapsedColumn, TimeRemainingColumn, TransferSpeedColumn,
    SpinnerColumn, TaskID, Task
)
from rich.text import Text

from config_manager import config
from core import (
    DownloaderException, FFmpegException, with_retries,
    CommandBuilder, SubprocessManager, FileProcessor, AuthenticationException
)
from core.cookies_manager import CookiesManager

log = logging.getLogger(__name__)
console = Console()

# 全局进度条信号量,确保同时只有一个进度条活动
_progress_semaphore = asyncio.Semaphore(1)


class SpeedOrFinishMarkColumn(ProgressColumn):
    """下载时显示速度,完成后显示标记"""

    def __init__(self, mark: str = "?", **kwargs):
        self.mark = mark
        self.speed_column = TransferSpeedColumn()
        super().__init__(**kwargs)

    def render(self, task: "Task") -> Text:
        """渲染速度或完成标记"""
        if task.finished:
            return Text(f" {self.mark} ", justify="left")
        return self.speed_column.render(task)


class Downloader:
    """
    简化的下载器,主要负责下载流程编排.
    
    重构后专注于业务流程,具体的执行逻辑委托给核心模块.
    """
    
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        """
        初始化下载器.
        
        Args:
            download_folder: 下载文件夹路径
            cookies_file: cookies文件路径(可选)
            proxy: 代理服务器地址(可选)
        """
        self.download_folder = Path(download_folder)
        self.cookies_file = cookies_file
        self.proxy = proxy
        
        # 组合各种专门的处理器
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.subprocess_manager = SubprocessManager()
        self.file_processor = FileProcessor(self.subprocess_manager, self.command_builder)
        
        # 初始化cookies管理器
        if cookies_file:
            self.cookies_manager = CookiesManager(cookies_file)
        else:
            self.cookies_manager = None
        
        log.info(f'初始化下载器,目标文件夹: {self.download_folder}')
        if cookies_file:
            log.info(f'使用cookies文件: {cookies_file}')
        if proxy:
            log.info(f'使用代理: {self.proxy}')

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes a string to be a valid filename."""
        max_len = config.file_processing.filename_max_length
        suffix = config.file_processing.filename_truncate_suffix
        # Remove invalid characters for filenames
        sanitized = re.sub(r'[\\/*?:"<>|]', '', filename)
        # Replace multiple spaces with a single space and strip leading/trailing whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        # Remove any trailing dots or spaces that might cause issues before appending extensions
        sanitized = sanitized.rstrip('. ')

        # If the string is empty after sanitization, return a default name
        if not sanitized:
            return "untitled"

        # Truncate and add suffix if necessary
        if len(sanitized) > max_len:
            return sanitized[:max_len] + suffix
        
        return sanitized


    async def _execute_info_cmd_with_auth_retry(self, url: str, info_cmd: list, timeout: int = 60):
        """
        执行信息获取命令,支持认证错误自动重试
        
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
                    log.warning(f"🍪 获取视频信息认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建信息获取命令
                        info_cmd = self.command_builder.build_playlist_info_cmd(url)
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试获取视频信息...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,获取视频信息失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

    async def stream_playlist_info(self, url: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式获取播放列表信息.
        
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
            
            # 执行命令获取信息(带认证重试支持)
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
                        
        except AuthenticationException:
            # 认证异常直接向上传递,让上层处理重试
            raise
        except Exception as e:
            raise DownloaderException(f'获取播放列表信息失败: {e}') from e
    
    @with_retries(max_retries=3)
    async def _execute_cmd_with_auth_retry(
        self,
        initial_cmd: list,
        cmd_builder_func,
        url: str,
        cmd_builder_args: dict,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        timeout: int = 1800
    ):
        """
        执行命令,支持认证错误自动重试,并可选择性地处理进度.
        这是一个通用的执行器,可以处理带或不带进度条的命令.

        Args:
            initial_cmd: 首次尝试执行的、已经构建好的命令.
            cmd_builder_func: 用于在重试时重新构建命令的CommandBuilder方法.
            url: 视频URL.
            cmd_builder_args: 传递给cmd_builder_func的参数字典.
            progress: (可选) Rich Progress对象.
            task_id: (可选) Rich TaskID.
            timeout: 命令执行的超时时间.

        Returns:
            tuple: (return_code, stdout, stderr)

        Raises:
            各种下载或执行相关的异常.
        """
        max_auth_retries = 1
        auth_retry_count = 0
        
        cmd = initial_cmd

        while auth_retry_count <= max_auth_retries:
            try:
                if progress and task_id is not None:
                    return await self.subprocess_manager.execute_with_progress(
                        cmd, progress, task_id, timeout=timeout
                    )
                else:
                    return await self.subprocess_manager.execute_simple(
                        cmd, timeout=timeout
                    )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 在重试时才重新构建命令
                        rebuilt_cmd = cmd_builder_func(**cmd_builder_args)
                        cmd = rebuilt_cmd[0] if isinstance(rebuilt_cmd, tuple) else rebuilt_cmd
                        
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试命令...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,命令执行失败.")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误.")
                    elif auth_retry_count >= max_auth_retries:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries}).")
                    raise e
            except Exception as e:
                raise e
        raise DownloaderException("命令执行失败,所有重试均已用尽.")

    def _parse_path_from_stderr(self, stderr: str) -> Optional[Path]:
        """从yt-dlp的stderr输出中解析目标文件路径。"""
        path_patterns = [
            re.compile(r"\[ExtractAudio\] Destination:\s*(?P<path>.+)"),
            re.compile(r"\[download\] Destination:\s*(?P<path>.+)"),
            re.compile(r"\[Merger\] Merging formats into \"(?P<path>.+)\""),
        ]

        log.debug(f"yt-dlp stderr for parsing:\n{stderr}")
        for line in stderr.strip().split('\n'):
            for pattern in path_patterns:
                match = pattern.search(line)
                if match:
                    found_path = match.group('path').strip('"')
                    log.info(f"从yt-dlp输出中解析到文件路径: {found_path}")
                    return Path(found_path)
        return None

    async def _find_output_file(self, prefix: str, extensions: tuple) -> Optional[Path]:
        """
        在下载目录中查找具有指定前缀和扩展名的文件
        
        Args:
            prefix: 文件名前缀
            extensions: 可能的文件扩展名元组

        Returns:
            找到的文件路径,如果未找到则返回None
        """
        log.info(f'查找文件: 前缀={prefix}, 扩展名={extensions}')
        log.info(f'搜索目录: {self.download_folder}')

        # 使用glob查找所有以该前缀开头的文件，这是最可靠的方法
        matching_files = list(self.download_folder.glob(f"{prefix}*"))

        if not matching_files:
            log.warning(f'未找到任何以 "{prefix}" 开头的文件。')
            log.warning(f'目录内容: {list(self.download_folder.glob("*"))}')
            return None

        # 过滤出扩展名在允许列表中的文件
        valid_files = [f for f in matching_files if f.suffix.lower() in extensions]

        if not valid_files:
            log.warning(f'找到以 "{prefix}" 开头的文件，但扩展名不匹配: {[f.name for f in matching_files]}')
            return None

        # 返回最新修改的文件，以处理可能的重试或覆盖情况
        latest_file = max(valid_files, key=lambda f: f.stat().st_mtime)
        log.info(f'找到最新的匹配文件: {latest_file.name}')
        return latest_file

    async def download_and_merge(self, video_url: str, format_id: str = None, resolution: str = '', fallback_prefix: Optional[str] = None) -> Optional[Path]:
        """
        下载视频和音频并合并为MP4格式.
        采用主/备（Primary/Fallback）策略以提高可靠性。
        主策略：尝试一体化下载和合并。
        备用策略：如果主策略失败，则分步下载视频和音频，然后手动合并。
        
        Args:
            video_url: 视频URL
            fallback_prefix: 获取标题失败时的备用文件前缀 (可选)
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (例如: '1080p60')

        Returns:
            合并后的文件路径,失败返回None

        Raises:
            DownloaderException: 下载或合并失败, 请检查日志获取详细信息
        """
        # --- 获取标题和分辨率，并生成最终文件名 ---
        try:
            # 1. Get video title
            video_info_gen = self.stream_playlist_info(video_url)
            video_info = await video_info_gen.__anext__()
            video_title = video_info.get('title', 'video')

            # 2. 根据 format_id 查找确切的分辨率
            resolution_suffix = ""
            if format_id and 'formats' in video_info:
                # Find the selected format to get its exact resolution
                selected_format = next((f for f in video_info['formats'] if f.get('format_id') == format_id), None)
                if selected_format and selected_format.get('width') and selected_format.get('height'):
                    resolution_suffix = f"_{selected_format['width']}x{selected_format['height']}"

            # 3. 组合成最终的文件前缀
            file_prefix = f"{self._sanitize_filename(video_title)}{resolution_suffix}"

        except (StopAsyncIteration, DownloaderException) as e:
            log.warning(f"无法获取视频标题: {e}。将使用备用前缀。")
            # 使用 fallback_prefix 或一个默认值
            file_prefix = fallback_prefix or "video"
        log.info(f'使用文件前缀: {file_prefix}')

        log.info(f'开始下载并合并: {file_prefix}')
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # --- 主策略：尝试一体化下载和合并 ---
        log.info("尝试主策略：一体化下载和合并...")
        try:
            cmd_builder_args = {
                "output_path": str(self.download_folder),
                "url": video_url,
                "file_prefix": file_prefix,
                "format_id": format_id,
                "resolution": resolution
            }
            download_cmd, _, exact_output_path = self.command_builder.build_combined_download_cmd(**cmd_builder_args)

            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    "•",
                    TransferSpeedColumn(),
                    console=console
                ) as progress:
                    download_task = progress.add_task("Download/Merge", total=100)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=download_cmd,
                        cmd_builder_func=self.command_builder.build_combined_download_cmd,
                        url=video_url,
                        cmd_builder_args=cmd_builder_args,
                        progress=progress,
                        task_id=download_task
                    )

            if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                log.info(f"✅ 主策略成功: {exact_output_path.name}")
                return exact_output_path
            else:
                log.warning("主策略执行后未找到有效的输出文件。")

        except asyncio.CancelledError:
            log.warning("主策略下载任务被取消")
            raise
        except Exception as e:
            log.warning(f"主策略失败: {e}。将尝试备用策略。")

        # --- 备用策略：分步下载和手动合并 ---
        log.info("切换到备用策略：分步下载和手动合并...")
        video_file = None
        audio_file = None

        try:
            # 1. 下载视频部分
            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    "•",
                    TransferSpeedColumn(),
                    console=console
                ) as progress:
                    video_task = progress.add_task("Downloading Video", total=100)
                    video_cmd_args = {
                        "output_path": str(self.download_folder),
                        "url": video_url,
                        "file_prefix": file_prefix,
                        "format_id": format_id
                    }
                    video_cmd = self.command_builder.build_separate_video_download_cmd(**video_cmd_args)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=video_cmd,
                        cmd_builder_func=self.command_builder.build_separate_video_download_cmd,
                        url=video_url,
                        cmd_builder_args=video_cmd_args,
                        progress=progress,
                        task_id=video_task
                    )

            video_file = await self._find_output_file(f"{file_prefix}.video", ('.mp4', '.webm', '.mkv'))
            if not video_file:
                raise DownloaderException("备用策略：视频部分下载后未找到文件。")
            log.info(f"✅ 视频部分下载成功: {video_file.name}")

            # 2. 下载音频部分
            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    "•",
                    TransferSpeedColumn(),
                    console=console
                ) as progress:
                    audio_task = progress.add_task("Downloading Audio", total=100)
                    audio_cmd_args = {
                        "output_path": str(self.download_folder),
                        "url": video_url,
                        "file_prefix": file_prefix
                    }
                    audio_cmd = self.command_builder.build_separate_audio_download_cmd(**audio_cmd_args)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=audio_cmd,
                        cmd_builder_func=self.command_builder.build_separate_audio_download_cmd,
                        url=video_url,
                        cmd_builder_args=audio_cmd_args,
                        progress=progress,
                        task_id=audio_task
                    )

            audio_file = await self._find_output_file(f"{file_prefix}.audio", ('.m4a', '.mp3', '.opus', '.aac'))
            if not audio_file:
                log.warning("备用策略：音频部分下载后未找到文件。将尝试无音频合并。")

            # 3. 手动合并
            if video_file and audio_file:
                merged_file_path = self.download_folder / f"{file_prefix}.mp4"
                log.info(f"🔧 正在手动合并: {video_file.name} + {audio_file.name} -> {merged_file_path.name}")
                
                await self.file_processor.merge_to_mp4(video_file, audio_file, merged_file_path)

                if merged_file_path.exists() and merged_file_path.stat().st_size > 0:
                    log.info(f"✅ 备用策略成功: {merged_file_path.name}")
                    return merged_file_path
                else:
                    raise DownloaderException("备用策略：手动合并后未生成有效文件。")

            # 如果只有视频文件，作为最后手段返回
            if video_file:
                log.warning("备用策略：无法合并，返回仅视频文件。")
                # 重命名视频文件以匹配最终文件名
                final_video_path = self.download_folder / f"{file_prefix}.mp4"
                video_file.rename(final_video_path)
                return final_video_path

        except Exception as e:
            log.error(f"备用策略执行失败: {e}", exc_info=True)
            # 如果备用策略也失败，但主策略可能已经下载了部分文件，最后再检查一次
            final_check = await self._find_output_file(file_prefix, ('.mp4',))
            if final_check:
                log.info(f"在所有策略失败后，找到了一个最终文件: {final_check.name}")
                return final_check
            raise DownloaderException(f"主策略和备用策略均失败: {e}") from e

        raise DownloaderException("下载和合并视频失败，所有策略均已尝试。")

    async def download_audio(self, video_url: str, audio_format: str = 'best', fallback_prefix: Optional[str] = None) -> Optional[Path]:
        """
        下载指定URL的音频。
        对已知的转换格式（如mp3）采用“主动指定”策略，对直接下载的原始流采用“主动搜索”策略。

        Args:
            video_url: 视频URL
            audio_format: 音频格式 (例如: 'mp3', 'm4a', 'best', 或一个特定的format_id)
            fallback_prefix: 获取标题失败时的备用文件前缀 (可选)

        Returns:
            下载的音频文件路径,失败返回None

        Raises:
            DownloaderException: 下载失败
        """
        log.info(f'开始下载音频: {video_url} (请求格式: {audio_format})')
        self.download_folder.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 获取视频标题
            try:
                video_info_gen = self.stream_playlist_info(video_url)
                video_info = await video_info_gen.__anext__()
                video_title = video_info.get('title', 'audio')
            except (StopAsyncIteration, DownloaderException) as e:
                log.warning(f"无法获取视频标题: {e}。将使用备用前缀。")
                video_title = fallback_prefix or "audio"

            # 2. 准备文件名和格式信息
            sanitized_title = self._sanitize_filename(video_title)
            file_prefix = f"{sanitized_title}_{audio_format}"
            log.info(f'使用文件前缀: {file_prefix}')

            known_conversion_formats = ['mp3', 'm4a', 'wav', 'opus', 'aac', 'flac']
            is_conversion_request = audio_format in known_conversion_formats

            if is_conversion_request:
                # --- 策略1: 转换格式 (路径可预测) ---
                exact_output_path = self.download_folder / f"{file_prefix}.{audio_format}"
                log.info(f"音频转换请求。确切的输出路径为: {exact_output_path}")
                cmd_args = {"url": video_url, "output_template": str(exact_output_path), "audio_format": audio_format}
                cmd = self.command_builder.build_audio_download_cmd(**cmd_args)
                await self._execute_cmd_with_auth_retry(initial_cmd=cmd, cmd_builder_func=self.command_builder.build_audio_download_cmd, url=video_url, cmd_builder_args=cmd_args)

                if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                    output_file = exact_output_path
                else:
                    raise DownloaderException(f"音频转换失败，预期的输出文件 '{exact_output_path}' 未找到或为空。")
            else:
                # --- 策略2: 直接下载原始流 (路径需要搜索) ---
                log.info(f"直接音频流下载请求。输出路径需要搜索。")
                # 使用模板让yt-dlp能自动添加正确的扩展名
                output_template = self.download_folder / f"{file_prefix}.%(ext)s"
                cmd_args = {"url": video_url, "output_template": str(output_template), "audio_format": audio_format}
                cmd = self.command_builder.build_audio_download_cmd(**cmd_args)
                await self._execute_cmd_with_auth_retry(initial_cmd=cmd, cmd_builder_func=self.command_builder.build_audio_download_cmd, url=video_url, cmd_builder_args=cmd_args)

                # 主动查找输出文件
                extensions_to_check = ('.webm', '.m4a', '.opus', '.ogg', '.mp3', '.aac', '.flac', '.wav')
                output_file = await self._find_output_file(file_prefix, extensions_to_check)

            if output_file:
                log.info(f'✅ 音频下载成功: {output_file.name}')
                return output_file
            else:
                raise DownloaderException('音频下载后未找到文件，所有策略均失败。')

        except asyncio.CancelledError:
            log.warning("音频下载任务被取消")
            raise
        except Exception as e:
            log.error(f'音频下载失败: {e}', exc_info=True)
            raise DownloaderException(f'音频下载失败: {e}') from e

    async def cleanup(self):
        """
        清理所有正在运行的子进程.
        """
        await self.subprocess_manager.cleanup_all_processes()
        log.info("下载器清理完成")
