# core/exceptions.py

from enum import Enum


class CircuitBreakerState(Enum):
    """熔断器状态枚举"""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class DownloaderException(Exception):
    """下载器模块的基础异常。"""


class MaxRetriesExceededException(DownloaderException):
    """当操作在所有重试后仍然失败时抛出。"""


class NetworkException(DownloaderException):
    """针对可能是临时性的网络相关错误。"""


class ProxyException(NetworkException):
    """针对代理特定的连接错误。"""


class AuthenticationException(DownloaderException):
    """针对认证/验证错误，通常需要更新cookies。"""


class DownloadStalledException(NetworkException):
    """当下载似乎停滞时抛出。"""


class NonRecoverableErrorException(DownloaderException):
    """针对不应重试的错误，例如 404 Not Found。"""

    def __init__(self, message, details=""):
        super().__init__(message)
        self.details = details


class FFmpegException(DownloaderException):
    """当 ffmpeg 处理文件失败时抛出。"""


class UnhandledException(DownloaderException):
    """当一个操作在重试循环中因为一个非预期的、不应重试的错误而失败时抛出。"""
