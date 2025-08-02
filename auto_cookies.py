#!/usr/bin/env python3
"""
自动获取浏览器cookies模块
支持Chrome, Firefox, Safari等主流浏览器
包含cookies缓存机制和详细异常处理
"""

import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from typing import Dict, List, Optional, Tuple
except ImportError:
    # Python 3.8兼容性
    from typing import Dict, List, Optional

    Tuple = tuple

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 定义特定的异常类
class BrowserCookieError(Exception):
    """浏览器cookies提取异常。

    当从浏览器提取cookies过程中发生错误时抛出此异常。
    """

    pass


class CacheError(Exception):
    """缓存操作异常。

    当缓存文件操作过程中发生错误时抛出此异常。
    """

    pass


class BrowserCookiesExtractor:
    """浏览器cookies提取器。

    支持从Chrome、Firefox、Safari、Edge等主流浏览器提取cookies，
    并提供缓存机制以提高性能和减少浏览器访问频率。

    Attributes:
        cache_enabled (bool): 是否启用缓存机制。
        cache_file (str): 缓存文件路径。
        cache_duration (timedelta): 缓存有效期。
        supported_browsers (dict): 支持的浏览器及其处理方法。
    """

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_file: str = "cookies.cache.txt",
        cache_duration_hours: int = 24,
    ):
        """初始化浏览器cookies提取器。

        Args:
            cache_enabled (bool): 是否启用缓存机制，默认为True。
            cache_file (str): 缓存文件路径，默认为'cookies.cache.txt'。
            cache_duration_hours (int): 缓存有效期（小时），默认为24小时。
        """
        self.cache_enabled = cache_enabled
        self.cache_file = cache_file
        self.cache_duration = timedelta(hours=cache_duration_hours)

        self.supported_browsers = {
            "chrome": self._get_chrome_cookies,
            "firefox": self._get_firefox_cookies,
            "safari": self._get_safari_cookies,
            "edge": self._get_edge_cookies,
        }

    def extract_cookies_for_domain(self, domain: str, browser: str = "auto") -> Optional[str]:
        """
        为指定域名提取cookies并保存为Netscape格式（含缓存机制）

        Args:
            domain: 目标域名（如 'youtube.com', 'bilibili.com'）
            browser: 浏览器类型 ('auto', 'chrome', 'firefox', 'safari', 'edge')

        Returns:
            str: cookies文件路径，如果失败则返回None
        """
        # 1. 首先检查缓存 (卫语句)
        if self.cache_enabled and self._is_cache_valid():
            logger.info(f"✅ 使用有效的cookies缓存: {self.cache_file}")
            return self.cache_file

        # 2. 确定要尝试的浏览器列表
        browsers_to_try = self.supported_browsers.keys() if browser == "auto" else [browser]

        # 3. 遍历并尝试提取
        for browser_name in browsers_to_try:
            if browser_name not in self.supported_browsers:
                logger.error(f"不支持的浏览器: {browser_name}")
                continue

            try:
                cookies_file = self._try_extract_and_save(browser_name, domain)
                if cookies_file:
                    return cookies_file  # 成功提取，立即返回
            except BrowserCookieError as e:
                log_message = f"从 {browser_name} 获取cookies失败: {e}"
                if browser == "auto":
                    logger.debug(log_message)  # 在自动模式下，失败是正常的，使用debug级别
                else:
                    logger.error(log_message)  # 在指定浏览器模式下，失败是错误
            except Exception as e:
                logger.warning(f"从 {browser_name} 获取cookies时发生未知错误: {e}")

        return None

    def _try_extract_and_save(self, browser: str, domain: str) -> Optional[str]:
        """
        尝试从单个浏览器提取、保存并缓存cookies。

        Args:
            browser: 浏览器名称
            domain: 目标域名

        Returns:
            str: 成功后的cookies文件路径，否则返回None
        """
        cookies = self._extract_cookies_with_retry(browser, domain)
        if not cookies:
            return None

        cookies_file = self._save_cookies_to_file(cookies, domain)
        if cookies_file and self.cache_enabled:
            self._update_cache(cookies_file)

        return cookies_file

    def _extract_cookies_with_retry(self, browser: str, domain: str, max_retries: int = 2) -> List[Dict]:
        """带重试机制的cookies提取。

        Args:
            browser (str): 浏览器类型。
            domain (str): 目标域名。
            max_retries (int): 最大重试次数，默认为2次。

        Returns:
            List[Dict]: 提取到的cookies列表。

        Raises:
            BrowserCookieError: 当cookies提取失败时。
        """
        if browser not in self.supported_browsers:
            raise BrowserCookieError(f"不支持的浏览器: {browser}")

        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                return self.supported_browsers[browser](domain)
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    logger.debug(f"第{attempt + 1}次尝试从{browser}获取cookies失败，重试中...")
                    time.sleep(1)  # 短暂等待后重试

        # 如果所有重试都失败了，则转换并抛出最终的异常
        if last_exception:
            raise self._convert_to_specific_error(last_exception, browser)

    def _convert_to_specific_error(self, e: Exception, browser: str) -> BrowserCookieError:
        """将通用异常转换为更具体的BrowserCookieError。"""
        error_message = str(e).lower()
        if "database is locked" in error_message:
            return BrowserCookieError(f"无法访问{browser}数据库，请关闭浏览器后重试")
        if "permission denied" in error_message:
            return BrowserCookieError(f"权限被拒绝，无法访问{browser}cookies文件")
        if "no such file" in error_message:
            return BrowserCookieError(f"未找到{browser}cookies文件，请确保浏览器已安装并使用过")
        return BrowserCookieError(f"从{browser}获取cookies失败: {e}")

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效。

        Returns:
            bool: 如果缓存文件存在且在有效期内则返回True，否则返回False。
        """
        try:
            cache_path = Path(self.cache_file)
            if not cache_path.exists():
                return False

            # 检查文件修改时间
            file_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            current_time = datetime.now()

            return (current_time - file_mtime) < self.cache_duration
        except (OSError, PermissionError) as e:
            logger.debug(f"检查缓存有效性时无法访问文件: {e}")
            return False
        except Exception as e:
            logger.warning(f"检查缓存有效性时发生未知错误: {e}", exc_info=True)
            return False

    def _update_cache(self, cookies_file: str) -> None:
        """更新cookies缓存。

        Args:
            cookies_file (str): 要复制到缓存的cookies文件路径。
        """
        try:
            if cookies_file != self.cache_file:
                shutil.copy2(cookies_file, self.cache_file)
                logger.info(f"✅ cookies缓存已更新: {self.cache_file}")
        except (OSError, PermissionError) as e:
            logger.warning(f"无法写入cookies缓存文件: {e}")
        except Exception as e:
            logger.error(f"更新cookies缓存时发生未知错误: {e}", exc_info=True)

    def clear_cache(self) -> bool:
        """清除cookies缓存。

        Returns:
            bool: 如果成功清除缓存则返回True，否则返回False。
        """
        try:
            cache_path = Path(self.cache_file)
            if cache_path.exists():
                cache_path.unlink()
                logger.info(f"✅ cookies缓存已清除: {self.cache_file}")
                return True
            return False
        except (OSError, PermissionError) as e:
            logger.error(f"无法删除cookies缓存文件，权限不足: {e}")
            return False
        except Exception as e:
            logger.error(f"清除cookies缓存时发生未知错误: {e}", exc_info=True)
            return False

    def _get_chrome_cookies(self, domain: str) -> List[Dict]:
        """从Chrome浏览器获取cookies。

        Args:
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从Chrome提取的cookies列表。

        Raises:
            BrowserCookieError: 当无法访问Chrome cookies数据库时。
        """
        cookies = []

        # Chrome cookies数据库路径（macOS）
        if sys.platform == "darwin":
            chrome_cookies_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")
        elif sys.platform == "win32":
            chrome_cookies_path = os.path.expanduser("~/AppData/Local/Google/Chrome/User Data/Default/Cookies")
        else:  # Linux
            chrome_cookies_path = os.path.expanduser("~/.config/google-chrome/Default/Cookies")

        if not os.path.exists(chrome_cookies_path):
            raise BrowserCookieError("未找到Chrome cookies数据库，请确保Chrome已安装并使用过")

        # 复制数据库到临时文件（因为Chrome可能正在使用）
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
                shutil.copy2(chrome_cookies_path, temp_file.name)
                temp_cookies_path = temp_file.name
        except PermissionError as e:
            raise BrowserCookieError("无法访问Chrome cookies文件，请关闭Chrome浏览器后重试") from e
        except (OSError, IOError) as e:
            raise BrowserCookieError(f"Chrome cookies文件操作失败: {e}") from e
        except Exception as e:
            raise BrowserCookieError(f"复制Chrome cookies文件时发生未知错误: {e}") from e

        try:
            conn = sqlite3.connect(temp_cookies_path, timeout=10.0)
            cursor = conn.cursor()

            # 查询指定域名的cookies
            query = """
            SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies 
            WHERE host_key LIKE ? OR host_key LIKE ?
            """

            cursor.execute(query, (f"%{domain}%", f"%.{domain}"))
            rows = cursor.fetchall()

            for row in rows:
                name, value, host_key, path, expires_utc, is_secure, is_httponly = row

                # 转换Chrome时间戳格式
                if expires_utc:
                    # Chrome使用Windows epoch (1601年1月1日)
                    expires = (expires_utc / 1000000) - 11644473600
                else:
                    expires = 0

                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": host_key,
                        "path": path,
                        "expires": int(expires),
                        "secure": bool(is_secure),
                        "httponly": bool(is_httponly),
                    }
                )

            conn.close()

        except sqlite3.DatabaseError as e:
            raise BrowserCookieError(f"Chrome数据库访问失败，可能被浏览器占用: {e}") from e
        except sqlite3.Error as e:
            raise BrowserCookieError(f"Chrome数据库操作失败: {e}") from e
        except Exception as e:
            raise BrowserCookieError(f"读取Chrome cookies时发生未知错误: {e}") from e
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_cookies_path)
            except (OSError, FileNotFoundError):
                # 文件可能已被删除或不存在，忽略错误
                pass
            except Exception as e:
                logger.warning(f"清理Chrome临时文件失败: {e}")

        if not cookies:
            logger.warning(f"在Chrome中未找到域名 {domain} 的cookies")

        return cookies

    def _get_firefox_cookies(self, domain: str) -> List[Dict]:
        """从Firefox浏览器获取cookies。

        Args:
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从Firefox提取的cookies列表。
        """
        cookies = []

        # Firefox profile目录
        if sys.platform == "darwin":
            firefox_path = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        elif sys.platform == "win32":
            firefox_path = os.path.expanduser("~/AppData/Roaming/Mozilla/Firefox/Profiles")
        else:  # Linux
            firefox_path = os.path.expanduser("~/.mozilla/firefox")

        if not os.path.exists(firefox_path):
            logger.warning("未找到Firefox profile目录")
            return cookies

        # 查找cookies.sqlite文件
        for profile_dir in os.listdir(firefox_path):
            profile_path = os.path.join(firefox_path, profile_dir)
            if os.path.isdir(profile_path):
                cookies_file = os.path.join(profile_path, "cookies.sqlite")
                if os.path.exists(cookies_file):
                    try:
                        cookies.extend(self._read_firefox_cookies(cookies_file, domain))
                    except BrowserCookieError as e:
                        logger.debug(f"读取Firefox profile {profile_dir} cookies失败: {e}")
                    except Exception as e:
                        logger.warning(
                            f"读取Firefox profile {profile_dir} cookies时发生未知错误: {e}",
                            exc_info=True,
                        )

        return cookies

    def _read_firefox_cookies(self, cookies_file: str, domain: str) -> List[Dict]:
        """读取Firefox cookies数据库。

        Args:
            cookies_file (str): Firefox cookies数据库文件路径。
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从数据库读取的cookies列表。
        """
        cookies = []

        # 复制到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
            shutil.copy2(cookies_file, temp_file.name)
            temp_cookies_path = temp_file.name

        try:
            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()

            query = """
            SELECT name, value, host, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies 
            WHERE host LIKE ? OR host LIKE ?
            """

            cursor.execute(query, (f"%{domain}%", f"%.{domain}"))
            rows = cursor.fetchall()

            for row in rows:
                name, value, host, path, expiry, is_secure, is_httponly = row

                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": host,
                        "path": path,
                        "expires": int(expiry) if expiry else 0,
                        "secure": bool(is_secure),
                        "httponly": bool(is_httponly),
                    }
                )

            conn.close()

        except (OSError, IOError, PermissionError) as e:
            logger.error(f"无法访问Firefox cookies文件: {e}")
        except sqlite3.Error as e:
            logger.error(f"Firefox数据库操作失败: {e}")
        except Exception as e:
            logger.error(f"读取Firefox cookies时发生未知错误: {e}", exc_info=True)
        finally:
            try:
                os.unlink(temp_cookies_path)
            except (OSError, FileNotFoundError):
                # 文件可能已被删除或不存在，忽略错误
                pass
            except Exception as e:
                logger.warning(f"清理Firefox临时文件失败: {e}")

        return cookies

    def _get_safari_cookies(self, domain: str) -> List[Dict]:
        """从Safari浏览器获取cookies。

        仅在macOS系统上支持，使用browser-cookie3库解析。

        Args:
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从Safari提取的cookies列表。
        """
        if sys.platform != "darwin":
            logger.warning("Safari cookies只在macOS上支持")
            return []

        try:
            import browser_cookie3

            logger.info(f"正在从Safari中为域名 {domain} 提取cookies...")
            cj = browser_cookie3.safari(domain_name=domain)
            cookies = []
            for cookie in cj:
                cookies.append(
                    {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "expires": cookie.expires,
                        "secure": cookie.secure,
                        "httponly": cookie.has_nonstandard_attr("HttpOnly"),
                    }
                )
            if not cookies:
                logger.warning(f"在Safari中未找到域名 {domain} 的cookies")
            return cookies
        except ImportError:
            logger.error("需要安装 'browser-cookie3' 库来提取Safari cookies。请运行: pip install browser-cookie3")
            return []
        except Exception as e:
            raise BrowserCookieError(f"从Safari提取cookies失败: {e}") from e

    def _get_edge_cookies(self, domain: str) -> List[Dict]:
        """从Microsoft Edge浏览器获取cookies。

        Args:
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从Edge提取的cookies列表。
        """
        cookies = []

        # Edge cookies路径（与Chrome类似）
        if sys.platform == "darwin":
            edge_cookies_path = os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Cookies")
        elif sys.platform == "win32":
            edge_cookies_path = os.path.expanduser("~/AppData/Local/Microsoft/Edge/User Data/Default/Cookies")
        else:  # Linux
            edge_cookies_path = os.path.expanduser("~/.config/microsoft-edge/Default/Cookies")

        if not os.path.exists(edge_cookies_path):
            logger.warning("未找到Edge cookies数据库")
            return cookies

        # 使用与Chrome相同的方法
        return self._read_chromium_cookies(edge_cookies_path, domain)

    def _read_chromium_cookies(self, cookies_path: str, domain: str) -> List[Dict]:
        """读取基于Chromium的浏览器cookies。

        Args:
            cookies_path (str): cookies数据库文件路径。
            domain (str): 目标域名。

        Returns:
            List[Dict]: 从数据库读取的cookies列表。
        """
        cookies = []

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_file:
            shutil.copy2(cookies_path, temp_file.name)
            temp_cookies_path = temp_file.name

        try:
            conn = sqlite3.connect(temp_cookies_path)
            cursor = conn.cursor()

            query = """
            SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies 
            WHERE host_key LIKE ? OR host_key LIKE ?
            """

            cursor.execute(query, (f"%{domain}%", f"%.{domain}"))
            rows = cursor.fetchall()

            for row in rows:
                name, value, host_key, path, expires_utc, is_secure, is_httponly = row

                if expires_utc:
                    expires = (expires_utc / 1000000) - 11644473600
                else:
                    expires = 0

                cookies.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": host_key,
                        "path": path,
                        "expires": int(expires),
                        "secure": bool(is_secure),
                        "httponly": bool(is_httponly),
                    }
                )

            conn.close()

        except (OSError, IOError, PermissionError) as e:
            logger.error(f"无法访问Chromium cookies文件: {e}")
        except sqlite3.Error as e:
            logger.error(f"Chromium数据库操作失败: {e}")
        except Exception as e:
            logger.error(f"读取Chromium cookies时发生未知错误: {e}", exc_info=True)
        finally:
            try:
                os.unlink(temp_cookies_path)
            except (OSError, FileNotFoundError):
                # 文件可能已被删除或不存在，忽略错误
                pass
            except Exception as e:
                logger.warning(f"清理Chromium临时文件失败: {e}")

        return cookies

    def _save_cookies_to_file(self, cookies: List[Dict], domain: str) -> Optional[str]:
        """保存cookies为Netscape格式文件。

        Args:
            cookies (List[Dict]): 要保存的cookies列表。
            domain (str): 目标域名。

        Returns:
            str: 保存的cookies文件路径，失败时返回None。
        """
        if not cookies:
            return None

        cookies_file = "cookies.txt"
        try:
            with open(cookies_file, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This is a generated file! Do not edit.\n\n")
                for cookie in cookies:
                    f.write(self._format_cookie_as_netscape(cookie))

            logger.info(f"成功保存 {len(cookies)} 个cookies到 {cookies_file}")
            return cookies_file

        except (OSError, IOError, PermissionError) as e:
            logger.error(f"无法写入cookies文件，权限不足或路径无效: {e}")
        except UnicodeEncodeError as e:
            logger.error(f"cookies内容编码错误: {e}")
        except Exception as e:
            logger.error(f"保存cookies文件时发生未知错误: {e}", exc_info=True)

        return None

    def _format_cookie_as_netscape(self, cookie: Dict) -> str:
        """将单个cookie字典格式化为Netscape格式的字符串行。"""
        domain_name = cookie.get("domain", "")
        domain_flag = "TRUE" if domain_name.startswith(".") else "FALSE"
        path = cookie.get("path", "/")
        secure = "TRUE" if cookie.get("secure", False) else "FALSE"
        expires = str(cookie.get("expires", 0))
        name = cookie.get("name", "")
        value = cookie.get("value", "")

        return f"{domain_name}\t{domain_flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n"

    def get_domain_from_url(self, url: str) -> str:
        """从URL提取域名。

        Args:
            url (str): 完整的URL地址。

        Returns:
            str: 提取的域名（移除www前缀）。
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc

        # 移除www前缀
        if domain.startswith("www."):
            domain = domain[4:]

        return domain


