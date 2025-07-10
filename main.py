import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from rich.console import Console

from config_manager import config_manager, config
from downloader import Downloader
from subtitles import AI_LIBRARIES_AVAILABLE, SubtitleProcessor
from utils import setup_logging, get_inputs, sanitize
from handlers import process_local_file, process_item

console = Console()
log = logging.getLogger(__name__)

async def main() -> None:
    script_path = Path(__file__).parent
    dl_folder = config_manager.get_download_folder(script_path)
    setup_logging(dl_folder)

    log.info("🚀 智能媒体下载与AI字幕工具 v4.0 (Async) 启动 🚀")
    parser = argparse.ArgumentParser(description="智能媒体下载与处理工具")
    parser.add_argument("inputs", nargs='+', help="URL或文件路径")
    parser.add_argument("-b", "--batch-file", action="store_true", help="批量处理文件中的URL")
    parser.add_argument("-m", "--mode", choices=['video', 'both', 'subtitle'], default='video')
    parser.add_argument("-p", "--proxy", type=str, default=None)
    parser.add_argument("--ai-subs", action="store_true", help="自动生成AI字幕")
    args = parser.parse_args()

    if (args.mode == 'subtitle' or args.ai_subs) and not AI_LIBRARIES_AVAILABLE:
        log.error("AI字幕功能需要相关库，请参考README安装。")
        return

    inputs = get_inputs(args)
    if not inputs:
        log.error("没有有效的输入可供处理。")
        return

    cookies = str(Path("cookies.txt").resolve()) if Path("cookies.txt").exists() else None
    downloader = Downloader(dl_folder, cookies, args.proxy)
    sub_processor = SubtitleProcessor(dl_folder, args.proxy) if (args.ai_subs or args.mode == 'subtitle') else None

    tasks = []
    if args.mode == 'subtitle':
        console.print(f"🧠 AI字幕生成模式启动，将并发处理 {len(inputs)} 个文件", style="bold cyan")
        for file_path in inputs:
            if sub_processor is not None:
                tasks.append(process_local_file(sub_processor, file_path))
            else:
                log.error("Subtitle processor is not initialized, cannot process local file for subtitles.")
    else:
        console.print(f"🚀 下载模式启动，将并发处理 {len(inputs)} 个URL/播放列表", style="bold cyan")
        i = 0
        for url in inputs:
            async for meta in downloader.stream_playlist_info(url):
                i += 1
                prefix = f"{i:03d}_{sanitize(meta.get('title', f'项目_{i}'))}"
                tasks.append(process_item(downloader, sub_processor, meta.get('url', url), prefix, args))
            if i == 0: # Handle single video URL
                i += 1
                prefix = f"001_{sanitize('单项下载')}"
                tasks.append(process_item(downloader, sub_processor, url, prefix, args))

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log.warning("用户中断操作，正在清理...")
        await downloader.cleanup_all_incomplete_files()
        console.print("✅ 清理完成，安全退出", style="bold green")
    except Exception as e:
        log.critical(f"发生致命错误: {e}", exc_info=True)
    finally:
        log.info("🎉 全部任务完成!")
        log.info(f"📁 日志与所有文件保存在: {dl_folder.resolve()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n🚫 操作被用户强制取消。", style="bold red")