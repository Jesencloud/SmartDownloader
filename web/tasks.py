# web/tasks.py
import sys
from pathlib import Path
import asyncio

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
def download_video_task(self, video_url: str, download_type: str, format_id: str, custom_path: str = None):
    """
    一个同步的Celery任务，它在内部创建一个新的事件循环来运行异步下载逻辑。
    """
    async def _async_download():
        download_folder = Path(custom_path) if custom_path else Path(config.downloader.save_path)
        # ... [Path validation logic remains the same] ...
        
        file_prefix = self.request.id 
        downloader = Downloader(download_folder=download_folder)

        if download_type == 'video':
            output_file = await downloader.download_and_merge(video_url, file_prefix, format_id)
        elif download_type == 'audio':
            to_mp3 = False
            actual_format_id = format_id
            if format_id.startswith('mp3-conversion-'):
                to_mp3 = True
                actual_format_id = format_id.replace('mp3-conversion-', '')
            
            output_file = await downloader.download_audio_directly(video_url, file_prefix, actual_format_id, to_mp3)
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