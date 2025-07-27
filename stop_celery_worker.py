#!/usr/bin/env python3
"""
快速停止所有Celery worker进程
"""

import subprocess
import time
import psutil
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def stop_celery_workers():
    """停止所有Celery worker进程"""
    log.info("🔍 查找Celery worker进程...")

    stopped_count = 0

    # 方法1：使用pkill命令
    try:
        result = subprocess.run(
            ["pkill", "-f", "celery worker"], capture_output=True, text=True
        )
        if result.returncode == 0:
            log.info("✅ 使用pkill命令停止了Celery worker")
            stopped_count += 1
    except Exception as e:
        log.warning(f"pkill命令失败: {e}")

    # 方法2：使用psutil查找并终止进程
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
                if ("celery" in cmdline and "worker" in cmdline) or (
                    proc.info["name"] and "celery" in proc.info["name"].lower()
                ):
                    log.info(f"🔪 终止进程 {proc.info['pid']}: {proc.info['name']}")
                    proc.terminate()
                    stopped_count += 1

                    # 等待进程优雅退出
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        log.warning(f"⚡ 强制杀死进程 {proc.info['pid']}")
                        proc.kill()

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        log.error(f"使用psutil停止进程失败: {e}")

    if stopped_count > 0:
        log.info(f"✅ 共停止了 {stopped_count} 个进程")
        time.sleep(1)  # 等待进程完全退出
    else:
        log.info("ℹ️  没有找到运行中的Celery worker进程")


def main():
    print("🛑 停止Celery Worker")
    print("=" * 30)

    stop_celery_workers()

    # 验证是否还有残留进程
    log.info("🔍 检查是否还有残留进程...")
    remaining = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
                if "celery" in cmdline and "worker" in cmdline:
                    remaining.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception:
        pass

    if remaining:
        log.warning(f"⚠️  仍有 {len(remaining)} 个进程残留: {remaining}")
        log.info("💡 你可能需要手动杀死这些进程:")
        for pid in remaining:
            log.info(f"   kill -9 {pid}")
    else:
        log.info("✅ 所有Celery worker进程已停止")


if __name__ == "__main__":
    main()
