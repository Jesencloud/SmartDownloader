#!/usr/bin/env python3
"""
下载器模块
提供异步视频下载功能,重构后的版本使用核心模块组件
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
import os
import shutil
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, DownloadColumn, ProgressColumn, TaskID,
    TextColumn, TimeElapsedColumn, TimeRemainingColumn, TransferSpeedColumn,
    SpinnerColumn, Task
)
from rich.text import Text

from config_manager import config
from core import (
    DownloaderException, FFmpegException, with_retries,
    CommandBuilder, SubprocessManager, FileProcessor, AuthenticationException
)
from core.cookies_manager import CookiesManager

log = logging.getLogger(__name__)
console = Console()

# 全局进度条信号量,确保同时只有一个进度条活动
_progress_semaphore = asyncio.Semaphore(1)


class SpeedOrFinishMarkColumn(ProgressColumn):
    """下载时显示速度,完成后显示标记"""

    def __init__(self, mark: str = "?", **kwargs):
        self.mark = mark
        self.speed_column = TransferSpeedColumn()
        super().__init__(**kwargs)

    def render(self, task: "Task") -> Text:
        """渲染速度或完成标记"""
        if task.finished:
            return Text(f" {self.mark} ", justify="left")
        return self.speed_column.render(task)


class Downloader:
    """
    简化的下载器,主要负责下载流程编排.
    
    重构后专注于业务流程,具体的执行逻辑委托给核心模块.
    """
    
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        """
        初始化下载器.
        
        Args:
            download_folder: 下载文件夹路径
            cookies_file: cookies文件路径(可选)
            proxy: 代理服务器地址(可选)
        """
        self.download_folder = Path(download_folder)
        self.cookies_file = cookies_file
        self.proxy = proxy
        
        # 组合各种专门的处理器
        self.command_builder = CommandBuilder(proxy, cookies_file)
        self.subprocess_manager = SubprocessManager()
        self.file_processor = FileProcessor(self.subprocess_manager, self.command_builder)
        
        # 初始化cookies管理器
        if cookies_file:
            self.cookies_manager = CookiesManager(cookies_file)
        else:
            self.cookies_manager = None
        
        log.info(f'初始化下载器,目标文件夹: {self.download_folder}')
        if cookies_file:
            log.info(f'使用cookies文件: {cookies_file}')
        if proxy:
            log.info(f'使用代理: {self.proxy}')

    async def _execute_info_cmd_with_auth_retry(self, url: str, info_cmd: list, timeout: int = 60):
        """
        执行信息获取命令,支持认证错误自动重试
        
        Args:
            url: 视频URL
            info_cmd: 信息获取命令
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
        """
        max_auth_retries = 1
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_simple(
                    info_cmd, timeout=timeout, check_returncode=True
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 获取视频信息认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建信息获取命令
                        info_cmd = self.command_builder.build_playlist_info_cmd(url)
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试获取视频信息...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,获取视频信息失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

    async def stream_playlist_info(self, url: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式获取播放列表信息.
        
        Args:
            url: 视频或播放列表URL
            
        Yields:
            包含视频信息的字典
            
        Raises:
            DownloaderException: 获取信息失败
        """
        try:
            # 构建获取信息的命令
            info_cmd = self.command_builder.build_playlist_info_cmd(url)
            
            # 执行命令获取信息(带认证重试支持)
            return_code, stdout, stderr = await self._execute_info_cmd_with_auth_retry(
                url, info_cmd, timeout=60
            )
            
            # 解析JSON输出
            for line in stdout.strip().split('\n'):
                if line.strip():
                    try:
                        video_info = json.loads(line)
                        yield video_info
                    except json.JSONDecodeError as e:
                        log.warning(f'解析视频信息JSON失败: {e}')
                        continue
                        
        except AuthenticationException:
            # 认证异常直接向上传递,让上层处理重试
            raise
        except Exception as e:
            raise DownloaderException(f'获取播放列表信息失败: {e}') from e
    
    @with_retries(max_retries=3)
    async def _execute_download_with_progress(self, cmd: list, progress, task_id: TaskID, timeout: int = 1800) -> None:
        """
        执行下载命令并更新进度条
        
        Args:
            cmd: 要执行的命令列表
            progress: 进度条对象
            task_id: 进度条任务ID
            timeout: 命令超时时间(秒)
            
        Raises:
            DownloaderException: 下载过程中发生错误
        """
        try:
            # 记录当前工作目录和下载目录
            cwd = str(self.download_folder.absolute())
            log.info(f"执行命令: {' '.join(cmd)}")
            log.info(f"当前工作目录: {cwd}")
            log.info(f"下载目录内容: {list(Path(cwd).glob('*'))}")
            
            # 记录环境变量
            log.debug(f"环境变量: {os.environ.get('PATH', '')}")
            
            # 确保输出目录存在
            os.makedirs(cwd, exist_ok=True)
            
            # 记录命令执行前的磁盘使用情况(只记录一次)
            if not hasattr(self, '_disk_usage_logged'):
                total, used, free = shutil.disk_usage(cwd)
                log.info(f"磁盘使用情况 - 总共: {total // (2**30)}GB, 已用: {used // (2**30)}GB, 可用: {free // (2**30)}GB")
                self._disk_usage_logged = True
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd  # 设置工作目录
            )
            
            output_lines = []
            error_lines = []
            
            # 设置超时
            start_time = asyncio.get_event_loop().time()
            
            while True:
                # 检查超时
                if asyncio.get_event_loop().time() - start_time > timeout:
                    process.terminate()
                    await asyncio.sleep(1)  # 给进程一点时间终止
                    if process.returncode is None:  # 如果进程还在运行,强制终止
                        process.kill()
                    raise DownloaderException(f"下载超时,已终止 (超时时间: {timeout}秒)")
                
                # 读取stderr(进度信息)
                while True:
                    output = await process.stderr.readline()
                    if not output:
                        break
                        
                    line = output.decode('utf-8', 'ignore').strip()
                    if not line:
                        continue
                        
                    output_lines.append(line)
                    log.debug(f"yt-dlp: {line}")
                    
                    # 捕获错误信息
                    if 'ERROR:' in line or 'error' in line.lower():
                        error_lines.append(line)
                    
                    # 解析下载进度
                    if '[download]' in line and '%' in line:
                        try:
                            # 从行中提取百分比
                            percent_str = line.split('[download]')[1].split('%')[0].strip()
                            percent = float(percent_str)
                            progress.update(task_id, completed=percent)
                        except (ValueError, IndexError) as e:
                            log.debug(f"解析进度失败: {line}")
                
                # 检查进程是否结束
                if process.returncode is not None:
                    break
                    
                # 短暂休眠,避免CPU占用过高
                await asyncio.sleep(0.1)
            
            # 读取剩余的输出
            stdout, stderr = await process.communicate()
            if stdout:
                log.debug(f"命令输出: {stdout.decode('utf-8', 'ignore')}")
            if stderr:
                error_lines.extend(stderr.decode('utf-8', 'ignore').splitlines())
            
            # 检查返回码
            if process.returncode != 0:
                error_msg = f"下载命令执行失败,返回码: {process.returncode}"
                if error_lines:
                    error_msg += f"\n错误输出:\n" + "\n".join(error_lines[-10:])  # 显示最后10行错误
                log.error(error_msg)
                raise DownloaderException(error_msg)
                
            # 更新进度到100%
            progress.update(task_id, completed=100)
            log.info("下载完成")
            
        except asyncio.CancelledError:
            log.warning("下载任务被取消")
            if process and process.returncode is None:
                process.terminate()
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
            raise
            
        except Exception as e:
            log.error(f"下载过程中发生未预期的错误: {str(e)}", exc_info=True)
            if process and process.returncode is None:
                process.terminate()
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
            raise DownloaderException(f"下载失败: {str(e)}") from e

    async def _execute_download_with_auth_retry(self, video_url: str, download_cmd: list, progress, task_id: TaskID, timeout: int = 1800):
        """
        执行下载命令,支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            download_cmd: 下载命令
            progress: 进度条对象
            task_id: 任务ID
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
            
        Raises:
            各种下载相关异常
        """
        max_auth_retries = 1  # 最多重试1次认证错误
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self._execute_download_with_progress(download_cmd, progress, task_id, timeout=timeout)
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    # 尝试自动刷新cookies
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        # 更新命令构建器的cookies文件
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建下载命令
                        download_cmd, _ = self.command_builder.build_combined_download_cmd(
                            str(self.download_folder), video_url
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,下载失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                # 其他类型的错误,直接抛出
                raise e

    async def _execute_audio_download_with_auth_retry(self, video_url: str, audio_cmd: list, progress, task_id: TaskID, file_prefix: str, timeout: int = 1800):
        """
        执行音频下载命令,支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            audio_cmd: 音频下载命令
            progress: 进度条对象
            task_id: 任务ID
            file_prefix: 文件前缀
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
        """
        max_auth_retries = 1
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_with_progress(
                    audio_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 音频下载认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    
                    new_cookies_file = self.cookies_manager.refresh_cookies_for_url(video_url)
                    
                    if new_cookies_file:
                        self.command_builder.update_cookies_file(new_cookies_file)
                        # 重新构建音频下载命令
                        audio_cmd = self.command_builder.build_audio_download_cmd(
                            str(self.download_folder), video_url, file_prefix
                        )
                        auth_retry_count += 1
                        log.info(f"✅ Cookies已更新,重试音频下载...")
                        continue
                    else:
                        log.error(f"❌ 无法自动更新cookies,音频下载失败")
                        raise e
                else:
                    if not self.cookies_manager:
                        log.error(f"❌ 未配置cookies管理器,无法自动处理认证错误")
                    else:
                        log.error(f"❌ 已达到最大认证重试次数 ({max_auth_retries})")
                    raise e
            except Exception as e:
                raise e

    async def _find_output_file(self, prefix: str, extensions: tuple) -> Optional[Path]:
        """
        在下载目录中查找具有指定前缀和扩展名的文件
        
        Args:
            prefix: 文件名前缀
            extensions: 可能的文件扩展名元组
            
        Returns:
            找到的文件路径,如果未找到则返回None
        """
        log.info(f'查找文件: 前缀={prefix}, 扩展名={extensions}')
        log.info(f'搜索目录: {self.download_folder}')
        
        # 首先检查目录中的所有文件(用于调试)
        all_files = list(self.download_folder.glob('*'))
        log.info(f'目录中的文件: {all_files}')
        
        # 1. 首先尝试精确匹配(包括扩展名)
        for ext in extensions:
            file_path = self.download_folder / f"{prefix}{ext}"
            if file_path.exists() and file_path.is_file():
                log.info(f'找到文件(精确匹配): {file_path}')
                return file_path
        
        # 2. 尝试不区分大小写的扩展名匹配
        for ext in extensions:
            # 移除点并转换为小写用于比较
            ext_lower = ext.lstrip('.').lower()
            for f in self.download_folder.glob(f"{prefix}*"):
                if f.suffix.lstrip('.').lower() == ext_lower and f.is_file():
                    log.info(f'找到文件(扩展名不区分大小写): {f}')
                    return f
        
        # 3. 尝试匹配前缀(不包含扩展名)
        for f in self.download_folder.glob(f"{prefix}*"):
            if f.is_file():
                # 检查文件扩展名是否在允许的扩展名列表中
                file_ext = f.suffix.lower()
                if any(ext.lower() == file_ext for ext in extensions):
                    log.info(f'找到文件(前缀匹配): {f}')
                    return f
        
        # 4. 如果还是没找到,尝试查找任何音频文件(最后的手段)
        audio_extensions = ('.mp3', '.m4a', '.opus', '.webm', '.ogg', '.wav', '.aac', '.flac')
        for f in self.download_folder.glob(f"{prefix}*"):
            if f.is_file() and f.suffix.lower() in audio_extensions:
                log.info(f'找到音频文件(通用匹配): {f}')
                return f
        
        # 5. 最后尝试按修改时间排序,返回最新的匹配文件
        possible_files = []
        for ext in extensions:
            possible_files.extend(self.download_folder.glob(f"*{ext}"))
        
        if possible_files:
            # 按修改时间排序,返回最新的文件
            possible_files.sort(key=os.path.getmtime, reverse=True)
            log.info(f'找到可能匹配的最新文件: {possible_files[0]}')
            return possible_files[0]
            
        log.warning(f'未找到匹配的文件: 前缀={prefix}, 扩展名={extensions}')
        log.warning(f'目录内容: {list(self.download_folder.glob("*"))}')
        return None
        
    async def download_and_merge(self, video_url: str, file_prefix: str, format_id: str = None, resolution: str = '') -> Optional[Path]:
        """
        下载视频和音频并合并为MP4格式.
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            format_id: 要下载的特定视频格式ID (可选)
            resolution: 视频分辨率 (例如: '1080p60')
            
        Returns:
            合并后的文件路径,失败返回None
            
        Raises:
            DownloaderException: 下载或合并失败, 请检查日志获取详细信息
        """
        try:
            log.info(f'开始下载并合并: {file_prefix}')
            log.info(f'视频URL: {video_url}')
            log.info(f'格式ID: {format_id if format_id else "默认格式"}')
            
            # 确保下载目录存在
            self.download_folder.mkdir(parents=True, exist_ok=True)
            
            # 清理可能存在的临时文件
            temp_files = list(self.download_folder.glob(f"{file_prefix}.*"))
            for temp_file in temp_files:
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                        log.debug(f'已清理临时文件: {temp_file}')
                except Exception as e:
                    log.warning(f'清理临时文件 {temp_file} 失败: {e}')
                    
            # 检查是否已经存在下载好的文件
            possible_files = list(self.download_folder.glob("*")) + list(self.download_folder.glob("*/*"))
            log.info(f'当前下载目录中的文件: {[str(f) for f in possible_files]}')
            
            # 使用组合下载命令,它会自动处理视频和音频的下载与合并
            download_cmd, used_format = self.command_builder.build_combined_download_cmd(
                str(self.download_folder),
                video_url,
                format_id=format_id,
                resolution=resolution  # 传递分辨率参数
            )
            
            # 添加详细的调试信息
            log.info(f'下载命令: {" ".join(download_cmd)}')
            log.info(f'使用的格式: {used_format}')
            log.info(f'下载目录: {self.download_folder.absolute()}')
            
            async with _progress_semaphore:
                with Progress(
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    "•",
                    TimeRemainingColumn(),
                    "•",
                    TransferSpeedColumn(),
                    console=console
                ) as progress:
                    try:
                        # 记录下载开始前的目录状态
                        log.info(f"下载前目录内容: {list(Path(self.download_folder).glob('*'))}")
                        
                        # 创建并启动下载任务进度条
                        download_task = progress.add_task("⬇️ 下载视频和音频", total=100)
                        
                        # 执行下载命令
                        await self._execute_download_with_progress(download_cmd, progress, download_task)
                        
                        # 标记任务为已完成
                        progress.update(download_task, completed=100, visible=False)
                        
                        # 记录下载后的目录状态
                        log.info(f"下载后目录内容: {list(Path(self.download_folder).glob('*'))}")
                        
                        # 查找下载的视频文件(使用视频标题作为文件名)
                        output_file = None
                        for ext in ['.mp4', '.webm', '.mkv']:
                            files = list(self.download_folder.glob(f'*{ext}'))
                            if files:
                                # 获取最新下载的文件
                                files.sort(key=os.path.getmtime, reverse=True)
                                output_file = files[0]
                                log.info(f"找到视频文件: {output_file}")
                                break
                        
                        if not output_file:
                            raise DownloaderException("未找到下载的视频文件")
                        
                        # 验证文件大小
                        file_size = output_file.stat().st_size
                        if file_size == 0:
                            log.warning(f'文件大小为0字节: {output_file}')
                            output_file.unlink()  # 删除空文件
                            raise DownloaderException("下载的文件为空")
                            
                        log.info(f'下载成功: {output_file.name} (大小: {file_size / (1024*1024):.2f} MB)')
                        return output_file
                        
                    except asyncio.CancelledError:
                        log.warning("下载任务被用户取消")
                        raise
                        
                    except Exception as e:
                        error_msg = f"下载失败: {str(e)}"
                        log.error(error_msg, exc_info=True)
                        
                        # 如果部分文件已下载,记录它们的信息
                        partial_files = list(self.download_folder.glob(f"{file_prefix}*"))
                        if partial_files:
                            log.warning(f"发现部分下载的文件: {[f.name for f in partial_files]}")
                            for f in partial_files:
                                try:
                                    size = f.stat().st_size / (1024*1024)
                                    log.warning(f"- {f.name} (大小: {size:.2f} MB)")
                                except Exception as file_err:
                                    log.warning(f"- {f.name} (无法获取文件信息: {str(file_err)})")
                        
                        raise DownloaderException(error_msg) from e
                    
                    try:
                        await self.file_processor.merge_video_audio(
                            video_file, audio_file, output_path,
                            progress_callback=lambda p: progress.update(merge_task, completed=p*100)
                        )
                        
                        if output_path.exists():
                            log.info(f"合并成功: {output_path.name}")
                            return output_path
                        else:
                            raise DownloaderException("合并后未生成输出文件")
                            
                    except Exception as e:
                        log.error(f"合并视频和音频失败: {str(e)}")
                        # 如果合并失败,但视频文件存在,返回视频文件
                        if video_file.exists():
                            log.warning(f"合并失败,返回仅视频文件: {video_file.name}")
                            return video_file
                        raise DownloaderException(f"合并失败: {str(e)}")
                        
        except asyncio.CancelledError:
            log.warning("下载任务被取消")
            raise
        except Exception as e:
            log.error(f"下载过程中发生错误: {str(e)}", exc_info=True)
            raise DownloaderException(f"下载失败: {str(e)}")
            
        # 如果自动合并失败,尝试手动合并
        log.warning('自动合并失败,尝试手动合并...')
        video_file = await self._find_output_file(f"{file_prefix}", ('.mp4', '.webm', '.mkv'))
        audio_file = await self._find_output_file(f"{file_prefix}", ('.m4a', '.webm', '.mp3', '.opus'))
        
        if video_file and audio_file:
            log.info(f'找到单独的视频和音频文件,尝试合并: {video_file.name} + {audio_file.name}')
            output_path = video_file.parent / f"{file_prefix}_merged.mp4"
            
            try:
                await self.file_processor.merge_video_audio(
                    video_file, audio_file, output_path
                )
                
                if output_path.exists():
                    log.info(f'手动合并成功: {output_path.name}')
                    return output_path
                    
            except Exception as e:
                log.error(f'手动合并失败: {str(e)}')
                # 如果手动合并也失败,返回视频文件
                if video_file.exists():
                    log.warning(f'返回仅视频文件: {video_file.name}')
                    return video_file
        
        # 如果所有方法都失败,尝试直接查找输出文件
        output_file = await self._find_output_file(file_prefix, ('.mp4', '.webm', '.mkv'))
        if output_file and await self.file_processor.verify_file_integrity(output_file):
            log.info(f'找到有效的输出文件: {output_file.name}')
            return output_file
            
        raise DownloaderException('下载和合并视频失败')

    @with_retries(max_retries=3)
    async def _execute_download_with_auth_retry(self, video_url: str, download_cmd: list, progress, task_id: TaskID, timeout: int = 1800):
        """
        执行下载命令,支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            download_cmd: 下载命令
            progress: 进度条对象
            task_id: 任务ID
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
            
        Raises:
            各种下载相关异常
        """
        max_auth_retries = 1  # 最多重试1次认证错误
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_with_progress(
                    download_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    auth_retry_count += 1
                    await self.cookies_manager.refresh_cookies()
                    # Rebuild command with refreshed cookies
                    download_cmd = self.command_builder.build_download_cmd(
                        str(self.download_folder), 
                        video_url,
                        format_id=None,  # Format ID is not needed here as we're just retrying
                        filename_prefix=None,
                        resolution=''
                    )
                    continue
                raise e
                
            # 如果自动合并失败,尝试手动合并
            log.warning('自动合并失败,尝试手动合并...')
            video_file = await self._find_output_file(f"{file_prefix}.f{format_id}" if format_id else file_prefix, 
                                                   ('.mp4', '.webm', '.mkv'))
            audio_file = await self._find_output_file(f"{file_prefix}", ('.m4a', '.webm', '.mp3', '.opus'))
            
            if video_file and audio_file:
                log.info(f'找到单独的视频和音频文件,尝试合并: {video_file.name} + {audio_file.name}')
                output_path = video_file.parent / f"{file_prefix}_merged.mp4"
                
                try:
                    await self.file_processor.merge_video_audio(
                        video_file, audio_file, output_path
                    )
                    if output_path.exists():
                        return output_path
                    else:
                        log.error('合并后的文件不存在')
                except Exception as e:
                    log.error(f'合并视频和音频失败: {e}', exc_info=True)
                
                # 如果合并失败,但找到了视频文件,返回它
                if video_file:
                    log.warning(f'无法合并音频,返回仅视频文件: {video_file.name}')
                    return video_file
                    
                # 如果只找到了音频文件,返回它
                if audio_file:
                    log.warning(f'仅找到音频文件: {audio_file.name}')
                    return audio_file
                    
                # 如果以上都失败,抛出异常
                # 查找输出文件时,如果是mp3转换,优先查找.mp3
                expected_extensions = ('.mp3',) if to_mp3 else ('.m4a', '.opus', '.aac', '.webm')
                output_file = await self._find_output_file(file_prefix, expected_extensions)

                if output_file and await self.file_processor.verify_file_integrity(output_file):
                    log.info(f'音频下载成功: {output_file.name}')
                    return output_file
                
            # 如果所有尝试都失败,抛出异常
            raise DownloaderException('无法找到或验证下载的文件')
    
    async def _execute_download_with_auth_retry(self, video_url: str, download_cmd: list, progress, task_id: TaskID, timeout: int = 1800):
        """
        执行下载命令,支持认证错误自动重试
        
        Args:
            video_url: 视频URL
            download_cmd: 下载命令
            progress: 进度条对象
            task_id: 任务ID
            timeout: 超时时间
            
        Returns:
            tuple: (return_code, stdout, stderr)
            
        Raises:
            各种下载相关异常
        """
        max_auth_retries = 1  # 最多重试1次认证错误
        auth_retry_count = 0
        
        while auth_retry_count <= max_auth_retries:
            try:
                return await self.subprocess_manager.execute_with_progress(
                    download_cmd, progress, task_id, timeout=timeout
                )
            except AuthenticationException as e:
                if auth_retry_count < max_auth_retries and self.cookies_manager:
                    log.warning(f"🍪 检测到认证错误,尝试第 {auth_retry_count + 1} 次自动刷新cookies...")
                    auth_retry_count += 1
                else:
                    raise

    async def _execute_download_with_progress(self, cmd: list, progress, task_id: TaskID, timeout: int = 1800) -> None:
        """
        执行下载命令并更新进度条
        
        Args:
            cmd: 要执行的命令列表
            progress: 进度条对象
            task_id: 进度条任务ID
            timeout: 命令超时时间(秒)
        """
        # 提取并显示关键下载信息
        url = next((arg for arg in cmd if arg.startswith('http')), 'unknown')
        output_template = next((arg.split('=', 1)[1] for arg in cmd if arg.startswith('--output')), '')
        output_path = Path(output_template).parent if output_template else self.download_folder
        log.info(f'Starting download: {url}')
            
        log.debug(f'Output path: {output_path.absolute()}')

        log.debug(f'Command: {" ".join(cmd)}')
        
        process = await asyncio.create_subprocess_exec(  # type: ignore
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        output_lines = []
        while True:
            output = await process.stderr.readline()
            if output == b'' and process.returncode is not None:
                break
                
            line = output.decode('utf-8', 'ignore').strip()
            if not line:
                continue
                
            output_lines.append(line)
            
            # 只记录非进度信息到debug日志
            if '[download]' not in line or '%' not in line:
                log.debug(f"yt-dlp: {line}")
            
            # 解析下载进度
            if '[download]' in line and '%' in line:
                try:
                    percent = float(line.split('%')[0].split()[-1])
                    progress.update(task_id, completed=percent)
                    # 只记录整数百分比变化，避免日志过多
                    if percent.is_integer():
                        log.debug(f'Download progress: {int(percent)}%')
                except (ValueError, IndexError):
                    pass
        
        await process.wait()
        
        if process.returncode != 0:
            error_msg = "\n".join(output_lines[-10:])  # Get last 10 lines of output for error
            log.error(f"下载失败: {error_msg}")
            raise DownloaderException(f"下载失败: {error_msg}")
            
        progress.update(task_id, completed=100)

    async def _execute_download_with_progress(self, cmd: list, progress, task_id: TaskID, timeout: int = 1800) -> None:
        """
        执行下载命令并更新进度条
        
        Args:
            cmd: 要执行的命令列表
            progress: 进度条对象
            task_id: 进度条任务ID
            timeout: 命令超时时间(秒)
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        output_lines = []
        while True:
            output = await process.stderr.readline()
            if output == b'' and process.returncode is not None:
                break
                
            line = output.decode('utf-8', 'ignore').strip()
            if not line:
                continue
                
            output_lines.append(line)
            log.debug(f"yt-dlp: {line}")
            
            # 解析下载进度
            if '[download]' in line and '%' in line:
                try:
                    percent = float(line.split('%')[0].split()[-1])
                    progress.update(task_id, completed=percent)
                except (ValueError, IndexError):
                    pass
        
        await process.wait()
        
        if process.returncode != 0:
            error_msg = "\n".join(output_lines[-10:])  # Get last 10 lines of output for error
            log.error(f"下载失败: {error_msg}")
            raise DownloaderException(f"下载失败: {error_msg}")
            
        progress.update(task_id, completed=100)

    async def download_metadata(self, video_url: str, file_prefix: str) -> bool:
        """
        下载视频元数据信息.
        
        Args:
            video_url: 视频URL
            file_prefix: 文件前缀
            
        Returns:
            bool: 下载是否成功
            
        Raises:
            DownloaderException: 下载失败
        """
        try:
            log.info(f'开始下载元数据: {file_prefix}')
            
            metadata_cmd = self.command_builder.build_metadata_download_cmd(
                str(self.download_folder), video_url
            )
            
            await self.subprocess_manager.execute_simple(
                metadata_cmd, timeout=60, check_returncode=True
            )
            
            log.info(f'元数据下载成功: {file_prefix}')
            return True
                
        except Exception as e:
            log.error(f'元数据下载失败: {e}', exc_info=True)
            raise DownloaderException(f'元数据下载失败: {e}') from e
    
    async def extract_audio_from_video(self, video_file: Path, audio_file: Path) -> bool:
        """
        从已下载的视频文件提取音频.
        
        Args:
            video_file: 源视频文件路径
            audio_file: 目标音频文件路径
            
        Returns:
            bool: 提取是否成功
            
        Raises:
            FFmpegException: 音频提取失败
        """
        try:
            return await self.file_processor.extract_audio_from_local_file(
                video_file, audio_file
            )
        except Exception as e:
            log.error(f'音频提取失败: {e}', exc_info=True)
            raise
    
    async def cleanup_all_incomplete_files(self):
        """
        清理所有未完成的下载文件.
        
        通常在程序异常退出时调用.
        """
        try:
            log.info('开始清理未完成的下载文件...')
            
            await self.subprocess_manager.cleanup_all_processes()
            
            cleanup_patterns = config.file_processing.cleanup_patterns
            for pattern in cleanup_patterns:
                matching_files = list(self.download_folder.glob(pattern))
                for file_path in matching_files:
                    try:
                        if file_path.exists():
                            file_path.unlink()
                            log.debug(f'清理临时文件: {file_path.name}')
                    except OSError as e:
                        log.warning(f'清理文件失败 {file_path}: {e}')
            
            log.info('临时文件清理完成')
            
        except Exception as e:
            log.error(f'清理过程中出错: {e}', exc_info=True)
    
    async def _find_output_file(self, file_prefix: str, extensions) -> Optional[Path]:
        """
        查找指定前缀和扩展名的输出文件.
        
        Args:
            file_prefix: 文件前缀
            extensions: 文件扩展名(字符串或元组)
            
        Returns:
            找到的文件路径,未找到返回None
        """
        if isinstance(extensions, str):
            extensions = (extensions,)
        
        # 1. 首先尝试精确匹配(带前缀和扩展名)
        for ext in extensions:
            exact_file = self.download_folder / f'{file_prefix}{ext}'
            if exact_file.exists():
                log.info(f'找到精确匹配的文件: {exact_file.name}')
                return exact_file
        
        # 2. 查找所有匹配扩展名的文件,然后过滤出包含前缀的文件
        all_matching_files = []
        for ext in extensions:
            pattern = f'*{ext}'
            try:
                matching_files = list(self.download_folder.glob(pattern))
                # 过滤出文件名中包含前缀的文件
                filtered_files = [f for f in matching_files if file_prefix in f.name]
                all_matching_files.extend(filtered_files)
                
                if filtered_files:
                    log.debug(f'找到 {len(filtered_files)} 个匹配 {file_prefix}*{ext} 的文件')
            except Exception as e:
                log.warning(f'搜索文件 {pattern} 时出错: {e}')
        
        # 3. 如果没有找到包含前缀的文件,则返回最新下载的匹配扩展名的文件
        if not all_matching_files:
            log.debug('没有找到包含前缀的文件,尝试查找最新下载的匹配扩展名文件')
            for ext in extensions:
                pattern = f'*{ext}'
                try:
                    matching_files = list(self.download_folder.glob(pattern))
                    if matching_files:
                        latest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
                        log.info(f'返回最新下载的文件: {latest_file.name}')
                        return latest_file
                except Exception as e:
                    log.warning(f'搜索最新 {ext} 文件时出错: {e}')
            return None
        
        # 4. 返回最新修改的文件
        try:
            latest_file = max(all_matching_files, key=lambda f: f.stat().st_mtime)
            log.info(f'找到匹配的文件: {latest_file.name} (修改时间: {latest_file.stat().st_mtime})')
            return latest_file
        except Exception as e:
            log.error(f'获取最新文件时出错: {e}')
            return None
    
    async def cleanup_temp_files(self, file_prefix: str):
        """
        清理指定前缀的临时文件.
        
        Args:
            file_prefix: 文件前缀
        """
        try:
            await self.file_processor.cleanup_temp_files(file_prefix)
        except Exception as e:
            log.warning(f'清理临时文件时出错: {e}', exc_info=True)
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取下载器当前状态.
        
        Returns:
            包含状态信息的字典
        """
        return {
            'download_folder': str(self.download_folder),
            'cookies_file': self.cookies_file,
            'proxy': self.proxy,
            'running_processes': self.subprocess_manager.get_running_process_count()
        }

    async def close(self):
        """
        安全关闭下载器,清理所有正在运行的进程.
        """
        log.info('正在关闭下载器并清理资源...')
        await self.subprocess_manager.cleanup_all_processes()
        log.info('下载器已安全关闭')