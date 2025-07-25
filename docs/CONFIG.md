# SmartDownloader 配置说明

## 概述
SmartDownloader 现在支持通过 `config.yaml` 文件进行配置，用户可以在不修改代码的情况下自定义程序的各种行为。

## 配置文件位置
配置文件应放置在项目根目录：`config.yaml`

如果配置文件不存在，程序会自动使用默认配置并提示用户。

## 主要配置项

### 1. 文件夹和路径设置 (folders)
```yaml
folders:
  # 下载文件夹设置
  base_download_folder: "downloads"     # 基础下载文件夹名称
  use_timestamp_folder: true            # 是否在下载文件夹下创建时间戳子文件夹
  timestamp_format: "%Y%m%d-%H%M%S"     # 时间戳格式
  
  # 自定义下载路径 (如果设置了此项，会忽略上面的base_download_folder设置)
  custom_download_path: null            # 例如: "/Users/username/MyDownloads"
  
  # 相对路径设置
  relative_to_script: true              # 路径是否相对于脚本位置 (false=相对于当前工作目录)
```

**文件夹配置说明：**
- **base_download_folder**: 基础下载文件夹名称，默认为"downloads"
- **use_timestamp_folder**: 是否在基础文件夹下创建带时间戳的子文件夹
- **timestamp_format**: 时间戳的格式，支持Python的strftime格式
- **custom_download_path**: 自定义完整下载路径，设置后会忽略base_download_folder
- **relative_to_script**: 相对路径的基准，true=相对于脚本位置，false=相对于当前工作目录

**文件夹路径示例：**
```yaml
# 示例1: 默认设置 - 脚本目录下的downloads/时间戳/
folders:
  base_download_folder: "downloads"
  use_timestamp_folder: true
  
# 示例2: 固定位置，无时间戳子文件夹
folders:
  base_download_folder: "MyVideos"
  use_timestamp_folder: false
  
# 示例3: 完全自定义路径
folders:
  custom_download_path: "/Users/username/Downloads/Videos"
  use_timestamp_folder: true
  
# 示例4: 相对于当前工作目录
folders:
  base_download_folder: "downloads"
  relative_to_script: false
```

### 2. 下载器设置 (downloader)
```yaml
downloader:
  max_retries: 3                # 最大重试次数
  base_delay: 10                # 基础延迟秒数
  max_delay: 300                # 最大延迟秒数
  backoff_factor: 2             # 退避系数
  
  # 网络超时设置
  network_timeout: 60           # 网络超时时间（秒）
  stall_detection_time: 30      # 停滞检测时间（秒）
  stall_check_interval: 5       # 停滞检查间隔（秒）
  stall_threshold_count: 6      # 停滞阈值次数
  
  # 代理设置
  proxy_retry_base_delay: 30    # 代理重试基础延迟（秒）
  proxy_retry_increment: 10     # 代理重试递增延迟（秒）
  proxy_retry_max_delay: 120    # 代理重试最大延迟（秒）
  
  # 临时文件清理模式
  cleanup_patterns:
    - "*.part"
    - "*.temp"
    - "*.ytdl"
    - "*.tmp"
    - "*.download"
    - "*.partial"
    - "*.f*"
```

### 2. 文件处理设置 (file_processing)
```yaml
file_processing:
  filename_max_length: 50       # 文件名最大长度
  filename_truncate_suffix: "..." # 文件名截断后缀
  polite_wait_time: 3           # 下载间隔等待时间（秒）
  
  # 临时文件清理模式
  cleanup_patterns:
    - "*.part"
    - "*.part-*"
    - "*.ytdl"
    - "*.tmp.*"
    - "*.f*"
```

### 3. AI字幕设置 (ai_subtitles)
```yaml
ai_subtitles:
  whisper_model: "base.en"      # Whisper模型选择
  whisper_device: "auto"        # 设备选择 (auto, cpu, cuda)
  translate_to_chinese: true    # 是否翻译为中文
  translator_service: "google"  # 翻译服务提供商
  subtitle_formats:             # 支持的字幕格式
    - "srt"
    - "vtt"
```

**可用的Whisper模型：**
- `tiny.en` - 最小模型，速度最快，准确度较低
- `base.en` - 默认模型，平衡速度和准确度
- `small.en` - 中等模型，较好准确度
- `medium.en` - 大模型，高准确度
- `large` - 最大模型，最高准确度但速度最慢

