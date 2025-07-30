#!/usr/bin/env python3
"""
启动脚本用于测试位置选择功能
"""

if __name__ == "__main__":
    import uvicorn

    from web.main import app

    # 启动FastAPI开发服务器
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
