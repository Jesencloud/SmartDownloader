#!/usr/bin/env python3
"""
内置的简单 Celery 监控 Web 界面
作为 Flower 的轻量级替代方案
"""
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import time
import psutil
import os
from pathlib import Path
import asyncio
from celery import Celery

# 导入现有的 Celery 应用
import sys
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from web.celery_app import celery_app

app = FastAPI(title="Celery 监控面板")

class CeleryMonitor:
    """Celery 监控器"""
    
    def __init__(self, celery_app):
        self.celery_app = celery_app
        self.inspect = celery_app.control.inspect()
    
    def get_worker_stats(self):
        """获取 Worker 统计信息"""
        try:
            stats = self.inspect.stats()
            active = self.inspect.active() or {}
            scheduled = self.inspect.scheduled() or {}
            reserved = self.inspect.reserved() or {}
            
            worker_info = {}
            
            for worker_name in (stats or {}):
                worker_info[worker_name] = {
                    'status': 'online',
                    'active_tasks': len(active.get(worker_name, [])),
                    'scheduled_tasks': len(scheduled.get(worker_name, [])),
                    'reserved_tasks': len(reserved.get(worker_name, [])),
                    'total_tasks': stats[worker_name]['total'],
                    'pool_type': stats[worker_name]['pool']['max-concurrency']
                }
                
            return worker_info
            
        except Exception as e:
            print(f"获取 Worker 统计信息失败: {e}")
            return {}
    
    def get_system_stats(self):
        """获取系统统计信息"""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_total': memory.total // (1000**3),  # GB
                'memory_used': memory.used // (1000**3),    # GB
                'memory_percent': memory.percent,
                'disk_total': disk.total // (1000**3),      # GB
                'disk_used': disk.used // (1000**3),        # GB
                'disk_percent': (disk.used / disk.total) * 100,
                'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            }
        except Exception as e:
            print(f"获取系统统计信息失败: {e}")
            return {}

