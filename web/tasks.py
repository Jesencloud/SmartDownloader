# web/tasks.py
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import redis
from celery import Task
from celery.signals import task_failure, task_postrun, task_prerun, task_revoked

from config_manager import config, config_manager
from downloader import Downloader

from .celery_app import celery_app

# 这是一个常见的模式，以确保当Celery worker在不同环境中启动时，
# 它仍然可以找到项目根目录下的模块（如`downloader`, `core`等）。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)

# Set up logging
log = logging.getLogger(__name__)

# 创建一个模块级别的 Redis 客户端，由所有任务共享
try:
    redis_client = redis.Redis.from_url(config_manager.config.celery.broker_url, decode_responses=True)
except Exception as e:
    log.error(f"无法在模块加载时初始化Redis客户端: {e}")
    redis_client = None


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

        # 确保异常信息被正确记录到任务状态中
        try:
            # 创建安全的错误信息，避免复杂对象导致序列化问题
            error_message = str(exc) if exc else "Unknown error"
            self.update_state(
                state="FAILURE",
                meta={
                    "status": f"Task failed: {error_message}",
                    "progress": 0,
                    "error": error_message,
                    "duration": duration,
                    "timestamp": time.time(),
                },
            )
        except Exception as update_error:
            # 如果更新状态失败，只记录日志，不再抛出异常
            log.error(f"Failed to update task state on failure: {update_error}")
            log.error(f"Original task failure: {exc}")

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
                if hasattr(self.downloader, "subprocess_manager"):
                    asyncio.run(self._cleanup_subprocess_manager())
        except Exception as e:
            log.error(f"Error during resource cleanup: {e}")

    async def _cleanup_subprocess_manager(self):
        """异步清理子进程管理器"""
        try:
            if hasattr(self.downloader.subprocess_manager, "_running_processes"):
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
    log.debug(f"Starting task {task_id}: {task.name}")


@task_postrun.connect
def task_postrun_handler(task_id, task, *args, **kwargs):
    """任务完成后的处理"""
    log.debug(f"Finished task {task_id}: {task.name}")


@task_failure.connect
def task_failure_handler(task_id, exception, traceback, einfo, *args, **kwargs):
    """任务失败处理"""
    log.error(f"Task {task_id} failed with exception: {exception}")


