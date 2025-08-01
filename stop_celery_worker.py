#!/usr/bin/env python3
"""
快速停止所有Celery worker进程
"""

import logging
import subprocess
import time
from typing import List

import psutil

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 定义Celery worker进程的标识
CELERY_WORKER_IDENTIFIER = "celery"
MAIN_PROCESS_IDENTIFIER = "celery worker"


def _find_celery_worker_processes() -> "List[psutil.Process]":
    """Finds all running Celery worker processes using psutil."""
    worker_procs = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            if ("celery" in cmdline and "worker" in cmdline) or (
                proc.info["name"] and "celery" in proc.info["name"].lower()
            ):
                worker_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return worker_procs


def stop_celery_workers():
    """停止所有Celery worker进程"""
    logging.info("🔍 查找Celery worker进程...")

    stopped_count = 0

    # 方法1：使用pkill命令
    try:
        result = subprocess.run(["pkill", "-f", "celery worker"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            logging.info("✅ 使用pkill命令停止了Celery worker")
            # 如果pkill成功，我们假设它已经完成了任务，可以直接返回
            return
    except FileNotFoundError:
        logging.warning("`pkill` 命令未找到，将使用psutil方法。")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        # 捕获更具体的子进程错误
        logging.warning("pkill命令执行失败: %s", e)

    # 方法2：使用psutil查找并终止进程
    try:
        worker_processes = _find_celery_worker_processes()
        for proc in worker_processes:
            logging.info("🔪 终止进程 %s: %s", proc.pid, proc.name())
            proc.terminate()
            stopped_count += 1

            # 等待进程优雅退出
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                logging.warning("⚡ 强制杀死进程 %s", proc.pid)
                proc.kill()
            except psutil.NoSuchProcess:
                pass  # Process already gone
    except psutil.Error as e:
        # 捕获psutil相关的特定错误
        logging.error("使用psutil停止进程时出错: %s", e)

    if stopped_count > 0:
        logging.info("✅ 共停止了 %s 个进程", stopped_count)
        time.sleep(1)  # 等待进程完全退出
    else:
        logging.info("ℹ️  没有找到运行中的Celery worker进程")


def main():
    print("🛑 停止Celery Worker")
    print("=" * 30)

    stop_celery_workers()

    # 验证是否还有残留进程
    logging.info("🔍 检查是否还有残留进程...")
    remaining_procs = _find_celery_worker_processes()
    remaining_pids = [p.pid for p in remaining_procs]

    if remaining_pids:
        logging.warning("⚠️  仍有 %s 个进程残留: %s", len(remaining_pids), remaining_pids)
        logging.info("💡 你可能需要手动杀死这些进程:")
        for pid in remaining_pids:
            logging.info("kill -9 %s", pid)
    else:
        logging.info("✅ 所有Celery worker进程已停止")


if __name__ == "__main__":
    main()
