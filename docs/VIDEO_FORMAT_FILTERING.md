# 视频格式过滤机制文档

本文档详细说明了 SmartDownloader 在视频解析时使用的格式过滤条件和策略。

## 概述

SmartDownloader 使用多层过滤机制来选择最优的视频和音频格式，确保在保证质量的前提下选择兼容性最好的格式进行下载。

## 主要过滤条件

### 1. 分辨率过滤

**实现位置**: `web/main.py` 第471-472行

- **最高分辨率优先**: 只保留前3个最高分辨率
- **像素排序**: 按 `width * height` 计算像素数量排序
- **视频模式优化**: 在视频模式下进行分辨率筛选

```python
# 按像素数量排序，保留前3个最高分辨率
sorted_formats = sorted(video_formats, key=resolution_score, reverse=True)[:3]
```

### 2. 格式类型过滤

**实现位置**: `web/main.py` 第440-444行

#### 视频格式识别
- 排除 `vcodec` 为 `"none", None, "audio only"` 的格式
- 保留有效的视频编解码器

#### 音频格式识别
音频格式需满足以下任一条件：
- `acodec` 不在 `("none", None, "video only")` 中
- `resolution == "audio only"`
- `format_id` 包含 `"audio"` 关键词
- 没有 `width` 和 `height` 信息

### 3. 编解码器偏好

**实现位置**: `core/format_analyzer.py` 第64-67行

```python
preferred_video_codecs = ["avc1", "h264", "mp4v"]
preferred_audio_codecs = ["mp4a", "aac", "m4a"]
preferred_containers = ["mp4", "m4v"]
```

- **视频编解码器**: 偏好 H264/AVC1，兼容性最好
- **音频编解码器**: 偏好 AAC/MP4A，质量和兼容性平衡
- **容器格式**: 偏好 MP4，广泛支持

### 4. 文件大小优化

**实现位置**: `web/main.py` 第480-508行

- **同分辨率最小**: 同分辨率下选择文件大小最小的格式
- **智能估算**: 对缺失文件大小的格式进行估算
- **无硬性限制**: 不设置文件大小上限，优先质量

```python
# 同分辨率下按文件大小排序
if filesize_a and filesize_b:
    return filesize_a - filesize_b  # 选择较小的文件
```

### 5. 音频质量评分系统

**实现位置**: `core/format_analyzer.py` 第449-520行

#### 基础得分计算
```python
score = 0
if format_info.get('abr'):
    score += format_info['abr'] / 10
elif format_info.get('tbr'):
    score += format_info['tbr'] / 20
```

#### 加分项目
- **比特率得分**: `abr/10` 或 `tbr/20`
- **编解码器加分**: MP4A/AAC +10分
- **容器格式加分**: 
  - M4A/AAC: +5分
  - MP3/OPUS: +3分
- **特殊标识符优先级**:
  - `"original (default)"`: +50分
  - `"default"`: +30分
  - `"original"`: +20分
- **语言偏好**: 主要语言(en-US, ja, ko等) +10分

### 6. 智能选择策略

#### 流类型判断

**实现位置**: `core/format_analyzer.py` 第111-161行

**完整流识别条件**:
- `vcodec == "unknown"` 且 `acodec == "unknown"` 且有分辨率
- `vcodec` 和 `acodec` 都为 `None` 且有分辨率  
- 既有视频又有音频编解码器

#### 格式评分系统

**综合评分计算**:
- **分辨率分数**: 最高100分 (4K=100, 1080p=80)
- **比特率分数**: 最高20分
- **容器偏好**: MP4 +10分，WebM/MKV +5分
- **完整流奖励**: +20分

## 配置文件设置

**配置位置**: `config.yaml` 第44-69行

```yaml
downloader:
  ytdlp_video_format: "bestvideo"
  ytdlp_audio_format: "bestaudio"  
  ytdlp_combined_format: "bestvideo+bestaudio/best"
  ytdlp_merge_output_format: "mp4"
```

**支持的媒体格式**:
```yaml
media_extensions:
  video: [".mp4", ".webm", ".avi", ".mkv", ".mov"]
  audio: [".mp3", ".m4a", ".opus", ".aac", ".wav", ".flac"]
```

## 下载模式差异

### 视频模式
1. 优先MP4格式
2. 保留最高3个分辨率
3. 同分辨率选最小文件大小
4. 智能音频流匹配

### 音频模式  
1. 使用FormatAnalyzer智能选择
2. 优先"original (default)"标记
3. 偏好AAC/M4A编解码器
4. 考虑比特率和语言偏好

## 性能优化考虑

### DASH/HLS清单处理

**不同命令的清单策略**:
- `build_yt_dlp_base_cmd()`: 不跳过清单（获取完整格式）
- `build_yt_dlp_base_cmd_no_progress()`: 跳过清单（提升速度）
- `build_yt_dlp_info_cmd()`: 不跳过清单（完整信息获取）

### 解析时间权衡
- **跳过清单**: 解析快2-5秒，但格式选择有限
- **不跳过清单**: 解析慢3-8秒，但获得完整高质量格式

## 最佳实践建议

1. **质量优先场景**: 使用完整清单解析，获得最佳格式选择
2. **速度优先场景**: 跳过DASH/HLS清单，快速解析基础格式
3. **兼容性优先**: 优先选择MP4容器和H264/AAC编解码器
4. **存储优化**: 利用文件大小过滤选择合适的质量-大小平衡点

## 相关文件

- `web/main.py`: Web端格式过滤逻辑
- `core/format_analyzer.py`: 智能格式分析器
- `core/command_builder.py`: 命令构建和清单策略
- `config.yaml`: 格式选择配置