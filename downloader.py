#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能,重构后的版本使用核心模块组件
"""

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TransferSpeedColumn,
)
from rich.text import Text

from config_manager import config
from core import (
    AuthenticationException,
    CommandBuilder,
    DownloaderException,
    FileProcessor,
    SubprocessManager,
    with_retries,
)
from core.cookies_manager import CookiesManager
from core.format_analyzer import DownloadStrategy

log = logging.getLogger(__name__)
# 明确创建写入 stdout 的控制台，以避免 rich 将进度条自动发送到 stderr，
# 从而导致 Celery 将其记录为 WARNING。
console = Console(file=sys.stdout)

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

    def __init__(
        self,
        download_folder: Path,
        cookies_file: Optional[str] = None,
        proxy: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ):
        """
        初始化下载器.

        Args:
            download_folder: 下载文件夹路径
            cookies_file: cookies文件路径(可选)
            proxy: 代理服务器地址(可选)
            progress_callback: 进度回调函数(可选)
        """
        self.download_folder = Path(download_folder)
        self.cookies_file = cookies_file
        self.proxy = proxy
        self.progress_callback = progress_callback

        # 组合各种专门的处理器
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.subprocess_manager = SubprocessManager()
        self.file_processor = FileProcessor(self.subprocess_manager, self.command_builder)

        # 初始化cookies管理器
        if cookies_file:
            self.cookies_manager = CookiesManager(cookies_file)
        else:
            self.cookies_manager = None

        log.info(f"初始化下载器,目标文件夹: {self.download_folder}")
        if cookies_file:
            log.info(f"使用cookies文件: {cookies_file}")
        if proxy:
            log.info(f"使用代理: {self.proxy}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitizes a string to be a valid filename."""
        max_len = config.file_processing.filename_max_length
        suffix = config.file_processing.filename_truncate_suffix
        # Remove invalid characters for filenames
        sanitized = re.sub(r'[\\/*?:"<>|]', "", filename)
        # Replace multiple spaces with a single space and strip leading/trailing whitespace
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        # Remove any trailing dots or spaces that might cause issues before appending extensions
        sanitized = sanitized.rstrip(". ")

        # If the string is empty after sanitization, return a default name
        if not sanitized:
            return "untitled"

        # Truncate and add suffix if necessary
        if len(sanitized) > max_len:
            return sanitized[:max_len] + suffix

        return sanitized

    def _update_progress(self, message: str, progress: int, eta_seconds: int = 0, speed: str = ""):
        """更新下载进度"""
        log.debug(f"Progress update: {progress}% - {message} (ETA: {eta_seconds}s, 速度: {speed})")

        # 强化防止进度回退：如果新进度小于上次进度，且不是明确的重置操作，则跳过更新
        last_progress = getattr(self, "_last_celery_progress", 0)

        # 只允许以下情况的进度更新：
        # 1. 进度增加
        # 2. 进度为100%（完成状态）
        # 3. 进度为0%且上次进度也很低（<20%，允许早期重置）
        # 4. 明确的状态消息变化（如从"下载中"变为"合并中"）
        if progress < last_progress:
            is_early_reset = progress == 0 and last_progress < 20
            is_completion = progress == 100

            if not (is_early_reset or is_completion):
                log.debug(f"阻止进度回退: {progress}% < {last_progress}% (消息: {message})")
                return

        # 记录最后的进度值，供Rich进度监控使用
        self._last_celery_progress = progress

        if self.progress_callback:
            try:
                # 支持扩展的进度回调，包含ETA和速度信息
                if hasattr(self.progress_callback, "__code__") and self.progress_callback.__code__.co_argcount > 3:
                    self.progress_callback(message, progress, eta_seconds, speed)
                else:
                    self.progress_callback(message, progress)
                # 移除sleep，让进度更新更加频繁和平滑
            except Exception as e:
                log.warning(f"进度回调函数执行失败: {e}")

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
                return await self.subprocess_manager.execute_simple(info_cmd, timeout=timeout, check_returncode=True)
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 获取视频信息认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")

                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)

                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建信息获取命令
                        info_cmd = self.command_builder.build_playlist_info_cmd(url)
                        auth_retry_count += 1
                        log.info("✅ Cookies已更新,重试获取视频信息...")
                        continue
                    else:
                        log.error("❌ 无法自动更新cookies,获取视频信息失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error("❌ 未配置cookies管理器,无法自动处理认证错误")
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
            return_code, stdout, stderr = await self._execute_info_cmd_with_auth_retry(url, info_cmd, timeout=60)

            # 解析JSON输出
            for line in stdout.strip().split("\n"):
                if line.strip():
                    try:
                        video_info = json.loads(line)
                        yield video_info
                    except json.JSONDecodeError as e:
                        log.warning(f"解析视频信息JSON失败: {e}")
                        continue

        except AuthenticationException:
            # 认证异常直接向上传递,让上层处理重试
            raise
        except Exception as e:
            raise DownloaderException(f"获取播放列表信息失败: {e}") from e

    @with_retries(max_retries=3)
    async def _execute_cmd_with_auth_retry(
        self,
        initial_cmd: list,
        cmd_builder_func,
        url: str,
        cmd_builder_args: dict,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        timeout: int = 1800,
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
                    # 启动进度监控任务
                    progress_monitor_task = None
                    if self.progress_callback:
                        progress_monitor_task = asyncio.create_task(self._monitor_rich_progress(progress, task_id))

                    try:
                        result = await self.subprocess_manager.execute_with_progress(
                            cmd, progress, task_id, timeout=timeout
                        )
                        return result
                    finally:
                        # 停止进度监控
                        if progress_monitor_task:
                            progress_monitor_task.cancel()
                            try:
                                await progress_monitor_task
                            except asyncio.CancelledError:
                                pass
                else:
                    return await self.subprocess_manager.execute_simple(cmd, timeout=timeout)
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
                        log.info("✅ Cookies已更新,重试命令...")
                        continue
                    else:
                        log.error("❌ 无法自动更新cookies,命令执行失败.")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error("❌ 未配置cookies管理器,无法自动处理认证错误.")
                    elif auth_retry_count >= max_auth_retries:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries}).")
                    raise e
            except Exception as e:
                raise e
        raise DownloaderException("命令执行失败,所有重试均已用尽.")

    async def _monitor_rich_progress(self, progress: Progress, task_id: TaskID):
        """监控Rich进度条并更新Celery进度回调"""
        last_percentage = -1
        last_update_time = 0
        update_interval = 0.5  # 每500ms检查一次

        # 获取当前Celery进度作为起始点，避免进度重置
        try:
            current_celery_progress = getattr(self, "_last_celery_progress", 0)
        except Exception:
            current_celery_progress = 0

        # 强化防回退：记录监控期间的最高进度
        max_progress_during_monitoring = current_celery_progress

        try:
            while True:
                task = progress.tasks[task_id]
                if task.total and task.total > 0:
                    rich_percentage = int((task.completed / task.total) * 100)

                    # 将Rich进度映射到剩余的Celery进度空间
                    # 如果当前Celery进度是70%，那么Rich的0-100%映射到70-100%
                    remaining_space = 100 - current_celery_progress
                    base_adjusted_percentage = current_celery_progress + int((rich_percentage / 100) * remaining_space)

                    # 强化防回退：确保调整后的进度不会低于监控期间的最高进度
                    adjusted_percentage = max(base_adjusted_percentage, max_progress_during_monitoring)

                    current_time = asyncio.get_event_loop().time()

                    # 检查是否需要更新（只有进度增加时才更新）
                    if adjusted_percentage > last_percentage and current_time - last_update_time >= update_interval:
                        # 从Rich任务中获取ETA和速度信息
                        eta_seconds = 0
                        speed = ""

                        if hasattr(task, "fields") and task.fields:
                            eta_seconds = task.fields.get("eta_seconds", 0)
                            speed = task.fields.get("speed", "")

                        # 调用进度回调
                        self._update_progress("正在下载中", adjusted_percentage, eta_seconds, speed)

                        last_percentage = adjusted_percentage
                        max_progress_during_monitoring = adjusted_percentage
                        last_update_time = current_time

                await asyncio.sleep(update_interval)

        except asyncio.CancelledError:
            log.debug("进度监控任务已取消")
            raise
        except Exception as e:
            log.warning(f"进度监控过程中出错: {e}")

    def _parse_path_from_stderr(self, stderr: str) -> Optional[Path]:
        """从yt-dlp的stderr输出中解析目标文件路径。"""
        path_patterns = [
            re.compile(r"\[ExtractAudio\] Destination:\s*(?P<path>.+)"),
            re.compile(r"\[download\] Destination:\s*(?P<path>.+)"),
            re.compile(r"\[Merger\] Merging formats into \"(?P<path>.+)\""),
        ]

        log.debug(f"yt-dlp stderr for parsing:\n{stderr}")
        for line in stderr.strip().split("\n"):
            for pattern in path_patterns:
                match = pattern.search(line)
                if match:
                    found_path = match.group("path").strip('"')
                    log.info(f"从yt-dlp输出中解析到文件路径: {found_path}")
                    return Path(found_path)
        return None

    async def _find_and_verify_output_file(self, prefix: str, preferred_extensions: tuple) -> Optional[Path]:
        """
        主动验证并查找输出文件。
        优先检查首选扩展名，然后回退到glob搜索。

        Args:
            prefix: 文件名前缀
            preferred_extensions: 按优先顺序列出的文件扩展名元组

        Returns:
            找到的文件路径,如果未找到则返回None
        """
        log.debug(f"主动验证文件: 前缀={prefix}, 首选扩展名={preferred_extensions}")

        # 策略1: 主动验证首选扩展名
        for ext in preferred_extensions:
            potential_file = self.download_folder / f"{prefix}{ext}"
            if potential_file.exists() and potential_file.stat().st_size > 0:
                log.debug(f"✅ 主动验证成功: 找到文件 '{potential_file.name}'")
                return potential_file

        log.warning("主动验证失败，未找到任何首选扩展名的文件。将回退到搜索模式...")

        # 策略2: 回退到glob搜索 (以处理未知扩展名)
        matching_files = list(self.download_folder.glob(f"{prefix}*"))

        if not matching_files:
            log.error(f'搜索模式失败: 未找到任何以 "{prefix}" 开头的文件。')
            return None

        # 过滤掉目录和空文件
        valid_files = [f for f in matching_files if f.is_file() and f.stat().st_size > 0]

        if not valid_files:
            log.error("搜索模式失败: 找到的文件均无效 (是目录或大小为0)。")
            return None

        # 返回最新修改的文件，以处理可能的重试或覆盖情况
        latest_file = max(valid_files, key=lambda f: f.stat().st_mtime)
        log.debug(f"✅ 搜索模式成功: 找到最新的匹配文件: {latest_file.name}")
        return latest_file

    async def download_and_merge(
        self,
        video_url: str,
        format_id: str = None,
        resolution: str = "",
        fallback_prefix: Optional[str] = None,
    ) -> Optional[Path]:
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
        # 开始下载
        self._update_progress("正在下载中", 0)

        # --- 获取标题和分辨率，并生成最终文件名 ---
        try:
            # 1. Get video title
            self._update_progress("正在获取视频信息", 5)
            video_info_gen = self.stream_playlist_info(video_url)
            video_info = await video_info_gen.__anext__()
            video_title = video_info.get("title", "video")

            self._update_progress("正在解析格式信息", 10)

            # 2. 根据 format_id 查找确切的分辨率，如果失败则使用传递的 resolution 参数
            resolution_suffix = ""
            if format_id and "formats" in video_info:
                # Find the selected format to get its exact resolution
                selected_format = next(
                    (f for f in video_info["formats"] if f.get("format_id") == format_id),
                    None,
                )
                if selected_format and selected_format.get("width") and selected_format.get("height"):
                    resolution_suffix = f"_{selected_format['width']}x{selected_format['height']}"

            # 如果无法从format_id获取分辨率，但有resolution参数，则使用它
            if not resolution_suffix and resolution:
                # resolution 可能是 "1920x1080" 格式，直接使用
                if "x" in resolution and resolution != "audio":
                    resolution_suffix = f"_{resolution}"
                    log.info(f"使用传递的分辨率参数: {resolution}")
                elif resolution.endswith("p") and resolution != "audio":
                    # 处理如 "1080p" 格式
                    resolution_suffix = f"_{resolution}"
                    log.info(f"使用传递的分辨率参数: {resolution}")

            # 3. 组合成最终的文件前缀
            file_prefix = f"{self._sanitize_filename(video_title)}{resolution_suffix}"

        except (StopAsyncIteration, DownloaderException) as e:
            log.warning(f"无法获取视频标题: {e}。将使用备用前缀。")
            # 使用 fallback_prefix 或一个默认值
            file_prefix = fallback_prefix or "video"
        log.info(f"使用文件前缀: {file_prefix}")

        log.info(f"开始下载并合并: {file_prefix}")
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # --- 主策略：尝试一体化下载和合并 ---
        log.info("尝试主策略：一体化下载和合并...")
        self._update_progress("准备下载", 15)

        try:
            cmd_builder_args = {
                "output_path": str(self.download_folder),
                "url": video_url,
                "file_prefix": file_prefix,
                "format_id": format_id,
                "resolution": resolution,
            }
            download_cmd, _, exact_output_path = self.command_builder.build_combined_download_cmd(**cmd_builder_args)

            self._update_progress("开始下载", 20)

            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    "•",
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    download_task = progress.add_task("Download/Merge", total=100)

                    # Rich进度监控会自动更新Celery进度，无需手动调用
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=download_cmd,
                        cmd_builder_func=self.command_builder.build_combined_download_cmd,
                        url=video_url,
                        cmd_builder_args=cmd_builder_args,
                        progress=progress,
                        task_id=download_task,
                    )

            # 验证下载结果
            if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                self._update_progress("下载完成", 100)
                log.info(f"✅ 主策略成功: {exact_output_path.name}")
                return exact_output_path
            else:
                log.warning("主策略执行后未找到有效的输出文件。")
                self._update_progress("正在下载中", 35)

        except asyncio.CancelledError:
            log.warning("主策略下载任务被取消")
            raise
        except Exception as e:
            log.warning(f"主策略失败: {e}。将尝试备用策略。")

        # --- 备用策略：分步下载和手动合并 ---
        log.info("切换到备用策略：分步下载和手动合并...")
        self._update_progress("切换备用策略", 35)
        video_file = None
        audio_file = None

        try:
            # 1. 下载视频部分
            self._update_progress("下载视频流", 40)
            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    "•",
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    video_task = progress.add_task("Downloading Video", total=100)
                    video_cmd_args = {
                        "output_path": str(self.download_folder),
                        "url": video_url,
                        "file_prefix": file_prefix,
                        "format_id": format_id,
                    }
                    video_cmd = self.command_builder.build_separate_video_download_cmd(**video_cmd_args)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=video_cmd,
                        cmd_builder_func=self.command_builder.build_separate_video_download_cmd,
                        url=video_url,
                        cmd_builder_args=video_cmd_args,
                        progress=progress,
                        task_id=video_task,
                    )

            # 查找视频文件
            video_file = await self._find_and_verify_output_file(f"{file_prefix}.video", (".mp4", ".webm", ".mkv"))
            if not video_file:
                raise DownloaderException("备用策略：视频部分下载后未找到文件。")
            log.info(f"✅ 视频部分下载成功: {video_file.name}")

            # 2. 下载音频部分
            self._update_progress("下载音频流", 70)  # 调整为70%，避免与音频进度冲突
            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    "•",
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    audio_task = progress.add_task("Downloading Audio", total=100)
                    audio_cmd_args = {
                        "output_path": str(self.download_folder),
                        "url": video_url,
                        "file_prefix": file_prefix,
                    }
                    audio_cmd = self.command_builder.build_separate_audio_download_cmd(**audio_cmd_args)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=audio_cmd,
                        cmd_builder_func=self.command_builder.build_separate_audio_download_cmd,
                        url=video_url,
                        cmd_builder_args=audio_cmd_args,
                        progress=progress,
                        task_id=audio_task,
                    )

            # 查找音频文件
            audio_file = await self._find_and_verify_output_file(
                f"{file_prefix}.audio", (".m4a", ".mp3", ".opus", ".aac")
            )
            if not audio_file:
                log.warning("备用策略：音频部分下载后未找到文件。将尝试无音频合并。")

            # 3. 手动合并
            if video_file and audio_file:
                self._update_progress("合并音视频", 85)  # 调整为85%
                merged_file_path = self.download_folder / f"{file_prefix}.mp4"
                log.info(f"🔧 正在手动合并: {video_file.name} + {audio_file.name} -> {merged_file_path.name}")

                await self.file_processor.merge_to_mp4(video_file, audio_file, merged_file_path)

                if merged_file_path.exists() and merged_file_path.stat().st_size > 0:
                    self._update_progress("下载完成", 100)
                    log.info(f"✅ 备用策略成功: {merged_file_path.name}")
                    return merged_file_path
                else:
                    raise DownloaderException("备用策略：手动合并后未生成有效文件。")

            # 如果只有视频文件，作为最后手段返回
            if video_file:
                self._update_progress("处理视频文件", 90)  # 调整为90%
                log.warning("备用策略：无法合并，返回仅视频文件。")
                # 重命名视频文件以匹配最终文件名
                final_video_path = self.download_folder / f"{file_prefix}.mp4"
                video_file.rename(final_video_path)
                self._update_progress("下载完成", 100)
                return final_video_path

        except Exception as e:
            log.error(f"备用策略执行失败: {e}", exc_info=True)
            # 如果备用策略也失败，但主策略可能已经下载了部分文件，最后再检查一次
            final_check = await self._find_and_verify_output_file(file_prefix, (".mp4",))
            if final_check:
                log.info(f"在所有策略失败后，找到了一个最终文件: {final_check.name}")
                return final_check
            raise DownloaderException(f"主策略和备用策略均失败: {e}") from e

        raise DownloaderException("下载和合并视频失败，所有策略均已尝试。")

    async def download_with_smart_strategy(
        self,
        video_url: str,
        format_id: str = None,
        resolution: str = "",
        fallback_prefix: Optional[str] = None,
    ) -> Optional[Path]:
        """
        使用智能策略下载视频，自动判断完整流vs分离流

        Args:
            video_url: 视频URL
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (例如: '1080p60')
            fallback_prefix: 获取标题失败时的备用文件前缀 (可选)

        Returns:
            下载完成的文件路径，失败返回None

        Raises:
            DownloaderException: 下载失败
        """
        # 获取视频信息和格式列表
        try:
            video_info_gen = self.stream_playlist_info(video_url)
            video_info = await video_info_gen.__anext__()
            video_title = video_info.get("title", "video")
            formats = video_info.get("formats", [])

            if not formats:
                raise DownloaderException("未找到任何可用的视频格式")

            # 生成文件前缀
            resolution_suffix = ""
            if format_id and "formats" in video_info:
                selected_format = next((f for f in formats if f.get("format_id") == format_id), None)
                if selected_format and selected_format.get("width") and selected_format.get("height"):
                    resolution_suffix = f"_{selected_format['width']}x{selected_format['height']}"

            # 如果无法从format_id获取分辨率，但有resolution参数，则使用它
            if not resolution_suffix and resolution:
                # resolution 可能是 "1920x1080" 格式，直接使用
                if "x" in resolution and resolution != "audio":
                    resolution_suffix = f"_{resolution}"
                    log.info(f"智能下载使用传递的分辨率参数: {resolution}")
                elif resolution.endswith("p") and resolution != "audio":
                    # 处理如 "1080p" 格式
                    resolution_suffix = f"_{resolution}"
                    log.info(f"智能下载使用传递的分辨率参数: {resolution}")

            file_prefix = f"{self._sanitize_filename(video_title)}{resolution_suffix}"

        except (StopAsyncIteration, DownloaderException) as e:
            log.warning(f"无法获取视频信息: {e}。将使用备用前缀。")
            file_prefix = fallback_prefix or "video"
            formats = []

        log.info(f"智能下载开始: {file_prefix}")
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # 如果无法获取格式信息，降级到传统方法
        if not formats:
            log.warning("无法获取格式列表，降级到传统下载方法")
            return await self.download_and_merge(video_url, format_id, resolution, fallback_prefix)

        try:
            # 构建智能下载命令
            cmd_builder_args = {
                "output_path": str(self.download_folder),
                "url": video_url,
                "file_prefix": file_prefix,
                "formats": formats,
                "format_id": format_id,
                "resolution": resolution,
            }

            download_cmd, format_used, exact_output_path, strategy = self.command_builder.build_smart_download_cmd(
                **cmd_builder_args
            )

            # 根据策略显示不同的进度描述
            if strategy == DownloadStrategy.DIRECT:
                progress_desc = "智能下载(完整流)"
            else:
                progress_desc = "智能下载(合并流)"

            # 执行下载
            async with _progress_semaphore:
                with Progress(
                    SpinnerColumn(spinner_name="line"),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    "•",
                    TransferSpeedColumn(),
                    console=console,
                ) as progress:
                    download_task = progress.add_task(progress_desc, total=100)
                    await self._execute_cmd_with_auth_retry(
                        initial_cmd=download_cmd,
                        cmd_builder_func=self.command_builder.build_smart_download_cmd,
                        url=video_url,
                        cmd_builder_args=cmd_builder_args,
                        progress=progress,
                        task_id=download_task,
                    )

            # 验证输出文件
            if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                strategy_name = "完整流直下" if strategy == DownloadStrategy.DIRECT else "分离流合并"
                log.info(f"✅ 智能下载成功({strategy_name}): {exact_output_path.name}")
                return exact_output_path
            else:
                log.warning("智能下载执行后未找到有效的输出文件，尝试传统方法")
                return await self.download_and_merge(video_url, format_id, resolution, fallback_prefix)

        except asyncio.CancelledError:
            log.warning("智能下载任务被取消")
            raise
        except Exception as e:
            log.warning(f"智能下载失败: {e}，降级到传统方法")
            return await self.download_and_merge(video_url, format_id, resolution, fallback_prefix)

    async def download_audio(
        self,
        video_url: str,
        audio_format: str = "best",
        fallback_prefix: Optional[str] = None,
    ) -> Optional[Path]:
        """
        下载指定URL的音频。
        对已知的转换格式（如mp3）采用"主动指定"策略，对直接下载的原始流采用"主动搜索"策略。

        Args:
            video_url: 视频URL
            audio_format: 音频格式 (例如: 'mp3', 'm4a', 'best', 或一个特定的format_id)
            fallback_prefix: 获取标题失败时的备用文件前缀 (可选)

        Returns:
            下载的音频文件路径,失败返回None

        Raises:
            DownloaderException: 下载失败
        """
        log.info(f"开始下载音频: {video_url} (请求的格式/策略: {audio_format})")
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # 开始音频下载进度更新
        self._update_progress("正在下载中", 0)

        try:
            try:
                self._update_progress("获取视频信息", 5)
                video_info_gen = self.stream_playlist_info(video_url)
                video_info = await video_info_gen.__anext__()
                video_title = video_info.get("title", "audio")
                self._update_progress("解析音频格式", 10)
            except (StopAsyncIteration, DownloaderException) as e:
                log.warning(f"无法获取视频标题: {e}。将使用备用前缀。")
                video_title = fallback_prefix or "audio"
                self._update_progress("使用备用信息", 10)

            sanitized_title = self._sanitize_filename(video_title)
            # 音频文件不使用格式后缀作为前缀，只使用标题
            file_prefix = sanitized_title
            log.info(f"使用文件前缀: {file_prefix}")
            self._update_progress("准备音频下载", 15)

            known_conversion_formats = ["mp3", "m4a", "wav", "opus", "aac", "flac"]

            if audio_format in known_conversion_formats:
                # --- 策略1: 转换格式 (路径可预测) ---
                exact_output_path = self.download_folder / f"{sanitized_title}.{audio_format}"
                log.info(f"音频转换请求。确切的输出路径为: {exact_output_path}")
                self._update_progress("开始音频下载", 20)

                cmd_args = {
                    "url": video_url,
                    "output_template": str(exact_output_path),
                    "audio_format": audio_format,
                }
                cmd = self.command_builder.build_audio_download_cmd(**cmd_args)

                async with _progress_semaphore:
                    with Progress(
                        SpinnerColumn(spinner_name="dots"),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        "•",
                        TransferSpeedColumn(),
                        console=console,
                    ) as progress:
                        audio_task = progress.add_task("Audio Download", total=100)

                        # Rich进度监控会自动更新Celery进度
                        await self._execute_cmd_with_auth_retry(
                            initial_cmd=cmd,
                            cmd_builder_func=self.command_builder.build_audio_download_cmd,
                            url=video_url,
                            cmd_builder_args=cmd_args,
                            progress=progress,
                            task_id=audio_task,
                        )

                if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                    self._update_progress("下载完成", 100)
                    return exact_output_path
                else:
                    raise DownloaderException(f"音频转换失败，预期的输出文件 '{exact_output_path}' 未找到或为空。")
            else:
                # --- 策略2: 直接下载原始流 (主动验证) ---
                log.info("直接音频流下载请求。将采用主动验证策略。")
                self._update_progress("准备直接下载", 20)

                # 使用模板让yt-dlp能自动添加正确的扩展名
                output_template = self.download_folder / f"{sanitized_title}.%(ext)s"
                cmd_args = {
                    "url": video_url,
                    "output_template": str(output_template),
                    "audio_format": audio_format,
                }
                cmd = self.command_builder.build_audio_download_cmd(**cmd_args)

                async with _progress_semaphore:
                    with Progress(
                        SpinnerColumn(spinner_name="dots"),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        "•",
                        TransferSpeedColumn(),
                        console=console,
                    ) as progress:
                        audio_task = progress.add_task("Audio Stream", total=100)

                        # Rich进度监控会自动更新Celery进度
                        await self._execute_cmd_with_auth_retry(
                            initial_cmd=cmd,
                            cmd_builder_func=self.command_builder.build_audio_download_cmd,
                            url=video_url,
                            cmd_builder_args=cmd_args,
                            progress=progress,
                            task_id=audio_task,
                        )

                # 主动验证并查找输出文件
                preferred_extensions = (
                    ".m4a",
                    ".mp4",
                    ".webm",
                    ".opus",
                    ".ogg",
                    ".mp3",
                )
                output_file = await self._find_and_verify_output_file(sanitized_title, preferred_extensions)

                if output_file:
                    self._update_progress("下载完成", 100)
                    log.info(f"✅ 音频下载成功: {output_file.name}")
                    return output_file
                else:
                    raise DownloaderException("音频下载后未找到文件，所有策略均失败。")

        except asyncio.CancelledError:
            log.warning("音频下载任务被取消")
            raise
        except Exception as e:
            log.error(f"音频下载失败: {e}", exc_info=True)
            raise DownloaderException(f"音频下载失败: {e}") from e

    async def cleanup(self):
        """
        清理所有正在运行的子进程.
        """
        await self.subprocess_manager.cleanup_all_processes()
        log.info("下载器清理完成")
