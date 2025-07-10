import json
import logging
import argparse
import asyncio
from pathlib import Path
from typing import Optional, Any, Dict, AsyncGenerator

import aiofiles
import aiofiles.os as aos
from rich.console import Console

from config_manager import config
from downloader import Downloader, DownloaderException, NonRecoverableErrorException, MaxRetriesExceededException, FFmpegException
from subtitles import SubtitleProcessor
from utils import is_media_file, extract_audio_if_needed, sanitize, console, log

async def process_local_file(sub_proc: SubtitleProcessor, file_path: str) -> None:
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

        if audio_path != media_path and audio_path.name.endswith('_extracted.wav'):
            await aos.remove(audio_path)
            console.print(f"🧹 已清理临时音频文件: {audio_path.name}", style="dim")

        console.print(f"✅ 字幕生成完成: {media_path.name}", style="bold green")
    except Exception as e:
        log.error(f"处理本地文件 {media_path.name} 时出错: {e}")

async def save_info(folder: Path, prefix: str) -> None:
    json_path = folder / f"{prefix}.info.json"
    if not json_path.exists():
        return
    try:
        async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
            info = json.loads(await f.read())
        
        txt_path = folder / f"{prefix}.txt"
        async with aiofiles.open(txt_path, 'w', encoding='utf-8') as f:
            await f.write(f"视频标题: {info.get('title', 'N/A')}\n")
            await f.write(f"视频URL: {info.get('webpage_url', 'N/A')}\n")
            await f.write(f"UP主: {info.get('uploader', 'N/A')}\n")
            file_size_mb = 'N/A'
            if isinstance(info.get('filesize_approx'), (int, float)):
                file_size_mb = f"{info['filesize_approx'] / (1024 * 1024):.2f} MB"
            await f.write(f"视频大小: {file_size_mb}\n")
            await f.write(f"视频分辨率: {info.get('resolution', 'N/A')}\n")
            await f.write(f"视频时长: {info.get('duration_string', 'N/A')}\n")
            
            
            await f.write(f"简介:\n{info.get('description', 'N/A')}\n")

        console.print(f"📄 信息文件已生成: {txt_path.name}", style="bold cyan")
    except Exception as e:
        log.error(f"生成 .txt 信息文件时出错: {json_path.name} - {e}")
    finally:
        if json_path.exists():
            await aos.remove(json_path)

async def process_item(dlr: Downloader, sub_proc: Optional[SubtitleProcessor], url: str, prefix: str, args: argparse.Namespace) -> None:
    log.info(f"▶️ (项目) 开始处理: {prefix}")
    try:
        await dlr.download_metadata(url, prefix)
        await save_info(dlr.download_folder, prefix)

        vid_path = None
        if args.mode in ['video', 'both']:
            vid_path = await dlr.download_and_merge(url, prefix)

        if args.mode == 'both' and vid_path:
            aud_path = await dlr.extract_audio_from_local_file(vid_path, prefix)
            if args.ai_subs and aud_path and sub_proc:
                await sub_proc.process_item(prefix, aud_path)
        elif args.ai_subs and vid_path and sub_proc:
             await sub_proc.process_item(prefix, vid_path)

    except (NonRecoverableErrorException, MaxRetriesExceededException, FFmpegException) as e:
        log.error(f"❌ 处理项目 '{prefix}' 失败: {e}")
    except DownloaderException as e:
        log.error(f"❌ 处理项目 '{prefix}' 时发生未知下载错误: {e}")
    finally:
        await dlr.cleanup_temp_files(prefix)
