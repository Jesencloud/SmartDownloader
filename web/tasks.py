# web/tasks.py
import sys
import logging
from pathlib import Path
import asyncio
import psutil
from celery import Task
from celery.signals import task_prerun, task_postrun, task_failure, task_revoked
import time

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

class BaseDownloadTask(Task):
    """基础下载任务类，提供通用功能"""
    
    def __init__(self):
        self.downloader = None
        self.start_time = None
        self.memory_usage = None
    
    def on_success(self, retval, task_id, args, kwargs):
        """任务成功回调"""
        duration = time.time() - self.start_time if self.start_time else 0
        log.info(f"Task {task_id} completed successfully in {duration:.2f}s")
        
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """任务失败回调"""
        duration = time.time() - self.start_time if self.start_time else 0
        log.error(f"Task {task_id} failed after {duration:.2f}s: {exc}")
        
        # 清理资源
        self.cleanup_resources()
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """任务重试回调"""
        log.warning(f"Task {task_id} retrying due to: {exc}")
        self.cleanup_resources()
    
    def cleanup_resources(self):
        """清理任务资源"""
        try:
            if self.downloader:
                # 清理下载器资源，包括终止子进程
                if hasattr(self.downloader, 'subprocess_manager'):
                    asyncio.run(self._cleanup_subprocess_manager())
        except Exception as e:
            log.error(f"Error during resource cleanup: {e}")
    
    async def _cleanup_subprocess_manager(self):
        """异步清理子进程管理器"""
        try:
            if hasattr(self.downloader.subprocess_manager, '_running_processes'):
                processes = self.downloader.subprocess_manager._running_processes.copy()
                for process in processes:
                    if process and process.returncode is None:
                        log.info(f"Terminating subprocess {process.pid}")
                        await self._force_terminate_process(process)
        except Exception as e:
            log.error(f"Error cleaning up subprocess manager: {e}")
    
    async def _force_terminate_process(self, process):
        """强制终止进程及其子进程"""
        try:
            import psutil
            
            # First try graceful termination
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                # Force kill if graceful termination fails
                process.kill()
                await process.wait()
                
            # Also kill any child processes using psutil
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                # Wait for children to terminate
                psutil.wait_procs(children, timeout=2)
                # Force kill any remaining children
                for child in children:
                    if child.is_running():
                        child.kill()
            except psutil.NoSuchProcess:
                pass  # Process already terminated
            except Exception as e:
                log.warning(f"Failed to clean up child processes: {e}")
                
        except Exception as e:
            log.error(f"Error force terminating process: {e}")

# 任务信号处理
@task_prerun.connect
def task_prerun_handler(task_id, task, *args, **kwargs):
    """任务开始前的处理"""
    log.info(f"Starting task {task_id}: {task.name}")
    
    # 记录系统资源使用情况
    process = psutil.Process()
    memory_info = process.memory_info()
    log.info(f"Memory usage before task: {memory_info.rss / 1024 / 1024:.2f} MB")

@task_postrun.connect
def task_postrun_handler(task_id, task, *args, **kwargs):
    """任务完成后的处理"""
    log.info(f"Finished task {task_id}: {task.name}")
    
    # 记录系统资源使用情况
    process = psutil.Process()
    memory_info = process.memory_info()
    log.info(f"Memory usage after task: {memory_info.rss / 1024 / 1024:.2f} MB")

@task_failure.connect
def task_failure_handler(task_id, exception, traceback, einfo, *args, **kwargs):
    """任务失败处理"""
    log.error(f"Task {task_id} failed with exception: {exception}")

@task_revoked.connect
def task_revoked_handler(sender=None, task_id=None, reason=None, signum=None, terminated=None, expired=None, **kwargs):
    """任务被撤销时的处理"""
    log.info(f"Task {task_id} revoked - reason: {reason}, terminated: {terminated}, signum: {signum}")
    
    # 强制清理相关进程
    try:
        # 查找与此任务相关的yt-dlp进程并终止
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'yt-dlp' in proc.info['name']:
                    log.info(f"Terminating yt-dlp process {proc.info['pid']}")
                    proc.terminate()
                    # Wait a bit for graceful termination
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                elif proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'yt-dlp' in cmdline:
                        log.info(f"Terminating yt-dlp process {proc.info['pid']} via cmdline")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        log.warning(f"Error during revoked task cleanup: {e}")

