# web/celery_app.py
from celery import Celery

# 第一个参数是当前模块的名称，这是Celery自动发现任务所必需的。
# `broker` 指向消息代理（我们使用Redis）。
# `backend` 指向结果存储（我们也使用Redis）。
# `include` 是一个模块列表，当worker启动时会自动导入它们，以注册任务。
celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["web.tasks"]
)

# 可选配置，让任务在启动时就更新其状态
celery_app.conf.update(
    task_track_started=True,
)
