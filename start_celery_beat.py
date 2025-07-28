#!/usr/bin/env python3
"""
启动 Celery Beat 定时任务调度器

这个脚本用于启动 Celery Beat，它会按照配置定期执行文件清理任务。
需要与 Celery Worker 一起运行。

使用方法:
    python start_celery_beat.py

或者在后台运行:
    python start_celery_beat.py &
"""

import sys
import os
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s: %(levelname)s/%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(project_root / "celery_beat.log"),
    ],
)

log = logging.getLogger(__name__)


def main():
    """启动 Celery Beat 调度器"""
    try:
        # 导入 Celery 应用
        from web.celery_app import celery_app

        log.info("启动 Celery Beat 定时任务调度器...")
        log.info("定时任务配置:")

        # 显示调度器配置
        beat_schedule = celery_app.conf.beat_schedule
        if beat_schedule:
            for task_name, task_config in beat_schedule.items():
                schedule = task_config.get("schedule", "Unknown")
                task = task_config.get("task", "Unknown")
                if isinstance(schedule, (int, float)):
                    schedule_str = f"每 {int(schedule / 60)} 分钟"
                else:
                    schedule_str = str(schedule)
                log.info(f"  - {task_name}: {task} ({schedule_str})")
        else:
            log.warning("没有找到定时任务配置")

        # 设置环境变量
        os.environ.setdefault("FORKED_BY_MULTIPROCESSING", "1")

        # 启动 Beat
        from celery.bin import beat

        beat_app = beat.beat(app=celery_app)

        # 配置 Beat 参数
        beat_options = {
            "loglevel": "INFO",
            "schedule_filename": "celerybeat-schedule",
            "max_interval": 60.0,  # 最大检查间隔 60 秒
        }

        log.info("Celery Beat 正在启动，按 Ctrl+C 停止...")
        beat_app.run(**beat_options)

    except KeyboardInterrupt:
        log.info("接收到停止信号，正在关闭 Celery Beat...")
    except Exception as e:
        log.error(f"启动 Celery Beat 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
