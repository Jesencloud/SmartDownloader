# web/tasks.py
import sys
import logging
import json
from pathlib import Path
import asyncio
import os

# Set up logging
log = logging.getLogger(__name__)

# 这是一个常见的模式，以确保当Celery worker在不同环境中启动时，
# 它仍然可以找到项目根目录下的模块（如`downloader`, `core`等）。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)

from downloader import Downloader
from config_manager import config
from .celery_app import celery_app

# 将任务改回一个普通的同步函数
@celery_app.task(bind=True, name="create_download_task")
def download_video_task(self, video_url: str, download_type: str, format_id: str, resolution: str = '', custom_path: str = None):
    """
    一个同步的Celery任务，它在内部创建一个新的事件循环来运行异步下载逻辑。
    
    Args:
        video_url: 要下载的视频URL
        download_type: 下载类型 ('video' 或 'audio')
        format_id: 视频格式ID
        resolution: 视频分辨率 (例如: '1080p60')
        custom_path: 自定义下载路径 (可选)
    """
    async def _async_download():
        download_folder = Path(custom_path) if custom_path else Path(config.downloader.save_path)
        # ... [Path validation logic remains the same] ...
        
        downloader = Downloader(download_folder=download_folder)

        if download_type == 'video':
            # Pass the format_id and resolution to ensure the correct video quality is downloaded
            output_file = await downloader.download_and_merge(
                video_url=video_url,
                # 文件名将由downloader根据视频标题自动生成
                # 任务ID作为获取标题失败时的备用名称
                fallback_prefix=self.request.id,
                format_id=format_id if format_id != 'best' else None,
                resolution=resolution  # Pass the resolution to the downloader
            )
        elif download_type == 'audio':
            # If the format_id contains 'conversion', it's a request to convert to a specific format.
            # Otherwise, it's a request to download the specified original audio stream.
            if format_id and 'conversion' in format_id:
                # Extract the target format from the id, e.g., "mp3-conversion-..." -> "mp3"
                audio_format = format_id.split('-')[0]
                # Ensure it's a valid conversion format, default to mp3 otherwise.
                if audio_format not in ['mp3', 'm4a', 'wav']:
                    audio_format = 'mp3'
                log.info(f"音频转换任务: url={video_url}, 请求的format_id='{format_id}', 解析的audio_format='{audio_format}'")
            else:
                # It's a direct download of a specific audio format ID.
                audio_format = format_id
                log.info(f"直接音频下载任务: url={video_url}, 使用原始format_id='{audio_format}'")

            output_file = await downloader.download_audio(
                video_url=video_url,
                audio_format=audio_format,
                # 将任务ID作为获取标题失败时的备用名称
                fallback_prefix=self.request.id
            )
        else:
            raise ValueError(f"无效的下载类型: {download_type}")

        if output_file:
            return {
                "status": "Completed", 
                "result": str(output_file),
                "relative_path": str(output_file.relative_to(download_folder)),
                "download_folder": str(download_folder)
            }
        else:
            raise FileNotFoundError("下载后未找到输出文件。")

    try:
        return asyncio.run(_async_download())
    except Exception as e:
        clean_exception = type(e)(f"Task failed: {e}")
        raise clean_exception
