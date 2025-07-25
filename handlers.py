#!/usr/bin/env python3
"""
处理器模块
包含文件处理、元数据处理和下载阶段的处理函数
"""

import argparse
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os as aos

from downloader import Downloader
from core import (
    DownloaderException,
    NonRecoverableErrorException,
    MaxRetriesExceededException,
    FFmpegException,
)
from subtitles import SubtitleProcessor
from utils import is_media_file, extract_audio_if_needed, sanitize, console, log


async def process_local_file(sub_proc: SubtitleProcessor, file_path: str) -> None:
    """处理本地媒体文件生成AI字幕。

    Args:
        sub_proc (SubtitleProcessor): 字幕处理器实例。
        file_path (str): 本地媒体文件路径。
    """
    media_path = Path(file_path)
    if not is_media_file(media_path):
        console.print(f"❌ 不支持的文件格式: {media_path.suffix}", style="bold red")
        return

    file_prefix = sanitize(media_path.stem)
    log.info(f"▶️ (本地文件) 开始处理: {file_prefix}")
    media_dir = media_path.parent.resolve()

    try:
        audio_path = await extract_audio_if_needed(media_path, media_dir)
        if not audio_path:
            return

        await sub_proc.process_item(file_prefix, audio_path, output_folder=media_dir)

        if audio_path != media_path and audio_path.name.endswith("_extracted.wav"):
            await aos.remove(audio_path)
            console.print(f"🧹 已清理临时音频文件: {audio_path.name}", style="dim")

        console.print(f"✅ 字幕生成完成: {media_path.name}", style="bold green")
    except (OSError, PermissionError) as e:
        log.error(f"无法访问本地文件 {media_path.name}: {e}")
    except Exception as e:
        log.error(f"处理本地文件 {media_path.name} 时发生未知错误: {e}", exc_info=True)


