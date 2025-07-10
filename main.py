# main.py
import argparse, time, json, re, logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# 从rich.logging导入RichHandler以美化控制台日志
from rich.logging import RichHandler
from rich.console import Console

# 导入配置管理器
from config_manager import config
from downloader import Downloader
from subtitles import SubtitleProcessor, AI_LIBRARIES_AVAILABLE

console = Console()

class CustomConsoleHandler(RichHandler):
    """自定义控制台处理器，只显示关键进度信息和错误"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 从配置获取关键词
        logging_config = config.get_logging_config()
        self.console_keywords = logging_config.get('console_keywords', [
            "🚀 智能媒体下载", "🎉 全部任务完成", "📁 日志与所有文件保存在"
        ])
    
    def emit(self, record):
        # 只显示错误级别或包含关键词的信息
        if record.levelno >= logging.ERROR:
            super().emit(record)
        elif any(keyword in record.getMessage() for keyword in self.console_keywords):
            super().emit(record)
        # 其他INFO级别的日志不在控制台显示，只保存到文件

def setup_logging(log_folder: Path):
    """配置全局日志系统，文件记录所有信息，控制台只显示关键信息。"""
    # 从配置获取日志设置
    logging_config = config.get_logging_config()
    log_filename = logging_config.get('log_filename', 'downloader.log')
    log_level = getattr(logging, logging_config.get('level', 'INFO').upper(), logging.INFO)
    
    log_file_path = log_folder / log_filename
    
    # 配置基础logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
        handlers=[
            # 文件处理器，记录所有信息
            logging.FileHandler(log_file_path, encoding='utf-8'),
            # 自定义控制台处理器，只显示关键信息和错误
            CustomConsoleHandler(rich_tracebacks=True, show_path=False, show_time=False)
        ]
    )

def get_inputs(args) -> list[str]:
    """获取输入内容：URL或本地文件路径"""
    inputs = []
    if args.mode == 'subtitle':
        # 字幕模式：处理本地文件
        log.info("模式: AI字幕生成（本地文件）")
        for input_path in args.inputs:
            file_path = Path(input_path)
            if file_path.exists() and file_path.is_file():
                inputs.append(str(file_path.resolve()))
                log.info(f"  - 已添加文件: {file_path}")
            else:
                log.error(f"文件不存在或不是文件: {input_path}")
    elif args.batch_file:
        # 批量URL模式
        log.info("模式: 从文件批量读取URL")
        for fpath in args.inputs:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                    inputs.extend(lines); log.info(f"  - 已从 '{fpath}' 加载 {len(lines)} 个URL。")
            except FileNotFoundError: log.error(f"错误: 找不到文件 '{fpath}'，已跳过。")
    else: 
        # 直接URL模式
        log.info("模式: 直接从命令行读取URL"); inputs = args.inputs
    return inputs

def is_media_file(file_path: Path) -> bool:
    """检查文件是否为支持的媒体格式"""
    media_extensions = {
        # 视频格式
        '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.mts', '.m2ts',
        # 音频格式  
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'
    }
    return file_path.suffix.lower() in media_extensions

def extract_audio_if_needed(media_path: Path, output_dir: Path) -> Optional[Path]:
    """如果是视频文件，提取音频；如果是音频文件，直接返回"""
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus'}
    
    if media_path.suffix.lower() in audio_extensions:
        # 已经是音频文件
        return media_path
    
    # 是视频文件，需要提取音频
    console.print(f"🎥 正在从视频提取音频: {media_path.name}", style="bold blue")
    audio_path = output_dir / f"{media_path.stem}_extracted.wav"
    
    import subprocess
    cmd = [
        'ffmpeg', '-y', '-i', str(media_path),
        '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
        str(audio_path)
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        console.print(f"✅ 音频提取成功: {audio_path.name}", style="bold green")
        return audio_path
    except subprocess.CalledProcessError as e:
        console.print(f"❌ 音频提取失败: {e}", style="bold red")
        return None
    except FileNotFoundError:
        console.print("❌ 未找到ffmpeg，请确保已安装并配置PATH", style="bold red")
        return None

def process_local_file(sub_proc: SubtitleProcessor, file_path: Path, args: argparse.Namespace):
    """处理本地媒体文件"""
    media_path = Path(file_path)
    
    if not is_media_file(media_path):
        console.print(f"❌ 不支持的文件格式: {media_path.suffix}", style="bold red")
        return False
    
    file_prefix = sanitize(media_path.stem)
    log.info(f"▶️ (本地文件) 开始处理: {file_prefix}")
    log.info(f"📁 文件: {media_path}")
    
    # 获取媒体文件所在的目录
    media_dir = media_path.parent.resolve()
    log.info(f"📂 字幕输出目录: {media_dir}")
    
    # 临时修改SubtitleProcessor的输出目录
    original_folder = sub_proc.download_folder
    sub_proc.download_folder = media_dir
    
    try:
        # 获取音频文件（如果是视频则提取到媒体文件同目录）
        audio_path = extract_audio_if_needed(media_path, media_dir)
        if not audio_path:
            console.print(f"❌ 无法获取音频: {media_path.name}", style="bold red")
            return False
        
        # 生成字幕
        sub_proc.process_item(file_prefix, audio_path)
        
        # 如果是临时提取的音频文件，清理它
        if audio_path != media_path and audio_path.name.endswith('_extracted.wav'):
            try:
                audio_path.unlink()
                console.print(f"🧹 已清理临时音频文件: {audio_path.name}", style="dim")
            except Exception as e:
                log.warning(f"清理临时文件失败: {e}")
        
        console.print(f"✅ 字幕生成完成: {media_path.name}", style="bold green")
        console.print(f"📍 字幕位置: {media_dir}", style="dim cyan")
        return True
        
    except Exception as e:
        log.error(f"处理文件时发生错误: {e}")
        return False
    finally:
        # 恢复原来的输出目录
        sub_proc.download_folder = original_folder

def sanitize(name: str, max_len: int = None) -> str:
    # 从配置获取文件名处理参数
    if max_len is None:
        file_config = config.get_file_processing_config()
        max_len = file_config.get('filename_max_length', 50)
        suffix = file_config.get('filename_truncate_suffix', '...')
    else:
        suffix = '...'
    
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    return f"{name[:max_len]}{suffix}" if len(name) > max_len else name

def save_info(folder: Path, prefix: str):
    json_path = folder / f"{prefix}.info.json"
    if not json_path.exists(): 
        return
    try:
        with open(json_path, 'r', encoding='utf-8') as f: 
            info = json.load(f)
        txt_path = folder / f"{prefix}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            # 基本信息
            f.write(f"视频标题: {info.get('title', 'N/A')}\n")
            f.write(f"视频ID: {info.get('id', 'N/A')}\n")
            f.write(f"UP主: {info.get('uploader', 'N/A')}\n")
            f.write(f"原始URL: {info.get('webpage_url', 'N/A')}\n\n")
            
            # 技术参数
            f.write("=== 技术参数 ===\n")
            if 'formats' in info and info['formats']:
                # 找到最佳视频格式
                video_format = None
                audio_format = None
                
                for fmt in info['formats']:
                    # 寻找最佳视频格式
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):
                        if not video_format or (fmt.get('height', 0) > video_format.get('height', 0)):
                            video_format = fmt
                    
                    # 寻找最佳音频格式
                    if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        if not audio_format or (fmt.get('abr', 0) > audio_format.get('abr', 0)):
                            audio_format = fmt
                
                if video_format:
                    width = video_format.get('width', 'N/A')
                    height = video_format.get('height', 'N/A')
                    f.write(f"分辨率: {width}x{height}\n")
                    f.write(f"视频编码: {video_format.get('vcodec', 'N/A')}\n")
                    
                    # 音频编码：优先从音频格式获取，否则从视频格式获取
                    audio_codec = 'N/A'
                    if audio_format and audio_format.get('acodec') != 'none':
                        audio_codec = audio_format.get('acodec')
                    elif video_format.get('acodec') != 'none':
                        audio_codec = video_format.get('acodec')
                    f.write(f"音频编码: {audio_codec}\n")
                    
                    # 文件大小
                    filesize = video_format.get('filesize') or info.get('filesize')
                    if filesize:
                        size_mb = filesize / (1024 * 1024)
                        f.write(f"文件大小: {size_mb:.2f} MB\n")
            f.write("\n")
            
            # 简介内容
            description = info.get('description', '')
            if description:
                f.write("------ 简介 ------\n")
                f.write(f"{description}\n")
            
        console.print(f"📄 信息文件已生成: {txt_path.name}", style="bold cyan")
    except Exception as e: 
        log.error(f"生成 .txt 信息文件时出错: {e}")
    finally: 
        # 确保删除json文件
        try:
            json_path.unlink(missing_ok=True)
        except Exception as e:
            log.error(f"删除json文件失败: {e}")

def process_item(dlr: Downloader, sub_proc: Optional[SubtitleProcessor], url: str, prefix: str, args: argparse.Namespace):
    # 记录当前正在处理的项目，用于中断时的清理
    current_prefix = prefix
    
    log.info(f"▶️ (项目) 开始处理: {prefix}")
    log.info(f"🔗 URL: {url}")
    vid_path, aud_path, ai_src = None, None, None
    
    try:
        dlr.download_metadata(url, prefix)  # 下载元数据，不管成功失败都尝试生成txt
        save_info(dlr.download_folder, prefix)  # 总是尝试生成信息文件
        if args.mode in ['video', 'both']:
            vid_path = dlr.download_and_merge(url, prefix)
            if not vid_path: 
                log.error(f"    视频下载或合并失败，中止。")
                dlr.cleanup_temp_files(prefix)
                return
            ai_src = vid_path
        if args.mode == 'both' and vid_path:
            log.info("-" * 25)
            aud_path = dlr.extract_audio_from_local_file(vid_path, prefix)
            if aud_path: ai_src = aud_path
        if args.ai_subs:
            if ai_src: sub_proc.process_item(prefix, ai_src)
            else: log.warning(f"    找不到用于AI转录的媒体文件。")
    except KeyboardInterrupt:
        # 如果在处理单个项目时被中断，清理当前项目的临时文件
        console.print(f"\n⚠️ 正在中断当前项目: {prefix}", style="bold yellow")
        dlr.cleanup_temp_files(prefix)
        raise  # 重新抛出中断信号给上层处理
    finally:
        # 清理当前项目的临时文件
        dlr.cleanup_temp_files(prefix)

def main():
    # 首先加载配置，确定下载文件夹位置
    script_path = Path(__file__).parent
    dl_folder = config.get_download_folder(script_path)
    setup_logging(dl_folder)
    
    global log
    log = logging.getLogger(__name__)

    log.info("🚀 智能媒体下载与AI字幕工具 v3.0 (Logging) 启动 🚀")
    
    parser = argparse.ArgumentParser(description="智能媒体下载与处理工具", formatter_class=argparse.RawTextHelpFormatter)
    # ... (参数解析逻辑不变) ...
    parser.add_argument("inputs", nargs='+', help="URL列表、文件路径（批量模式时）或本地媒体文件路径（AI字幕模式时）")
    parser.add_argument("-b", "--batch-file", action="store_true", help="将输入视为包含URL列表的文本文件。")
    parser.add_argument("-m", "--mode", choices=['video', 'both', 'subtitle'], default='video', 
                       help="运行模式:\n  video: 仅下载视频(默认)\n  both:  下载视频和音频\n  subtitle: 仅为本地文件生成AI字幕")
    parser.add_argument("-p", "--proxy", type=str, default=None, help="设置HTTP/SOCKS代理。")
    parser.add_argument("--ai-subs", action="store_true", help="当无官方字幕时，自动生成AI字幕。")
    args = parser.parse_args()

    if (args.mode == 'subtitle' and not AI_LIBRARIES_AVAILABLE) or (args.ai_subs and not AI_LIBRARIES_AVAILABLE):
        log.error("AI字幕功能需要 `deep-translator` 和 `openai-whisper` 库。")
        log.error("请运行: pip install -r requirements.txt")
        return
        
    inputs = get_inputs(args)
    if not inputs: 
        if args.mode == 'subtitle':
            log.error("没有有效的本地文件可供处理。")
        else:
            log.error("没有有效的URL可供处理。")
        return
    
    cookies = str(Path("cookies.txt").resolve()) if Path("cookies.txt").exists() else None
    downloader = Downloader(dl_folder, cookies, args.proxy)
    sub_processor = SubtitleProcessor(dl_folder, args.proxy) if (args.ai_subs or args.mode == 'subtitle') else None

    log.info(f"所有内容将保存到: {dl_folder.resolve()}")
    log.info(f"运行模式: {args.mode}")
    if args.proxy: log.info(f"代理设置: {args.proxy}")
    if args.ai_subs or args.mode == 'subtitle': log.info("AI字幕生成: 已启用")
    if cookies: log.info("已加载Cookies文件")

    total_items = 0
    try:
        if args.mode == 'subtitle':
            # 字幕生成模式：处理本地文件
            console.print(f"🧠 AI字幕生成模式启动，将处理 {len(inputs)} 个文件", style="bold cyan")
            success_count = 0
            for i, file_path in enumerate(inputs, 1):
                console.print(f"\n📋 处理文件 {i}/{len(inputs)}: {Path(file_path).name}", style="bold blue")
                if process_local_file(sub_processor, Path(file_path), args):
                    success_count += 1
                total_items += 1
                
                # 处理间隔等待（除了最后一个文件）
                if i < len(inputs):
                    file_config = config.get_file_processing_config()
                    wait_time = file_config.get('polite_wait_time', 3)
                    log.info(f"等待{wait_time}秒...")
                    time.sleep(wait_time)
            
            console.print(f"\n📊 字幕生成完成: 成功 {success_count}/{len(inputs)} 个文件", style="bold green")
        else:
            # 原有的下载模式
            for url in inputs:
                log.info("============================================================")
                log.info(f"正在处理URL: {url}")
                stream = downloader.stream_playlist_info(url)
                count, has_started = 0, False
                for i, meta in enumerate(stream, 1):
                    has_started, count = True, i
                    prefix = f"{i:03d}_{sanitize(meta.get('title', f'项目_{i}'))}"
                    process_item(downloader, sub_processor, meta.get('url', url), prefix, args)
                    
                    # 从配置获取等待时间
                    file_config = config.get_file_processing_config()
                    wait_time = file_config.get('polite_wait_time', 3)
                    log.info(f"礼貌等待{wait_time}秒..."); time.sleep(wait_time)
                if not has_started:
                    log.warning("未能从流中解析到项目，尝试作为单个链接处理...")
                    prefix = f"001_{sanitize(inputs[0] if len(inputs)==1 else '单项下载')}"
                    process_item(downloader, sub_processor, url, prefix, args); count = 1
                total_items += count
                log.info(f"--- URL处理完成: {url} | 共处理了 {count} 个项目 ---")
    except KeyboardInterrupt: 
        console.print("\n\n🚫 用户中断操作，正在清理未完成文件...", style="bold red")
        log.warning("用户中断了操作。")
        
        # 清理未完成的下载文件
        try:
            cleaned_files = downloader.cleanup_all_incomplete_files()
            if cleaned_files:
                log.info(f"已清理未完成文件: {', '.join(cleaned_files[:5])}{'...' if len(cleaned_files) > 5 else ''}")
            console.print("✅ 清理完成，安全退出", style="bold green")
        except Exception as cleanup_error:
            log.error(f"清理过程中出错: {cleanup_error}")
            console.print("⚠️ 清理过程中出现错误，请手动检查文件", style="bold yellow")
    except Exception as e: log.critical(f"发生致命错误: {e}", exc_info=True) # exc_info=True会记录完整的错误堆栈
    finally:
        log.info("============================================================")
        log.info(f"🎉 全部任务完成! 本次运行共处理 {total_items} 个项目。")
        log.info(f"📁 日志与所有文件保存在: {dl_folder.resolve()}")

if __name__ == "__main__":
    main()