### 4. 日志设置 (logging)
```yaml
logging:
  level: "INFO"                 # 日志级别
  log_filename: "downloader.log" # 日志文件名
  
  # 控制台显示关键词
  console_keywords:
    - "🚀 智能媒体下载"
    - "🎉 全部任务完成"
    - "📁 日志与所有文件保存在"
```

### 5. 用户界面设置 (ui)
```yaml
ui:
  progress_bar_width: null      # 进度条宽度 (null为自动)
  show_transfer_speed: true     # 显示传输速度
  show_time_remaining: true     # 显示剩余时间
  show_detailed_errors: true    # 显示详细错误信息
  show_network_status: true     # 显示网络状态信息
```

### 6. 高级设置 (advanced)
```yaml
advanced:
  ytdlp_extra_args: []          # 额外的yt-dlp参数
  
  # 网络检测
  connectivity_test_host: "8.8.8.8"  # 网络连接测试主机
  connectivity_test_port: 53          # 网络连接测试端口
  connectivity_timeout: 5             # 网络连接测试超时
  
  # 代理检测
  proxy_test_url: "http://httpbin.org/ip"  # 代理测试URL
  proxy_test_timeout: 10                   # 代理测试超时
```

## 常用配置示例

### 1. 加快下载速度（降低等待时间）
```yaml
file_processing:
  polite_wait_time: 1           # 减少到1秒
```

### 2. 使用更精确的Whisper模型
```yaml
ai_subtitles:
  whisper_model: "medium.en"    # 使用更大的模型
```

### 3. 只生成英文字幕，不翻译
```yaml
ai_subtitles:
  translate_to_chinese: false   # 禁用中文翻译
```

### 4. 增加代理重试等待时间
```yaml
downloader:
  proxy_retry_base_delay: 60    # 增加到60秒
  proxy_retry_max_delay: 300    # 最大等待5分钟
```

### 5. 调整文件名长度
```yaml
file_processing:
  filename_max_length: 80       # 增加到80字符
```

### 6. 自定义下载文件夹位置
```yaml
# 设置固定的下载文件夹，不使用时间戳
folders:
  base_download_folder: "MyDownloads"
  use_timestamp_folder: false

# 或者使用完全自定义的路径
folders:
  custom_download_path: "/Users/username/Videos"
  use_timestamp_folder: true
```

### 7. 修改时间戳格式
```yaml
folders:
  timestamp_format: "%Y-%m-%d_%H-%M-%S"  # 格式: 2024-01-15_14-30-25
```

### 8. 为本地文件生成AI字幕
```bash
# 为单个视频文件生成字幕
python main.py -m subtitle video.mp4

# 为多个文件批量生成字幕
python main.py -m subtitle *.mp4 *.mkv

# 为音频文件生成字幕
python main.py -m subtitle audio.wav
```

## 配置验证
程序启动时会自动验证配置文件的正确性：
- 检查必要参数的类型和范围
- 验证Whisper模型名称的有效性
- 验证时间戳格式的正确性
- 确保数值参数在合理范围内
- 验证文件夹路径配置的有效性

如果发现配置错误，程序会显示具体的错误信息并使用默认值。

## 故障排除

### 配置文件格式错误
如果看到 "配置文件格式错误" 提示：
1. 检查YAML语法是否正确
2. 确保缩进使用空格而非制表符
3. 检查引号匹配

### 模型文件未找到
如果看到 "模型文件未找到" 错误：
1. 确保已安装对应的Whisper模型
2. 检查模型名称是否正确
3. 模型文件路径：`~/.cache/whisper/whisper.cpp/`

### 网络连接问题
如果遇到代理相关问题：
1. 调整 `proxy_retry_base_delay` 增加等待时间
2. 检查 `proxy_test_url` 是否可访问
3. 确认代理服务器地址正确

### 文件夹权限问题
如果遇到文件夹创建失败：
1. 检查指定路径的写入权限
2. 确保父目录存在
3. 程序会自动回退到当前目录下的时间戳文件夹

### 自定义路径问题
如果自定义下载路径不生效：
1. 检查路径格式是否正确（使用正斜杠 / ）
2. 确保 `custom_download_path` 不为空字符串
3. Windows用户注意使用正斜杠或双反斜杠