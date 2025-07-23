import os
import argparse
import asyncio
import logging
import sys
import re
from pathlib import Path
from typing import Optional, List

import aiofiles
from rich.console import Console
from rich.logging import RichHandler

from config_manager import config

console = Console(file=sys.stdout)
log = logging.getLogger(__name__)

class CustomConsoleHandler(RichHandler):
    """自定义控制台处理器，只显示关键进度信息和错误"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.console_keywords = config.logging.console_keywords

    def emit(self, record):
        if record.levelno >= logging.ERROR or any(keyword in record.getMessage() for keyword in self.console_keywords):
            super().emit(record)

def setup_logging(log_folder: Path) -> None:
    log_filename = config.logging.log_filename
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    
    # 确保日志文件夹存在
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file_path = log_folder / log_filename

    # 清除现有的日志处理器，避免重复设置
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path, encoding='utf-8'),
            CustomConsoleHandler(rich_tracebacks=True, show_path=False, show_time=False)
        ],
        force=True  # 强制重新配置，即使之前已经配置过
    )

def get_inputs(args: argparse.Namespace) -> List[str]:
    """获取输入内容：URL或本地文件路径"""
    inputs = []
    if args.mode == 'subtitle':
        log.info("模式: AI字幕生成（本地文件）")
        for input_path in args.inputs:
            file_path = Path(input_path)
            if file_path.exists() and file_path.is_file():
                inputs.append(str(file_path.resolve()))
            else:
                log.error(f"文件不存在或不是文件: {input_path}")
    elif args.batch_file:
        log.info("模式: 从文件批量读取URL")
        try:
            with open(args.inputs[0], 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # 提取以 https://www. 开头的URL
                    url_match = re.search(r'https://www\.[^\s]+', line)
                    if url_match:
                        inputs.append(url_match.group(0))
                    elif line.startswith('http'):
                        # 如果整行就是URL
                        inputs.append(line)
                    else:
                        log.warning(f"跳过无法识别的行: {line}")
        except FileNotFoundError:
            log.error(f"错误: 找不到文件 '{args.inputs[0]}'，已跳过。")
    else:
        log.info("模式: 直接从命令行读取URL")
        inputs = args.inputs
    return inputs

def is_media_file(file_path: Path) -> bool:
    return file_path.suffix.lower() in config.file_processing.media_extensions

async def extract_audio_if_needed(media_path: Path, output_dir: Path) -> Optional[Path]:
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'}
    if media_path.suffix.lower() in audio_extensions:
        return media_path

    console.print(f"🎥 正在从视频提取音频: {media_path.name}", style="bold blue")
    audio_path = output_dir / f"{media_path.stem}_extracted.wav"
    cmd = ['ffmpeg', '-y', '-i', str(media_path), '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', str(audio_path)]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()

    if process.returncode != 0:
        console.print(f"❌ 音频提取失败: {stderr.decode()}", style="bold red")
        return None
    
    console.print(f"✅ 音频提取成功: {audio_path.name}", style="bold green")
    return audio_path

def sanitize(name: str, max_len: Optional[int] = None) -> str:
    if max_len is None:
        max_len = config.file_processing.filename_max_length
        suffix = config.file_processing.filename_truncate_suffix
    else:
        suffix = '...'
    name = re.sub(r'[\\/*?"<>|]', '_', name).strip()
    return f"{name[:max_len]}{suffix}" if len(name) > max_len else name
