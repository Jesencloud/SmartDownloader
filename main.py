# main.py
import argparse, time, json, re, logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# 从rich.logging导入RichHandler以美化控制台日志
from rich.logging import RichHandler

from downloader import Downloader
from subtitles import SubtitleProcessor, AI_LIBRARIES_AVAILABLE

def setup_logging(log_folder: Path):
    """配置全局日志系统，同时输出到控制台和文件。"""
    log_file_path = log_folder / "downloader.log"
    
    # 配置基础logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
        handlers=[
            # 文件处理器，记录所有信息
            logging.FileHandler(log_file_path, encoding='utf-8'),
            # 控制台处理器，使用rich美化
            RichHandler(rich_tracebacks=True, show_path=False)
        ]
    )

def get_urls(args) -> list[str]:
    # ... (此函数无需改动) ...
    urls = []
    if args.batch_file:
        log.info("模式: 从文件批量读取URL")
        for fpath in args.inputs:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                    urls.extend(lines); log.info(f"  - 已从 '{fpath}' 加载 {len(lines)} 个URL。")
            except FileNotFoundError: log.error(f"错误: 找不到文件 '{fpath}'，已跳过。")
    else: log.info("模式: 直接从命令行读取URL"); urls = args.inputs
    return urls

def sanitize(name: str, max_len: int = 50) -> str:
    # ... (此函数无需改动) ...
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    return f"{name[:max_len]}..." if len(name) > max_len else name

def save_info(folder: Path, prefix: str):
    json_path = folder / f"{prefix}.info.json"
    if not json_path.exists(): return
    try:
        with open(json_path, 'r', encoding='utf-8') as f: info = json.load(f)
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
            
        log.info(f"    📄 已生成信息文件: {txt_path.name}")
    except Exception as e: log.error(f"    生成 .txt 信息文件时出错: {e}")
    finally: json_path.unlink(missing_ok=True)

def process_item(dlr: Downloader, sub_proc: Optional[SubtitleProcessor], url: str, prefix: str, args: argparse.Namespace):
    # ... (此函数无需改动) ...
    log.info(f"▶️ (项目) 开始处理: {prefix}")
    log.info(f"🔗 URL: {url}")
    vid_path, aud_path, ai_src = None, None, None
    if dlr.download_metadata(url, prefix): save_info(dlr.download_folder, prefix)
    if args.mode in ['video', 'both']:
        vid_path = dlr.download_and_merge(url, prefix)
        if not vid_path: log.error(f"    视频下载或合并失败，中止。"); dlr.cleanup_temp_files(prefix); return
        ai_src = vid_path
    if args.mode == 'both' and vid_path:
        log.info("-" * 25)
        aud_path = dlr.extract_audio_from_local_file(vid_path, prefix)
        if aud_path: ai_src = aud_path
    if args.ai_subs:
        if ai_src: sub_proc.process_item(prefix, ai_src)
        else: log.warning(f"    找不到用于AI转录的媒体文件。")
    dlr.cleanup_temp_files(prefix)

def main():
    # 在所有操作开始前，先创建文件夹并配置日志
    dl_folder = Path(datetime.now().strftime("%Y%m%d-%H%M%S"))
    dl_folder.mkdir(exist_ok=True)
    setup_logging(dl_folder)
    
    global log
    log = logging.getLogger(__name__)

    log.info("🚀 智能媒体下载与AI字幕工具 v3.0 (Logging) 启动 🚀")
    
    parser = argparse.ArgumentParser(description="智能媒体下载与处理工具", formatter_class=argparse.RawTextHelpFormatter)
    # ... (参数解析逻辑不变) ...
    parser.add_argument("inputs", nargs='+', help="一个或多个URL；或当使用-b时，为文件路径。")
    parser.add_argument("-b", "--batch-file", action="store_true", help="将输入视为包含URL列表的文本文件。")
    parser.add_argument("-m", "--mode", choices=['video', 'both'], default='video', help="下载模式:\n  video: 仅下载视频(默认)\n  both:  下载视频和音频")
    parser.add_argument("-p", "--proxy", type=str, default=None, help="设置HTTP/SOCKS代理。")
    parser.add_argument("--ai-subs", action="store_true", help="当无官方字幕时，自动生成AI字幕。")
    args = parser.parse_args()

    if args.ai_subs and not AI_LIBRARIES_AVAILABLE:
        log.error("--ai-subs 功能需要 `deep-translator` 和 `openai-whisper` 库。")
        log.error("请运行: pip install -r requirements.txt")
        return
        
    urls = get_urls(args)
    if not urls: log.error("没有有效的URL可供处理。"); return
    
    cookies = str(Path("cookies.txt").resolve()) if Path("cookies.txt").exists() else None
    downloader = Downloader(dl_folder, cookies, args.proxy)
    sub_processor = SubtitleProcessor(dl_folder, args.proxy) if args.ai_subs else None

    log.info(f"所有内容将保存到: {dl_folder.resolve()}")
    log.info(f"下载模式: {args.mode}")
    if args.proxy: log.info(f"代理设置: {args.proxy}")
    if args.ai_subs: log.info("AI字幕生成: 已启用")
    if cookies: log.info("已加载Cookies文件")

    total_items = 0
    try:
        for url in urls:
            log.info("============================================================")
            log.info(f"正在处理URL: {url}")
            stream = downloader.stream_playlist_info(url)
            count, has_started = 0, False
            for i, meta in enumerate(stream, 1):
                has_started, count = True, i
                prefix = f"{i:03d}_{sanitize(meta.get('title', f'项目_{i}'))}"
                process_item(downloader, sub_processor, meta.get('url', url), prefix, args)
                log.info("礼貌等待3秒..."); time.sleep(3)
            if not has_started:
                log.warning("未能从流中解析到项目，尝试作为单个链接处理...")
                prefix = f"001_{sanitize(urls[0] if len(urls)==1 else '单项下载')}"
                process_item(downloader, sub_processor, url, prefix, args); count = 1
            total_items += count
            log.info(f"--- URL处理完成: {url} | 共处理了 {count} 个项目 ---")
    except KeyboardInterrupt: log.warning("\n\n用户中断了操作。")
    except Exception as e: log.critical(f"发生致命错误: {e}", exc_info=True) # exc_info=True会记录完整的错误堆栈
    finally:
        log.info("============================================================")
        log.info(f"🎉 全部任务完成! 本次运行共处理 {total_items} 个项目。")
        log.info(f"📁 日志与所有文件保存在: {dl_folder.resolve()}")

if __name__ == "__main__":
    main()