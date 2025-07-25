# core/cookies_manager.py

import logging
import os
from typing import Optional
from urllib.parse import urlparse

from auto_cookies import auto_extract_cookies_for_url
from core.exceptions import AuthenticationException

log = logging.getLogger(__name__)


class CookiesManager:
    """Cookies管理器，负责自动更新和管理cookies"""

    def __init__(self, cookies_file: str):
        """
        初始化Cookies管理器

        Args:
            cookies_file: 当前使用的cookies文件路径
        """
        self.cookies_file = cookies_file
        self.auto_refresh_enabled = True

    def should_refresh_cookies(self, error: Exception) -> bool:
        """
        判断是否应该刷新cookies

        Args:
            error: 发生的异常

        Returns:
            bool: 是否需要刷新cookies
        """
        return isinstance(error, AuthenticationException) and self.auto_refresh_enabled

    def refresh_cookies_for_url(self, url: str, browser: str = "auto") -> Optional[str]:
        """
        为指定URL刷新cookies

        Args:
            url: 目标URL
            browser: 浏览器类型 ('auto', 'chrome', 'firefox', etc.)

        Returns:
            str: 新的cookies文件路径，失败时返回None
        """
        log.info("🍪 检测到认证错误，正在自动从浏览器更新cookies...")

        try:
            # 备份当前cookies文件
            self._backup_current_cookies()

            # 从浏览器获取新cookies
            new_cookies_file = auto_extract_cookies_for_url(
                url=url,
                browser=browser,
                cache_enabled=True,
                cache_file="cookies.cache.txt",
                cache_duration_hours=1,  # 认证错误时缩短缓存时间
            )

            if new_cookies_file:
                # 更新主cookies文件
                self._update_main_cookies_file(new_cookies_file)
                log.info("✅ Cookies自动更新成功！")
                return self.cookies_file
            else:
                log.warning("❌ 无法从浏览器获取新cookies")
                # 尝试恢复备份
                self._restore_backup_cookies()
                return None

        except Exception as e:
            log.error(f"❌ 自动更新cookies失败: {e}")
            # 尝试恢复备份
            self._restore_backup_cookies()
            return None

    def _backup_current_cookies(self) -> None:
        """备份当前cookies文件"""
        try:
            if os.path.exists(self.cookies_file):
                backup_file = f"{self.cookies_file}.backup"
                import shutil

                shutil.copy2(self.cookies_file, backup_file)
                log.debug(f"已备份当前cookies: {backup_file}")
        except Exception as e:
            log.warning(f"备份cookies文件失败: {e}")

    def _restore_backup_cookies(self) -> None:
        """恢复备份的cookies文件"""
        try:
            backup_file = f"{self.cookies_file}.backup"
            if os.path.exists(backup_file):
                import shutil

                shutil.copy2(backup_file, self.cookies_file)
                log.info("已恢复备份的cookies文件")
        except Exception as e:
            log.warning(f"恢复备份cookies文件失败: {e}")

    def _update_main_cookies_file(self, new_cookies_file: str) -> None:
        """
        更新主cookies文件

        Args:
            new_cookies_file: 新的cookies文件路径
        """
        try:
            if new_cookies_file != self.cookies_file:
                import shutil

                shutil.copy2(new_cookies_file, self.cookies_file)
                log.debug(f"已更新主cookies文件: {self.cookies_file}")
        except Exception as e:
            log.error(f"更新主cookies文件失败: {e}")
            raise

    def get_domain_from_url(self, url: str) -> str:
        """
        从URL提取域名

        Args:
            url: URL地址

        Returns:
            str: 域名
        """
        parsed = urlparse(url)
        domain = parsed.netloc

        # 移除www前缀
        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    def disable_auto_refresh(self) -> None:
        """禁用自动刷新功能"""
        self.auto_refresh_enabled = False
        log.info("已禁用cookies自动刷新功能")

    def enable_auto_refresh(self) -> None:
        """启用自动刷新功能"""
        self.auto_refresh_enabled = True
        log.info("已启用cookies自动刷新功能")