async def save_info(folder: Path, prefix: str, url: str, dlr) -> None:
    """保存视频信息为文本文件。

    直接从yt-dlp获取视频信息并生成可读的.txt文件，不依赖.info.json。

    Args:
        folder (Path): 保存文件夹路径。
        prefix (str): 文件前缀。
        url (str): 视频URL。
        dlr: 下载器实例。
    """
    try:
        # 构建获取信息的命令
        info_cmd = [
            "yt-dlp",
            "--ignore-config",
            "--no-warnings",
            "--no-color",
            "--dump-json",
            "--no-download",
        ]
        if dlr.cookies_file:
            info_cmd.extend(["--cookies", dlr.cookies_file])
        info_cmd.append(url)

        # 执行命令获取信息
        import asyncio

        process = await asyncio.create_subprocess_exec(
            *info_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            import json

            info = json.loads(stdout.decode())

            # 生成.txt文件
            txt_path = folder / f"{prefix}.txt"
            async with aiofiles.open(txt_path, "w", encoding="utf-8") as f:
                await f.write(f"视频标题: {info.get('title', 'N/A')}\n")
                await f.write(f"视频URL: {info.get('webpage_url', 'N/A')}\n")
                await f.write(f"UP主: {info.get('uploader', 'N/A')}\n")
                file_size_mb = "N/A"
                if isinstance(info.get("filesize_approx"), (int, float)):
                    file_size_mb = f"{info['filesize_approx'] / (1000 * 1000):.2f} MB"
                await f.write(f"视频大小: {file_size_mb}\n")
                await f.write(f"视频分辨率: {info.get('resolution', 'N/A')}\n")
                await f.write(f"视频时长: {info.get('duration_string', 'N/A')}\n")

                # 添加描述信息（如果存在）
                description = info.get("description", "")
                if description:
                    await f.write(
                        f"\n简介:\n{description[:500]}{'...' if len(description) > 500 else ''}\n"
                    )

            console.print(f"📄 信息文件已生成: {txt_path.name}", style="bold cyan")
        else:
            log.warning(f"获取视频信息失败: {prefix}")

    except Exception as e:
        log.error(f"生成信息文件失败 '{prefix}': {e}", exc_info=True)


async def process_metadata_phase(dlr: Downloader, url: str, prefix: str) -> None:
    """处理元数据阶段。

    下载视频元数据并生成信息文件。

    Args:
        dlr (Downloader): 下载器实例。
        url (str): 视频URL。
        prefix (str): 文件前缀。

    Raises:
        Exception: 当元数据处理失败时。
    """
    try:
        await dlr.download_metadata(url, prefix)
        await save_info(dlr.download_folder, prefix, url, dlr)
    except (DownloaderException, IOError, OSError) as e:
        log.error(f"元数据处理阶段失败 '{prefix}': {e}")
        raise
    except Exception as e:
        log.error(f"元数据处理阶段发生未知错误 '{prefix}': {e}", exc_info=True)
        raise


async def process_download_phase(
    dlr: Downloader,
    sub_proc: Optional[SubtitleProcessor],
    url: str,
    prefix: str,
    args: argparse.Namespace,
) -> None:
    """处理下载阶段。

    根据指定模式下载视频和/或音频，并处理AI字幕生成。

    Args:
        dlr (Downloader): 下载器实例。
        sub_proc (Optional[SubtitleProcessor]): 字幕处理器实例。
        url (str): 视频URL。
        prefix (str): 文件前缀。
        args (argparse.Namespace): 命令行参数。
    """
    try:
        vid_path = None
        aud_path = None

        # 处理视频下载 - 优先采用智能下载模式
        if args.mode in ["video", "both"]:
            console.print(f"🎬 正在准备智能下载: {prefix}", style="bold blue")
            try:
                # 尝试使用智能下载策略
                vid_path = await dlr.download_with_smart_strategy(url, prefix)
            except Exception as e:
                console.print(f"⚠️  智能下载失败，使用传统方法: {e}", style="yellow")
                vid_path = await dlr.download_and_merge(url, prefix)

        # 处理纯音频下载
        if args.mode == "audio":
            console.print(f"🎵 正在准备下载音频: {prefix}", style="bold blue")
            aud_path = await dlr.download_audio_directly(url, prefix)

        # 处理both模式下的音频在线下载
        if args.mode == "both":
            console.print(f"🎵 正在在线下载音频: {prefix}_audio", style="bold blue")
            # both模式统一采用在线下载音频，添加_audio后缀
            aud_path = await dlr.download_audio_directly(url, f"{prefix}_audio")

            # 处理AI字幕
            if args.ai_subs and aud_path and sub_proc:
                await sub_proc.process_item(prefix, aud_path)
        elif args.mode == "audio" and args.ai_subs and aud_path and sub_proc:
            # 纯音频模式下的AI字幕处理
            await sub_proc.process_item(prefix, aud_path)
        elif args.ai_subs and vid_path and sub_proc:
            # video模式下如果需要AI字幕，使用视频文件
            await sub_proc.process_item(prefix, vid_path)

    except (
        NonRecoverableErrorException,
        MaxRetriesExceededException,
        FFmpegException,
    ) as e:
        log.error(f"❌ 处理项目 '{prefix}' 失败: {e}")
    except DownloaderException as e:
        log.error(f"❌ 处理项目 '{prefix}' 时发生未知下载错误: {e}")
    finally:
        await dlr.cleanup_temp_files(prefix)


async def process_item(
    dlr: Downloader,
    sub_proc: Optional[SubtitleProcessor],
    url: str,
    prefix: str,
    args: argparse.Namespace,
) -> None:
    """完整的项目处理流程。

    包括元数据下载和媒体文件下载两个阶段。

    Args:
        dlr (Downloader): 下载器实例。
        sub_proc (Optional[SubtitleProcessor]): 字幕处理器实例。
        url (str): 视频URL。
        prefix (str): 文件前缀。
        args (argparse.Namespace): 命令行参数。
    """
    log.info(f"▶️ (项目) 开始处理: {prefix}")

    # 元数据阶段
    await process_metadata_phase(dlr, url, prefix)

    # 下载阶段
    await process_download_phase(dlr, sub_proc, url, prefix, args)
