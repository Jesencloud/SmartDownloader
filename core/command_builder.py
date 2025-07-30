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

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        # 添加进度模板
        cmd.extend(["--progress", "--progress-template", "%(progress)j"])

        # 添加健壮性参数：片段重试
        # 无限次重试片段，每次重试之间有指数退避延迟（1到30秒）
        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])

        # 添加更激进的性能优化参数
        cmd.extend(
            [
                "--no-check-certificate",  # 跳过SSL证书检查
                "--prefer-insecure",  # 优先使用HTTP而非HTTPS
                "--youtube-skip-dash-manifest",  # YouTube: 跳过DASH清单
                "--youtube-skip-hls-manifest",  # YouTube: 跳过HLS清单
                "--no-part",  # 不创建部分文件
                "--no-mtime",  # 不设置修改时间
                "--concurrent-fragments",
                "4",  # 并发片段下载
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

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        # 添加健壮性参数
        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])

        # 添加更激进的性能优化参数
        cmd.extend(
            [
                "--no-check-certificate",  # 跳过SSL证书检查
                "--prefer-insecure",  # 优先使用HTTP而非HTTPS
                "--youtube-skip-dash-manifest",  # YouTube: 跳过DASH清单
                "--youtube-skip-hls-manifest",  # YouTube: 跳过HLS清单
                "--no-part",  # 不创建部分文件
                "--no-mtime",  # 不设置修改时间
                "--concurrent-fragments",
                "4",  # 并发片段下载
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
        """
        构建音频下载命令。

        Args:
            url: 视频URL。
            output_template: yt-dlp的输出模板,可以是目录或完整路径。
            audio_format: 音频格式 (例如: 'mp3', 'm4a', 'best')。

        Returns:
            list: 命令列表。
        """
        cmd = self.build_yt_dlp_base_cmd_no_progress()

        # 始终为任何音频下载请求提取音频
        cmd.extend(["--extract-audio"])

        if audio_format == "best_original_audio":
            # 策略1: 下载最佳原始音频流 (智能适配m4a/mp4)
            cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best"])
        elif audio_format in ["mp3", "m4a", "wav", "opus", "aac", "flac"]:
            # 策略2: 下载最佳音频并转换为指定格式
            cmd.extend(["-f", "bestaudio/best"])
            cmd.extend(["--audio-format", audio_format])
            cmd.extend(["--audio-quality", "0"])
        else:
            # 策略3: 假定它是要直接下载的特定格式ID
            cmd.extend(["-f", audio_format])

        cmd.extend(["--newline", "-o", output_template, url])
        return cmd

    def build_streaming_download_cmd(self, output_path: str, url: str, format_spec: str = "best") -> List[str]:
        """构建浏览器直流下载命令，包含简化的来源元数据"""
        cmd = [
            "yt-dlp",
            "--ignore-config",
            "--no-warnings",
            "--no-color",
            "--force-overwrites",
            "--force-ipv4",
        ]

        if self.proxy:
            cmd.extend(["--proxy", self.proxy])

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd.extend(["--cookies", str(Path(self.cookies_file).resolve())])

        # 添加健壮性参数
        cmd.extend(["--fragment-retries", "infinite", "--retry-sleep", "fragment:exp=1:30"])

        # 添加更激进的性能优化参数
        cmd.extend(
            [
                "--no-check-certificate",  # 跳过SSL证书检查
                "--prefer-insecure",  # 优先使用HTTP而非HTTPS
                "--youtube-skip-dash-manifest",  # YouTube: 跳过DASH清单
                "--youtube-skip-hls-manifest",  # YouTube: 跳过HLS清单
                "--no-part",  # 不创建部分文件
                "--no-mtime",  # 不设置修改时间
                "--concurrent-fragments",
                "4",  # 并发片段下载
            ]
        )

        # 为浏览器直流下载添加简化来源元数据
        from utils import create_simplified_identifier

        simplified_source = create_simplified_identifier(url)

        cmd.extend(
            [
                "--add-metadata",  # 添加元数据到文件
                "--embed-metadata",  # 嵌入元数据到容器
                "--xattrs",  # 写入 macOS/Linux 扩展属性
                # 设置关键元数据字段
                "--replace-in-metadata",
                "webpage_url",
                "^.*$",
                simplified_source,  # yt-dlp 网页URL字段
                "--replace-in-metadata",
                "comment",
                "^.*$",
                f"Source: {simplified_source}",  # FFmpeg comment 字段
            ]
        )

        cmd.extend(["-f", format_spec, "--newline", "-o", output_path, url])
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

    def build_playlist_info_cmd(self, url: str) -> List[str]:
        """构建播放列表信息获取命令"""
        cmd = self.build_yt_dlp_base_cmd()
        cmd.extend(["--flat-playlist", "--print-json", "--skip-download", url])
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
