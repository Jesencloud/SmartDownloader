# core/command_builder.py

import logging
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)


class CommandBuilder:
    """负责构建各种命令行命令"""
    
    def __init__(self, proxy: Optional[str] = None, cookies_file: Optional[str] = None):
        self.proxy = proxy
        self.cookies_file = cookies_file

    def build_yt_dlp_base_cmd(self) -> List[str]:
        """构建基础的yt-dlp命令"""
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings', '--no-color']
        
        if self.proxy:
            cmd.extend(['--proxy', self.proxy])
        
        if self.cookies_file:
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        
        # 添加进度模板
        cmd.extend(['--progress', '--progress-template', '%(progress)j'])
        
        return cmd

    def build_video_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建视频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend([
            '-f', 'bestvideo[ext=mp4]/bestvideo',
            '--newline',
            '-o', output_path,
            url
        ])
        return cmd

    def build_audio_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend([
            '-f', 'bestaudio[ext=m4a]/bestaudio',
            '--newline',
            '-o', output_path,
            url
        ])
        return cmd

    def build_metadata_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建元数据下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend([
            '--skip-download',
            '--write-info-json',
            '--write-thumbnail',
            '--convert-thumbnails', 'png',
            '-o', output_path,
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