# 优化的下载任务
@celery_app.task(
    bind=True, 
    name="download_video_task",
    base=BaseDownloadTask,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    soft_time_limit=600,  # 10分钟软限制
    time_limit=900,       # 15分钟硬限制
    acks_late=True,
    reject_on_worker_lost=True
)
def download_video_task(self, video_url: str, download_type: str, format_id: str, resolution: str = '', custom_path: str = None):
    """
    优化的异步Celery下载任务
    
    Args:
        video_url: 要下载的视频URL
        download_type: 下载类型 ('video' 或 'audio')
        format_id: 视频格式ID
        resolution: 视频分辨率 (例如: '1080p60')
        custom_path: 自定义下载路径 (可选)
    """
    self.start_time = time.time()
    task_id = self.request.id
    
    # 更新任务状态
    self.update_state(
        state='PROGRESS',
        meta={'status': 'Initializing download...', 'progress': 0}
    )
    
    async def _async_download():
        try:
            download_folder = Path(custom_path) if custom_path else Path(config.downloader.save_path)
            
            # 验证下载路径
            if not download_folder.exists():
                download_folder.mkdir(parents=True, exist_ok=True)
            
            # 检查磁盘空间（至少需要1GB）
            free_space = psutil.disk_usage(download_folder).free
            if free_space < 1024 * 1024 * 1024:  # 1GB
                raise Exception(f"Insufficient disk space: {free_space / 1024 / 1024:.2f} MB available")
            
            # 初始化下载器
            self.downloader = Downloader(download_folder=download_folder)
            
            # 更新进度
            self.update_state(
                state='PROGRESS',
                meta={'status': 'Starting download...', 'progress': 10}
            )

            if download_type == 'video':
                # 视频下载
                output_file = await self.downloader.download_and_merge(
                    video_url=video_url,
                    fallback_prefix=task_id,
                    format_id=format_id if format_id != 'best' else None,
                    resolution=resolution
                )
                
            elif download_type == 'audio':
                # 音频下载逻辑
                if format_id and 'conversion' in format_id:
                    audio_format = format_id.split('-')[0]
                    if audio_format not in ['mp3', 'm4a', 'wav']:
                        audio_format = 'mp3'
                    log.info(f"音频转换任务: url={video_url}, 请求的format_id='{format_id}', 解析的audio_format='{audio_format}'")
                else:
                    audio_format = format_id
                    log.info(f"直接音频下载任务: url={video_url}, 使用原始format_id='{audio_format}'")

                output_file = await self.downloader.download_audio(
                    video_url=video_url,
                    audio_format=audio_format,
                    fallback_prefix=task_id
                )
            else:
                raise ValueError(f"无效的下载类型: {download_type}")

            # 验证输出文件
            if not output_file or not output_file.exists():
                raise FileNotFoundError("下载后未找到输出文件")
            
            # 准备完整的结果信息
            final_result = {
                "status": "Completed", 
                "result": str(output_file),
                "relative_path": str(output_file.relative_to(download_folder)),
                "download_folder": str(download_folder),
                "file_size": output_file.stat().st_size,
                "duration": time.time() - self.start_time
            }
            
            # 更新最终状态，将完整结果放入 meta
            self.update_state(
                state='SUCCESS',
                meta=final_result
            )

            return final_result

        except Exception as e:
            # 更新失败状态
            self.update_state(
                state='FAILURE',
                meta={'status': f'Download failed: {str(e)}', 'progress': 0}
            )
            raise e

    try:
        # 检查是否有足够的系统资源
        memory = psutil.virtual_memory()
        if memory.percent > 90:  # 内存使用超过90%
            log.warning(f"High memory usage: {memory.percent}%")
            # 可以选择延迟任务或减少并发
            
        # 运行异步下载
        return asyncio.run(_async_download())
        
    except Exception as e:
        # 记录详细错误信息
        log.error(f"Download task {task_id} failed: {str(e)}", exc_info=True)
        
        # 检查是否需要重试
        if isinstance(e, (ConnectionError, TimeoutError)):
            log.info(f"Retrying task {task_id} due to network error")
            raise self.retry(countdown=60, max_retries=3, exc=e)
        
        # 创建清理的异常信息
        clean_exception = type(e)(f"Task failed: {str(e)}")
        raise clean_exception
    
    finally:
        # 清理资源
        self.cleanup_resources()

# 添加清理任务
@celery_app.task(
    bind=True,
    name="cleanup_task",
    soft_time_limit=60,
    time_limit=120
)
def cleanup_task(self):
    """定期清理任务"""
    log.info("Starting cleanup task...")
    
    try:
        # 清理过期的结果
        # 这里可以添加清理逻辑
        
        return {"status": "Cleanup completed", "timestamp": time.time()}
        
    except Exception as e:
        log.error(f"Cleanup task failed: {e}")
        raise e
