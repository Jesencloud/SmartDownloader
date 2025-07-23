#!/usr/bin/env python3
"""
Web服务器启动脚本 (简化版)
"""
import uvicorn
from pathlib import Path
import os

if __name__ == "__main__":
    # 确保在项目根目录运行，以便Uvicorn能找到 'web.main:app'
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("🚀 启动SmartDownloader Web服务器 (开发模式)...")
    print("   - 访问地址: http://0.0.0.0:8000")
    print("   - 按 Ctrl+C 停止服务器")
    
    # 直接调用 uvicorn.run()
    # 这使得 Ctrl+C 行为更可预测，由 uvicorn 内部处理
    # 通过 reload_dirs 精确指定要监控的目录
    # 通过 reload_excludes 排除日志、缓存和下载文件，防止不必要的重启
    uvicorn.run(
        "web.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        reload_dirs=["web", "core"],  # 只监控这两个核心代码目录
        reload_excludes=[
            "*.log", "*.cache", "downloads/*", "tests/*"
        ]
    )