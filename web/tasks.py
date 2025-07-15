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
def download_video_task(self, video_url: str, download_type: str, custom_path: str = None):
    """
    一个同步的Celery任务，它在内部创建一个新的事件循环来运行异步下载逻辑。
    这是在Celery中运行asyncio代码最可靠的方法。
    """
    # 1. 定义一个包含所有异步逻辑的内部函数
    async def _async_download():
        # 确定下载文件夹
        if custom_path:
            download_folder = Path(custom_path)
            # 检查自定义路径是否存在且可写
            if not download_folder.exists():
                raise FileNotFoundError(f"自定义路径不存在: {custom_path}")
            if not download_folder.is_dir():
                raise NotADirectoryError(f"自定义路径不是目录: {custom_path}")
            # 检查写入权限
            try:
                test_file = download_folder / f".test_{self.request.id}"
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                raise PermissionError(f"对自定义路径没有写入权限: {custom_path}")
        else:
            download_folder = Path(config.downloader.save_path)
        
        # 使用唯一的任务ID作为文件前缀，以避免文件名冲突。
        file_prefix = self.request.id 
        
        downloader = Downloader(download_folder=download_folder)

        if download_type == 'video':
            output_file = await downloader.download_and_merge(video_url, file_prefix)
        elif download_type == 'audio':
            output_file = await downloader.download_audio_directly(video_url, file_prefix)
        else:
            raise ValueError(f"无效的下载类型: {download_type}")

        if output_file:
            # 返回文件的完整路径信息
            return {
                "status": "Completed", 
                "result": str(output_file),
                "relative_path": str(output_file.relative_to(download_folder)),
                "download_folder": str(download_folder)
            }
        else:
            # 这种情况通常由下载器中的异常处理，但作为备用。
            raise FileNotFoundError("下载后未找到输出文件。")

    # 2. 在一个全新的、干净的事件循环中运行异步函数
    try:
        # asyncio.run() 会自动处理事件循环的创建和销毁，
        # 并返回异步函数的最终结果。
        return asyncio.run(_async_download())
    except Exception as e:
        # 3. 如果异步代码中发生任何异常，捕获它。
        # 创建一个新的、干净的异常，只包含原始异常的类型和消息，
        # 然后重新抛出。这可以确保Celery得到一个可以安全序列化的异常。
        clean_exception = type(e)(f"Task failed: {e}")
        raise clean_exception