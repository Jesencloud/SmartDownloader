# Celery 工作进程使用指南

## 🚀 快速开始

### 方法一：一键启动所有服务
```bash
python start_all_services.py
```
这会自动启动：
- Redis (如果未运行)
- Celery Worker (简单模式)
- 内置监控面板 (http://localhost:8001)
- Web 服务器 (http://localhost:8000)

### 方法二：分别启动

#### 1. 启动 Celery Worker

**选项 A: 简单模式 (推荐，已修复下载问题)**
```bash
# 启动简单模式 Worker（等同于直接 celery 命令）
python celery_manager.py start --simple

# 指定并发数
python celery_manager.py start --simple --concurrency 2

# 监控模式（启动后立即开始监控）
python celery_manager.py monitor --simple --interval 30
```

**选项 B: 完整模式 (高级用户)**
```bash
# 启动下载队列 Worker
python celery_manager.py start --worker download_worker --concurrency 2 --queue download_queue

# 启动维护队列 Worker  
python celery_manager.py start --worker maintenance_worker --concurrency 1 --queue maintenance_queue
```

**选项 C: 直接命令 (调试用)**
```bash
# 如果管理脚本有问题，可以使用直接命令
celery -A web.celery_app worker --loglevel=info
```

#### 2. 启动监控界面

**选项 A: 使用 Flower (功能最全)**
```bash
python celery_manager.py flower --port 5555
```
访问：http://localhost:5555
用户名：admin，密码：admin123

**选项 B: 使用内置监控 (轻量级)**  
```bash
python celery_manager.py builtin-monitor --port 8001
```
访问：http://localhost:8001

#### 3. 监控 Worker 状态
```bash
# 命令行监控
python celery_manager.py monitor --interval 30
```

## 📊 监控功能对比

| 功能 | Flower | 内置监控 | 命令行监控 |
|------|--------|----------|------------|
| **Web 界面** | ✅ | ✅ | ❌ |
| **实时任务状态** | ✅ | ✅ | ✅ |
| **系统资源监控** | ✅ | ✅ | ✅ |
| **任务历史** | ✅ | ❌ | ❌ |
| **Worker 控制** | ✅ | ❌ | ❌ |
| **安装要求** | 需要 flower | 无额外依赖 | 无额外依赖 |
| **资源消耗** | 中等 | 低 | 最低 |

## 🛠️ 常用操作

### 管理 Worker
```bash
# 启动简单模式 Worker（推荐 - 现已支持进程检测）
python celery_manager.py start --simple

# 系统会自动检测现有进程并提供选项：
# → 发现已存在的worker进程，询问是否替换
# → 安全停止旧进程并启动新的
# → 防止进程积累问题

# 停止 Worker（简单模式使用默认名称 worker1）
python celery_manager.py stop --worker worker1

# 重启 Worker
python celery_manager.py restart --worker worker1

# 查看所有 Worker 状态（包括发现的进程）
python celery_manager.py monitor --simple
```

### 不同启动模式对比

| 启动方式 | 命令 | 优点 | 缺点 | 推荐场景 |
|---------|------|------|------|----------|
| **简单模式** | `python celery_manager.py start --simple` | ✅ 日志清晰<br>✅ 配置简单<br>✅ 下载正常<br>✅ **智能进程检测**<br>✅ **防进程积累** | ❌ 功能较基础 | 🔥 **日常使用** |
| **完整模式** | `python celery_manager.py start --worker ...` | ✅ 功能丰富<br>✅ 队列分离 | ❌ 配置复杂<br>❌ 可能有问题 | 🔧 高级配置 |
| **直接命令** | `celery -A web.celery_app worker` | ✅ 最直接<br>✅ 调试友好 | ❌ 无管理功能 | 🐛 调试排查 |

### 性能测试
```bash
# 运行 Celery 优化测试
python test_celery_optimization.py
```

## ⚙️ 配置说明

### Worker 并发配置
- **下载队列**：建议并发数 = CPU核心数 (最大4个)
- **维护队列**：建议并发数 = 1-2个

### 超时配置
- **软超时**：10分钟 (可以优雅取消)
- **硬超时**：15分钟 (强制终止)
- **重试**：最多3次，间隔60秒

### 队列分离
- `download_queue` - 下载任务
- `maintenance_queue` - 清理任务

## 🔧 故障排除

### 🚨 问题：Worker 进程积累 (CRITICAL)
**症状：** 系统中出现大量重复的 Celery worker 进程（80+个），导致资源浪费和代码更新不生效

**根本原因：**
- **设计缺陷**：每次运行 `celery_manager.py` 创建新实例，无法跟踪已存在的进程
- **缺少全局发现**：管理器无法检测系统中已存在的 Celery 进程
- **多入口启动**：3种不同方式启动 worker，互相不知情

**解决方案 (v1.3.0 已修复)：**
```bash
# 1. 自动进程发现和管理（推荐）
python celery_manager.py start --simple
# → 系统会自动发现现有进程并询问是否替换

# 2. 手动清理所有进程（紧急情况）
pkill -f "celery -A web.celery_app worker"

# 3. 检查进程发现功能
python -c "
from celery_manager import CeleryManager
manager = CeleryManager()
print(f'发现的workers: {list(manager.workers.keys())}')
"
```

**预防措施：**
- ✅ 使用统一的启动入口：`celery_manager.py start --simple`
- ✅ 避免同时使用多种启动方式
- ✅ 定期检查运行的进程数量：`ps aux | grep celery | wc -l`

### 🚨 问题：下载任务无法工作
**症状：** 前端显示下载完成但实际没有下载文件

**根本原因：**
- 使用了过于复杂的配置参数
- 输出重定向导致日志无法显示  
- 队列配置不匹配

**解决方案 (按优先级)：**
```bash
# 1. 首选：使用修复后的简单模式
python celery_manager.py start --simple

# 2. 备选：使用直接命令对比调试
celery -A web.celery_app worker --loglevel=info

# 3. 检查前端控制台日志，确认任务状态
# 浏览器 F12 -> Console 查看下载相关日志
```

### 🌸 问题：Flower 启动失败
**解决方案：**
```bash
# 安装 Flower
pip install flower

# 或使用内置监控
python celery_manager.py builtin-monitor
```

### 问题：Redis 连接失败
**解决方案：**
```bash
# macOS (Homebrew)
brew install redis
brew services start redis

# 验证连接
redis-cli ping
```

### 问题：Worker 内存占用过高
**解决方案：**
- 降低 `worker_max_tasks_per_child` (已设为1000)
- 减少并发数
- 定期重启 Worker

### 📊 问题：任务堆积或性能问题
**解决方案：**
```bash
# 检查任务状态
python celery_manager.py monitor --simple

# 增加并发数
python celery_manager.py start --simple --concurrency 4

# 重启清理
python celery_manager.py restart --worker worker1
```

### 🔍 调试技巧

**查看实时日志：**
```bash
# 简单模式会直接显示日志到终端
python celery_manager.py start --simple

# 直接命令看更详细日志
celery -A web.celery_app worker --loglevel=debug
```

**检查任务执行：**
```bash
# Python 交互式检查
python -c "
from web.celery_app import celery_app
inspect = celery_app.control.inspect()
print('Active tasks:', inspect.active())
print('Scheduled tasks:', inspect.scheduled())
"
```

## 📈 性能优化建议

1. **合理设置并发数**
   - CPU 密集型：并发数 = CPU核心数
   - IO 密集型：并发数 = CPU核心数 × 2

2. **监控系统资源**
   - CPU 使用率 < 80%
   - 内存使用率 < 90%
   - 磁盘空间 > 1GB

3. **定期清理**
   - 设置任务结果过期时间（1小时）
   - 定期重启 Worker 进程
   - 清理临时文件

4. **错误处理**
   - 设置合理的重试次数
   - 记录详细的错误日志
   - 实现任务降级策略

## 🎯 最佳实践

### 📋 推荐使用流程

**日常使用（推荐）：**
```bash
# 1. 启动简单模式 Worker（现已支持智能进程检测）
python celery_manager.py start --simple
# → 如发现现有进程，会询问是否替换

# 2. 启动 Web 服务器
python start_web_server.py

# 3. 测试下载功能
# 访问 http://localhost:8000 进行测试
```

**开发调试：**
```bash
# 1. 使用直接命令查看详细日志
celery -A web.celery_app worker --loglevel=debug

# 2. 监控任务状态
python celery_manager.py builtin-monitor --port 8001
```

**生产环境：**
```bash
# 使用一键启动脚本
python start_all_services.py
```

### 💡 性能调优建议

1. **合理设置并发数**
   - 简单模式：自动设置为 CPU 核心数（最大4个）
   - 下载任务：建议 1-2 个并发（避免网络拥堵）
   - IO 密集型：可以增加到 CPU 核心数 × 2

2. **监控系统资源**
   - CPU 使用率 < 80%
   - 内存使用率 < 90%  
   - 磁盘空间 > 1GB

3. **日志和调试**
   - 使用简单模式获得清晰的日志输出
   - 必要时使用 `--loglevel=debug` 进行详细调试
   - 检查浏览器控制台的前端日志

## 📞 获取帮助

### 命令行帮助
```bash
# 查看所有可用命令
python celery_manager.py --help

# 查看特定命令的详细选项  
python celery_manager.py start --help
```

### 🔄 版本更新日志

**v1.3.0 - 2025年进程管理修复版本 (MAJOR)**
- 🔥 **修复进程积累问题**：添加全局进程发现机制，防止worker进程无限积累
- ✅ **智能启动检查**：启动前自动检测现有进程，提供安全替换选项
- ✅ **批量进程管理**：新增 `stop_all_existing_workers()` 和 `discover_existing_workers()` 功能
- ✅ **用户确认机制**：启动新worker前询问是否停止现有进程，避免意外重复
- ✅ **完整下载流程修复**：解决了前端-后端连接问题，现在下载任务完全正常

**v1.2.0 - 2024 年修复版本**
- ✅ 修复了简单模式下载任务无法工作的问题
- ✅ 移除了导致日志隐藏的输出重定向
- ✅ 简化了启动参数，提高兼容性
- ✅ 增加了调试和故障排除指南
- ✅ 更新了前端下载逻辑，正确使用缓存文件

**主要改进：**
- **进程管理革命**：从根本上解决了worker进程积累的设计缺陷
- **智能化启动**：每次启动都会扫描现有进程，提供清晰的管理选项
- **下载系统完整性**：前端Celery任务结果正确连接到文件服务
- **用户体验**：提供清晰的进程状态显示和确认机制