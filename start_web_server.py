#!/usr/bin/env python3
"""
Web服务器启动脚本 (简化版)
"""

from pathlib import Path
import os
import subprocess
import signal
import sys

# 全局变量来持有子进程
uvicorn_process = None


def signal_handler(sig, frame):
    """
    捕获 Ctrl+C 信号并优雅地终止子进程
    """
    global uvicorn_process
    print("\n🛑 检测到 Ctrl+C, 正在停止服务器...")
    if uvicorn_process:
        # 终止整个进程组，以确保 reloader 也被关闭
        os.killpg(os.getpgid(uvicorn_process.pid), signal.SIGTERM)
    sys.exit(0)


if __name__ == "__main__":
    # 确保在项目根目录运行，以便Uvicorn能找到 'web.main:app'
    project_root = Path(__file__).parent
    os.chdir(project_root)

    print("🚀 启动SmartDownloader Web服务器 (开发模式)...")
    print("   - 访问地址: http://0.0.0.0:8000")
    print("   - 按 Ctrl+C 停止服务器")

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)

    # 构建 uvicorn 命令
    command = [
        sys.executable,  # 使用当前Python解释器
        "-m",
        "uvicorn",
        "web.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
        "--log-level",
        "info",
        "--reload-dir",
        "web",
        "--reload-dir",
        "core",
        "--reload-exclude",
        "*.log",
        "--reload-exclude",
        "*.cache",
        "--reload-exclude",
        "downloads/*",
        "--reload-exclude",
        "tests/*",
    ]

    # 使用 subprocess.Popen 启动 uvicorn
    # preexec_fn=os.setsid 使得 uvicorn 成为新会话的领导者，便于我们终止整个进程组
    uvicorn_process = subprocess.Popen(command, preexec_fn=os.setsid)

    # 等待子进程结束
    uvicorn_process.wait()
