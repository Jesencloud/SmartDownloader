#!/usr/bin/env python3
"""
快速启动 Celery 工作进程的脚本
"""
import subprocess
import sys
import time
import signal
import os
from pathlib import Path

def start_redis():
    """检查并启动 Redis"""
    try:
        # 检查 Redis 是否运行
        result = subprocess.run(['redis-cli', 'ping'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and 'PONG' in result.stdout:
            print("✅ Redis 已运行")
            return True
    except:
        pass
    
    print("🔄 尝试启动 Redis...")
    try:
        # 尝试启动 Redis (macOS with Homebrew)
        subprocess.Popen(['brew', 'services', 'start', 'redis'])
        time.sleep(3)
        
        # 再次检查
        result = subprocess.run(['redis-cli', 'ping'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and 'PONG' in result.stdout:
            print("✅ Redis 启动成功")
            return True
    except:
        pass
    
    print("❌ Redis 启动失败，请手动启动 Redis")
    return False

def main():
    print("🚀 SmartDownloader Celery 快速启动")
    
    # 检查 Redis
    if not start_redis():
        return
    
    processes = []
    
    try:
        print("\n1️⃣ 启动 Celery Worker...")
        worker_process = subprocess.Popen([
            sys.executable, "celery_manager.py", "start", 
            "--worker", "download_worker",
            "--concurrency", "2",
            "--queue", "download_queue"
        ])
        processes.append(("Celery Worker", worker_process))
        time.sleep(3)
        
        print("\n2️⃣ 启动内置监控面板...")
        monitor_process = subprocess.Popen([
            sys.executable, "celery_manager.py", "builtin-monitor",
            "--port", "8001"
        ])
        processes.append(("内置监控", monitor_process))
        time.sleep(2)
        
        print("\n3️⃣ 启动 Web 服务器...")
        preexec_fn = os.setsid if sys.platform != "win32" else None
        web_process = subprocess.Popen([
            sys.executable, "-m", "uvicorn", 
            "web.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
            "--reload-dir", "web",
            "--reload-dir", "core",
            "--reload-exclude", "*.log",
            "--reload-exclude", "downloads/*"
        ], preexec_fn=preexec_fn)
        processes.append(("Web 服务器", web_process))
        time.sleep(2)
        
        print("\n" + "="*50)
        print("🎉 所有服务已启动！")
        print("="*50)
        print("🌐 Web 服务器: http://localhost:8000")
        print("📊 监控面板: http://localhost:8001")
        print("🌸 Flower (可选): python celery_manager.py flower")
        print("="*50)
        print("\n按 Ctrl+C 停止所有服务...")
        
        # 等待信号
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 正在停止所有服务...")
        
        for name, process in processes:
            try:
                print(f"停止 {name}...")
                # 对 uvicorn --reload 使用进程组终止
                if name == "Web 服务器" and sys.platform != "win32":
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"强制停止 {name}...")
                    if name == "Web 服务器" and sys.platform != "win32":
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        process.kill()
            except:
                pass
        
        print("✅ 所有服务已停止")

if __name__ == "__main__":
    main()