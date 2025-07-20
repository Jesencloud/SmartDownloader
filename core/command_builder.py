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

    def build_combined_download_cmd(self, output_path: str, url: str, format_id: str = None) -> Tuple[List[str], str]:
        """
        构建合并视频+音频下载命令
        
        Args:
            output_path: 输出目录
            url: 视频URL
            format_id: 要下载的特定视频格式ID (可选)
            
        Returns:
            tuple: (命令列表, 使用的格式)
        """
        cmd = self.build_yt_dlp_base_cmd()
        
        output_template = f"{output_path}/%(title)s.%(ext)s"
        
        # 如果指定了format_id，则组合视频和音频流
        if format_id and format_id != 'best':
            # 格式为: 视频流ID+bestaudio
            combined_format = f"{format_id}+bestaudio"
            log.info(f'使用视频格式: {format_id} + 最佳音频流')
        else:
            # 使用默认格式，通常是 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
            combined_format = config.downloader.ytdlp_combined_format
            log.info(f'使用默认的视频+音频格式: {combined_format}')
        
        cmd.extend([
            '-f', combined_format,
            '--merge-output-format', config.downloader.ytdlp_merge_output_format,
            '--newline',
            '--embed-subs',  # 嵌入字幕（如果可用）
            '--embed-thumbnail',  # 嵌入缩略图
            '--embed-metadata',  # 嵌入元数据
            '--embed-chapters',  # 嵌入章节信息
            '--audio-quality', '0',  # 最佳音频质量
            '--audio-format', 'best',  # 最佳音频格式
            '-o', output_template,
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