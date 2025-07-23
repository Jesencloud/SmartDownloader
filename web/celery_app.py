# web/celery_app.py
from celery import Celery
import os

# 第一个参数是当前模块的名称，这是Celery自动发现任务所必需的。
# `broker` 指向消息代理（我们使用Redis）。
# `backend` 指向结果存储（我们也使用Redis）。
# `include` 是一个模块列表，当worker启动时会自动导入它们，以注册任务。
celery_app = Celery(
    "smartdownloader",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["web.tasks"]
)

# 优化的Celery配置
celery_app.conf.update(
    # === 任务执行配置 ===
    task_track_started=True,                    # 跟踪任务启动状态
    task_serializer='json',                     # 使用JSON序列化
    accept_content=['json'],                    # 只接受JSON内容
    result_serializer='json',                   # 结果序列化
    timezone='Asia/Shanghai',                   # 时区设置
    enable_utc=True,                           # 启用UTC
    
    # === 任务超时配置 ===
    task_soft_time_limit=600,                  # 软超时：10分钟（下载任务）
    task_time_limit=900,                       # 硬超时：15分钟
    task_acks_late=True,                       # 任务完成后再确认
    worker_prefetch_multiplier=1,               # 每次只预取1个任务
    
    # === 重试配置 ===
    task_reject_on_worker_lost=True,           # Worker丢失时拒绝任务
    task_default_retry_delay=60,               # 默认重试延迟60秒
    task_max_retries=3,                        # 最大重试3次
    
    # === 结果存储配置 ===
    result_expires=3600,                       # 结果1小时后过期
    result_backend_transport_options={         # Redis连接池优化
        'master_name': 'mymaster',
        'visibility_timeout': 3600,
        'retry_policy': {
            'timeout': 5.0
        },
        'connection_pool_kwargs': {
            'max_connections': 20,             # 最大连接数
            'retry_on_timeout': True,
        }
    },
    
    # === Worker配置 ===
    worker_concurrency=os.cpu_count() or 4,   # 基于CPU核心数设置并发
    worker_max_tasks_per_child=1000,          # 每个子进程最多处理1000个任务后重启
    worker_disable_rate_limits=False,         # 启用速率限制
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    
    # === 监控和健康检查 ===
    worker_send_task_events=True,             # 发送任务事件
    task_send_sent_event=True,                # 发送任务发送事件
    
    # === 路由配置 ===
    task_routes={
        'web.tasks.download_video_task': {
            'queue': 'download_queue',         # 下载任务使用专门队列
            'routing_key': 'download',
        },
        'web.tasks.cleanup_task': {
            'queue': 'maintenance_queue',      # 清理任务使用维护队列
            'routing_key': 'maintenance',
        }
    },
    
    # === 安全配置 ===
    broker_transport_options={
        'visibility_timeout': 3600,            # 消息可见性超时
        'fanout_prefix': True,
        'fanout_patterns': True
    },
)
