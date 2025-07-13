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
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings', '--no-color']
        
        if self.proxy:
            cmd.extend(['--proxy', self.proxy])
        
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        
        # 添加进度模板
        cmd.extend(['--progress', '--progress-template', '%(progress)j'])
        
        return cmd

    def build_list_formats_cmd(self, url: str) -> List[str]:
        """构建获取格式列表的命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend(['--list-formats', url])
        return cmd

    def _build_video_format_string(self) -> str:
        """根据配置构建视频格式字符串（传统模式）"""
        video_quality = config.downloader.video_quality
        video_format = config.downloader.video_format_preference
        
        quality_map = {
            "4k": "[height<=2160]",
            "1080p": "[height<=1080]",
            "720p": "[height<=720]",
            "480p": "[height<=480]",
            "360p": "[height<=360]",
        }
        
        quality_selector = quality_map.get(video_quality, "")
        base_selector = "bestvideo" if video_quality != "worst" else "worstvideo"
        
        if video_format == "any":
            return f"{base_selector}{quality_selector}/{base_selector}"
        else:
            return f"{base_selector}[ext={video_format}]{quality_selector}/{base_selector}{quality_selector}"

    def _build_audio_format_string(self) -> str:
        """根据配置构建音频格式字符串（传统模式）"""
        audio_quality = config.downloader.audio_quality
        audio_format = config.downloader.audio_format_preference
        
        base_selector = "bestaudio" if audio_quality != "worst" else "worstaudio"
        
        quality_selector = ""
        if audio_quality.endswith("k"):
            bitrate = audio_quality[:-1]
            quality_selector = f"[abr<={bitrate}]"

        if audio_format == "any":
            return f"{base_selector}{quality_selector}/{base_selector}"
        else:
            return f"{base_selector}[ext={audio_format}]{quality_selector}/{base_selector}{quality_selector}"

    def build_video_download_cmd(self, output_path: str, url: str, video_id: Optional[str] = None) -> List[str]:
        """构建视频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        if video_id:
            video_format = video_id
            log.info(f"使用auto_best模式，选择视频格式: {video_format}")
        else:
            video_format = self._build_video_format_string()
            log.debug(f"使用传统模式，视频格式: {video_format}")
        
        cmd.extend([
            '-f', video_format,
            '--newline',
            '-o', output_path,
            url
        ])
        
        return cmd

    def build_audio_download_cmd(self, output_path: str, url: str, filename_prefix: str = None, audio_id: Optional[str] = None) -> List[str]:
        """构建音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        if audio_id:
            audio_format = audio_id
            log.info(f"使用auto_best模式，选择音频格式: {audio_format}")
        else:
            audio_format = self._build_audio_format_string()
            log.debug(f"使用传统模式，音频格式: {audio_format}")
        
        output_template = f"{output_path}/{filename_prefix or '%(title)s'}.%(ext)s"
        
        cmd.extend([
            '-f', audio_format,
            '--newline',
            '-o', output_template,
            url
        ])
        
        return cmd

    def build_combined_download_cmd(self, output_path: str, url: str, video_id: Optional[str] = None, audio_id: Optional[str] = None) -> Tuple[List[str], str]:
        """构建合并视频+音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        if video_id and audio_id:
            combined_format = f"{video_id}+{audio_id}"
            log.info(f"使用auto_best组合格式: {combined_format}")
        else:
            video_format = self._build_video_format_string()
            audio_format = self._build_audio_format_string()
            if "auto_best" in [config.downloader.video_quality, config.downloader.audio_quality]:
                 log.warning("auto_best模式解析失败或未完全启用，回退到传统格式")
            combined_format = f"{video_format}+{audio_format}/bestvideo+bestaudio/best"

        output_template = f"{output_path}/%(title)s.%(ext)s"
        
        cmd.extend([
            '-f', combined_format,
            '--newline',
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
