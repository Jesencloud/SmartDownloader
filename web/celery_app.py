# web/celery_app.py
from celery import Celery
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# 从环境变量中获取Redis URL，并为本地开发提供默认值
broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
backend_url = os.environ.get("CELERY_RESULT_BACKEND_URL", "redis://localhost:6379/0")

# 检测是否在CI环境中
is_ci_environment = os.environ.get("GITHUB_ACTIONS") == "true"

# 检测是否禁用Redis重连（用于开发调试）
disable_redis_retry = (
    os.environ.get("CELERY_DISABLE_REDIS_RETRY", "false").lower() == "true"
)

# 第一个参数是当前模块的名称，这是Celery自动发现任务所必需的。
# `broker` 指向消息代理（我们使用Redis）。
# `backend` 指向结果存储（我们也使用Redis）。
# `include` 是一个模块列表，当worker启动时会自动导入它们，以注册任务。
celery_app = Celery(
    "smartdownloader", broker=broker_url, backend=backend_url, include=["web.tasks"]
)

# 为CI环境使用简化配置
if is_ci_environment:
    celery_app.conf.update(
        # === 基础配置 ===
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        # === 简化的超时配置 ===
        task_soft_time_limit=120,  # CI环境2分钟软超时
        task_time_limit=180,  # CI环境3分钟硬超时
        # === 简化的队列配置 ===
        task_default_queue="celery",
        task_default_routing_key="default",
        # === 关闭一些CI中不需要的功能 ===
        worker_send_task_events=False,
        task_send_sent_event=False,
        worker_prefetch_multiplier=1,
    )
else:
    # 生产环境的完整配置
    celery_app.conf.update(
        # === 任务执行配置 ===
        task_track_started=True,  # 跟踪任务启动状态
        task_serializer="json",  # 使用JSON序列化
        accept_content=["json"],  # 只接受JSON内容
        result_serializer="json",  # 结果序列化
        timezone="Asia/Shanghai",  # 时区设置
        enable_utc=True,  # 启用UTC
        # === 任务超时配置 ===
        task_soft_time_limit=600,  # 软超时：10分钟（下载任务）
        task_time_limit=900,  # 硬超时：15分钟
        task_acks_late=True,  # 任务完成后再确认
        worker_prefetch_multiplier=1,  # 每次只预取1个任务
        # === 重试配置 ===
        task_reject_on_worker_lost=True,  # Worker丢失时拒绝任务
        task_default_retry_delay=60,  # 默认重试延迟60秒
        task_max_retries=3,  # 最大重试3次
        # === 结果存储配置 ===
        result_expires=3600,  # 结果1小时后过期
        result_backend_transport_options={  # Redis连接池优化
            "connection_pool_kwargs": {
                "max_connections": 20,  # 最大连接数
                "retry_on_timeout": True,
                "socket_keepalive": True,  # 启用socket keepalive
                "socket_keepalive_options": {},
            }
        },
        # === Broker连接配置（Redis） ===
        broker_connection_retry_on_startup=not disable_redis_retry,  # 可选择禁用启动重试
        broker_connection_retry=not disable_redis_retry,  # 可选择禁用连接重试
        broker_connection_max_retries=3 if not disable_redis_retry else 0,  # 可禁用重试
        broker_heartbeat=60,  # 增加心跳间隔到60秒
        broker_transport_options={
            "visibility_timeout": 3600,  # 消息可见性超时
            "fanout_prefix": True,
            "fanout_patterns": True,
            # Redis连接池配置
            "connection_pool_kwargs": {
                "max_connections": 10,  # 减少最大连接数
                "retry_on_timeout": not disable_redis_retry,
                "socket_keepalive": True,
                "socket_keepalive_options": {},
                "socket_connect_timeout": 3,  # 进一步减少连接超时到3秒
                "socket_timeout": 3,  # 进一步减少socket超时到3秒
            },
            # 连接重试配置
            "retry_policy": {
                "timeout": 3.0,  # 减少重试超时到3秒
                "interval_start": 10.0,  # 增加重试起始间隔到10秒
                "interval_step": 5.0,  # 每次重试增加5秒
                "interval_max": 60.0,  # 最大重试间隔60秒
            }
            if not disable_redis_retry
            else {},
        },
        # === Worker配置 ===
        worker_concurrency=os.cpu_count() or 4,  # 基于CPU核心数设置并发
        worker_max_tasks_per_child=1000,  # 每个子进程最多处理1000个任务后重启
        worker_disable_rate_limits=False,  # 启用速率限制
        worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
        worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
        # 优雅关闭配置
        worker_proc_alive_timeout=60,  # worker进程存活检查超时
        worker_max_memory_per_child=500000,  # 每个子进程最大内存限制(KB)
        # === 监控和健康检查 ===
        worker_send_task_events=True,  # 发送任务事件
        task_send_sent_event=True,  # 发送任务发送事件
        # === 路由配置 ===
        task_routes={
            "web.tasks.download_video_task": {
                "queue": "download_queue",  # 下载任务使用专门队列
                "routing_key": "download",
            },
            "web.tasks.cleanup_task": {
                "queue": "maintenance_queue",  # 清理任务使用维护队列
                "routing_key": "maintenance",
            },
        },
        # === 默认队列配置 ===
        task_default_queue="celery",  # 默认队列
        task_default_routing_key="default",
    )


# === Redis连接健康检查 ===
def check_redis_connection():
    """检查Redis连接是否可用"""
    try:
        import redis

        # 解析Redis URL
        if broker_url.startswith("redis://"):
            redis_client = redis.from_url(
                broker_url, socket_connect_timeout=5, socket_timeout=5
            )
            redis_client.ping()
            return True
    except Exception as e:
        log.warning(f"Redis连接检查失败: {e}")
        return False


# === Worker信号处理 ===
from celery.signals import worker_ready, worker_shutdown, worker_process_init


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Worker启动时的处理"""
    log.info("Celery worker已启动并准备接收任务")
    if not check_redis_connection():
        log.warning("Redis连接不可用，worker可能无法正常工作")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Worker关闭时的处理"""
    log.info("Celery worker正在关闭...")


@worker_process_init.connect
def worker_process_init_handler(sender=None, **kwargs):
    """Worker进程初始化时的处理"""
    log.debug("Worker进程已初始化")
