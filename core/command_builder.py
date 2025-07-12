# core/command_builder.py

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

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
        
        if self.cookies_file:
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        
        # 添加进度模板
        cmd.extend(['--progress', '--progress-template', '%(progress)j'])
        
        return cmd

    async def _parse_available_formats(self, url: str, log_video_format: bool = True) -> Tuple[Optional[str], Optional[str]]:
        """
        解析URL的可用格式，返回(最佳视频格式ID, 最佳音频格式ID)
        """
        try:
            cmd = self.build_yt_dlp_base_cmd()
            cmd.extend(['--list-formats', url])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                log.error(f"格式解析失败: {stderr.decode()}")
                return None, None
            
            format_output = stdout.decode()
            return self._extract_best_formats(format_output, log_video_format)
            
        except Exception as e:
            log.error(f"解析格式时出错: {e}")
            return None, None

    def _extract_best_formats(self, format_output: str, log_video_format: bool = True) -> Tuple[Optional[str], Optional[str]]:
        """
        从yt-dlp格式输出中提取最佳视频和音频格式ID
        """
        lines = format_output.split('\n')
        video_formats = []
        audio_formats = []
        
        # 解析格式表格
        in_table = False
        for line in lines:
            line = line.strip()
            
            # 跳过表头和分隔线
            if 'ID' in line and 'EXT' in line and 'RESOLUTION' in line:
                in_table = True
                continue
            if not in_table or not line or line.startswith('-'):
                continue
            
            # 解析格式行
            parts = line.split()
            if len(parts) < 3:
                continue
                
            format_id = parts[0]
            ext = parts[1]
            resolution = parts[2]
            
            # 跳过故事板和其他特殊格式
            if 'mhtml' in ext or 'storyboard' in line:
                continue
            
            # 识别视频格式（有分辨率信息且不是"audio only"）
            if 'audio only' not in line and 'x' in resolution:
                # 提取分辨率高度用于排序
                height_match = re.search(r'(\d+)x(\d+)', resolution)
                if height_match:
                    height = int(height_match.group(2))
                    video_formats.append((format_id, height, ext, line))
            
            # 识别音频格式（包含"audio only"的行）
            elif 'audio only' in line:
                # 提取文件大小用于排序（优先使用FILESIZE，其次使用比特率）
                filesize_bytes = 0
                bitrate = 0
                
                # 解析文件大小 (例如: "13.06MiB", "4.96MiB")
                filesize_match = re.search(r'(\d+\.?\d*)(MiB|GiB|KiB|MB|GB|KB)', line)
                if filesize_match:
                    size_value = float(filesize_match.group(1))
                    size_unit = filesize_match.group(2)
                    
                    # 转换为字节数进行比较
                    if size_unit in ['MiB', 'MB']:
                        filesize_bytes = int(size_value * 1024 * 1024)  # MB to bytes
                    elif size_unit in ['GiB', 'GB']:
                        filesize_bytes = int(size_value * 1024 * 1024 * 1024)  # GB to bytes
                    elif size_unit in ['KiB', 'KB']:
                        filesize_bytes = int(size_value * 1024)  # KB to bytes
                
                # 如果没有找到文件大小，使用比特率作为备选
                if filesize_bytes == 0:
                    bitrate_matches = re.findall(r'(\d+)k', line)
                    if bitrate_matches:
                        bitrate = int(bitrate_matches[-1])
                        # 将比特率转换为估算文件大小（假设5分钟视频）
                        filesize_bytes = bitrate * 1000 * 300 // 8  # kbps * 300s / 8 bits per byte
                
                audio_formats.append((format_id, filesize_bytes, bitrate, ext, line))
        
        # 排序并选择最佳格式
        best_video_id = None
        best_audio_id = None
        
        if video_formats:
            # 按分辨率排序，选择最高分辨率（列表最后一个）
            video_formats.sort(key=lambda x: x[1])  # 按高度排序
            best_video_id = video_formats[-1][0]
            if log_video_format:
                log.info(f"选择最佳视频格式: {video_formats[-1][0]} ({video_formats[-1][1]}p, {video_formats[-1][2]})")
        
        if audio_formats:
            # 按文件大小排序，选择FILESIZE最大的（列表最后一个）
            audio_formats.sort(key=lambda x: x[1])  # 按文件大小排序
            best_audio_id = audio_formats[-1][0]
            best_audio_filesize = audio_formats[-1][1]
            best_audio_bitrate = audio_formats[-1][2]
            best_audio_ext = audio_formats[-1][3]
            
            # 格式化文件大小显示
            if best_audio_filesize > 1024 * 1024:
                size_display = f"{best_audio_filesize / (1024 * 1024):.2f}MB"
            else:
                size_display = f"{best_audio_filesize / 1024:.2f}KB"
                
            log.info(f"选择最佳音频格式: {best_audio_id} ({size_display}, {best_audio_bitrate}k, {best_audio_ext})")
        
        return best_video_id, best_audio_id

    def _build_video_format_string(self) -> str:
        """根据配置构建视频格式字符串（传统模式）"""
        video_quality = config.downloader.video_quality
        video_format = config.downloader.video_format_preference
        
        # 构建格式字符串
        if video_quality == "best":
            if video_format == "any":
                return "bestvideo"
            else:
                return f"bestvideo[ext={video_format}]/bestvideo"
        elif video_quality == "worst":
            if video_format == "any":
                return "worstvideo"
            else:
                return f"worstvideo[ext={video_format}]/worstvideo"
        elif video_quality == "4k":
            if video_format == "any":
                return "bestvideo[height<=2160]/bestvideo"
            else:
                return f"bestvideo[height<=2160][ext={video_format}]/bestvideo[height<=2160]"
        elif video_quality == "1080p":
            if video_format == "any":
                return "bestvideo[height<=1080]/bestvideo"
            else:
                return f"bestvideo[height<=1080][ext={video_format}]/bestvideo[height<=1080]"
        elif video_quality == "720p":
            if video_format == "any":
                return "bestvideo[height<=720]/bestvideo"
            else:
                return f"bestvideo[height<=720][ext={video_format}]/bestvideo[height<=720]"
        elif video_quality == "480p":
            if video_format == "any":
                return "bestvideo[height<=480]/bestvideo"
            else:
                return f"bestvideo[height<=480][ext={video_format}]/bestvideo[height<=480]"
        elif video_quality == "360p":
            if video_format == "any":
                return "bestvideo[height<=360]/bestvideo"
            else:
                return f"bestvideo[height<=360][ext={video_format}]/bestvideo[height<=360]"
        else:
            # 默认回退到最高质量
            return f"bestvideo[ext={video_format}]/bestvideo" if video_format != "any" else "bestvideo"

    def _build_audio_format_string(self) -> str:
        """根据配置构建音频格式字符串（传统模式）"""
        audio_quality = config.downloader.audio_quality
        audio_format = config.downloader.audio_format_preference
        
        if audio_quality == "best":
            if audio_format == "any":
                return "bestaudio"
            else:
                return f"bestaudio[ext={audio_format}]/bestaudio"
        elif audio_quality == "worst":
            if audio_format == "any":
                return "worstaudio"
            else:
                return f"worstaudio[ext={audio_format}]/worstaudio"
        elif audio_quality.endswith("k"):
            # 具体比特率设置
            bitrate = audio_quality[:-1]  # 去掉 'k'
            if audio_format == "any":
                return f"bestaudio[abr<={bitrate}]/bestaudio"
            else:
                return f"bestaudio[abr<={bitrate}][ext={audio_format}]/bestaudio[abr<={bitrate}]"
        else:
            # 默认回退到最高质量
            return f"bestaudio[ext={audio_format}]/bestaudio" if audio_format != "any" else "bestaudio"

    async def build_video_download_cmd(self, output_path: str, url: str) -> List[str]:
        """构建视频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        # 检查是否使用auto_best模式
        if config.downloader.video_quality == "auto_best":
            video_id, _ = await self._parse_available_formats(url)
            if video_id:
                video_format = video_id
                log.info(f"使用auto_best模式，选择视频格式: {video_format}")
            else:
                video_format = "bestvideo"
                log.warning("auto_best模式解析失败，回退到bestvideo")
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

    async def build_audio_download_cmd(self, output_path: str, url: str, filename_prefix: str = None) -> List[str]:
        """构建音频下载命令"""
        cmd = self.build_yt_dlp_base_cmd()
        
        # 检查是否使用auto_best模式
        if config.downloader.audio_quality == "auto_best":
            _, audio_id = await self._parse_available_formats(url, log_video_format=False)
            if audio_id:
                audio_format = audio_id
                log.info(f"使用auto_best模式，选择音频格式: {audio_format}")
            else:
                audio_format = "bestaudio"
                log.warning("auto_best模式解析失败，回退到bestaudio")
        else:
            audio_format = self._build_audio_format_string()
            log.debug(f"使用传统模式，音频格式: {audio_format}")
        
        # 创建正确的输出模板
        if filename_prefix:
            # 使用自定义前缀
            output_template = f"{output_path}/{filename_prefix}.%(ext)s"
        else:
            # 使用默认标题
            output_template = f"{output_path}/%(title)s.%(ext)s"
        
        cmd.extend([
            '-f', audio_format,
            '--newline',
            '-o', output_template,
            url
        ])
        
        return cmd

    async def build_combined_download_cmd(self, output_path: str, url: str) -> Tuple[List[str], str]:
        """构建合并视频+音频下载命令（auto_best模式专用）"""
        cmd = self.build_yt_dlp_base_cmd()
        
        if (config.downloader.video_quality == "auto_best" and 
            config.downloader.audio_quality == "auto_best"):
            
            video_id, audio_id = await self._parse_available_formats(url)
            
            if video_id and audio_id:
                # 使用特定ID组合，让yt-dlp自动合并
                combined_format = f"{video_id}+{audio_id}"
                log.info(f"使用auto_best组合格式: {combined_format}")
            else:
                # 回退到传统最佳格式
                combined_format = "bestvideo+bestaudio/best"
                log.warning("auto_best模式解析失败，回退到传统格式")
        else:
            # 混合模式或传统模式
            if config.downloader.video_quality == "auto_best":
                video_format = (await self._parse_available_formats(url))[0]
            else:
                video_format = self._build_video_format_string()
                
            if config.downloader.audio_quality == "auto_best":
                audio_format = (await self._parse_available_formats(url))[1]
            else:
                audio_format = self._build_audio_format_string()
            
            if video_format and audio_format:
                combined_format = f"{video_format}+{audio_format}"
            else:
                combined_format = "bestvideo+bestaudio/best"
        
        # 创建正确的输出模板
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
        
        # 创建正确的输出模板
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