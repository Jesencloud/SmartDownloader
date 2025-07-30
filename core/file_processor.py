#!/usr/bin/env python3
"""
文件处理器模块
专门处理文件操作：合并、音频提取、清理等
"""

import logging
from pathlib import Path
from typing import List, Optional

import aiofiles.os
from rich.console import Console

from config_manager import config

from .command_builder import CommandBuilder
from .exceptions import DownloaderException, FFmpegException
from .subprocess_manager import SubprocessManager

log = logging.getLogger(__name__)
console = Console()


class FileProcessor:
    """
    专门处理文件操作的处理器。

    负责视频音频合并、音频提取、文件清理等操作。
    """

    def __init__(
        self,
        subprocess_manager: Optional[SubprocessManager] = None,
        command_builder: Optional[CommandBuilder] = None,
    ):
        """
        初始化文件处理器。

        Args:
            subprocess_manager: 子进程管理器实例，None则创建默认实例
            command_builder: 命令构建器实例，None则创建默认实例
        """
        self.subprocess_manager = subprocess_manager or SubprocessManager()
        self.command_builder = command_builder or CommandBuilder()

    async def merge_to_mp4(
        self,
        video_part: Path,
        audio_part: Path,
        output_file: Path,
        cleanup_parts: bool = True,
    ) -> bool:
        """
        将视频和音频文件合并为MP4格式。

        Args:
            video_part: 视频文件路径
            audio_part: 音频文件路径
            output_file: 输出文件路径
            cleanup_parts: 是否清理临时文件

        Returns:
            bool: 合并是否成功

        Raises:
            FFmpegException: FFmpeg操作失败
            DownloaderException: 文件不存在或其他错误
        """
        try:
            # 检查输入文件是否存在
            if not video_part.exists():
                raise DownloaderException(f"视频文件不存在: {video_part}")
            if not audio_part.exists():
                raise DownloaderException(f"音频文件不存在: {audio_part}")

            log.info(f"开始合并视频: {video_part.name} + {audio_part.name} -> {output_file.name}")

            # 构建FFmpeg合并命令
            merge_cmd = self.command_builder.build_ffmpeg_merge_cmd(str(video_part), str(audio_part), str(output_file))

            # 执行合并命令
            return_code, stdout, stderr = await self.subprocess_manager.execute_simple(
                merge_cmd,
                timeout=300,  # 5分钟超时
            )

            # 检查输出文件是否生成
            if not output_file.exists():
                raise FFmpegException(f"合并失败，输出文件未生成: {output_file}")

            # 检查输出文件大小
            output_size = output_file.stat().st_size
            if output_size == 0:
                raise FFmpegException(f"合并失败，输出文件为空: {output_file}")

            log.info(f"合并成功: {output_file.name} ({output_size / (1024 * 1024):.1f} MB)")

            # 清理临时文件
            if cleanup_parts:
                await self._cleanup_temp_files([video_part, audio_part])

            return True

        except (FFmpegException, DownloaderException):
            raise
        except Exception as e:
            raise FFmpegException(f"合并过程中发生错误: {e}") from e

    async def extract_audio_from_local_file(
        self,
        video_file: Path,
        output_file: Path,
        audio_format: str = "mp3",
        audio_quality: str = "192k",
    ) -> bool:
        """
        从本地视频文件提取音频。

        Args:
            video_file: 源视频文件路径
            output_file: 输出音频文件路径
            audio_format: 音频格式 (mp3, aac, etc.)
            audio_quality: 音频质量 (192k, 320k, etc.)

        Returns:
            bool: 提取是否成功

        Raises:
            FFmpegException: FFmpeg操作失败
            DownloaderException: 文件不存在或其他错误
        """
        try:
            # 检查输入文件是否存在
            if not video_file.exists():
                raise DownloaderException(f"视频文件不存在: {video_file}")

            log.info(f"开始从视频提取音频: {video_file.name} -> {output_file.name}")

            # 构建FFmpeg音频提取命令
            extract_cmd = self.command_builder.build_ffmpeg_extract_audio_cmd(str(video_file), str(output_file))

            # 执行提取命令
            return_code, stdout, stderr = await self.subprocess_manager.execute_simple(
                extract_cmd,
                timeout=300,  # 5分钟超时
            )

            # 检查输出文件是否生成
            if not output_file.exists():
                raise FFmpegException(f"音频提取失败，输出文件未生成: {output_file}")

            # 检查输出文件大小
            output_size = output_file.stat().st_size
            if output_size == 0:
                raise FFmpegException(f"音频提取失败，输出文件为空: {output_file}")

            log.info(f"音频提取成功: {output_file.name} ({output_size / (1024 * 1024):.1f} MB)")

            return True

        except (FFmpegException, DownloaderException):
            raise
        except Exception as e:
            raise FFmpegException(f"音频提取过程中发生错误: {e}") from e

    async def convert_to_audio_format(
        self,
        input_file: Path,
        audio_format: str = "mp3",
        audio_quality: str = "192k",
        cleanup_original: bool = True,
    ) -> Optional[Path]:
        """
        将音频文件转换为指定格式。

        Args:
            input_file: 输入文件路径
            audio_format: 目标音频格式 (mp3, aac, etc.)
            audio_quality: 音频质量 (192k, 320k, etc.)
            cleanup_original: 是否清理原始文件

        Returns:
            转换后的文件路径,失败返回None

        Raises:
            FFmpegException: FFmpeg操作失败
            DownloaderException: 文件不存在或其他错误
        """
        try:
            if not input_file.exists():
                raise DownloaderException(f"输入文件不存在: {input_file}")

            output_file = input_file.with_suffix(f".{audio_format}")
            log.info(f"开始转换音频格式: {input_file.name} -> {output_file.name}")

            # 构建FFmpeg转换命令
            convert_cmd = self.command_builder.build_ffmpeg_extract_audio_cmd(str(input_file), str(output_file))

            # 执行转换命令
            return_code, stdout, stderr = await self.subprocess_manager.execute_simple(
                convert_cmd,
                timeout=300,  # 5分钟超时
            )

            if not output_file.exists() or output_file.stat().st_size == 0:
                raise FFmpegException(f"音频转换失败，输出文件未生成或为空: {output_file}")

            log.info(f"音频转换成功: {output_file.name}")

            if cleanup_original:
                await self._cleanup_temp_files([input_file])

            return output_file

        except (FFmpegException, DownloaderException):
            raise
        except Exception as e:
            raise FFmpegException(f"音频转换过程中发生错误: {e}") from e

    async def cleanup_temp_files(self, file_prefix: str, extensions: List[str] = None):
        """
        清理指定前缀的临时文件。

        Args:
            file_prefix: 文件前缀
            extensions: 要清理的文件扩展名列表，None则使用配置中的清理模式
        """
        try:
            if extensions is None:
                # 使用配置中的清理模式
                cleanup_patterns = config.file_processing.cleanup_patterns
                extensions = []
                for pattern in cleanup_patterns:
                    if pattern.startswith("*."):
                        extensions.append(pattern[2:])  # 移除 '*.'

            # 查找匹配的文件
            files_to_remove = []
            base_path = Path(file_prefix).parent

            for ext in extensions:
                pattern = f"{Path(file_prefix).name}*.{ext}"
                matching_files = list(base_path.glob(pattern))
                files_to_remove.extend(matching_files)

            # 清理文件
            await self._cleanup_temp_files(files_to_remove)

        except Exception as e:
            log.warning(f"清理临时文件时出错: {e}", exc_info=True)

    import aiofiles.os

    # ... (rest of the file) ...

    async def _cleanup_temp_files(self, files: List[Path]):
        """
        内部方法：清理指定的文件列表。

        Args:
            files: 要删除的文件路径列表
        """
        for file_path in files:
            try:
                if await aiofiles.os.path.exists(file_path):
                    await aiofiles.os.remove(file_path)
                    log.debug(f"删除临时文件: {file_path.name}")
            except OSError as e:
                log.warning(f"删除文件失败 {file_path}: {e}")

    async def get_file_info(self, file_path: Path) -> dict:
        """
        获取文件的基本信息。

        Args:
            file_path: 文件路径

        Returns:
            包含文件信息的字典

        Raises:
            DownloaderException: 文件不存在或无法访问
        """
        try:
            if not file_path.exists():
                raise DownloaderException(f"文件不存在: {file_path}")

            stat = file_path.stat()

            return {
                "path": str(file_path),
                "name": file_path.name,
                "size": stat.st_size,
                "size_mb": stat.st_size / (1024 * 1024),
                "modified_time": stat.st_mtime,
                "exists": True,
            }

        except OSError as e:
            raise DownloaderException(f"无法获取文件信息 {file_path}: {e}") from e

    async def verify_file_integrity(self, file_path: Path, min_size_bytes: int = 1024) -> bool:
        """
        验证文件完整性。

        Args:
            file_path: 文件路径
            min_size_bytes: 最小文件大小（字节）

        Returns:
            bool: 文件是否完整
        """
        try:
            if not file_path.exists():
                return False

            stat = file_path.stat()

            # 检查文件大小
            if stat.st_size < min_size_bytes:
                log.warning(f"文件太小可能不完整: {file_path.name} ({stat.st_size} bytes)")
                return False

            # 尝试读取文件头部，确保文件可读
            try:
                with open(file_path, "rb") as f:
                    f.read(1024)  # 读取前1KB
            except IOError:
                log.warning(f"文件无法读取: {file_path.name}")
                return False

            return True

        except Exception as e:
            log.warning(f"验证文件完整性时出错 {file_path}: {e}")
            return False
