# SmartDownloader 使用说明

## 功能概述

SmartDownloader 是一个智能媒体下载和AI字幕生成工具，支持三种主要模式：

1. **video模式**：下载在线视频
2. **both模式**：下载视频并提取音频
3. **subtitle模式**：为本地媒体文件生成AI字幕

## 基本用法

### 1. 下载在线视频
```bash
# 下载单个视频
python main.py https://www.youtube.com/watch?v=VIDEO_ID

# 下载播放列表
python main.py https://www.youtube.com/playlist?list=PLAYLIST_ID

# 下载视频并提取音频
python main.py -m both https://www.youtube.com/watch?v=VIDEO_ID
```

### 2. 批量处理URL
```bash
# 从文件读取URL列表
python main.py -b urls.txt

# urls.txt 文件格式：
# https://www.youtube.com/watch?v=VIDEO_ID1
# https://www.youtube.com/watch?v=VIDEO_ID2
# # 这是注释，会被忽略
```

### 3. 为本地文件生成AI字幕 🆕
```bash
# 为单个视频文件生成字幕
python main.py -m subtitle video.mp4

# 为多个文件批量生成字幕
python main.py -m subtitle video1.mp4 video2.mkv audio.wav

# 使用通配符批量处理
python main.py -m subtitle *.mp4
```

## 支持的媒体格式

### 视频格式
MP4, AVI, MKV, MOV, WMV, FLV, WebM, M4V, MPG, MPEG, 3GP, OGV, TS, MTS, M2TS

### 音频格式
MP3, WAV, FLAC, AAC, OGG, WMA, M4A, Opus

## 命令行参数

- `-m, --mode`: 运行模式
  - `video`: 仅下载视频（默认）
  - `both`: 下载视频和音频
  - `subtitle`: 为本地文件生成AI字幕
- `-b, --batch-file`: 从文件读取URL列表
- `-p, --proxy`: 设置代理服务器
- `--ai-subs`: 为下载的视频生成AI字幕

## 配置文件

所有设置都可以通过 `config.yaml` 配置文件自定义：

- 下载文件夹位置
- Whisper模型选择
- 文件名长度限制
- 网络重试参数
- AI字幕翻译设置

详细配置说明请查看 `CONFIG.md`

## 使用示例

### 示例1：下载YouTube视频并生成字幕
```bash
python main.py --ai-subs https://www.youtube.com/watch?v=VIDEO_ID
```

### 示例2：为已下载的视频生成字幕
```bash
python main.py -m subtitle "downloaded_video.mp4"
```

### 示例3：批量处理本地视频库
```bash
python main.py -m subtitle /Users/username/Videos/*.mp4
```

### 示例4：使用代理下载
```bash
python main.py -p http://127.0.0.1:7890 https://www.youtube.com/watch?v=VIDEO_ID
```

## 输出文件

### 下载模式
- 视频文件：`001_video_title.mp4`
- 音频文件：`001_video_title.mp3`（如果使用both模式）
- 信息文件：`001_video_title.txt`
- AI字幕：`001_video_title.srt`（如果启用）

### 字幕模式输出

**字幕文件位置**：字幕文件会生成在与原始媒体文件相同的目录下

```bash
# 示例：处理以下文件结构
/Users/username/Videos/
├── movie1.mp4
├── movie2.mkv
└── subfolder/
    └── documentary.mp4

# 运行命令
python main.py -m subtitle /Users/username/Videos/*.mp4 /Users/username/Videos/subfolder/*.mp4

# 生成结果
/Users/username/Videos/
├── movie1.mp4
├── movie1.en.srt          # 英文字幕
├── movie1.zh-CN.srt       # 中文字幕
├── movie1.srt             # 合并字幕
├── movie2.mkv
├── movie2.en.srt
├── movie2.zh-CN.srt
├── movie2.srt
└── subfolder/
    ├── documentary.mp4
    ├── documentary.en.srt
    ├── documentary.zh-CN.srt
    └── documentary.srt
```

## 故障排除

### 常见问题

1. **"AI库未安装"错误**
   ```bash
   pip install deep-translator openai-whisper
   ```

2. **"未找到ffmpeg"错误**
   - macOS: `brew install ffmpeg`
   - Ubuntu: `sudo apt install ffmpeg`
   - Windows: 下载ffmpeg并添加到PATH

3. **代理连接失败**
   - 检查代理服务器地址
   - 程序会自动重试，等待时间较长属正常

4. **字幕生成很慢**
   - 修改配置文件中的whisper_model为更小的模型（如tiny.en）
   - AI转录需要时间，请耐心等待

### 配置优化

根据需要调整 `config.yaml` 中的设置：
- 修改下载文件夹位置
- 调整Whisper模型大小（精度vs速度）
- 设置是否翻译字幕
- 自定义文件名长度和等待时间

更多详细配置请参考 `CONFIG.md`