# core/command_builder.py

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config_manager import config

from .format_analyzer import DownloadStrategy, FormatAnalyzer

log = logging.getLogger(__name__)


class CommandBuilder:
    """负责构建各种命令行命令"""

    def __init__(self, proxy: Optional[str] = None, cookies_file: Optional[str] = None):
        self.proxy = proxy
        self.cookies_file = cookies_file
        self.format_analyzer = FormatAnalyzer()

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
        cmd = [
            "yt-dlp",
            "--ignore-config",
            "--no-warnings",
            "--no-color",
            "--force-overwrites",
            "--force-ipv4",
        ]

        # 统一临时文件路径管理
        temp_path = config.downloader.temp_path
        if temp_path:
            Path(temp_path).mkdir(parents=True, exist_ok=True)
            cmd.extend(["--paths", f"temp:{temp_path}"])

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        cmd.extend(["--progress", "--progress-template", "%(progress)j"])
        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])
        cmd.extend(
            [
                "--no-check-certificate",
                "--prefer-insecure",
                "--no-part",
                "--no-mtime",
                "--concurrent-fragments",
                "4",
            ]
        )
        return cmd

    def build_yt_dlp_base_cmd_no_progress(self) -> List[str]:
        """构建一个没有进度条的基础yt-dlp命令，用于捕获输出"""
        cmd = [
            "yt-dlp",
            "--ignore-config",
            "--no-warnings",
            "--no-color",
            "--force-overwrites",
            "--force-ipv4",
        ]

        # 统一临时文件路径管理
        temp_path = config.downloader.temp_path
        if temp_path:
            Path(temp_path).mkdir(parents=True, exist_ok=True)
            cmd.extend(["--paths", f"temp:{temp_path}"])

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])
        cmd.extend(
            [
                "--no-check-certificate",
                "--prefer-insecure",
                "--no-part",
                "--no-mtime",
                "--concurrent-fragments",
                "4",
            ]
        )
        return cmd

    def build_video_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建视频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        video_format = config.downloader.ytdlp_video_format
        cmd.extend(["-f", video_format, "--newline", "-o", output_path, url])
        return cmd

    def build_audio_download_cmd(self, url: str, output_template: str, audio_format: str = "mp3") -> List[str]:
        """构建音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd_no_progress()
        cmd.extend(["--extract-audio"])
        if audio_format == "best_original_audio":
            cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best"])
        elif audio_format in ["mp3", "m4a", "wav", "opus", "aac", "flac"]:
            cmd.extend(["-f", "bestaudio/best", "--audio-format", audio_format, "--audio-quality", "0"])
        else:
            cmd.extend(["-f", audio_format])
        cmd.extend(["--newline", "-o", output_template, url])
        return cmd

    def build_streaming_download_cmd(self, output_path: str, url: str, format_spec: str = "best") -> List[str]:
        """构建浏览器直流下载命令（后台元数据嵌入模式）"""
        cmd = self.build_yt_dlp_base_cmd_no_progress()  # 依赖基础命令
        from utils import create_simplified_identifier

        simplified_source = create_simplified_identifier(url)
        cmd.extend(
            [
                "--add-metadata",
                "--embed-metadata",
                "--xattrs",
                "--replace-in-metadata",
                "webpage_url",
                "^.*$",
                simplified_source,
                "--replace-in-metadata",
                "comment",
                "^.*$",
                f"Source: {simplified_source}",
            ]
        )
        cmd.extend(["-f", format_spec, "--newline", "-o", output_path, url])
        return cmd

    def build_streaming_download_cmd_to_stdout(
        self,
        url: str,
        format_spec: str = "best",
        byte_range: Optional[Tuple[int, Optional[int]]] = None,
        temp_dir_path: Optional[str] = None,
    ) -> List[str]:
        """构建浏览器直流下载命令，将内容输出到stdout，支持范围请求和自定义临时目录"""
        cmd = [
            "yt-dlp",
            "--ignore-config",
            "--no-warnings",
            "--no-color",
            "--force-overwrites",
            "--force-ipv4",
            "--no-progress",
        ]

        # 直流模式使用专用的、每次都清理的临时目录
        if temp_dir_path:
            cmd.extend(["--paths", f"temp:{temp_dir_path}"])
        else:
            # 如果没有提供专用目录，则使用配置中的全局临时目录
            temp_path = config.downloader.temp_path
            if temp_path:
                Path(temp_path).mkdir(parents=True, exist_ok=True)
                cmd.extend(["--paths", f"temp:{temp_path}"])

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])
        cmd.extend(
            [
                "--no-check-certificate",
                "--prefer-insecure",
                "--no-part",
                "--no-mtime",
                "--concurrent-fragments",
                "4",
            ]
        )

        if byte_range:
            start, end = byte_range
            end_str = str(end) if end is not None else ""
            cmd.extend(["--download-section", f"*{start}-{end_str}"])
            log.info(f"为yt-dlp构建范围下载: *{start}-{end_str}")

        cmd.extend(["-f", format_spec, "-o", "-", url])
        return cmd

    def build_separate_video_download_cmd(
        self,
        output_path: str,
        url: str,
        file_prefix: str,
        format_id: Optional[str] = None,
    ) -> List[str]:
        """
        构建独立的视频部分下载命令。

        Args:
            output_path: 输出目录
            url: 视频URL
            file_prefix: 文件前缀
            format_id: 要下载的特定视频格式ID (可选)

        Returns:
            list: 命令列表
        """
        cmd = self.build_yt_dlp_base_cmd()
        # 使用可预测的文件名模板
        output_template = Path(output_path) / f"{file_prefix}.video.%(ext)s"

        video_format = format_id or "bestvideo[ext=mp4]/bestvideo"

        cmd.extend(["-f", video_format, "--newline", "-o", str(output_template), "--", url])
        return cmd

    def build_separate_audio_download_cmd(self, output_path: str, url: str, file_prefix: str) -> List[str]:
        """
        构建独立的音频部分下载命令。

        Args:
            output_path: 输出目录
            url: 视频URL
            file_prefix: 文件前缀

        Returns:
            list: 命令列表
        """
        cmd = self.build_yt_dlp_base_cmd()
        # 使用可预测的文件名模板
        output_template = Path(output_path) / f"{file_prefix}.audio.%(ext)s"
        audio_format = "bestaudio[ext=m4a]/bestaudio"
        cmd.extend(["-f", audio_format, "--newline", "-o", str(output_template), "--", url])
        return cmd

    def build_combined_download_cmd(
        self,
        output_path: str,
        url: str,
        file_prefix: str,
        format_id: str = None,
        resolution: str = None,
    ) -> Tuple[List[str], str, Path]:
        """
        构建合并视频+音频下载命令

        Args:
            output_path: 输出目录
            url: 视频URL
            file_prefix: 文件前缀 (不含扩展名)
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (可选，例如: '720p60')

        Returns:
            tuple: (命令列表, 使用的格式, 确切的输出文件路径)
        """
        cmd = self.build_yt_dlp_base_cmd()

        # 确保下载目录存在
        output_dir = Path(output_path).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        # 构建确切的输出文件路径，强制使用 .mp4 扩展名
        exact_output_path = output_dir / f"{file_prefix}.mp4"
        log.info(f"确切的输出路径: {exact_output_path}")

        # 构建格式选择器 - 简化格式选择，优先使用mp4容器
        if format_id and format_id != "best":
            # 使用指定的视频格式 + 最佳音频
            combined_format = f"{format_id}+bestaudio"
        else:
            # 默认使用 mp4 容器格式, yt-dlp 会选择最佳的视频和音频流
            combined_format = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

        # 输出格式组合信息
        log.info(f"🎬 视频音频组合: {combined_format}")

        # 添加格式选择
        cmd.extend(["-f", combined_format])

        # 简化命令，移除可能导致问题的后处理步骤
        cmd.extend(
            [
                "--merge-output-format",
                "mp4",  # 确保合并后的文件是mp4格式
                "--newline",
                "--no-warnings",  # 减少警告信息
                "--no-playlist",  # 不下载播放列表
                "--no-keep-fragments",  # 删除下载的片段
                "--hls-prefer-native",  # 优先使用原生HLS下载
                "-o",
                str(exact_output_path),
                "--",  # 分隔符，防止URL被误解为参数
                url,
            ]
        )

        return cmd, combined_format, exact_output_path

    def build_smart_download_cmd(
        self,
        output_path: str,
        url: str,
        file_prefix: str,
        formats: List[Dict[str, Any]],
        format_id: str = None,
        resolution: str = None,
    ) -> Tuple[List[str], str, Path, DownloadStrategy]:
        """
        构建智能下载命令 - 自动判断使用完整流还是分离流策略

        Args:
            output_path: 输出目录
            url: 视频URL
            file_prefix: 文件前缀 (不含扩展名)
            formats: 从yt-dlp获取的格式列表
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (可选，例如: '720p60')

        Returns:
            tuple: (命令列表, 使用的格式, 确切的输出文件路径, 下载策略)
        """
        try:
            # 分析格式并获取最佳下载计划
            download_plan = self.format_analyzer.find_best_download_plan(formats, format_id)

            log.info(f"智能下载策略: {download_plan.strategy.value} - {download_plan.reason}")

            # 确保下载目录存在
            output_dir = Path(output_path).resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            exact_output_path = output_dir / f"{file_prefix}.mp4"

            if download_plan.strategy == DownloadStrategy.DIRECT:
                # 直接下载完整流
                return self._build_direct_download_cmd(
                    url,
                    exact_output_path,
                    download_plan.primary_format.format_id,
                    download_plan.strategy,
                )

            elif download_plan.strategy == DownloadStrategy.MERGE:
                # 构建合并下载命令
                video_format_id = download_plan.primary_format.format_id
                audio_format_id = (
                    download_plan.secondary_format.format_id if download_plan.secondary_format else "bestaudio"
                )
                combined_format = f"{video_format_id}+{audio_format_id}"

                # 输出视频音频组合信息
                log.info(f"🎬 视频音频组合: {combined_format}")

                return self._build_merge_download_cmd(url, exact_output_path, combined_format, download_plan.strategy)

        except Exception as e:
            log.warning(f"智能格式分析失败: {e}，降级到传统方法")
            # 降级到原有的组合下载逻辑
            cmd, format_str, path = self.build_combined_download_cmd(
                output_path, url, file_prefix, format_id, resolution
            )
            return cmd, format_str, path, DownloadStrategy.DIRECT

    def _build_direct_download_cmd(
        self, url: str, output_path: Path, format_id: str, strategy: DownloadStrategy
    ) -> Tuple[List[str], str, Path, DownloadStrategy]:
        """构建直接下载完整流的命令"""
        cmd = self.build_yt_dlp_base_cmd()

        cmd.extend(
            [
                "-f",
                format_id,
                "--merge-output-format",
                "mp4",
                "--newline",
                "--no-warnings",
                "--no-playlist",
                "--no-keep-fragments",
                "--hls-prefer-native",
                "-o",
                str(output_path),
                "--",
                url,
            ]
        )

        log.info(f"构建直接下载命令: 格式={format_id}")
        return cmd, format_id, output_path, strategy

    def _build_merge_download_cmd(
        self,
        url: str,
        output_path: Path,
        combined_format: str,
        strategy: DownloadStrategy,
    ) -> Tuple[List[str], str, Path, DownloadStrategy]:
        """构建合并下载命令"""
        cmd = self.build_yt_dlp_base_cmd()

        # 记录合并下载的格式组合
        log.info(f"构建合并下载命令: 格式组合={combined_format}")

        cmd.extend(
            [
                "-f",
                combined_format,
                "--merge-output-format",
                "mp4",
                "--newline",
                "--no-warnings",
                "--no-playlist",
                "--no-keep-fragments",
                "--hls-prefer-native",
                "-o",
                str(output_path),
                "--",
                url,
            ]
        )

        log.info(f"构建合并下载命令: 格式={combined_format}")
        return cmd, combined_format, output_path, strategy

    def build_metadata_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建元数据下载命令"""
        cmd = self.build_yt_dlp_base_cmd()

        output_template = f"{output_path}/%(title)s.%(ext)s"

        cmd.extend(
            [
                "--skip-download",
                "--write-thumbnail",
                "--convert-thumbnails",
                "png",
                "-o",
                output_template,
                url,
            ]
        )
        return cmd

    def build_yt_dlp_info_cmd(self) -> List[str]:
        """构建用于获取视频信息的yt-dlp基础命令（不跳过任何清单以获取完整格式列表）"""
        cmd = ["yt-dlp"]

        # 基础网络配置
        cmd.extend(
            [
                "--socket-timeout",
                "30",
                "--retries",
                "3",
                "--no-call-home",
                "--no-check-certificate",
            ]
        )

        # 添加代理配置（如果有）
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        # 添加cookies配置（如果有）
        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        return cmd

    def build_playlist_info_cmd(self, url: str) -> List[str]:
        """构建播放列表信息获取命令"""
        # 使用专门的信息获取命令，不跳过HLS/DASH清单
        cmd = self.build_yt_dlp_info_cmd()
        cmd.extend(["--dump-json", "--no-download", "--no-playlist", url])
        return cmd

    def build_ffmpeg_merge_cmd(self, video_path: str, audio_path: str, output_path: str) -> List[str]:
        """构建FFmpeg合并命令"""
        return [
            "ffmpeg",
            "-y",
            "-i",
            str(Path(video_path).resolve()),
            "-i",
            str(Path(audio_path).resolve()),
            "-c",
            "copy",
            str(Path(output_path).resolve()),
        ]

    def build_ffmpeg_extract_audio_cmd(self, video_path: str, audio_path: str) -> List[str]:
        """构建FFmpeg音频提取命令"""
        return [
            "ffmpeg",
            "-y",
            "-i",
            str(Path(video_path).resolve()),
            "-vn",
            "-q:a",
            "0",
            str(Path(audio_path).resolve()),
        ]

    def build_ffmpeg_convert_to_wav_cmd(self, input_path: str, output_path: str) -> List[str]:
        """构建FFmpeg WAV转换命令"""
        return [
            "ffmpeg",
            "-i",
            str(Path(input_path).resolve()),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(Path(output_path).resolve()),
        ]

    def build_whisper_cmd(self, model_path: str, source_language: str, audio_path: str) -> List[str]:
        """构建Whisper转录命令"""
        return [
            "whisper-cli",
            "-m",
            str(Path(model_path).resolve()),
            "-l",
            source_language,
            str(Path(audio_path).resolve()),
        ]
