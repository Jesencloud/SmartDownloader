# main.py
import argparse, time, json, re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# 【新】增加并发库导入
from concurrent.futures import ThreadPoolExecutor

from downloader import Downloader
from subtitles import SubtitleProcessor, AI_LIBRARIES_AVAILABLE

# ... (get_urls, sanitize, save_info, process_item 函数无需改动) ...
def get_urls(args) -> list[str]:
    urls = []
    if args.batch_file:
        print("模式: 从文件批量读取URL")
        for fpath in args.inputs:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                    urls.extend(lines); print(f"  - 已从 '{fpath}' 加载 {len(lines)} 个URL。")
            except FileNotFoundError: print(f"❌ 错误: 找不到文件 '{fpath}'，已跳过。")
    else: print("模式: 直接从命令行读取URL"); urls = args.inputs
    return urls

def sanitize(name: str, max_len: int = 50) -> str:
    name = re.sub(r'[\\/*?:"<>|]', '_', name).strip()
    return f"{name[:max_len]}..." if len(name) > max_len else name

def save_info(folder: Path, prefix: str):
    json_path = folder / f"{prefix}.info.json"
    if not json_path.exists(): return
    try:
        with open(json_path, 'r', encoding='utf-8') as f: info = json.load(f)
        txt_path = folder / f"{prefix}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"标题: {info.get('title', 'N/A')}\nID: {info.get('id', 'N/A')}\n")
            f.write(f"作者: {info.get('uploader', 'N/A')}\nURL: {info.get('webpage_url', 'N/A')}\n")
        print(f"    📄 已生成信息文件: {txt_path.name}")
    except Exception as e: print(f"    ❌ 生成 .txt 信息文件时出错: {e}")
    finally: json_path.unlink(missing_ok=True)

def process_item(dlr: Downloader, sub_proc: Optional[SubtitleProcessor], url: str, prefix: str, args: argparse.Namespace):
    print("\n" + "="*50); print(f"▶️ (项目) 开始处理: {prefix}"); print(f"🔗 URL: {url}")
    vid_path, aud_path, ai_src = None, None, None
    if dlr.download_metadata(url, prefix): 
        save_info(dlr.download_folder, prefix)
    if args.mode in ['video', 'both']:
        temp_vid, temp_aud = dlr.download_parts(url, prefix)
        if temp_vid and temp_aud:
            if temp_vid == temp_aud:
                vid_path = dlr.download_folder / f"{prefix}.mp4"; temp_vid.rename(vid_path)
            else: vid_path = dlr.merge_to_mp4(temp_vid, temp_aud, prefix)
            ai_src = vid_path
        else: print(f"    ❌ 视频下载失败，中止。"); dlr.cleanup_temp_files(prefix); return
    if args.mode == 'both' and vid_path:
        print("-" * 25); aud_path = dlr.extract_audio_from_local_file(vid_path, prefix)
        if aud_path: ai_src = aud_path
    if args.ai_subs:
        if ai_src: sub_proc.process_item(prefix, ai_src)
        else: print(f"    ⚠️ 找不到用于AI转录的媒体文件。")
    dlr.cleanup_temp_files(prefix)


def main():
    parser = argparse.ArgumentParser(description="智能媒体下载与处理工具", formatter_class=argparse.RawTextHelpFormatter)
    
    # 【新】使用互斥组来确保URL输入和文件翻译功能不冲突
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("inputs", nargs='*', default=None, help="一个或多个URL；或当使用-b时，为文件路径。")
    group.add_argument("--translate-file", type=str, help="仅对指定的本地SRT文件执行翻译和合并操作。")

    parser.add_argument("-b", "--batch-file", action="store_true", help="[下载模式] 将输入视为包含URL列表的文本文件。")
    parser.add_argument("-m", "--mode", choices=['video', 'both'], default='video', help="[下载模式] 下载模式:\n  video: 仅下载视频(默认)\n  both:  下载视频和音频")
    parser.add_argument("-p", "--proxy", type=str, default=None, help="设置HTTP/SOCKS代理。")
    parser.add_argument("--ai-subs", action="store_true", help="[下载模式] 当无官方字幕时，自动生成AI字幕。")
    args = parser.parse_args()

    # --- 新的翻译模式逻辑 ---
    if args.translate_file:
        print("模式: 独立翻译模式")
        srt_path = Path(args.translate_file)
        if not srt_path.exists() or srt_path.suffix.lower() != '.srt':
            print(f"❌ 错误: 文件不存在或不是一个 .srt 文件 -> {srt_path}")
            return
        
        # 初始化一个临时的下载文件夹和字幕处理器
        dl_folder = srt_path.parent
        sub_processor = SubtitleProcessor(dl_folder, args.proxy)
        print(f"处理文件: {srt_path.name}")
        
        zh_srt = sub_processor.translate(srt_path)
        if zh_srt:
            sub_processor.merge(srt_path, zh_srt)
        
        print("\n🎉 翻译任务完成!")
        return # 翻译完成，直接退出程序

    # --- 原有的下载模式逻辑 ---
    if args.ai_subs and not AI_LIBRARIES_AVAILABLE:
        print("❌ 错误: --ai-subs 功能需要 `deep-translator` 和 `openai-whisper` 库。"); return
        
    urls = get_urls(args)
    if not urls: print("❌ 错误: 没有有效的URL可供处理。"); return
    
    dl_folder = Path(datetime.now().strftime("%Y%m%d-%H%M%S"))
    dl_folder.mkdir(exist_ok=True)
    cookies = str(Path("cookies.txt").resolve()) if Path("cookies.txt").exists() else None
    downloader = Downloader(dl_folder, cookies, args.proxy)
    sub_processor = SubtitleProcessor(dl_folder, args.proxy) if args.ai_subs else None

    print(f"📂 所有内容将保存到: {dl_folder.resolve()}"); print(f"下载模式: {args.mode}")
    if args.proxy: print(f"代理设置: {args.proxy}")
    if args.ai_subs: print("AI字幕生成: 已启用")
    if cookies: print(f"✅ 已加载Cookies文件")

    total_items = 0
    try:
        for url in urls:
            print("\n" + "#"*60); print(f"正在处理URL: {url}"); print("#"*60)
            stream = downloader.stream_playlist_info(url)
            count, has_started = 0, False
            for i, meta in enumerate(stream, 1):
                has_started, count = True, i
                prefix = f"{i:03d}_{sanitize(meta.get('title', f'项目_{i}'))}"
                process_item(downloader, sub_processor, meta.get('url', url), prefix, args)
                print("\n⏳ 礼貌等待3秒..."); time.sleep(3)
            if not has_started:
                print("\n🤔 未能从流中解析到项目，尝试作为单个链接处理...")
                prefix = f"001_{sanitize(urls[0] if len(urls)==1 else '单项下载')}"
                process_item(downloader, sub_processor, url, prefix, args); count = 1
            total_items += count
            print(f"\n--- URL处理完成: {url} | 共处理了 {count} 个项目 ---")
    except KeyboardInterrupt: print("\n\n用户中断了操作。")
    except Exception as e: print(f"\n⚠️ 发生致命错误: {e}")
    finally:
        print("\n" + "🎉"*20); print(f"全部任务完成! 本次运行共处理 {total_items} 个项目。"); print(f"📁 所有文件保存在: {dl_folder.resolve()}")


if __name__ == "__main__":
    main()