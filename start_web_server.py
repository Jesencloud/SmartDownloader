#!/usr/bin/env python3
"""
Web服务器启动脚本
支持自动重启功能
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path

def start_server():
    """启动Web服务器"""
    print("🚀 启动SmartDownloader Web服务器...")
    
    # 确保在项目根目录
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # 启动命令
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "web.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"  # 开发模式，支持自动重载
    ]
    
    return subprocess.Popen(cmd)

def main():
    """主启动循环，支持自动重启"""
    restart_count = 0
    max_restarts = 10
    
    while restart_count < max_restarts:
        try:
            print(f"📡 启动服务器 (重启次数: {restart_count})")
            
            # 启动服务器进程
            server_process = start_server()
            
            # 等待进程结束
            return_code = server_process.wait()
            
            print(f"⚠️ 服务器进程结束，返回码: {return_code}")
            
            if return_code == 0:
                print("✅ 服务器正常退出")
                break
            elif return_code == -signal.SIGTERM:
                print("🔄 收到重启信号，准备重启...")
                restart_count += 1
                time.sleep(2)  # 等待2秒后重启
                continue
            else:
                print(f"❌ 服务器异常退出，返回码: {return_code}")
                restart_count += 1
                time.sleep(5)  # 等待5秒后重启
                
        except KeyboardInterrupt:
            print("\n🛑 收到中断信号，正在关闭服务器...")
            if 'server_process' in locals():
                server_process.terminate()
                server_process.wait()
            break
        except Exception as e:
            print(f"❌ 启动服务器时出错: {e}")
            restart_count += 1
            time.sleep(5)
    
    if restart_count >= max_restarts:
        print(f"❌ 达到最大重启次数 ({max_restarts})，停止重启")
    
    print("🏁 服务器启动脚本结束")

if __name__ == "__main__":
    main()