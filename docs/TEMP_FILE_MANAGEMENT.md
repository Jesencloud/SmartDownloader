# 临时文件管理指南

## 📋 概述

本文档提供SmartDownloader临时文件管理的完整指南，包括监控、清理和优化策略。

## 🏗️ 架构说明

### 临时文件使用场景

SmartDownloader在以下情况下使用临时文件：

1. **元数据嵌入下载**：为了支持视频文件元数据嵌入（简化来源信息），需要先下载到临时文件
2. **流式传输优化**：下载完成后通过64KB缓冲区高效流式传输给客户端
3. **网络重试机制**：支持SSL错误等网络问题的自动重试

### 技术实现

```python
# 临时文件创建
with tempfile.NamedTemporaryFile(suffix=f".{file_extension}", delete=False) as temp_file:
    temp_path = temp_file.name

# 元数据嵌入命令
cmd = command_builder.build_streaming_download_cmd(temp_path, url, format_id)

# 高效流式传输
chunk_size = 65536  # 64KB chunks
async with aiofiles.open(temp_path, 'rb') as f:
    while True:
        chunk = await f.read(chunk_size)
        if not chunk:
            break
        yield chunk
```

## 📊 临时文件位置与监控

### 默认位置
- **macOS**: `/var/folders/r_/wft7gp413qz1yjh3fj58b4700000gn/T/`
- **Linux**: `/tmp/`
- **Windows**: `%TEMP%`

### 实时监控
系统会自动监控：
- 临时目录可用空间
- 当可用空间 < 1GB时发出警告
- 每次下载显示临时文件路径和系统状态

## 🛠️ 管理工具

### 1. 临时文件管理器 (`temp_file_manager.py`)

完整功能的Python管理脚本：

```bash
# 查看状态
python3 scripts/temp_file_manager.py status

# 预览清理（安全模式）
python3 scripts/temp_file_manager.py clean --dry-run

# 执行清理
python3 scripts/temp_file_manager.py clean --execute

# 高级选项
python3 scripts/temp_file_manager.py clean --older-than 6 --execute --smartdownloader-only
```

### 2. 便捷Shell命令 (`temp_utils.sh`)

加载后可使用简化命令：

```bash
# 加载便捷函数
source scripts/temp_utils.sh

# 使用便捷命令
temp-status                 # 查看状态
temp-clean-preview         # 预览清理
temp-clean 2               # 清理2小时前文件
temp-clean-sd 0.5          # 清理30分钟前SD文件
```

## 📈 功能特性

### 🔍 监控功能

| 功能 | 描述 |
|------|------|
| **磁盘空间检查** | 显示总计/已用/可用空间及百分比 |
| **文件分类** | 区分SmartDownloader vs 其他工具文件 |
| **时间标记** | 显示文件修改时间和年龄 |
| **大小统计** | 自动格式化显示（B/KB/MB/GB） |

### 🧹 清理功能

| 功能 | 描述 |
|------|------|
| **安全预览** | 默认dry-run模式，避免误删 |
| **时间过滤** | 可指定清理多少小时前的文件 |
| **选择性清理** | 可只清理SmartDownloader文件 |
| **错误处理** | 记录清理失败的文件和原因 |

### 🔒 安全特性

- **默认预览模式**：不会意外删除文件
- **时间保护**：只清理指定时间之前的文件  
- **详细日志**：所有操作都有完整记录
- **异常处理**：确保临时文件在任何情况下都被清理

## 🎯 使用建议

### 日常维护

1. **定期检查**（推荐每日）：
   ```bash
   temp-status
   ```

2. **预防性清理**（推荐每小时）：
   ```bash
   temp-clean-preview 1    # 先预览
   temp-clean 1           # 再执行
   ```

3. **磁盘空间紧张时**：
   ```bash
   temp-clean 0.5         # 清理30分钟前的文件
   ```

### 自动化设置

#### Cron定时任务（Linux/macOS）

```bash
# 每小时清理1小时前的临时文件
0 * * * * cd /path/to/SmartDownloader && python3 scripts/temp_file_manager.py clean --older-than 1 --execute --smartdownloader-only

# 每天凌晨清理所有临时媒体文件
0 2 * * * cd /path/to/SmartDownloader && python3 scripts/temp_file_manager.py clean --older-than 6 --execute
```

#### systemd定时器（Linux）

```ini
# /etc/systemd/system/smartdownloader-cleanup.timer
[Unit]
Description=SmartDownloader临时文件清理
Requires=smartdownloader-cleanup.service

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

### 性能优化

1. **调整缓冲区大小**：
   - 当前：64KB chunks
   - 大文件可考虑增加到128KB或256KB

2. **监控磁盘I/O**：
   - 使用`iostat`监控I/O使用率
   - 考虑将临时目录移至更快的SSD

3. **并发限制**：
   - 根据可用磁盘空间限制同时下载数量
   - 大文件下载时动态调整并发数

## 🚨 故障排除

### 常见问题

#### 1. 磁盘空间不足
```bash
# 症状：下载失败，日志显示空间不足
# 解决：
temp-clean 0    # 立即清理所有临时文件
df -h /tmp      # 检查空间释放情况
```

#### 2. 临时文件未清理
```bash
# 症状：临时文件持续积累
# 检查：
temp-status     # 查看具体情况

# 解决：
temp-clean 0 --execute    # 强制清理所有文件
```

#### 3. 权限问题
```bash
# 症状：无法删除临时文件
# 解决：
sudo python3 scripts/temp_file_manager.py clean --execute
```

### 调试模式

启用详细日志记录：

```python
import logging
logging.getLogger('web.main').setLevel(logging.DEBUG)
```

## 📋 配置选项

### 环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `TMPDIR` | 临时目录路径 | 系统默认 |
| `TEMP_CLEANUP_HOURS` | 自动清理时间阈值 | 1 |
| `TEMP_WARN_SPACE_GB` | 磁盘空间警告阈值 | 1.0 |

### 代码配置

```python
# 在web/main.py中可调整的参数
chunk_size = 65536      # 流式传输缓冲区大小
max_retries = 3         # 网络重试次数
temp_warn_space = 1.0   # 磁盘空间警告阈值(GB)
```

## 🔄 升级路径

### 未来改进计划

1. **内存流式传输**：
   - 对于小文件（<50MB）考虑纯内存流式传输
   - 避免磁盘I/O开销

2. **智能缓存**：
   - 相同URL的重复请求使用缓存
   - LRU策略管理缓存空间

3. **分布式临时存储**：
   - 支持多磁盘临时目录
   - 负载均衡分配下载任务

4. **Web界面**：
   - 添加临时文件管理的Web界面
   - 实时监控和一键清理功能

## 📚 相关文档

- [配置指南](CONFIG.md) - 系统配置选项
- [文件管理指南](FILE_MANAGEMENT_GUIDE.md) - 下载文件管理
- [技术指南](SMART_DOWNLOAD_TECHNICAL_GUIDE.md) - 下载技术细节

---

*最后更新：2025年1月*