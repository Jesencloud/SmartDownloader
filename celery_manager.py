#!/usr/bin/env python3
"""
Celery 工作进程管理脚本
提供启动、监控和管理 Celery worker 的功能
"""
import os
import sys
import time
import subprocess
import psutil
from pathlib import Path

class CeleryManager:
    """Celery 工作进程管理器"""
    
    def __init__(self, project_root=None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent
        self.workers = {}
        # 启动时自动发现已存在的进程
        self.discover_existing_workers()
    
    def discover_existing_workers(self):
        """发现系统中已存在的Celery worker进程"""
        discovered = 0
        
        try:
            for proc in psutil.process_iter(['pid', 'cmdline', 'create_time']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if not cmdline:
                        continue
                        
                    # 检查是否是我们的Celery worker进程
                    cmdline_str = ' '.join(cmdline)
                    if ('celery' in cmdline_str and 
                        'web.celery_app' in cmdline_str and 
                        'worker' in cmdline_str):
                        
                        pid = proc.info['pid']
                        worker_name = f"existing_{pid}"
                        
                        # 避免重复添加
                        if worker_name not in self.workers:
                            self.workers[worker_name] = {
                                'process': psutil.Process(pid),
                                'pid': pid,
                                'start_time': proc.info['create_time'],
                                'queue': 'discovered',
                                'concurrency': 'unknown',
                                'simple_mode': True,
                                'discovered': True
                            }
                            discovered += 1
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
            if discovered > 0:
                print(f"🔍 发现 {discovered} 个已存在的Celery worker进程")
                    
        except Exception as e:
            print(f"⚠️ 进程发现时出错: {e}")
    
    def stop_all_existing_workers(self):
        """停止所有已发现的worker进程"""
        stopped = 0
        for worker_name, worker_info in list(self.workers.items()):
            if worker_info.get('discovered'):
                try:
                    process = worker_info['process']
                    if process.is_running():
                        print(f"🔄 停止已存在的worker: {worker_name} (PID: {worker_info['pid']})")
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            process.kill()
                        stopped += 1
                    del self.workers[worker_name]
                except Exception as e:
                    print(f"❌ 停止worker {worker_name} 时出错: {e}")
        
        if stopped > 0:
            print(f"✅ 成功停止 {stopped} 个已存在的worker")
        return stopped
    
    def _confirm_multiple_workers(self):
        """确认是否允许启动多个worker"""
        try:
            response = input("是否要停止现有worker并启动新的? (y/N): ").lower().strip()
            if response in ['y', 'yes']:
                return self.stop_all_existing_workers() >= 0
            return False
        except KeyboardInterrupt:
            print("\n操作已取消")
            return False
        
    def start_worker(self, worker_name="worker1", concurrency=None, queue=None, simple_mode=False):
        """启动 Celery 工作进程"""
        
        # 检查是否已有worker在运行
        existing_workers = [name for name, info in self.workers.items() 
                          if info.get('discovered') or not info.get('discovered', True)]
        
        if existing_workers and not self._confirm_multiple_workers():
            print(f"⚠️ 发现已存在的worker: {existing_workers}")
            print("使用 --force 参数强制启动新worker，或先停止现有worker")
            return None
            
        if not concurrency:
            concurrency = min(os.cpu_count() or 4, 4)  # 最大4个并发
            
        if simple_mode:
            # 简单模式：更接近直接 celery 命令
            cmd = [
                sys.executable, "-m", "celery",
                "-A", "web.celery_app",
                "worker",
                "--loglevel", "info"
            ]
            if concurrency and concurrency > 1:
                cmd.extend(["--concurrency", str(concurrency)])
        else:
            # 完整模式：带队列和主机名
            if not queue:
                queue = "download_queue,maintenance_queue"
            cmd = [
                sys.executable, "-m", "celery",
                "-A", "web.celery_app",
                "worker",
                "--hostname", f"{worker_name}@%h",
                "--concurrency", str(concurrency),
                "--queues", queue,
                "--loglevel", "info"
                # 简化配置，移除可能导致问题的限制参数
            ]
        
        print(f"🚀 启动 Celery Worker: {worker_name}")
        print(f"   模式: {'简单' if simple_mode else '完整'}")
        print(f"   并发数: {concurrency}")
        if not simple_mode:
            print(f"   队列: {queue}")
        print(f"   命令: {' '.join(cmd)}")
        
        try:
            # 设置工作目录
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env
                # 移除输出重定向，让日志正常输出到终端
            )
            
            self.workers[worker_name] = {
                'process': process,
                'pid': process.pid,
                'start_time': time.time(),
                'queue': queue if not simple_mode else 'all',
                'concurrency': concurrency,
                'simple_mode': simple_mode
            }
            
            print(f"✅ Worker {worker_name} 已启动 (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"❌ 启动 Worker {worker_name} 失败: {e}")
            return None
    
    def start_flower(self, port=5555):
        """启动 Flower 监控界面"""
        cmd = [
            sys.executable, "-m", "celery",
            "-A", "web.celery_app",
            "flower",
            f"--port={port}",
            "--basic_auth=admin:admin123"  # 简单认证
        ]
        
        print(f"🌸 启动 Flower 监控界面 (端口: {port})")
        
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env
            )
            
            self.workers['flower'] = {
                'process': process,
                'pid': process.pid,
                'start_time': time.time()
            }
            
            print(f"✅ Flower 已启动 (PID: {process.pid})")
            print(f"   访问地址: http://localhost:{port}")
            print("   用户名: admin, 密码: admin123")
            
            return process
            
        except Exception as e:
            print(f"❌ 启动 Flower 失败: {e}")
    def start_builtin_monitor(self, port=8001):
        """启动内置监控界面（Flower 的替代方案）"""
        cmd = [
            sys.executable, "celery_monitor.py"
        ]
        
        print(f"🖥️ 启动内置 Celery 监控面板 (端口: {port})")
        
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            env["MONITOR_PORT"] = str(port)
            
            process = subprocess.Popen(
                cmd,
                cwd=self.project_root,
                env=env
            )
            
            self.workers['builtin_monitor'] = {
                'process': process,
                'pid': process.pid,
                'start_time': time.time()
            }
            
            print(f"✅ 内置监控面板已启动 (PID: {process.pid})")
            print(f"   访问地址: http://localhost:{port}")
            print("   这是一个轻量级的 Celery 监控替代方案")
            
            return process
            
        except Exception as e:
            print(f"❌ 启动内置监控失败: {e}")
            return None
    
    def get_worker_stats(self):
        """获取工作进程统计信息"""
        stats = {}
        
        for name, worker in self.workers.items():
            if name == 'flower':
                continue
                
            try:
                process = psutil.Process(worker['pid'])
                stats[name] = {
                    'pid': worker['pid'],
                    'status': process.status(),
                    'cpu_percent': process.cpu_percent(),
                    'memory_mb': process.memory_info().rss / 1024 / 1024,
                    'uptime': time.time() - worker['start_time'],
                    'queue': worker['queue'],
                    'concurrency': worker['concurrency']
                }
            except psutil.NoSuchProcess:
                stats[name] = {'status': 'dead'}
                
        return stats
    
    def monitor_workers(self, interval=30):
        """监控工作进程状态"""
        print(f"📊 开始监控工作进程 (每 {interval} 秒更新)")
        print("按 Ctrl+C 停止监控")
        
        try:
            while True:
                stats = self.get_worker_stats()
                
                print(f"\n{'='*60}")
                print(f"监控时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*60}")
                
                for name, stat in stats.items():
                    if stat.get('status') == 'dead':
                        print(f"❌ {name}: 进程已死亡")
                        continue
                        
                    print(f"✅ {name}:")
                    print(f"   PID: {stat['pid']}")
                    print(f"   状态: {stat['status']}")
                    print(f"   CPU: {stat['cpu_percent']:.1f}%")
                    print(f"   内存: {stat['memory_mb']:.1f} MB")
                    print(f"   运行时间: {stat['uptime']:.0f} 秒")
                    print(f"   队列: {stat['queue']}")
                    print(f"   并发数: {stat['concurrency']}")
                    print()
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n🛑 停止监控")
    
    def stop_worker(self, worker_name):
        """停止指定的工作进程"""
        if worker_name not in self.workers:
            print(f"❌ Worker {worker_name} 不存在")
            return False
            
        worker = self.workers[worker_name]
        try:
            process = worker['process']
            print(f"🛑 正在停止 Worker {worker_name} (PID: {worker['pid']})")
            
            # 发送 SIGTERM 信号
            process.terminate()
            
            # 等待进程结束
            try:
                process.wait(timeout=10)
                print(f"✅ Worker {worker_name} 已优雅停止")
            except subprocess.TimeoutExpired:
                print(f"⚠️ Worker {worker_name} 未在10秒内停止，强制杀死")
                process.kill()
                process.wait()
                print(f"✅ Worker {worker_name} 已强制停止")
                
            del self.workers[worker_name]
            return True
            
        except Exception as e:
            print(f"❌ 停止 Worker {worker_name} 失败: {e}")
            return False
    
    def stop_all_workers(self):
        """停止所有工作进程"""
        print("🛑 正在停止所有工作进程...")
        
        worker_names = list(self.workers.keys())
        for name in worker_names:
            self.stop_worker(name)
        
        print("✅ 所有工作进程已停止")
    
    def restart_worker(self, worker_name):
        """重启指定的工作进程"""
        if worker_name not in self.workers:
            print(f"❌ Worker {worker_name} 不存在")
            return False
            
        # 保存原配置
        worker = self.workers[worker_name]
        queue = worker.get('queue')
        concurrency = worker['concurrency']
        simple_mode = worker.get('simple_mode', False)
        
        # 停止
        self.stop_worker(worker_name)
        
        # 等待一秒
        time.sleep(1)
        
        # 重新启动
        return self.start_worker(worker_name, concurrency, queue, simple_mode)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Celery 工作进程管理")
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'monitor', 'flower', 'builtin-monitor'], help='操作类型')
    parser.add_argument('--worker', default='worker1', help='Worker 名称')
    parser.add_argument('--concurrency', type=int, help='并发数')
    parser.add_argument('--queue', help='队列名称')
    parser.add_argument('--simple', action='store_true', help='使用简单模式（更接近直接 celery 命令）')
    parser.add_argument('--port', type=int, default=5555, help='Flower/监控端口')
    parser.add_argument('--interval', type=int, default=30, help='监控间隔(秒)')
    
    args = parser.parse_args()
    
    manager = CeleryManager()
    
    if args.action == 'start':
        manager.start_worker(args.worker, args.concurrency, args.queue, args.simple)
        
    elif args.action == 'stop':
        manager.stop_worker(args.worker)
        
    elif args.action == 'restart':
        # 需要先获取原有的 simple_mode 设置
        if args.worker in manager.workers:
            manager.restart_worker(args.worker)
        else:
            manager.start_worker(args.worker, args.concurrency, args.queue, args.simple)
        
    elif args.action == 'monitor':
        # 先启动一个默认 worker
        manager.start_worker(args.worker, args.concurrency, args.queue, args.simple)
        time.sleep(2)  # 等待启动
        manager.monitor_workers(args.interval)
        
    elif args.action == 'flower':
        manager.start_flower(args.port)
        try:
            print("Flower 正在运行，按 Ctrl+C 停止...")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 停止 Flower")
            manager.stop_worker('flower')
            
    elif args.action == 'builtin-monitor':
        manager.start_builtin_monitor(args.port if args.port != 5555 else 8001)
        try:
            print("内置监控正在运行，按 Ctrl+C 停止...")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 停止内置监控")
            manager.stop_worker('builtin_monitor')

if __name__ == "__main__":
    main()