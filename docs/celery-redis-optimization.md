# Celery Worker Redis连接优化说明

## 问题描述
当Redis服务器关闭后，Celery worker会不断尝试重连并打印错误信息，影响开发体验。

## 解决方案

### 1. 优化的Celery配置 (`web/celery_app.py`)

**新增配置项：**
- `broker_connection_retry_on_startup=True` - 启动时重试连接
- `broker_connection_retry=True` - 启用连接重试  
- `broker_connection_max_retries=10` - 最大重试次数
- `broker_heartbeat=30` - 心跳间隔30秒
- 优化的Redis连接池配置
- socket超时和重试策略

**连接池优化：**
```python
"connection_pool_kwargs": {
    "max_connections": 20,
    "retry_on_timeout": True,
    "socket_keepalive": True,
    "socket_connect_timeout": 10,  # 连接超时10秒
    "socket_timeout": 10,  # socket超时10秒
}
```

### 2. 智能启动脚本 (`start_celery_worker.py`)

**功能特性：**
- ✅ Redis连接检查（最多5次重试）
- ✅ 优雅的错误提示和用户交互
- ✅ 实时日志输出
- ✅ 信号处理（Ctrl+C优雅关闭）
- ✅ 进程管理和清理

**使用方法：**
```bash
# 使用新的启动脚本
python start_celery_worker.py

# 或者传统方式
python -m celery worker -A web.celery_app:celery_app --loglevel=info
```

### 3. 错误处理机制 (`web/tasks.py`)

**新增功能：**
- Redis连接错误装饰器
- 自动重试机制（最多3次，间隔10秒）
- 详细的错误日志记录
- 优雅降级处理

### 4. 监控和健康检查

**Worker信号处理：**
- `worker_ready` - 启动时检查Redis连接
- `worker_shutdown` - 关闭时清理资源
- `worker_process_init` - 进程初始化日志

## 使用建议

### 开发环境
1. **启动Redis服务：**
   ```bash
   # macOS
   brew services start redis
   
   # Ubuntu
   sudo systemctl start redis-server
   
   # Docker
   docker run -d -p 6379:6379 redis:alpine
   ```

2. **启动Celery Worker：**
   ```bash
   python start_celery_worker.py
   ```

### 生产环境
1. **使用systemd管理服务**
2. **配置Redis持久化和备份**
3. **监控Redis和Celery健康状态**
4. **设置告警机制**

## 故障排除

### Redis连接失败
**常见原因：**
- Redis服务未启动
- 端口被占用
- 网络连接问题
- 权限问题

**解决方法：**
1. 检查Redis服务状态：`redis-cli ping`
2. 查看Redis日志：`tail -f /var/log/redis/redis-server.log`
3. 检查端口：`netstat -tlnp | grep 6379`

### Worker频繁重连
**优化措施：**
- 增加连接超时时间
- 调整重试间隔
- 启用连接池
- 监控网络质量

### 内存泄漏
**预防措施：**
- 设置worker最大任务数：`worker_max_tasks_per_child=1000`
- 启用内存限制：`worker_max_memory_per_child=500000`
- 定期重启worker进程

## 配置参数说明

| 参数 | 默认值 | 说明 |
|------|-------|------|
| broker_connection_max_retries | 10 | 最大重连次数 |
| broker_heartbeat | 30 | 心跳间隔（秒） |
| socket_connect_timeout | 10 | 连接超时（秒） |
| socket_timeout | 10 | socket超时（秒） |
| worker_max_tasks_per_child | 1000 | 每个子进程最大任务数 |
| worker_max_memory_per_child | 500MB | 每个子进程最大内存 |

## 监控命令

```bash
# 查看worker状态
celery -A web.celery_app:celery_app status

# 查看活动任务
celery -A web.celery_app:celery_app active

# 查看队列信息
celery -A web.celery_app:celery_app inspect reserved

# 实时监控
celery -A web.celery_app:celery_app events
```