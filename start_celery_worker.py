#!/usr/bin/env python3
"""
Celery Worker和Beat启动脚本（带Redis连接检查）

功能：
- 启动Celery Worker处理任务
- 可选启动Celery Beat进行定时任务调度
- 智能Redis连接检查和重试机制
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import redis

from web.celery_app import broker_url

# 设置日志
logging.basicConfig(level=logging.INFO, format="[%(asctime)s: %(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def check_redis_connection(max_attempts=5, delay=2):
    """检查Redis连接，带重试机制"""
    for attempt in range(max_attempts):
        try:
            redis_client = redis.from_url(broker_url, socket_connect_timeout=5, socket_timeout=5)
            redis_client.ping()
            log.info("✅ Redis连接成功")
            return True
        except Exception as e:
            if attempt < max_attempts - 1:
                log.warning(f"❌ Redis连接失败 (尝试 {attempt + 1}/{max_attempts}): {e}")
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
        # "--workdir={project_root}",  # 强制设置工作目录
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
        return process

    except Exception as e:
        log.error(f"❌ 启动Celery Worker失败: {e}")
        return None


def start_celery_beat():
    """启动Celery Beat"""
    log.info("⏰ 启动Celery Beat定时任务调度器...")

    # 切换到项目目录
    project_root = Path(__file__).parent

    # 构建celery beat命令
    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "web.celery_app:celery_app",
        "beat",
        "--loglevel=info",
        "--schedule=celerybeat-schedule",
        "--max-interval=60",
    ]

    try:
        # 启动beat进程
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        log.info(f"📅 Celery Beat已启动 (PID: {process.pid})")

        # 显示定时任务配置
        try:
            from web.celery_app import celery_app

            beat_schedule = celery_app.conf.beat_schedule
            if beat_schedule:
                log.info("📋 定时任务配置:")
                for task_name, task_config in beat_schedule.items():
                    schedule = task_config.get("schedule", "Unknown")
                    task = task_config.get("task", "Unknown")
                    if isinstance(schedule, (int, float)):
                        schedule_str = f"每 {int(schedule / 60)} 分钟"
                    else:
                        schedule_str = str(schedule)
                    log.info(f"  - {task_name}: {task} ({schedule_str})")
        except Exception as e:
            log.warning(f"无法显示定时任务配置: {e}")

        return process

    except Exception as e:
        log.error(f"❌ 启动Celery Beat失败: {e}")
        return None


def monitor_processes(processes):
    """监控进程状态并输出日志"""

    def read_output(process, name):
        """读取进程输出"""
        try:
            for line in process.stdout:
                print(f"[{name}] {line.rstrip()}")
        except Exception as e:
            log.error(f"读取{name}输出失败: {e}")

    # 为每个进程创建线程来读取输出
    threads = []
    for process, name in processes:
        if process:
            thread = threading.Thread(target=read_output, args=(process, name))
            thread.daemon = True
            thread.start()
            threads.append(thread)

    # 等待所有进程结束
    try:
        for process, name in processes:
            if process:
                process.wait()
    except KeyboardInterrupt:
        log.info("🛑 接收到停止信号，正在关闭进程...")
        for process, name in processes:
            if process:
                log.info(f"正在停止 {name}...")
                process.terminate()
                try:
                    process.wait(timeout=30)
                    log.info(f"✅ {name} 已正常停止")
                except subprocess.TimeoutExpired:
                    log.warning(f"⚠️  强制终止 {name} 进程")
                    process.kill()


def get_user_choice():
    """获取用户启动选择"""
    print("\n" + "=" * 60)
    print("🎯 SmartDownloader Celery服务启动选择")
    print("=" * 60)
    print("1. 只启动Worker (处理下载任务)")
    print("2. 启动Worker + Beat (处理下载任务 + 定时清理)")
    print("3. 只启动Beat (仅定时任务调度)")
    print("=" * 60)

    while True:
        try:
            choice = input("请选择启动模式 (1/2/3): ").strip()
            if choice in ["1", "2", "3"]:
                return int(choice)
            else:
                print("❌ 无效选择，请输入 1、2 或 3")
        except KeyboardInterrupt:
            log.info("\n🚪 用户取消，退出程序")
            sys.exit(0)


def main():
    """主函数"""
    print("=" * 60)
    print("🎯 SmartDownloader Celery服务管理器")
    print("=" * 60)

    # 获取用户选择
    choice = get_user_choice()

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
            response = input("\n❓ 是否要在Redis不可用的情况下继续启动? (y/N): ").lower()
            if response not in ["y", "yes"]:
                log.info("🚪 退出程序")
                sys.exit(1)
            else:
                # 设置环境变量禁用Redis重连
                os.environ["CELERY_DISABLE_REDIS_RETRY"] = "true"
                log.warning("⚠️  已禁用Redis重连，服务将不会正常处理任务")
        except KeyboardInterrupt:
            log.info("\n🚪 用户取消，退出程序")
            sys.exit(1)
    else:
        # Redis可用，确保不禁用重连
        os.environ.pop("CELERY_DISABLE_REDIS_RETRY", None)

    # 根据用户选择启动服务
    processes = []

    try:
        if choice == 1:  # 只启动Worker
            log.info("🚀 启动模式: 仅Worker")
            worker_process = start_celery_worker()
            if worker_process:
                processes.append((worker_process, "Worker"))

        elif choice == 2:  # 启动Worker + Beat
            log.info("🚀 启动模式: Worker + Beat")
            worker_process = start_celery_worker()
            beat_process = start_celery_beat()

            if worker_process:
                processes.append((worker_process, "Worker"))
            if beat_process:
                processes.append((beat_process, "Beat"))

        elif choice == 3:  # 只启动Beat
            log.info("🚀 启动模式: 仅Beat")
            beat_process = start_celery_beat()
            if beat_process:
                processes.append((beat_process, "Beat"))

        if not processes:
            log.error("❌ 没有成功启动任何服务")
            sys.exit(1)

        log.info("💡 按 Ctrl+C 停止所有服务")
        monitor_processes(processes)

    except KeyboardInterrupt:
        log.info("\n🚪 用户中断，退出程序")
    except Exception as e:
        log.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