@task_revoked.connect
def task_revoked_handler(
    sender=None,
    task_id=None,
    reason=None,
    signum=None,
    terminated=None,
    expired=None,
    **kwargs,
):
    """任务被撤销时的处理"""
    log.info(f"Task {task_id} revoked - reason: {reason}, terminated: {terminated}, signum: {signum}")

    # 强制清理相关进程
    try:
        # 查找与此任务相关的yt-dlp进程并终止
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["name"] and "yt-dlp" in proc.info["name"]:
                    log.info(f"Terminating yt-dlp process {proc.info['pid']}")
                    proc.terminate()
                    # Wait a bit for graceful termination
                    try:
                        proc.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        proc.kill()
                elif proc.info["cmdline"]:
                    cmdline = " ".join(proc.info["cmdline"])
                    if "yt-dlp" in cmdline:
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
    retry_kwargs={"max_retries": 3, "countdown": 60},
    soft_time_limit=600,  # 10分钟软限制
    time_limit=900,  # 15分钟硬限制
    acks_late=True,
    reject_on_worker_lost=True,
)
def download_video_task(
    self,
    video_url: str,
    download_type: str,
    format_id: str,
    resolution: str = "",
    title: str = "",
    custom_path: str = None,
):
    task_id = self.request.id
    try:
        if not redis_client:
            raise ConnectionError("Redis client not initialized")

        self.start_time = time.time()

        # 更新任务状态
        self.update_state(state="PROGRESS", meta={"status": "正在下载中", "progress": 0})

        async def _async_download():
            root_download_folder = Path(config_manager.config.downloader.save_path).resolve()
            if custom_path:
                # 将 custom_path 与根目录结合，并解析为绝对路径
                download_folder = (root_download_folder / custom_path).resolve()
                # 关键安全检查：确保最终路径仍在根下载目录内
                if root_download_folder not in download_folder.parents and download_folder != root_download_folder:
                    raise ValueError("非法的自定义路径")
            else:
                download_folder = root_download_folder

            # 验证下载路径
            if not download_folder.exists():
                download_folder.mkdir(parents=True, exist_ok=True)

            # 检查磁盘空间（至少需要1GB）
            free_space = psutil.disk_usage(download_folder).free
            if free_space < 1024 * 1024 * 1024:  # 1GB
                raise Exception(f"Insufficient disk space: {free_space / 1024 / 1024:.2f} MB available")

            # 定义进度回调函数
            def progress_callback(message: str, progress: int, eta_seconds: int = 0, speed: str = ""):
                """进度回调函数，更新Celery任务状态"""
                # 确保进度值在合理范围内
                progress = max(0, min(100, progress))

                meta = {"status": message, "progress": progress}

                # 如果有ETA信息，添加到meta中
                if eta_seconds > 0:
                    # 限制ETA范围，避免异常值影响前端动画
                    eta_seconds = min(max(eta_seconds, 1), 3600)  # 1秒到1小时
                    meta["eta_seconds"] = eta_seconds

                if speed:
                    meta["speed"] = speed

                # 添加时间戳用于前端去重和排序
                meta["timestamp"] = time.time()

                try:
                    self.update_state(state="PROGRESS", meta=meta)
                except Exception as update_error:
                    # 进度更新失败时只记录日志，不影响下载过程
                    log.debug(f"Failed to update progress state: {update_error}")

                # 记录详细的进度信息用于调试
                log.debug(f"进度回调: {progress}% - {message} (ETA: {eta_seconds}s, 速度: {speed})")

            # 初始化下载器，传入进度回调
            self.downloader = Downloader(download_folder=download_folder, progress_callback=progress_callback)

            if download_type == "video":
                # 视频下载 - 使用智能策略
                output_file = await self.downloader.download_with_smart_strategy(
                    video_url=video_url,
                    fallback_prefix=title or task_id,
                    format_id=format_id if format_id != "best" else None,
                    resolution=resolution,
                )

            elif download_type == "audio":
                # 音频下载逻辑
                if format_id and "conversion" in format_id:
                    audio_format = format_id.split("-")[0]
                    if audio_format not in ["mp3", "m4a", "wav"]:
                        audio_format = "mp3"
                    log.info(
                        f"音频转换任务: url={video_url}, 请求的format_id='{format_id}', 解析的audio_format='{audio_format}'"
                    )
                else:
                    audio_format = format_id
                    log.info(f"直接音频下载任务: url={video_url}, 使用原始format_id='{audio_format}'")

                output_file = await self.downloader.download_audio(
                    video_url=video_url,
                    audio_format=audio_format,
                    fallback_prefix=title or task_id,
                )
            else:
                raise ValueError(f"无效的下载类型: {download_type}")

            # 验证输出文件
            if not output_file or not output_file.exists():
                raise FileNotFoundError("下载后未找到输出文件")

            # --- 新增逻辑：注册下载凭证到 Redis ---
            download_key = f"download:{task_id}"
            file_info = {
                "file_path": str(output_file.resolve()),
                "filename": output_file.name,
                "media_type": "video/mp4" if download_type == "video" else "audio/mpeg",  # 可以做得更精确
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # 使用 pipeline 保证原子性
            pipe = redis_client.pipeline()
            pipe.hset(download_key, mapping=file_info)
            pipe.expire(download_key, config.file_management.redis_expiry_seconds)  # 使用配置的Redis过期时间
            pipe.execute()

            log.info(f"文件下载完成并注册到 Redis: {output_file.name} (凭证: {task_id})")

            # 准备完整的结果信息
            final_result = {
                "status": "Completed",
                "result": str(output_file),
                "relative_path": str(output_file.relative_to(download_folder)),
                "download_folder": str(download_folder),
                "file_size": output_file.stat().st_size,
                "duration": time.time() - self.start_time,
            }

            # 更新最终状态，将完整结果放入 meta
            try:
                self.update_state(state="SUCCESS", meta=final_result)
            except Exception as update_error:
                # 如果更新SUCCESS状态失败，只记录日志，但不改变结果
                log.error(f"Failed to update SUCCESS state, but download completed: {update_error}")

            return final_result

        # 检查是否有足够的系统资源
        memory = psutil.virtual_memory()
        if memory.percent > 90:  # 内存使用超过90%
            log.warning(f"High memory usage: {memory.percent}%")
            # 可以选择延迟任务或减少并发

        # 运行异步下载
        result = asyncio.run(_async_download())
        return result

    except (ConnectionError, TimeoutError) as e:
        log.error(f"Redis连接错误: {e}")
        raise self.retry(exc=e, countdown=10, max_retries=3)

    except Exception as e:
        # 记录详细错误信息
        log.error(f"Download task {task_id} failed: {str(e)}", exc_info=True)
        # 确保异常信息格式正确
        error_message = f"Task failed: {str(e)}"
        raise Exception(error_message)

    finally:
        # 清理资源
        self.cleanup_resources()


# 添加文件清理任务
@celery_app.task(bind=True, name="cleanup_expired_files", soft_time_limit=300, time_limit=600)
def cleanup_expired_files(self):
    """
    定期清理过期文件的任务
    - 清理Redis中已过期的下载凭证对应的文件
    - 清理孤立的文件（没有对应Redis记录的文件）
    """
    log.info("开始执行文件清理任务...")

    if not redis_client:
        log.error("Redis client not initialized, skipping cleanup.")
        return

    download_folder = Path(config_manager.config.downloader.save_path)

    cleanup_stats = {
        "expired_files_deleted": [],
        "orphaned_files_deleted": [],
        "total_size_freed_mb": 0,
        "errors": [],
    }

    try:
        if not download_folder.exists():
            log.info("下载目录不存在，跳过清理")
            return cleanup_stats

        # 1. 获取所有现存文件
        existing_files = {}
        for file_path in download_folder.iterdir():
            if file_path.is_file() and not file_path.name.startswith("."):
                existing_files[str(file_path)] = file_path

        log.info(f"发现 {len(existing_files)} 个文件需要检查")

        # 2. 获取所有Redis中的下载记录
        active_download_keys = set()
        valid_file_paths = set()

        # 扫描Redis中所有以"download:"开头的键
        for key in redis_client.scan_iter(match="download:*"):
            try:
                file_info = redis_client.hgetall(key)
                if file_info and "file_path" in file_info:
                    active_download_keys.add(key)
                    valid_file_paths.add(file_info["file_path"])
            except Exception as e:
                log.error(f"检查Redis键 {key} 时出错: {e}")
                cleanup_stats["errors"].append(f"Redis键检查错误: {key}")

        log.info(f"Redis中有 {len(active_download_keys)} 个活跃的下载记录")

        # 3. 清理孤立文件（存在于文件系统但没有Redis记录的文件）
        for file_path_str, file_path in existing_files.items():
            if file_path_str not in valid_file_paths:
                try:
                    # 检查文件是否超过1.5小时（90分钟），给一些缓冲时间
                    file_age = time.time() - file_path.stat().st_mtime
                    if file_age > config.file_management.orphan_cleanup_seconds:  # 使用配置的孤立文件清理时间
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleanup_stats["orphaned_files_deleted"].append(file_path.name)
                        cleanup_stats["total_size_freed_mb"] += file_size / (1024 * 1024)
                        log.info(f"清理孤立文件: {file_path.name} ({file_size / (1024 * 1024):.2f}MB)")
                except Exception as e:
                    cleanup_stats["errors"].append(f"删除孤立文件失败: {file_path.name} - {str(e)}")
                    log.error(f"删除孤立文件 {file_path.name} 失败: {e}")

        # 4. 清理已过期的Redis记录对应的文件
        for key in list(active_download_keys):
            try:
                # 检查键是否仍然存在（可能已被Redis自动过期）
                if not redis_client.exists(key):
                    # 键已过期，查找对应文件并删除
                    task_id = key.replace("download:", "")
                    # 尝试找到可能存在的对应文件
                    for file_path_str, file_path in existing_files.items():
                        if task_id in file_path.name or file_path.name in [
                            f.get("filename", "")
                            for f in [redis_client.hgetall(k) for k in active_download_keys if redis_client.exists(k)]
                        ]:
                            continue  # 这个文件还有有效的Redis记录

                    # 如果文件确实对应于过期的记录，删除它
                    # 这里的逻辑可能需要根据实际的文件命名规则调整
                    pass  # 暂时跳过，因为Redis自动过期已经处理了大部分情况

            except Exception as e:
                cleanup_stats["errors"].append(f"处理过期记录失败: {key} - {str(e)}")
                log.error(f"处理过期记录 {key} 失败: {e}")

        # 5. 记录清理结果
        cleanup_stats["total_size_freed_mb"] = round(cleanup_stats["total_size_freed_mb"], 2)

        log.info(
            f"文件清理完成 - 孤立文件: {len(cleanup_stats['orphaned_files_deleted'])}个, "
            f"释放空间: {cleanup_stats['total_size_freed_mb']}MB, "
            f"错误: {len(cleanup_stats['errors'])}个"
        )

        return cleanup_stats

    except Exception as e:
        log.error(f"文件清理任务失败: {e}")
        cleanup_stats["errors"].append(f"清理任务错误: {str(e)}")
        raise e


# 保留原有的清理任务
@celery_app.task(bind=True, name="cleanup_task", soft_time_limit=60, time_limit=120)
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


# 监控任务
@celery_app.task(bind=True, name="monitor_task", soft_time_limit=60, time_limit=120)
def monitor_task(self):
    """定期监控任务"""
    log.info("Starting monitor task...")

    try:
        # 监控逻辑
        # 例如，检查worker状态、队列长度等
        i = celery_app.control.inspect()
        active_tasks = i.active()
        queued_tasks = i.scheduled()

        result = {
            "active_tasks": active_tasks,
            "queued_tasks": queued_tasks,
            "timestamp": time.time(),
        }

        return result

    except Exception as e:
        log.error(f"Monitor task failed: {e}")
        raise e
