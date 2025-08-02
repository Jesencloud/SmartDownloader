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
        """执行信息获取命令,支持认证错误自动重试。"""
        max_auth_retries = 1
        auth_retry_count = 0

        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_simple(info_cmd, timeout=timeout, check_returncode=True)
            except AuthenticationException as e:
                auth_retry_count += 1
                info_cmd = await self._handle_info_auth_failure(e, auth_retry_count, max_auth_retries, url)
            except Exception:
                raise  # Re-throw other exceptions

        raise DownloaderException("获取信息失败,所有重试均已用尽.")

    async def _handle_info_auth_failure(
        self, e: AuthenticationException, attempt: int, max_attempts: int, url: str
    ) -> list:
        """处理信息获取命令的认证失败。"""
        if attempt > max_attempts:
            log.error(f"❌ 已达到最大认证重试次数 ({max_attempts})")
            raise e

        if not self.cookies_manager:
            log.error("❌ 未配置cookies管理器,无法自动处理认证错误.")
            raise e

        log.warning(f"🍪 获取视频信息认证错误,尝试第 {attempt} 次自动刷新cookies...")
        new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)

        if not new_cookies_file:
            log.error("❌ 无法自动更新cookies,获取视频信息失败")
            raise e

        self.command_builder.update_cookies_file(new_cookies_file)
        log.info("✅ Cookies已更新,重试获取视频信息...")
        return self.command_builder.build_playlist_info_cmd(url)

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
            if stdout.strip():
                try:
                    # --dump-json 返回的是单个JSON对象，不是每行一个
                    video_info = json.loads(stdout.strip())
                    yield video_info
                except json.JSONDecodeError as e:
                    log.warning(f"解析视频信息JSON失败: {e}")
                    # 回退到逐行解析（兼容旧行为）
                    for line in stdout.strip().split("\n"):
                        if line.strip():
                            try:
                                video_info = json.loads(line)
                                yield video_info
                            except json.JSONDecodeError:
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
        """
        max_auth_retries = 1
        auth_retry_count = 0
        cmd = initial_cmd

        while auth_retry_count <= max_auth_retries:
            try:
                if progress and task_id is not None:
                    return await self._execute_with_progress_monitoring(cmd, progress, task_id, timeout)
                else:
                    return await self.subprocess_manager.execute_simple(cmd, timeout=timeout)
            except AuthenticationException as e:
                auth_retry_count += 1
                cmd = await self._handle_auth_failure(
                    e, auth_retry_count, max_auth_retries, url, cmd_builder_func, cmd_builder_args
                )
            except Exception:
                raise  # 重新抛出其他所有异常

        raise DownloaderException("命令执行失败,所有重试均已用尽.")

    async def _execute_with_progress_monitoring(self, cmd: list, progress: Progress, task_id: TaskID, timeout: int):
        """执行命令并监控Rich进度条。"""
        progress_monitor_task = None
        if self.progress_callback:
            progress_monitor_task = asyncio.create_task(self._monitor_rich_progress(progress, task_id))

        try:
            return await self.subprocess_manager.execute_with_progress(cmd, progress, task_id, timeout=timeout)
        finally:
            if progress_monitor_task:
                progress_monitor_task.cancel()
                try:
                    await progress_monitor_task
                except asyncio.CancelledError:
                    pass  # 正常取消

    async def _handle_auth_failure(
        self,
        e: AuthenticationException,
        attempt: int,
        max_attempts: int,
        url: str,
        cmd_builder_func,
        cmd_builder_args: dict,
    ) -> list:
        """处理认证失败,刷新cookies并返回新命令。"""
        if attempt > max_attempts:
            log.error(f"❌ 已达到最大认证重试次数 ({max_attempts}).")
            raise e

        if not self.cookies_manager:
            log.error("❌ 未配置cookies管理器,无法自动处理认证错误.")
            raise e

        log.warning(f"🍪 检测到认证错误,尝试第 {attempt} 次自动刷新cookies...")
        new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)

        if not new_cookies_file:
            log.error("❌ 无法自动更新cookies,命令执行失败.")
            raise e

        self.command_builder.update_cookies_file(new_cookies_file)
        rebuilt_cmd = cmd_builder_func(**cmd_builder_args)
        log.info("✅ Cookies已更新,重试命令...")
        return rebuilt_cmd[0] if isinstance(rebuilt_cmd, tuple) else rebuilt_cmd

    async def _monitor_rich_progress(self, progress: Progress, task_id: TaskID):
        """监控Rich进度条并更新Celery进度回调。"""
        state = {
            "last_percentage": -1,
            "last_update_time": 0,
            "update_interval": 0.5,
            "celery_base_progress": getattr(self, "_last_celery_progress", 0),
            "initial_checks": 0,
            "max_initial_checks": 10,
        }
        state["max_seen_progress"] = state["celery_base_progress"]

        try:
            while True:
                task = progress.tasks[task_id]
                self._process_progress_tick(task, state)
                await asyncio.sleep(state["update_interval"])
        except asyncio.CancelledError:
            log.debug("进度监控任务已取消")
            raise
        except Exception as e:
            log.warning(f"进度监控过程中出错: {e}")

    def _process_progress_tick(self, task: Task, state: dict) -> None:
        """处理单次进度检查，并在需要时更新。"""
        # Guard Clause 1: 任务数据尚未准备好进行进度计算
        if not (task.total and task.total > 0 and task.completed is not None):
            if state["initial_checks"] < state["max_initial_checks"]:
                state["initial_checks"] += 1
                log.debug(f"等待进度初始化... (checks: {state['initial_checks']})")
            return

        rich_percentage = int((task.completed / task.total) * 100)

        # Guard Clause 2: 忽略下载初期的、可能是错误的100%进度
        if state["initial_checks"] < state["max_initial_checks"] and rich_percentage >= 100:
            state["initial_checks"] += 1
            log.debug(f"初期阶段忽略100%进度 (checks: {state['initial_checks']})")
            return

        adjusted_percentage = self._calculate_adjusted_progress(rich_percentage, state)
        current_time = asyncio.get_event_loop().time()

        # 检查是否满足更新条件
        if (
            adjusted_percentage > state["last_percentage"]
            and current_time - state["last_update_time"] >= state["update_interval"]
        ):
            self._send_progress_update(task, adjusted_percentage, rich_percentage, state)

    def _calculate_adjusted_progress(self, rich_percentage: int, state: dict) -> int:
        """计算调整后的Celery进度，确保不回退。"""
        remaining_space = 100 - state["celery_base_progress"]
        base_adjusted = state["celery_base_progress"] + int((rich_percentage / 100) * remaining_space)
        return max(base_adjusted, state["max_seen_progress"])

    def _send_progress_update(self, task: Task, adjusted_percentage: int, rich_percentage: int, state: dict) -> None:
        """发送进度回调并更新状态。"""
        eta = task.fields.get("eta_seconds", 0) if hasattr(task, "fields") else 0
        speed = task.fields.get("speed", "") if hasattr(task, "fields") else ""

        self._update_progress("正在下载中", adjusted_percentage, eta, speed)
        log.debug(f"进度更新: Rich={rich_percentage}%, Celery={adjusted_percentage}%")

        # 更新状态
        state["last_percentage"] = adjusted_percentage
        state["max_seen_progress"] = adjusted_percentage
        state["last_update_time"] = asyncio.get_event_loop().time()
        if state["initial_checks"] > 0:
            state["initial_checks"] = 0
            log.debug("检测到真实下载进度，开始正常监控")

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
        这是协调下载流程的主函数。
        """
        self._update_progress("正在下载中", 0)
        file_prefix = await self._prepare_download_prefix(video_url, format_id, resolution, fallback_prefix)
        log.info(f"开始下载并合并: {file_prefix}")
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # --- 主策略 ---
        primary_result = await self._run_primary_strategy(video_url, file_prefix, format_id, resolution)
        if primary_result:
            self._update_progress("下载完成", 100)
            log.info(f"✅ 主策略成功: {primary_result.name}")
            return primary_result

        # --- 备用策略 ---
        log.warning("主策略失败。将尝试备用策略。")
        self._update_progress("切换备用策略", 35)
        fallback_result = await self._run_fallback_strategy(video_url, file_prefix, format_id)
        if fallback_result:
            self._update_progress("下载完成", 100)
            log.info(f"✅ 备用策略成功: {fallback_result.name}")
            return fallback_result

        # --- 最终检查与失败 ---
        log.error("主策略和备用策略均失败。")
        final_check = await self._find_and_verify_output_file(file_prefix, (".mp4",))
        if final_check:
            log.info(f"在所有策略失败后，找到了一个最终文件: {final_check.name}")
            return final_check

        raise DownloaderException("下载和合并视频失败，所有策略均已尝试。")

    async def _prepare_download_prefix(
        self, video_url: str, format_id: str, resolution: str, fallback_prefix: Optional[str]
    ) -> str:
        """获取视频信息并准备文件名前缀。"""
        try:
            self._update_progress("正在获取视频信息", 5)
            video_info_gen = self.stream_playlist_info(video_url)
            video_info = await video_info_gen.__anext__()
            video_title = video_info.get("title", "video")
            self._update_progress("正在解析格式信息", 10)

            resolution_suffix = ""
            if format_id and "formats" in video_info:
                selected_format = next((f for f in video_info["formats"] if f.get("format_id") == format_id), None)
                if selected_format and selected_format.get("width") and selected_format.get("height"):
                    resolution_suffix = f"_{selected_format['width']}x{selected_format['height']}"

            if not resolution_suffix and resolution:
                if "x" in resolution and resolution != "audio":
                    resolution_suffix = f"_{resolution}"
                elif resolution.endswith("p") and resolution != "audio":
                    resolution_suffix = f"_{resolution}"

            return f"{self._sanitize_filename(video_title)}{resolution_suffix}"
        except (StopAsyncIteration, DownloaderException) as e:
            log.warning(f"无法获取视频标题: {e}。将使用备用前缀。")
            return fallback_prefix or "video"

    async def _run_primary_strategy(
        self, video_url: str, file_prefix: str, format_id: str, resolution: str
    ) -> Optional[Path]:
        """执行主策略（一体化下载）。"""
        log.info("尝试主策略：一体化下载和合并...")
        self._update_progress("准备下载", 15)
        try:
            cmd_args = {
                "output_path": str(self.download_folder),
                "url": video_url,
                "file_prefix": file_prefix,
                "format_id": format_id,
                "resolution": resolution,
            }
            cmd, _, exact_output_path = self.command_builder.build_combined_download_cmd(**cmd_args)

            self._update_progress("开始下载", 20)
            await self._download_with_progress(
                "Download/Merge", cmd, self.command_builder.build_combined_download_cmd, video_url, cmd_args
            )

            if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
                return exact_output_path
            log.warning("主策略执行后未找到有效的输出文件。")
            return None
        except asyncio.CancelledError:
            log.warning("主策略下载任务被取消")
            raise
        except Exception as e:
            log.warning(f"主策略执行中出错: {e}")
            return None

    async def _run_fallback_strategy(self, video_url: str, file_prefix: str, format_id: str) -> Optional[Path]:
        """执行备用策略（分步下载和合并）。"""
        try:
            video_file = await self._download_separate_stream("video", video_url, file_prefix, format_id)
            if not video_file:
                raise DownloaderException("备用策略：视频部分下载后未找到文件。")
            log.info(f"✅ 视频部分下载成功: {video_file.name}")

            audio_file = await self._download_separate_stream("audio", video_url, file_prefix)
            if not audio_file:
                log.warning("备用策略：音频部分下载后未找到文件。将尝试无音频合并。")

            return await self._merge_or_finalize_fallback(video_file, audio_file, file_prefix)
        except Exception as e:
            log.error(f"备用策略执行失败: {e}", exc_info=True)
            return None

    async def _download_separate_stream(
        self, stream_type: str, video_url: str, file_prefix: str, format_id: Optional[str] = None
    ) -> Optional[Path]:
        """为备用策略下载单个流（视频或音频）。"""
        if stream_type == "video":
            self._update_progress("下载视频流", 40)
            task_desc, builder, cmd_args, search_prefix, exts = (
                "Downloading Video",
                self.command_builder.build_separate_video_download_cmd,
                {
                    "output_path": str(self.download_folder),
                    "url": video_url,
                    "file_prefix": file_prefix,
                    "format_id": format_id,
                },
                f"{file_prefix}.video",
                (".mp4", ".webm", ".mkv"),
            )
        else:
            self._update_progress("下载音频流", 70)
            task_desc, builder, cmd_args, search_prefix, exts = (
                "Downloading Audio",
                self.command_builder.build_separate_audio_download_cmd,
                {"output_path": str(self.download_folder), "url": video_url, "file_prefix": file_prefix},
                f"{file_prefix}.audio",
                (".m4a", ".mp3", ".opus", ".aac"),
            )

        cmd = builder(**cmd_args)
        await self._download_with_progress(task_desc, cmd, builder, video_url, cmd_args)
        return await self._find_and_verify_output_file(search_prefix, exts)

    async def _merge_or_finalize_fallback(
        self, video_file: Path, audio_file: Optional[Path], file_prefix: str
    ) -> Optional[Path]:
        """处理备用策略的最后合并或重命名步骤。"""
        final_path = self.download_folder / f"{file_prefix}.mp4"

        if audio_file:
            self._update_progress("合并音视频", 85)
            log.info(f"🔧 正在手动合并: {video_file.name} + {audio_file.name} -> {final_path.name}")
            await self.file_processor.merge_to_mp4(video_file, audio_file, final_path)
            if final_path.exists() and final_path.stat().st_size > 0:
                return final_path
            raise DownloaderException("备用策略：手动合并后未生成有效文件。")
        else:
            self._update_progress("处理视频文件", 90)
            log.warning("备用策略：无法合并，返回仅视频文件。")
            video_file.rename(final_path)
            return final_path

    async def _download_with_progress(
        self, task_desc: str, cmd: list, cmd_builder_func, url: str, cmd_builder_args: dict
    ):
        """辅助函数，在Rich进度条上下文中运行命令。"""
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
                task = progress.add_task(task_desc, total=100)
                await self._execute_cmd_with_auth_retry(
                    initial_cmd=cmd,
                    cmd_builder_func=cmd_builder_func,
                    url=url,
                    cmd_builder_args=cmd_builder_args,
                    progress=progress,
                    task_id=task,
                )

    async def download_with_smart_strategy(
        self,
        video_url: str,
        format_id: str = None,
        resolution: str = "",
        fallback_prefix: Optional[str] = None,
    ) -> Optional[Path]:
        """
        使用智能策略下载视频，自动判断完整流vs分离流。
        这是一个协调函数，负责准备、执行和处理下载降级。
        """
        # 1. 准备下载所需信息
        preparation_result = await self._prepare_smart_download(video_url, format_id, resolution, fallback_prefix)
        if not preparation_result:
            log.warning("无法获取格式列表，降级到传统下载方法")
            return await self.download_and_merge(video_url, format_id, resolution, fallback_prefix)

        file_prefix, formats = preparation_result
        log.info(f"智能下载开始: {file_prefix}")
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # 2. 执行智能下载，并在失败时降级
        try:
            result_path = await self._execute_smart_download(video_url, file_prefix, formats, format_id, resolution)
            if result_path:
                return result_path
            else:
                log.warning("智能下载执行后未找到有效的输出文件，尝试传统方法")
                return await self.download_and_merge(video_url, format_id, resolution, file_prefix)
        except asyncio.CancelledError:
            log.warning("智能下载任务被取消")
            raise
        except Exception as e:
            log.warning(f"智能下载失败: {e}，降级到传统方法")
            return await self.download_and_merge(video_url, format_id, resolution, file_prefix)

    async def _prepare_smart_download(
        self, video_url: str, format_id: str, resolution: str, fallback_prefix: Optional[str]
    ) -> Optional[tuple]:
        """获取视频信息，准备文件前缀和格式列表。如果失败则返回None。"""
        try:
            video_info_gen = self.stream_playlist_info(video_url)
            video_info = await video_info_gen.__anext__()
            video_title = video_info.get("title", "video")
            formats = video_info.get("formats", [])
            if not formats:
                raise DownloaderException("未找到任何可用的视频格式")

            resolution_suffix = ""
            if format_id:
                format_id_str = str(format_id)
                selected_format = next((f for f in formats if str(f.get("format_id")) == format_id_str), None)
                if selected_format and selected_format.get("width") and selected_format.get("height"):
                    resolution_suffix = f"_{selected_format['width']}x{selected_format['height']}"

            if not resolution_suffix and resolution:
                if "x" in resolution and resolution != "audio":
                    resolution_suffix = f"_{resolution}"
                elif resolution.endswith("p") and resolution != "audio":
                    resolution_suffix = f"_{resolution}"

            file_prefix = f"{self._sanitize_filename(video_title)}{resolution_suffix}"
            return file_prefix, formats
        except (StopAsyncIteration, DownloaderException) as e:
            log.warning(f"无法获取视频信息: {e}。")
            return None

    async def _execute_smart_download(
        self, video_url: str, file_prefix: str, formats: list, format_id: str, resolution: str
    ) -> Optional[Path]:
        """执行智能下载的核心逻辑。"""
        cmd_builder_args = {
            "output_path": str(self.download_folder),
            "url": video_url,
            "file_prefix": file_prefix,
            "formats": formats,
            "format_id": format_id,
            "resolution": resolution,
        }
        cmd, _, exact_output_path, strategy = self.command_builder.build_smart_download_cmd(**cmd_builder_args)
        progress_desc = "智能下载(完整流)" if strategy == DownloadStrategy.DIRECT else "智能下载(合并流)"

        await self._download_with_progress(
            progress_desc, cmd, self.command_builder.build_smart_download_cmd, video_url, cmd_builder_args
        )

        if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
            strategy_name = "完整流直下" if strategy == DownloadStrategy.DIRECT else "分离流合并"
            log.info(f"✅ 智能下载成功({strategy_name}): {exact_output_path.name}")
            return exact_output_path
        return None

    async def download_audio(
        self,
        video_url: str,
        audio_format: str = "best",
        fallback_prefix: Optional[str] = None,
    ) -> Optional[Path]:
        """
        下载指定URL的音频。
        这是一个调度函数，根据请求的格式选择合适的下载策略。
        """
        log.info(f"开始下载音频: {video_url} (格式: {audio_format})")
        self.download_folder.mkdir(parents=True, exist_ok=True)
        self._update_progress("正在下载中", 0)

        try:
            file_prefix = await self._prepare_audio_download(video_url, fallback_prefix)
            known_conversion_formats = ["mp3", "m4a", "wav", "opus", "aac", "flac"]

            if audio_format in known_conversion_formats:
                return await self._download_and_convert_audio(video_url, file_prefix, audio_format)
            else:
                return await self._download_direct_audio_stream(video_url, file_prefix, audio_format)

        except asyncio.CancelledError:
            log.warning("音频下载任务被取消")
            raise
        except Exception as e:
            log.error(f"音频下载失败: {e}", exc_info=True)
            raise DownloaderException(f"音频下载失败: {e}") from e

    async def _prepare_audio_download(self, video_url: str, fallback_prefix: Optional[str]) -> str:
        """获取视频信息并准备音频文件名前缀。"""
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
        log.info(f"使用文件前缀: {sanitized_title}")
        self._update_progress("准备音频下载", 15)
        return sanitized_title

    async def _download_and_convert_audio(self, video_url: str, file_prefix: str, audio_format: str) -> Path:
        """策略1: 下载并转换为已知格式，输出路径是可预测的。"""
        exact_output_path = self.download_folder / f"{file_prefix}.{audio_format}"
        log.info(f"音频转换请求。确切的输出路径为: {exact_output_path}")
        self._update_progress("开始音频下载", 20)

        cmd_args = {"url": video_url, "output_template": str(exact_output_path), "audio_format": audio_format}
        cmd = self.command_builder.build_audio_download_cmd(**cmd_args)

        await self._download_with_progress(
            "Audio Download", cmd, self.command_builder.build_audio_download_cmd, video_url, cmd_args
        )

        if exact_output_path.exists() and exact_output_path.stat().st_size > 0:
            self._update_progress("下载完成", 100)
            return exact_output_path
        raise DownloaderException(f"音频转换失败，预期的输出文件 '{exact_output_path}' 未找到或为空。")

    async def _download_direct_audio_stream(self, video_url: str, file_prefix: str, audio_format: str) -> Path:
        """策略2: 直接下载原始音频流，输出路径需要主动搜索。"""
        log.info("直接音频流下载请求。将采用主动验证策略。")
        self._update_progress("准备直接下载", 20)

        output_template = self.download_folder / f"{file_prefix}.%(ext)s"
        cmd_args = {"url": video_url, "output_template": str(output_template), "audio_format": audio_format}
        cmd = self.command_builder.build_audio_download_cmd(**cmd_args)

        await self._download_with_progress(
            "Audio Stream", cmd, self.command_builder.build_audio_download_cmd, video_url, cmd_args
        )

        preferred_extensions = (".m4a", ".mp4", ".webm", ".opus", ".ogg", ".mp3")
        output_file = await self._find_and_verify_output_file(file_prefix, preferred_extensions)

        if output_file:
            self._update_progress("下载完成", 100)
            log.info(f"✅ 音频下载成功: {output_file.name}")
            return output_file
        raise DownloaderException("音频下载后未找到文件，所有策略均失败。")

    async def cleanup(self):
        """
        清理所有正在运行的子进程.
        """
        await self.subprocess_manager.cleanup_all_processes()
        log.info("下载器清理完成")
