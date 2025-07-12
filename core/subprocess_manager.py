#!/usr/bin/env python3
"""
子进程管理器模块
统一管理子进程的创建、执行、监控和清理
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Any

from rich.console import Console
from rich.progress import Progress, TaskID

from .retry_manager import RetryManager, with_retries
from .subprocess_progress_handler import SubprocessProgressHandler
from .error_handler import ErrorHandler
from .exceptions import (
    DownloaderException, FFmpegException, NetworkException,
    DownloadStalledException, MaxRetriesExceededException
)

log = logging.getLogger(__name__)
console = Console()


class SubprocessManager:
    """
    统一的子进程管理器，整合重试、进度、错误处理。
    
    负责管理所有子进程的生命周期，包括创建、监控、重试和清理。
    """
    
    def __init__(
        self,
        retry_manager: Optional[RetryManager] = None,
        progress_handler: Optional[SubprocessProgressHandler] = None,
        error_handler: Optional[ErrorHandler] = None
    ):
        """
        初始化子进程管理器。
        
        Args:
            retry_manager: 重试管理器实例，None则创建默认实例
            progress_handler: 进度处理器实例，None则创建默认实例
            error_handler: 错误处理器实例，None则创建默认实例
        """
        self.retry_manager = retry_manager or RetryManager()
        self.progress_handler = progress_handler or SubprocessProgressHandler()
        self.error_handler = error_handler or ErrorHandler()
        
        # 当前运行的进程列表，用于清理
        self._running_processes: List[asyncio.subprocess.Process] = []
    
    async def execute_with_progress(
        self,
        cmd: List[str],
        progress: Progress,
        task_id: TaskID,
        timeout: Optional[float] = None
    ) -> Tuple[int, str, str]:
        """
        执行带进度显示的子进程，自动包含重试逻辑。
        
        Args:
            cmd: 要执行的命令列表
            progress: Rich进度条实例
            task_id: 进度任务ID
            timeout: 超时时间（秒）
            
        Returns:
            Tuple[return_code, stdout, stderr]
            
        Raises:
            DownloaderException: 执行失败
            MaxRetriesExceededException: 重试次数超限
        """
        @with_retries()
        async def _execute():
            return await self._run_subprocess_with_progress(cmd, progress, task_id, timeout)
        
        return await _execute()
    
    async def execute_simple(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        check_returncode: bool = True
    ) -> Tuple[int, str, str]:
        """
        执行简单子进程，不带进度显示但包含重试逻辑。
        
        Args:
            cmd: 要执行的命令列表
            timeout: 超时时间（秒）
            check_returncode: 是否检查返回码
            
        Returns:
            Tuple[return_code, stdout, stderr]
            
        Raises:
            DownloaderException: 执行失败且check_returncode为True
            MaxRetriesExceededException: 重试次数超限
        """
        @with_retries()
        async def _execute():
            return await self._run_subprocess_simple(cmd, timeout, check_returncode)
        
        return await _execute()
    
    async def _run_subprocess_with_progress(
        self,
        cmd: List[str],
        progress: Progress,
        task_id: TaskID,
        timeout: Optional[float] = None
    ) -> Tuple[int, str, str]:
        """
        实际执行带进度的子进程的内部方法。
        
        Args:
            cmd: 要执行的命令列表
            progress: Rich进度条实例
            task_id: 进度任务ID
            timeout: 超时时间（秒）
            
        Returns:
            Tuple[return_code, stdout, stderr]
            
        Raises:
            DownloaderException: 执行失败
            DownloadStalledException: 下载停滞
        """
        process = None
        try:
            log.debug(f'执行带进度的命令: {" ".join(cmd)}')
            
            # 创建子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 添加到运行进程列表
            self._running_processes.append(process)
            
            # 使用进度处理器监控进程
            error_output = await self.progress_handler.handle_subprocess_with_progress(
                process, progress, task_id
            )
            
            # 获取返回码和输出
            return_code = process.returncode
            stdout = b''
            stderr = error_output.encode('utf-8')
            
            # 检查执行结果
            if return_code != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                
                # 使用错误处理器分析错误类型
                if self.retry_manager.should_retry(error_msg):
                    if self.retry_manager.is_proxy_error(error_msg):
                        raise NetworkException(f'代理错误: {error_msg}')
                    else:
                        raise DownloadStalledException(f'下载停滞: {error_msg}')
                else:
                    # 创建适当的异常类型
                    exception = self.error_handler.create_exception(return_code, error_msg)
                    raise exception
            
            return return_code, stdout.decode('utf-8', errors='ignore'), stderr.decode('utf-8', errors='ignore')
        
        except asyncio.TimeoutError as e:
            raise DownloadStalledException(f'进程执行超时: {e}') from e
        except OSError as e:
            raise DownloaderException(f'进程创建失败: {e}') from e
        finally:
            # 确保进程被正确清理
            if process:
                await self._cleanup_process(process)
    
    async def _run_subprocess_simple(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        check_returncode: bool = True
    ) -> Tuple[int, str, str]:
        """
        实际执行简单子进程的内部方法。
        
        Args:
            cmd: 要执行的命令列表
            timeout: 超时时间（秒）
            check_returncode: 是否检查返回码
            
        Returns:
            Tuple[return_code, stdout, stderr]
            
        Raises:
            DownloaderException: 执行失败且check_returncode为True
        """
        process = None
        try:
            log.debug(f'执行简单命令: {" ".join(cmd)}')
            
            # 创建子进程
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # 添加到运行进程列表
            self._running_processes.append(process)
            
            # 等待进程完成
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                raise DownloadStalledException(f'进程执行超时')
            
            stdout_str = stdout.decode('utf-8', errors='ignore')
            stderr_str = stderr.decode('utf-8', errors='ignore')
            
            # 检查返回码
            if check_returncode and process.returncode != 0:
                # 使用错误处理器分析错误类型
                if self.retry_manager.should_retry(stderr_str):
                    if self.retry_manager.is_proxy_error(stderr_str):
                        raise NetworkException(f'代理错误: {stderr_str}')
                    else:
                        raise DownloadStalledException(f'执行失败: {stderr_str}')
                else:
                    # 创建适当的异常类型
                    exception = self.error_handler.create_appropriate_exception(stderr_str, ' '.join(cmd))
                    raise exception
            
            return process.returncode, stdout_str, stderr_str
        
        except OSError as e:
            raise DownloaderException(f'进程创建失败: {e}') from e
        finally:
            # 确保进程被正确清理
            if process:
                await self._cleanup_process(process)
    
    async def _cleanup_process(self, process: asyncio.subprocess.Process):
        """
        清理单个进程。
        
        Args:
            process: 要清理的进程
        """
        try:
            # 从运行进程列表中移除
            if process in self._running_processes:
                self._running_processes.remove(process)
            
            # 如果进程仍在运行，尝试优雅终止
            if process.returncode is None:
                try:
                    process.terminate()
                    # 等待进程终止，最多等待5秒
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # 如果优雅终止失败，强制杀死进程
                    log.warning('进程优雅终止超时，强制杀死进程')
                    try:
                        process.kill()
                        await process.wait()
                    except ProcessLookupError:
                        # 进程已经不存在了
                        pass
                except ProcessLookupError:
                    # 进程已经终止了
                    pass
        except Exception as e:
            log.warning(f'清理进程时出错: {e}', exc_info=True)
    
    async def cleanup_all_processes(self):
        """
        清理所有正在运行的进程。
        
        通常在程序退出或异常情况下调用。
        """
        log.info(f'正在清理 {len(self._running_processes)} 个运行中的进程...')
        
        cleanup_tasks = []
        for process in self._running_processes.copy():
            cleanup_tasks.append(self._cleanup_process(process))
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        self._running_processes.clear()
        log.info('所有进程清理完成')
    
    def get_running_process_count(self) -> int:
        """
        获取当前运行的进程数量。
        
        Returns:
            正在运行的进程数量
        """
        return len(self._running_processes)