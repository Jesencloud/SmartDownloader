#!/usr/bin/env python3
"""
Celery Worker启动脚本（带Redis连接检查）
"""

import os
import sys
import time
import logging
import subprocess
import signal
from pathlib import Path
import redis
from web.celery_app import broker_url

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="[%(asctime)s: %(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def check_redis_connection(max_attempts=5, delay=2):
    """检查Redis连接，带重试机制"""
    for attempt in range(max_attempts):
        try:
            redis_client = redis.from_url(
                broker_url, socket_connect_timeout=5, socket_timeout=5
            )
            redis_client.ping()
            log.info("✅ Redis连接成功")
            return True
        except Exception as e:
            if attempt < max_attempts - 1:
                log.warning(
                    f"❌ Redis连接失败 (尝试 {attempt + 1}/{max_attempts}): {e}"
                )
                log.info(f"⏳ {delay}秒后重试...")
                time.sleep(delay)
            else:
                log.error(f"❌ Redis连接失败，已尝试{max_attempts}次: {e}")
                return False
    return False


def start_celery_worker():
    """启动Celery Worker"""
    log.info("🚀 启动Celery Worker...")

    # 切换到项目目录
    project_root = Path(__file__).parent

    # 构建celery命令 - Celery 5.0+ 需要将 -A 放在 worker 之前
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "web.celery_app:celery_app",
        "worker",
        "--loglevel=info",
        "--concurrency=4",
        "--pool=prefork",
    ]

    try:
        # 启动worker进程
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        log.info(f"📋 Celery Worker已启动 (PID: {process.pid})")
        log.info("💡 按 Ctrl+C 停止worker")

        # 设置信号处理器
        def signal_handler(signum, frame):
            log.info("🛑 接收到停止信号，正在关闭worker...")
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                log.warning("⚠️  强制终止worker进程")
                process.kill()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 实时输出日志
        for line in process.stdout:
            print(line.rstrip())

        # 等待进程结束
        process.wait()

    except Exception as e:
        log.error(f"❌ 启动Celery Worker失败: {e}")
        return False

    return True


def main():
    """主函数"""
    print("=" * 60)
    print("🎯 SmartDownloader Celery Worker")
    print("=" * 60)

    # 检查Redis连接
    log.info("🔍 检查Redis连接...")
    redis_available = check_redis_connection()

    if not redis_available:
        log.error("❌ Redis服务器不可用！")
        log.info("💡 请确保Redis服务器正在运行:")
        log.info("   - macOS: brew services start redis")
        log.info("   - Ubuntu: sudo systemctl start redis-server")
        log.info("   - Docker: docker run -d -p 6379:6379 redis:alpine")

        # 询问是否继续
        try:
            response = input(
                "\n❓ 是否要在Redis不可用的情况下继续启动worker? (y/N): "
            ).lower()
            if response not in ["y", "yes"]:
                log.info("🚪 退出程序")
                sys.exit(1)
            else:
                # 设置环境变量禁用Redis重连
                os.environ["CELERY_DISABLE_REDIS_RETRY"] = "true"
                log.warning("⚠️  已禁用Redis重连，worker将不会处理任务")
        except KeyboardInterrupt:
            log.info("\n🚪 用户取消，退出程序")
            sys.exit(1)
    else:
        # Redis可用，确保不禁用重连
        os.environ.pop("CELERY_DISABLE_REDIS_RETRY", None)

    # 启动Celery Worker
    try:
        start_celery_worker()
    except KeyboardInterrupt:
        log.info("\n🚪 用户中断，退出程序")
    except Exception as e:
        log.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
