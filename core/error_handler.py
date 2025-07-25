# core/error_handler.py

import logging
import re
from typing import Optional

from config_manager import config
from .exceptions import (
    ProxyException,
    NetworkException,
    DownloaderException,
    AuthenticationException,
)

log = logging.getLogger(__name__)


class ErrorHandler:
    """处理各种类型的错误和异常"""

    def __init__(self):
        self.retry_patterns = config.downloader.retry_patterns
        self.proxy_patterns = config.downloader.proxy_patterns

    def should_retry(self, error_output: str) -> bool:
        """判断是否应该重试"""
        if not error_output:
            return False

        error_lower = error_output.lower()
        return any(re.search(p.lower(), error_lower) for p in self.retry_patterns)

    def is_proxy_error(self, error_output: str) -> bool:
        """判断是否是代理错误"""
        if not error_output:
            return False

        error_lower = error_output.lower()
        return any(p.lower() in error_lower for p in self.proxy_patterns)

    def classify_error(self, error_output: str) -> str:
        """
        分类错误类型

        Returns:
            str: 错误类型 ('proxy', 'network', 'auth', 'other')
        """
        if self.is_auth_error(error_output):
            return "auth"
        elif self.is_proxy_error(error_output):
            return "proxy"
        elif self.should_retry(error_output):
            return "network"
        else:
            return "other"

    def is_auth_error(self, error_output: str) -> bool:
        """判断是否是认证/验证错误"""
        if not error_output:
            return False

        error_lower = error_output.lower()
        auth_patterns = [
            "sign in to confirm you're not a bot",
            "use --cookies-from-browser or --cookies for the authentication",
            "authentication required",
            "login required",
            "cookies are required",
            "please sign in",
            "verification required",
            "does not look like a netscape format cookies file",
            "invalid cookies",
            "cookies file is invalid",
        ]
        return any(pattern in error_lower for pattern in auth_patterns)

    def create_appropriate_exception(
        self, error_output: str, command: str
    ) -> Exception:
        """
        根据错误输出创建合适的异常

        Args:
            error_output: 错误输出内容
            command: 执行的命令

        Returns:
            Exception: 相应的异常对象
        """
        error_type = self.classify_error(error_output)
        truncated_error = error_output[:200] if error_output else "未知错误"

        if error_type == "auth":
            return AuthenticationException(
                f"认证失败，需要更新cookies: {truncated_error}"
            )
        elif error_type == "proxy":
            return ProxyException(f"代理连接失败: {truncated_error}")
        elif error_type == "network":
            return NetworkException(f"可重试的网络错误: {truncated_error}")
        else:
            return DownloaderException(f"命令 '{command}' 执行失败: {truncated_error}")

    def handle_subprocess_error(
        self, returncode: int, error_output: str, command: str
    ) -> Optional[Exception]:
        """
        处理子进程错误

        Args:
            returncode: 进程返回码
            error_output: 错误输出
            command: 执行的命令

        Returns:
            Optional[Exception]: 如果需要抛出异常则返回异常对象，否则返回None
        """
        if returncode == 0:
            return None

        log.error(f"子进程 '{command}' 失败，返回码: {returncode}")
        log.error(f"错误输出: {error_output}")

        return self.create_appropriate_exception(error_output, command)

    def log_error_details(self, error: Exception, context: str = "") -> None:
        """
        记录错误详情

        Args:
            error: 异常对象
            context: 上下文信息
        """
        error_context = f" ({context})" if context else ""
        log.error(f"错误发生{error_context}: {str(error)}", exc_info=True)

    def get_user_friendly_error_message(self, error: Exception) -> str:
        """
        获取用户友好的错误信息

        Args:
            error: 异常对象

        Returns:
            str: 用户友好的错误信息
        """
        if isinstance(error, AuthenticationException):
            return "需要重新登录或更新cookies，正在尝试自动获取..."
        elif isinstance(error, ProxyException):
            return "代理连接失败，请检查代理设置"
        elif isinstance(error, NetworkException):
            return "网络连接出现问题，正在重试..."
        elif isinstance(error, DownloaderException):
            return f"下载过程中出现错误: {str(error)}"
        else:
            return f"发生未知错误: {str(error)}"
