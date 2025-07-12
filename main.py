#!/usr/bin/env python3
"""
SmartDownloader主程序
智能媒体下载与AI字幕工具的主入口点
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from rich.console import Console

from config_manager import config_manager, config
from downloader import Downloader
from subtitles import SubtitleProcessor
from utils import setup_logging, get_inputs, sanitize
from handlers import process_local_file, process_metadata_phase, process_download_phase


console = Console()
log = logging.getLogger(__name__)


def get_cookies_configuration() -> tuple[str, str, str, bool, bool]:
    """获取cookies配置信息。
    
    Returns:
        tuple: (cookies_mode, browser_type, manual_cookies_file, auto_extract_enabled, force_refresh)
    """
    cookies_config = config.cookies
    return (
        cookies_config.mode,
        cookies_config.browser_type,
        cookies_config.manual_cookies_file,
        cookies_config.auto_extract_enabled,
        cookies_config.force_refresh
    )


def handle_manual_cookies(manual_cookies_file: str) -> Optional[str]:
    """处理手动cookies文件。
    
    Args:
        manual_cookies_file (str): 手动cookies文件路径。
        
    Returns:
        Optional[str]: cookies文件路径，如果找到则返回路径，否则返回None。
    """
    manual_cookies_path = Path(manual_cookies_file)
    if manual_cookies_path.exists():
        cookies = str(manual_cookies_path.resolve())
        console.print(f'🍪 使用手动cookies文件: {cookies}', style='green')
        return cookies
    else:
        console.print(f'⚠️ 未找到手动cookies文件: {manual_cookies_file}', style='yellow')
        return None


def try_auto_extract_cookies(first_url: str, browser_type: str, cookies_config) -> Optional[str]:
    """尝试自动提取cookies。
    
    Args:
        first_url (str): 第一个URL。
        browser_type (str): 浏览器类型。
        cookies_config: cookies配置对象。
        
    Returns:
        Optional[str]: cookies文件路径，如果成功则返回路径，否则返回None。
    """
    try:
        from auto_cookies import auto_extract_cookies_for_url
        
        console.print(f'🍪 正在为 {first_url} 从{browser_type}浏览器自动提取cookies...', style='cyan')
        auto_cookies_file = auto_extract_cookies_for_url(
            first_url,
            browser_type,
            cache_enabled=cookies_config.cache_enabled,
            cache_file=cookies_config.cache_file,
            cache_duration_hours=cookies_config.cache_duration_hours
        )
        
        if auto_cookies_file and Path(auto_cookies_file).exists():
            cookies = str(Path(auto_cookies_file).resolve())
            console.print(f'✅ 成功自动获取cookies: {cookies}', style='bold green')
            return cookies
        else:
            console.print(f'⚠️ 无法自动获取cookies，将在无cookies情况下继续', style='yellow')
            return None
    except ImportError as e:
        console.print(f'⚠️ 自动cookies模块不可用，请手动放置cookies.txt文件: {e}', style='yellow')
        return None
    except Exception as e:
        console.print(f'⚠️ 自动获取cookies时发生未知错误: {e}', style='yellow')
        return None


def handle_browser_mode_cookies(inputs: List[str], browser_type: str, cookies_config, force_refresh: bool) -> Optional[str]:
    """处理浏览器模式cookies。
    
    Args:
        inputs (List[str]): 输入URL列表。
        browser_type (str): 浏览器类型。
        cookies_config: cookies配置对象。
        force_refresh (bool): 是否强制刷新。
        
    Returns:
        Optional[str]: cookies文件路径，如果成功则返回路径，否则返回None。
    """
    if not cookies_config.auto_extract_enabled:
        console.print(f'⚠️ 自动cookies提取已禁用', style='yellow')
        return None
    
    if cookies_config.mode == 'browser':
        console.print(f'🔍 配置设置强制从浏览器获取cookies...', style='cyan')
    elif force_refresh:
        console.print(f'🔄 配置设置强制刷新cookies...', style='cyan')
    
    if inputs:
        first_url = inputs[0]
        return try_auto_extract_cookies(first_url, browser_type, cookies_config)
    
    return None


def handle_cache_cookies(cookies_config, inputs: List[str], browser_type: str) -> Optional[str]:
    """处理缓存cookies。
    
    Args:
        cookies_config: cookies配置对象。
        inputs (List[str]): 输入URL列表。
        browser_type (str): 浏览器类型。
        
    Returns:
        Optional[str]: cookies文件路径，如果成功则返回路径，否则返回None。
    """
    cache_cookies_path = Path(cookies_config.cache_file)
    
    if not (cookies_config.cache_enabled and cache_cookies_path.exists()):
        return None
    
    try:
        from auto_cookies import BrowserCookiesExtractor
        extractor = BrowserCookiesExtractor(
            cache_enabled=cookies_config.cache_enabled,
            cache_file=cookies_config.cache_file,
            cache_duration_hours=cookies_config.cache_duration_hours
        )
        
        if extractor._is_cache_valid():
            cookies = str(cache_cookies_path.resolve())
            console.print(f'🍪 使用有效的cookies缓存: {cookies}', style='green')
            return cookies
        else:
            console.print(f'⚠️ cookies缓存已过期，尝试自动获取新cookies...', style='yellow')
            if cookies_config.auto_extract_enabled and inputs:
                first_url = inputs[0]
                return try_auto_extract_cookies(first_url, browser_type, cookies_config)
            return None
    except ImportError as e:
        console.print(f'⚠️ 自动cookies模块不可用，使用现有缓存文件: {e}', style='yellow')
        return str(cache_cookies_path.resolve())
    except Exception as e:
        console.print(f'⚠️ 检查cookies缓存时发生未知错误: {e}', style='yellow')
        return None


def handle_auto_mode_cookies(inputs: List[str], browser_type: str, cookies_config) -> Optional[str]:
    """处理自动模式cookies。
    
    Args:
        inputs (List[str]): 输入URL列表。
        browser_type (str): 浏览器类型。
        cookies_config: cookies配置对象。
        
    Returns:
        Optional[str]: cookies文件路径，如果成功则返回路径，否则返回None。
    """
    manual_cookies_path = Path(cookies_config.manual_cookies_file)
    
    # 优先级：手动cookies > 缓存cookies > 自动获取cookies
    if manual_cookies_path.exists():
        cookies = str(manual_cookies_path.resolve())
        console.print(f'🍪 使用手动cookies文件: {cookies}', style='green')
        return cookies
    
    # 检查缓存cookies
    cached_cookies = handle_cache_cookies(cookies_config, inputs, browser_type)
    if cached_cookies:
        return cached_cookies
    
    # 没有手动cookies和缓存，尝试自动获取
    if cookies_config.auto_extract_enabled:
        console.print(f'🔍 未找到手动cookies文件和缓存，尝试自动获取浏览器cookies...', style='yellow')
        if inputs:
            first_url = inputs[0]
            return try_auto_extract_cookies(first_url, browser_type, cookies_config)
    else:
        console.print(f'⚠️ 未找到cookies文件且自动获取已禁用', style='yellow')
    
    return None


def get_cookies(inputs: List[str]) -> Optional[str]:
    """获取cookies文件路径。
    
    Args:
        inputs (List[str]): 输入URL列表。
        
    Returns:
        Optional[str]: cookies文件路径，如果成功则返回路径，否则返回None。
    """
    cookies_mode, browser_type, manual_cookies_file, auto_extract_enabled, force_refresh = get_cookies_configuration()
    cookies_config = config.cookies
    
    if cookies_mode == 'skip':
        console.print(f'🚫 跳过cookies（配置设置）', style='yellow')
        return None
    
    if cookies_mode == 'manual':
        return handle_manual_cookies(manual_cookies_file)
    elif cookies_mode == 'browser' or force_refresh:
        return handle_browser_mode_cookies(inputs, browser_type, cookies_config, force_refresh)
    else:
        # auto模式
        return handle_auto_mode_cookies(inputs, browser_type, cookies_config)


def process_x_com_urls(current_url_tasks: List[tuple], video_count: int, url: str) -> List[tuple]:
    """处理X.com多视频链接情况。
    
    Args:
        current_url_tasks (List[tuple]): 当前URL任务列表。
        video_count (int): 视频数量。
        url (str): 当前URL。
        
    Returns:
        List[tuple]: 处理后的任务列表。
    """
    if video_count > 1 and ('x.com' in url or 'twitter.com' in url):
        console.print(f'⚠️  不支持一个链接🔗里包含多个视频下载哦～', style='bold red')
        console.print(f'🔗 当前链接包含 {video_count} 个视频，仅支持单视频链接', style='yellow')
        console.print(f'💡 建议：请分别获取每个视频的单独链接进行下载', style='cyan')
        console.print(f'📥 将仅下载第一个视频...', style='bold yellow')
        
        if current_url_tasks:
            return [current_url_tasks[0]]  # 只返回第一个视频
    
    return current_url_tasks


async def collect_task_metadata(downloader: Downloader, inputs: List[str]) -> List[tuple]:
    """收集所有任务的元数据。
    
    Args:
        downloader (Downloader): 下载器实例。
        inputs (List[str]): 输入URL列表。
        
    Returns:
        List[tuple]: 任务元数据列表。
    """
    task_metadata = []
    i = 0
    
    for url in inputs:
        video_count = 0
        current_url_tasks = []
        
        async for meta in downloader.stream_playlist_info(url):
            video_count += 1
            i += 1
            
            # 为避免多视频同名冲突，添加唯一标识符
            title = meta.get('title', f'项目_{i}')
            video_id = meta.get('id', f'video_{i}')
            
            # 如果有视频ID，将其添加到文件名中以确保唯一性
            if video_id and video_id != f'video_{i}':
                # 截取视频ID的最后8位作为唯一标识
                unique_id = str(video_id)[-8:]
                prefix = f"{i:03d}_{sanitize(title)}_{unique_id}"
            else:
                prefix = f"{i:03d}_{sanitize(title)}"
            
            current_url_tasks.append((url, prefix, meta))
        
        # 处理X.com多视频链接情况
        processed_tasks = process_x_com_urls(current_url_tasks, video_count, url)
        task_metadata.extend(processed_tasks)
        
        if video_count == 0:  # Handle single video URL
            i += 1
            prefix = f"001_{sanitize('单项下载')}"
            task_metadata.append((url, prefix, {'url': url}))
    
    return task_metadata


async def process_subtitle_tasks(sub_processor: SubtitleProcessor, inputs: List[str]) -> None:
    """处理字幕任务。
    
    Args:
        sub_processor (SubtitleProcessor): 字幕处理器实例。
        inputs (List[str]): 输入文件路径列表。
    """
    console.print(f'🧠 AI字幕生成模式启动，将并发处理 {len(inputs)} 个文件', style='bold cyan')
    
    tasks = []
    for file_path in inputs:
        if sub_processor is not None:
            tasks.append(process_local_file(sub_processor, file_path))
        else:
            log.error('Subtitle processor is not initialized, cannot process local file for subtitles.')
    
    if tasks:
        await asyncio.gather(*tasks)


async def process_download_tasks(downloader: Downloader, sub_processor: Optional[SubtitleProcessor], inputs: List[str], args: argparse.Namespace) -> None:
    """处理下载任务。
    
    Args:
        downloader (Downloader): 下载器实例。
        sub_processor (Optional[SubtitleProcessor]): 字幕处理器实例。
        inputs (List[str]): 输入URL列表。
        args (argparse.Namespace): 命令行参数。
    """
    console.print(f'🚀 下载模式启动，将并发处理 {len(inputs)} 个URL/播放列表', style='bold cyan')
    
    # 收集所有任务的元数据
    task_metadata = await collect_task_metadata(downloader, inputs)
    
    # 阶段1：并发处理所有元数据
    metadata_tasks = []
    for url, prefix, meta in task_metadata:
        metadata_tasks.append(process_metadata_phase(downloader, meta.get('url', url), prefix))
    
    await asyncio.gather(*metadata_tasks)
    
    # 阶段2：顺序处理所有下载任务
    for url, prefix, meta in task_metadata:
        await process_download_phase(downloader, sub_processor, meta.get('url', url), prefix, args)


async def main() -> None:
    """SmartDownloader主程序入口点。
    
    处理命令行参数，初始化下载器和字幕处理器，
    根据指定模式执行下载或字幕生成任务。
    
    Raises:
        KeyboardInterrupt: 用户中断操作时进行清理。
        Exception: 处理过程中发生的其他错误。
    """
    script_path = Path(__file__).parent
    dl_folder = config_manager.get_download_folder(script_path)
    setup_logging(dl_folder)

    log.info("🚀 智能媒体下载与AI字幕工具 v4.0 (Async) 启动 🚀")
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="智能媒体下载与处理工具")
    parser.add_argument('inputs', nargs='+', help='URL或文件路径')
    parser.add_argument('-b', '--batch-file', action='store_true', help='批量处理文件中的URL')
    parser.add_argument('-m', '--mode', choices=['video', 'both', 'audio', 'subtitle'], default='video')
    parser.add_argument('-p', '--proxy', type=str, default=None)
    parser.add_argument('--ai-subs', action='store_true', help='自动生成AI字幕')
    args = parser.parse_args()

    # 获取输入
    inputs = get_inputs(args)
    if not inputs:
        log.error('没有有效的输入可供处理。')
        return

    # 获取cookies
    cookies = get_cookies(inputs)
    
    # 初始化下载器和字幕处理器
    downloader = Downloader(dl_folder, cookies, args.proxy)
    sub_processor = SubtitleProcessor(dl_folder, args.proxy) if (args.ai_subs or args.mode == 'subtitle') else None

    # 根据模式处理任务
    if args.mode == 'subtitle':
        await process_subtitle_tasks(sub_processor, inputs)
    else:
        await process_download_tasks(downloader, sub_processor, inputs, args)

    try:
        # 处理模式的错误处理已经在各个阶段内部处理
        pass
    except KeyboardInterrupt:
        log.warning('用户中断操作，正在清理...')
        try:
            await downloader.cleanup_all_incomplete_files()
        except Exception as cleanup_error:
            log.error(f'清理过程中发生错误: {cleanup_error}')
        console.print('✅ 清理完成，安全退出', style='bold green')
    except Exception as e:
        log.critical(f"发生致命错误: {e}", exc_info=True)
    finally:
        log.info("🎉 全部任务完成!")
        log.info(f"📁 日志与所有文件保存在: {dl_folder.resolve()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print('\n\n🚫 操作被用户强制取消。', style='bold red')
    except Exception as e:
        console.print(f'\n\n❌ 程序执行时发生致命错误: {e}', style='bold red')
        logging.getLogger(__name__).critical(f'未处理的异常: {e}', exc_info=True)