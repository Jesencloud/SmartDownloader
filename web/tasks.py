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
            file_prefix = self.request.id
            # Pass the format_id and resolution to ensure the correct video quality is downloaded
            output_file = await downloader.download_and_merge(
                video_url=video_url,
                file_prefix=file_prefix,
                format_id=format_id if format_id != 'best' else None,
                resolution=resolution  # Pass the resolution to the downloader
            )
        elif download_type == 'audio':
            audio_format = format_id if format_id else 'mp3'
            output_file = await downloader.download_audio(
                video_url=video_url,
                audio_format=audio_format
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