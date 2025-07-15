#!/usr/bin/env python3
"""
重试管理器模块
提供重试逻辑、熔断器管理和装饰器支持
"""

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, TypeVar, Union

from rich.console import Console

from config_manager import config
from .exceptions import (
    CircuitBreakerState, DownloaderException, MaxRetriesExceededException,
    DownloadStalledException, ProxyException, NetworkException, AuthenticationException
)

log = logging.getLogger(__name__)
console = Console()

F = TypeVar('F', bound=Callable[..., Any])


def with_retries(
    max_retries: int = None,
    base_delay: float = None,
    max_delay: float = None,
    backoff_factor: float = None
) -> Callable[[F], F]:
    """
    重试装饰器，为异步函数添加重试功能。
    
    Args:
        max_retries: 最大重试次数，默认使用配置文件值
        base_delay: 基础延迟时间，默认使用配置文件值
        max_delay: 最大延迟时间，默认使用配置文件值
        backoff_factor: 退避因子，默认使用配置文件值
        
    Returns:
        装饰后的函数
        
    Usage:
        @with_retries(max_retries=3, base_delay=5)
        async def download_operation():
            # 你的下载逻辑
            pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_manager = RetryManager(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_factor=backoff_factor
            )
            return await retry_manager.execute_with_retries(func, *args, **kwargs)
        return wrapper
    return decorator


class RetryManager:
    """负责重试逻辑和熔断器管理"""
    
    def __init__(
        self, 
        max_retries: int = None,
        base_delay: float = None,
        max_delay: float = None,
        backoff_factor: float = None
    ):
        """
        初始化重试管理器。
        
        Args:
            max_retries: 最大重试次数，None则使用配置文件值
            base_delay: 基础延迟时间，None则使用配置文件值
            max_delay: 最大延迟时间，None则使用配置文件值
            backoff_factor: 退避因子，None则使用配置文件值
        """
        # 从配置获取重试相关参数，支持参数覆盖
        self.max_retries = max_retries if max_retries is not None else config.downloader.max_retries
        self.base_delay = base_delay if base_delay is not None else config.downloader.base_delay
        self.max_delay = max_delay if max_delay is not None else config.downloader.max_delay
        self.backoff_factor = backoff_factor if backoff_factor is not None else config.downloader.backoff_factor
        
        # 熔断器相关参数（这些不支持覆盖，始终使用配置文件值）
        self.circuit_breaker_failure_threshold = config.downloader.circuit_breaker_failure_threshold
        self.circuit_breaker_timeout = config.downloader.circuit_breaker_timeout
        
        # 熔断器状态
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0

    def _calculate_delay(self, attempt: int) -> int:
        """计算指数退避延迟时间"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        jitter = random.uniform(0.5, 1.5)
        delay = min(delay * jitter, self.max_delay)
        return int(delay)

    def _check_circuit_breaker(self):
        """检查熔断器状态，并根据需要转换状态。"""
        if self._circuit_breaker_state == CircuitBreakerState.OPEN:
            elapsed_time = time.time() - self._last_failure_timestamp
            if elapsed_time > self.circuit_breaker_timeout:
                self._circuit_breaker_state = CircuitBreakerState.HALF_OPEN
                log.info("熔断器从 OPEN 转换为 HALF-OPEN 状态。")
            else:
                raise DownloaderException("熔断器处于 OPEN 状态，快速失败。")
        elif self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            log.info("熔断器处于 HALF-OPEN 状态，允许一次尝试。")

    def _record_failure(self):
        """记录一次失败，并根据阈值转换熔断器状态。"""
        self._failure_count += 1
        if self._circuit_breaker_state == CircuitBreakerState.HALF_OPEN:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            self._failure_count = 0  # Reset failure count for OPEN state
            log.warning("熔断器从 HALF-OPEN 转换为 OPEN 状态。")
        elif self._circuit_breaker_state == CircuitBreakerState.CLOSED and self._failure_count >= self.circuit_breaker_failure_threshold:
            self._circuit_breaker_state = CircuitBreakerState.OPEN
            self._last_failure_timestamp = time.time()
            log.warning(f"连续失败 {self._failure_count} 次，熔断器从 CLOSED 转换为 OPEN 状态。")

    def _reset_circuit_breaker(self):
        """重置熔断器到 CLOSED 状态。"""
        if self._circuit_breaker_state != CircuitBreakerState.CLOSED:
            log.info("熔断器重置为 CLOSED 状态。")
        self._circuit_breaker_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_timestamp = 0

    async def execute_with_retries(self, operation, *args, **kwargs) -> Any:
        """
        执行操作并在失败时重试
        
        Args:
            operation: 要执行的异步操作
            *args, **kwargs: 传递给操作的参数
            
        Returns:
            操作的结果
            
        Raises:
            MaxRetriesExceededException: 当所有重试都失败时
        """
        attempt = 0
        while attempt <= self.max_retries:
            self._check_circuit_breaker()
            
            try:
                if attempt > 0:
                    delay = self._calculate_delay(attempt - 1)
                    console.print(f"♾️ 第 {attempt + 1} 次尝试，等待 {delay} 秒...", style="bold yellow")
                    await asyncio.sleep(delay)

                result = await operation(*args, **kwargs)
                self._reset_circuit_breaker()  # 成功时重置熔断器
                return result

            except (DownloadStalledException, ProxyException, NetworkException) as e:
                log.warning(f"操作中遇到问题: {e}", exc_info=True)
                self._record_failure()
                
                attempt += 1
                if attempt > self.max_retries:
                    raise MaxRetriesExceededException(f"操作在 {self.max_retries + 1} 次尝试后失败。")
                continue

            except KeyboardInterrupt:
                raise
            except AuthenticationException:
                # 认证异常直接传播，不包装在DownloaderException中
                raise
            except Exception as e:
                log.error(f"未知错误: {e}", exc_info=True)
                raise

        raise MaxRetriesExceededException(f"操作在 {self.max_retries + 1} 次尝试后失败。")

    def should_retry(self, error_output: str) -> bool:
        """判断是否应该重试"""
        error_lower = error_output.lower()
        return any(p.lower() in error_lower for p in config.downloader.retry_patterns)

    def is_proxy_error(self, error_output: str) -> bool:
        """判断是否是代理错误"""
        error_lower = error_output.lower()
        return any(p.lower() in error_lower for p in config.downloader.proxy_patterns)