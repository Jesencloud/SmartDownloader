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
        # Remove invalid characters
        sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
        # Replace whitespace with a single space
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        # Limit length
        return sanitized[:100]


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
    async def _execute_download_with_auth_retry(self, video_url: str, download_cmd: list, progress, task_id: TaskID, timeout: int = 1800):
        """
        执行下载命令,支持认证错误自动重试
        
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
                # 使用SubprocessManager执行命令
                return await self.subprocess_manager.execute_with_progress(
                    download_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    # 尝试自动刷新cookies
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        # 更新命令构建器的cookies文件
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建下载命令
                        download_cmd, _, _ = self.command_builder.build_combined_download_cmd(
                            str(self.download_folder), video_url
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,下载失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                # 其他类型的错误,直接抛出
                raise e

    async def _execute_audio_download_with_auth_retry(self, video_url: str, audio_cmd: list, progress, task_id: TaskID, file_prefix: str, timeout: int = 1800):
        """
        执行音频下载命令,支持认证错误自动重试
        
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
                    log.warning(f"🍪 音频下载认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建音频下载命令
                        audio_cmd = self.command_builder.build_audio_download_cmd(
                            str(self.download_folder), video_url, file_prefix
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试音频下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,音频下载失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

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
        
        # 首先检查目录中的所有文件(用于调试)
        all_files = list(self.download_folder.glob('*'))
        log.info(f'目录中的文件: {all_files}')
        
        # 1. 首先尝试精确匹配(包括扩展名)
        for ext in extensions:
            file_path = self.download_folder / f"{prefix}{ext}"
            if file_path.exists() and file_path.is_file():
                log.info(f'找到文件(精确匹配): {file_path}')
                return file_path
        
        # 2. 尝试不区分大小写的扩展名匹配
        for ext in extensions:
            # 移除点并转换为小写用于比较
            ext_lower = ext.lstrip('.').lower()
            for f in self.download_folder.glob(f"{prefix}*"):
                if f.suffix.lstrip('.').lower() == ext_lower and f.is_file():
                    log.info(f'找到文件(扩展名不区分大小写): {f}')
                    return f
        
        # 3. 尝试匹配前缀(不包含扩展名)
        for f in self.download_folder.glob(f"{prefix}*"):
            if f.is_file():
                # 检查文件扩展名是否在允许的扩展名列表中
                file_ext = f.suffix.lower()
                if any(ext.lower() == file_ext for ext in extensions):
                    log.info(f'找到文件(前缀匹配): {f}')
                    return f
        
        # 4. 如果还是没找到,尝试查找任何音频文件(最后的手段)
        audio_extensions = ('.mp3', '.m4a', '.opus', '.webm', '.ogg', '.wav', '.aac', '.flac')
        for f in self.download_folder.glob(f"{prefix}*"):
            if f.is_file() and f.suffix.lower() in audio_extensions:
                log.info(f'找到音频文件(通用匹配): {f}')
                return f
        
        # 5. 最后尝试按修改时间排序,返回最新的匹配文件
        possible_files = []
        for ext in extensions:
            possible_files.extend(self.download_folder.glob(f"*{ext}"))
        
        if possible_files:
            # 按修改时间排序,返回最新的文件
            possible_files.sort(key=os.path.getmtime, reverse=True)
            log.info(f'找到可能匹配的最新文件: {possible_files[0]}')
            return possible_files[0]
            
        log.warning(f'未找到匹配的文件: 前缀={prefix}, 扩展名={extensions}')
        log.warning(f'目录内容: {list(self.download_folder.glob("*"))}')
        return None

    async def download_and_merge(self, video_url: str, file_prefix: str, format_id: str = None, resolution: str = '') -> Optional[Path]:
        """
        下载视频和音频并合并为MP4格式.
        采用主/备（Primary/Fallback）策略以提高可靠性。
        主策略：尝试一体化下载和合并。
        备用策略：如果主策略失败，则分步下载视频和音频，然后手动合并。
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (例如: '1080p60')

        Returns:
            合并后的文件路径,失败返回None

        Raises:
            DownloaderException: 下载或合并失败, 请检查日志获取详细信息
        """
        log.info(f'开始下载并合并: {file_prefix}')
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # --- 主策略：尝试一体化下载和合并 ---
        log.info("尝试主策略：一体化下载和合并...")
        try:
            download_cmd, _, exact_output_path = self.command_builder.build_combined_download_cmd(
                str(self.download_folder),
                video_url,
                file_prefix=file_prefix,
                format_id=format_id,
                resolution=resolution
            )

            async with _progress_semaphore:
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    "•",
                    TransferSpeedColumn(),
                    console=console
                ) as progress:
                    download_task = progress.add_task("⬇️ 下载并合并", total=100)
                    await self._execute_download_with_auth_retry(video_url, download_cmd, progress, download_task)

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
                with Progress(console=console) as progress:
                    video_task = progress.add_task("⬇️ 下载视频部分", total=100)
                    video_cmd = self.command_builder.build_separate_video_download_cmd(
                        str(self.download_folder), video_url, file_prefix, format_id
                    )
                    await self._execute_download_with_auth_retry(video_url, video_cmd, progress, video_task)

            video_file = await self._find_output_file(f"{file_prefix}.video", ('.mp4', '.webm', '.mkv'))
            if not video_file:
                raise DownloaderException("备用策略：视频部分下载后未找到文件。")
            log.info(f"✅ 视频部分下载成功: {video_file.name}")

            # 2. 下载音频部分
            async with _progress_semaphore:
                with Progress(console=console) as progress:
                    audio_task = progress.add_task("⬇️ 下载音频部分", total=100)
                    audio_cmd = self.command_builder.build_separate_audio_download_cmd(
                        str(self.download_folder), video_url, file_prefix
                    )
                    await self._execute_download_with_auth_retry(video_url, audio_cmd, progress, audio_task)

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

    async def download_audio(self, video_url: str, audio_format: str = 'mp3') -> Optional[Path]:
        """
        下载指定URL的音频.
        
        Args:
            video_url: 视频URL
            audio_format: 音频格式 (例如: 'mp3', 'm4a', 'best')
            
        Returns:
            下载的音频文件路径,失败返回None
            
        Raises:
            DownloaderException: 下载失败
        """
        log.info(f'开始下载音频: {video_url}')
        self.download_folder.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. Get video title
            try:
                video_info_gen = self.stream_playlist_info(video_url)
                video_info = await anext(video_info_gen)
                video_title = video_info.get('title', 'audio')
            except (StopAsyncIteration, DownloaderException):
                video_title = "audio" # Fallback title

            # 2. Sanitize title for filename
            file_prefix = self._sanitize_filename(video_title)
            log.info(f'使用文件前缀: {file_prefix}')

            # 3. Build audio download command
            audio_cmd = self.command_builder.build_audio_download_cmd(
                str(self.download_folder), video_url, file_prefix, audio_format
            )
            
            # 4. Execute download command (no progress bar, but captures output)
            _, stdout, _ = await self.subprocess_manager.execute_simple(
                audio_cmd, timeout=1800 # 30 min timeout
            )
            
            # 5. Get filename from stdout and check existence
            output_filename = stdout.strip().split('\n')[-1]
            output_file = Path(output_filename)

            if output_file.exists() and output_file.is_file():
                log.info(f'✅ 音频下载成功: {output_file.name}')
                return output_file
            else:
                # Fallback to glob search if direct check fails
                log.warning("Direct file check failed, falling back to glob search.")
                extensions = ('.mp3', '.m4a', '.opus', '.webm', '.aac', '.flac', '.wav', '.ogg')
                output_file = await self._find_output_file(file_prefix, extensions)
                if output_file:
                    return output_file

            raise DownloaderException(f'音频下载后未找到文件: {output_filename}')
                
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