monitor = CeleryMonitor(celery_app)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """主监控面板"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Celery 监控面板</title>
        <meta charset="UTF-8">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 20px; 
                background-color: #f5f5f5; 
            }
            .container { 
                max-width: 1200px; 
                margin: 0 auto; 
            }
            .card { 
                background: white; 
                padding: 20px; 
                margin: 10px 0; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }
            .header { 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                color: white; 
                text-align: center; 
                padding: 30px; 
                border-radius: 8px; 
                margin-bottom: 20px; 
            }
            .stats-grid { 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
                gap: 20px; 
            }
            .stat-item { 
                display: flex; 
                justify-content: space-between; 
                padding: 10px 0; 
                border-bottom: 1px solid #eee; 
            }
            .stat-value { 
                font-weight: bold; 
                color: #333; 
            }
            .status-online { 
                color: #4CAF50; 
            }
            .status-offline { 
                color: #f44336; 
            }
            .progress-bar { 
                width: 100%; 
                height: 20px; 
                background-color: #f0f0f0; 
                border-radius: 10px; 
                overflow: hidden; 
                margin: 5px 0; 
            }
            .progress-fill { 
                height: 100%; 
                background: linear-gradient(90deg, #4CAF50, #45a049); 
                transition: width 0.3s ease; 
            }
            .refresh-btn { 
                background: #4CAF50; 
                color: white; 
                border: none; 
                padding: 10px 20px; 
                border-radius: 5px; 
                cursor: pointer; 
                margin: 10px 0; 
            }
            .refresh-btn:hover { 
                background: #45a049; 
            }
        </style>
        <script>
            async function refreshData() {
                try {
                    const response = await fetch('/api/stats');
                    const data = await response.json();
                    
                    // 更新 Worker 信息
                    updateWorkerStats(data.workers);
                    
                    // 更新系统信息
                    updateSystemStats(data.system);
                    
                    // 更新时间戳
                    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
                    
                } catch (error) {
                    console.error('刷新数据失败:', error);
                }
            }
            
            function updateWorkerStats(workers) {
                const container = document.getElementById('workers-container');
                container.innerHTML = '';
                
                if (Object.keys(workers).length === 0) {
                    container.innerHTML = '<p>没有在线的 Worker</p>';
                    return;
                }
                
                for (const [name, stats] of Object.entries(workers)) {
                    const workerDiv = document.createElement('div');
                    workerDiv.className = 'card';
                    workerDiv.innerHTML = `
                        <h3>${name} <span class="status-online">● 在线</span></h3>
                        <div class="stat-item">
                            <span>活跃任务:</span>
                            <span class="stat-value">${stats.active_tasks}</span>
                        </div>
                        <div class="stat-item">
                            <span>预约任务:</span>
                            <span class="stat-value">${stats.scheduled_tasks}</span>
                        </div>
                        <div class="stat-item">
                            <span>保留任务:</span>
                            <span class="stat-value">${stats.reserved_tasks}</span>
                        </div>
                        <div class="stat-item">
                            <span>总任务数:</span>
                            <span class="stat-value">${stats.total_tasks}</span>
                        </div>
                        <div class="stat-item">
                            <span>并发数:</span>
                            <span class="stat-value">${stats.pool_type}</span>
                        </div>
                    `;
                    container.appendChild(workerDiv);
                }
            }
            
            function updateSystemStats(system) {
                if (!system) return;
                
                document.getElementById('cpu-percent').textContent = `${system.cpu_percent.toFixed(1)}%`;
                document.getElementById('memory-usage').textContent = `${system.memory_used}GB / ${system.memory_total}GB (${system.memory_percent.toFixed(1)}%)`;
                document.getElementById('disk-usage').textContent = `${system.disk_used}GB / ${system.disk_total}GB (${system.disk_percent.toFixed(1)}%)`;
                
                // 更新进度条
                document.getElementById('cpu-fill').style.width = `${system.cpu_percent}%`;
                document.getElementById('memory-fill').style.width = `${system.memory_percent}%`;
                document.getElementById('disk-fill').style.width = `${system.disk_percent}%`;
            }
            
            // 页面加载时刷新数据
            window.onload = function() {
                refreshData();
                // 每30秒自动刷新
                setInterval(refreshData, 30000);
            };
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔍 Celery 监控面板</h1>
                <p>实时监控 Celery 工作进程和系统状态</p>
                <button class="refresh-btn" onclick="refreshData()">🔄 刷新数据</button>
                <p>最后更新: <span id="lastUpdate">-</span></p>
            </div>
            
            <div class="stats-grid">
                <div class="card">
                    <h2>📊 系统资源</h2>
                    <div class="stat-item">
                        <span>CPU 使用率:</span>
                        <span class="stat-value" id="cpu-percent">-</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="cpu-fill" style="width: 0%;"></div>
                    </div>
                    
                    <div class="stat-item">
                        <span>内存使用:</span>
                        <span class="stat-value" id="memory-usage">-</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="memory-fill" style="width: 0%;"></div>
                    </div>
                    
                    <div class="stat-item">
                        <span>磁盘使用:</span>
                        <span class="stat-value" id="disk-usage">-</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="disk-fill" style="width: 0%;"></div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h2>⚙️ Celery Workers</h2>
                <div id="workers-container">
                    <p>加载中...</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/stats")
async def get_stats():
    """获取监控数据 API"""
    worker_stats = monitor.get_worker_stats()
    system_stats = monitor.get_system_stats()
    
    return JSONResponse({
        "workers": worker_stats,
        "system": system_stats,
        "timestamp": time.time()
    })

def start_monitor_server(port=8001):
    """启动监控服务器"""
    import uvicorn
    print(f"🖥️ 启动内置 Celery 监控面板 (端口: {port})")
    print(f"   访问地址: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start_monitor_server()