# core/command_builder.py

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from config_manager import config

log = logging.getLogger(__name__)


class CommandBuilder:
    """负责构建各种命令行命令"""

    def __init__(self, proxy: Optional[str] = None, cookies_file: Optional[str] = None):
        self.proxy = proxy
        self.cookies_file = cookies_file

    def update_cookies_file(self, new_cookies_file: str) -> None:
        """
        更新cookies文件路径
        
        Args:
            new_cookies_file: 新的cookies文件路径
        """
        self.cookies_file = new_cookies_file
        log.debug(f"已更新cookies文件路径: {new_cookies_file}")

    def build_yt_dlp_base_cmd(self) -> List[str]:
        """构建基础的yt-dlp命令"""
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings', '--no-color', '--force-overwrites']
        
        if self.proxy:
            cmd.extend(['--proxy', self.proxy])
        
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        
        # 添加进度模板
        cmd.extend(['--progress', '--progress-template', '%(progress)j'])
        
        return cmd

    def build_video_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建视频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        video_format = config.downloader.ytdlp_video_format
        
        cmd.extend([
            '-f', video_format,
            '--newline',
            '-o', output_path,
            url
        ])
        
        return cmd

    def build_audio_download_cmd(self, output_path: str, url: str, filename_prefix: str = None, format_id: Optional[str] = None, to_mp3: bool = False) -> List[str]:
        """构建音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        output_template = f"{output_path}/{filename_prefix or '%(title)s'}.%(ext)s"
        
        if to_mp3:
            # 如果需要转换为MP3，使用特定参数
            cmd.extend([
                '-f', 'bestaudio', # 选择最佳音质的源
                '--extract-audio',
                '--audio-format', 'mp3',
                '--audio-quality', '0', # 0是最高质量
            ])
        else:
            # 否则，使用指定的format_id或默认配置
            audio_format = format_id or config.downloader.ytdlp_audio_format
            cmd.extend(['-f', audio_format])

        cmd.extend([
            '--newline',
            '-o', output_template,
            url
        ])
        
        return cmd

    def build_combined_download_cmd(self, output_path: str, url: str, format_id: str = None, resolution: str = None) -> Tuple[List[str], str]:
        """
        构建合并视频+音频下载命令
        
        Args:
            output_path: 输出目录
            url: 视频URL
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (可选，例如: '720p60')
            
        Returns:
            tuple: (命令列表, 使用的格式)
        """
        cmd = self.build_yt_dlp_base_cmd()
        
        # 确保下载目录存在
        output_dir = Path(output_path).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用前端提供的分辨率信息
        if resolution and resolution != 'best':
            # 清理分辨率字符串，移除空格和特殊字符
            resolution = resolution.strip().replace(' ', '_')
            # 确保分辨率以p或i结尾（如1080p或1080i）
            if not any(resolution.lower().endswith(x) for x in ['p', 'i']):
                resolution += 'p'  # 默认添加p作为后缀
            resolution = f'_{resolution}'  # 添加下划线前缀
        
        # 构建输出模板，确保路径正确，并移除可能的多余空格
        output_template = str(output_dir / f"%(title)s{resolution if resolution else ''}.%(ext)s").replace(' .', '.').replace(' ', '_')
        log.info(f"Using output template: {output_template}")
        
        # 构建格式选择器 - 简化格式选择，优先使用mp4容器
        if format_id and format_id != 'best':
            # 使用指定的视频格式 + 最佳音频
            combined_format = f"{format_id}+bestaudio"
        else:
            # 默认使用 mp4 容器格式
            combined_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            
            
        # 添加格式选择
        cmd.extend(['-f', combined_format])
        
        # 简化命令，移除可能导致问题的后处理步骤
        cmd.extend([
            '--merge-output-format', 'mp4',  # 强制使用mp4作为输出格式
            '--newline',
            '--no-embed-subs',               # 暂时禁用字幕嵌入
            '--no-embed-thumbnail',          # 暂时禁用缩略图嵌入
            '--no-embed-metadata',           # 暂时禁用元数据嵌入
            '--no-embed-chapters',           # 暂时禁用章节嵌入
            '--audio-quality', '0',
            '--audio-format', 'best',
            '--no-check-formats',            # 不检查格式，直接下载
            '--no-warnings',                 # 减少警告信息
            '--no-playlist',                 # 不下载播放列表
            '--no-part',                     # 不生成部分下载文件
            '--no-mtime',                    # 不设置文件修改时间
            '--no-overwrites',               # 不覆盖已存在的文件
            '--no-post-overwrites',          # 不覆盖后处理文件
            '--no-keep-fragments',           # 删除下载的片段
            '--hls-prefer-native',           # 优先使用原生HLS下载
            '--downloader', 'ffmpeg',        # 使用ffmpeg下载器
            '--downloader-args', 'ffmpeg:-c copy -movflags +faststart',  # 优化mp4输出
            '-o', output_template,
            '--',  # 分隔符，防止URL被误解为参数
            url
        ])
        
        return cmd, combined_format

    def build_metadata_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建元数据下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        output_template = f"{output_path}/%(title)s.%(ext)s"
        
        cmd.extend([
            '--skip-download',
            '--write-thumbnail',
            '--convert-thumbnails', 'png',
            '-o', output_template,
            url
        ])
        return cmd

    def build_playlist_info_cmd(self, url: str) -> List[str]:
        """构建播放列表信息获取命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend([
            '--flat-playlist',
            '--print-json',
            '--skip-download',
            url
        ])
        return cmd

    def build_ffmpeg_merge_cmd(self, video_path: str, audio_path: str, output_path: str) -> List[str]:
        """构建FFmpeg合并命令"""
        return [
            'ffmpeg', '-y',
            '-i', str(Path(video_path).resolve()),
            '-i', str(Path(audio_path).resolve()),
            '-c', 'copy',
            str(Path(output_path).resolve())
        ]

    def build_ffmpeg_extract_audio_cmd(self, video_path: str, audio_path: str) -> List[str]:
        """构建FFmpeg音频提取命令"""
        return [
            'ffmpeg', '-y',
            '-i', str(Path(video_path).resolve()),
            '-vn', '-q:a', '0',
            str(Path(audio_path).resolve())
        ]

    def build_ffmpeg_convert_to_wav_cmd(self, input_path: str, output_path: str) -> List[str]:
        """构建FFmpeg WAV转换命令"""
        return [
            'ffmpeg',
            '-i', str(Path(input_path).resolve()),
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            str(Path(output_path).resolve())
        ]

    def build_whisper_cmd(self, model_path: str, source_language: str, audio_path: str) -> List[str]:
        """构建Whisper转录命令"""
        return [
            'whisper-cli',
            '-m', str(Path(model_path).resolve()),
            '-l', source_language,
            str(Path(audio_path).resolve())
        ]