def auto_extract_cookies_for_url(
    url: str,
    browser: str = "auto",
    cache_enabled: bool = True,
    cache_file: str = "cookies.cache.txt",
    cache_duration_hours: int = 24,
) -> Optional[str]:
    """
    为指定URL自动提取cookies（含缓存支持）

    Args:
        url: 目标URL
        browser: 浏览器类型
        cache_enabled: 是否启用缓存
        cache_file: 缓存文件路径
        cache_duration_hours: 缓存有效期（小时）

    Returns:
        str: cookies文件路径，如果失败则返回None
    """
    extractor = BrowserCookiesExtractor(
        cache_enabled=cache_enabled,
        cache_file=cache_file,
        cache_duration_hours=cache_duration_hours,
    )
    domain = extractor.get_domain_from_url(url)

    logger.info(f"正在为域名 {domain} 自动提取cookies...")

    # 移除外层try-except，让异常在调用栈中向上传播
    # BrowserCookiesExtractor内部已有健壮的错误处理和日志记录
    cookies_file = extractor.extract_cookies_for_domain(domain, browser)

    if cookies_file:
        logger.info(f"✅ 成功提取cookies并保存到 {cookies_file}")
    else:
        logger.warning(f"❌ 无法为域名 {domain} 提取cookies")

    return cookies_file


def main():
    """主函数，用于命令行调用或无参数刷新。"""
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        # 如果有非标志的命令行参数，则按原方式处理
        url = sys.argv[1]
        browser = sys.argv[2] if len(sys.argv) > 2 else "auto"
        auto_extract_cookies_for_url(url, browser)
    else:
        # 如果没有命令行参数或只有标志，则刷新默认域名的cookies
        logger.info("没有提供URL，将尝试刷新默认域名的cookies...")
        default_domains = ["youtube.com", "bilibili.com"]
        for domain in default_domains:
            try:
                auto_extract_cookies_for_url(f"https://www.{domain}", "auto")
            except Exception as e:
                logger.warning(f"刷新 {domain} 的cookies时出错: {e}")


if __name__ == "__main__":
    main()
