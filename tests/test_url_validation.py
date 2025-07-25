#!/usr/bin/env python3
"""
URL安全验证功能测试
测试前端和后端的URL安全验证机制
"""

import pytest
from fastapi.testclient import TestClient
from web.main import app, validate_url_security


class TestURLSecurityValidation:
    """测试URL安全验证功能"""

    def test_valid_urls(self):
        """测试有效的URL"""
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://bilibili.com/video/BV1xx411c7mD",
            "https://twitter.com/user/status/123456789",
            "https://x.com/user/status/123456789",
            "http://example.com/video",
            "https://music.youtube.com/watch?v=abc123",
            "https://www.tiktok.com/@user/video/1234567890",
            "https://soundcloud.com/artist/track",
        ]

        for url in valid_urls:
            is_valid, error = validate_url_security(url)
            assert is_valid, f"URL '{url}' should be valid, but got error: {error}"

    def test_invalid_protocols(self):
        """测试无效的协议"""
        invalid_protocols = [
            ("javascript:alert('xss')", "JavaScript injection"),
            ("data:text/html,<script>alert('xss')</script>", "Data URI with script"),
            ("file:///etc/passwd", "File protocol"),
            ("ftp://ftp.example.com/file", "FTP protocol"),
            ("mailto:test@example.com", "Mailto protocol"),
            ("tel:+1234567890", "Tel protocol"),
            ("vbscript:msgbox('xss')", "VBScript injection"),
            ("about:blank", "About protocol"),
            ("chrome://settings", "Chrome protocol"),
            ("chrome-extension://abc123/popup.html", "Chrome extension"),
            ("moz-extension://abc123/popup.html", "Mozilla extension"),
        ]

        for url, description in invalid_protocols:
            is_valid, error = validate_url_security(url)
            assert not is_valid, f"URL with {description} should be invalid: {url}"
            assert "protocol" in error.lower()

    def test_xss_prevention(self):
        """测试XSS防护"""
        xss_attempts = [
            ("https://evil.com/<script>alert('xss')</script>", "Script tag in URL"),
            (
                "https://evil.com/</script><script>alert('xss')</script>",
                "Script tag injection",
            ),
            (
                "https://evil.com/<iframe src='javascript:alert(1)'></iframe>",
                "Iframe injection",
            ),
            (
                "https://evil.com/<object data='javascript:alert(1)'></object>",
                "Object injection",
            ),
            (
                "https://evil.com/<embed src='javascript:alert(1)'></embed>",
                "Embed injection",
            ),
            (
                "https://evil.com/<link rel='stylesheet' href='javascript:alert(1)'>",
                "Link injection",
            ),
            (
                "https://evil.com/<meta http-equiv='refresh' content='0;javascript:alert(1)'>",
                "Meta injection",
            ),
            ("https://evil.com/page?onclick=alert('xss')", "Event handler injection"),
            ("https://evil.com/page?onload=alert('xss')", "Onload event injection"),
            ("https://evil.com/page\x00null", "Null byte injection"),  # 实际的空字节
            ("https://evil.com/page\ninjection", "Newline injection"),  # 实际的换行符
            (
                "https://evil.com/page\rinjection",
                "Carriage return injection",
            ),  # 实际的回车符
        ]

        for url, description in xss_attempts:
            is_valid, error = validate_url_security(url)
            assert not is_valid, (
                f"XSS attempt should be rejected ({description}): {url}"
            )
            assert "dangerous" in error.lower()

    def test_ssrf_prevention(self):
        """测试SSRF防护"""
        ssrf_attempts = [
            ("http://localhost/admin", "Localhost access"),
            ("https://127.0.0.1/secret", "Loopback IP"),
            ("http://0.0.0.0/internal", "All interfaces IP"),
            ("https://[::1]/ipv6-loopback", "IPv6 loopback"),
            ("http://10.0.0.1/internal-network", "Private network 10.x.x.x"),
            ("https://172.16.0.1/internal", "Private network 172.16-31.x.x"),
            ("http://192.168.1.1/router", "Private network 192.168.x.x"),
            ("https://169.254.169.254/metadata", "Link-local address"),
            ("http://example.com:22/ssh", "SSH port"),
            ("https://example.com:3306/mysql", "MySQL port"),
            ("http://example.com:6379/redis", "Redis port"),
            ("https://example.com:27017/mongodb", "MongoDB port"),
        ]

        for url, description in ssrf_attempts:
            is_valid, error = validate_url_security(url)
            assert not is_valid, (
                f"SSRF attempt should be rejected ({description}): {url}"
            )

    def test_edge_cases(self):
        """测试边界情况"""
        # 测试空URL
        is_valid, _ = validate_url_security("")
        assert not is_valid, "Empty URL should be invalid"

        is_valid, _ = validate_url_security("   ")
        assert not is_valid, "Whitespace-only URL should be invalid"

        # 测试长度限制
        long_url = "https://example.com/" + "a" * 2048
        is_valid, error = validate_url_security(long_url)
        assert not is_valid, "Overly long URL should be invalid"
        assert "too long" in error.lower()

        # 测试最大允许长度
        max_length_url = "https://example.com/" + "a" * (
            2048 - len("https://example.com/")
        )
        is_valid, _ = validate_url_security(max_length_url)
        assert is_valid, "URL at max length should be valid"

        # 测试无效URL格式
        is_valid, _ = validate_url_security("not-a-valid-url")
        assert not is_valid, "Invalid URL format should be rejected"

        # 测试缺少hostname
        is_valid, _ = validate_url_security("https://")
        assert not is_valid, "URL without hostname should be invalid"


class TestAPIURLValidation:
    """测试API端点的URL验证"""

    def setup_method(self):
        """设置测试客户端"""
        self.client = TestClient(app)

    def test_video_info_endpoint_invalid_url(self):
        """测试/video-info端点的URL验证"""
        invalid_requests = [
            {"url": "javascript:alert('xss')", "download_type": "video"},
            {"url": "http://localhost/admin", "download_type": "video"},
            {"url": "https://127.0.0.1/secret", "download_type": "video"},
            {"url": "file:///etc/passwd", "download_type": "video"},
            {
                "url": "https://example.com/<script>alert('xss')</script>",
                "download_type": "video",
            },
        ]

        for request_data in invalid_requests:
            response = self.client.post("/video-info", json=request_data)
            assert response.status_code == 400
            assert "Invalid URL" in response.json()["detail"]

    def test_downloads_endpoint_invalid_url(self):
        """测试/downloads端点的URL验证"""
        invalid_request = {
            "url": "javascript:alert('xss')",
            "download_type": "video",
            "format_id": "best",
            "resolution": "1080p",
        }

        response = self.client.post("/downloads", json=invalid_request)
        assert response.status_code == 400
        assert "Invalid URL" in response.json()["detail"]

    def test_download_stream_endpoint_invalid_url(self):
        """测试/download-stream端点的URL验证"""
        response = self.client.get(
            "/download-stream",
            params={
                "url": "javascript:alert('xss')",
                "download_type": "video",
                "format_id": "best",
                "resolution": "1080p",
                "title": "test",
            },
        )
        assert response.status_code == 400
        assert "Invalid URL" in response.json()["detail"]

    def test_valid_url_passes_validation(self):
        """测试有效URL能通过验证（到达下一步验证或处理）"""
        valid_request = {
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "download_type": "video",
        }

        # 这个请求应该在URL验证后到达下一步（可能因为其他原因失败，但不应该是URL验证失败）
        response = self.client.post("/video-info", json=valid_request)
        # URL验证应该通过，如果失败应该是其他原因（比如网络问题、yt-dlp问题等）
        if response.status_code == 400:
            # 如果是400错误，确保不是URL验证错误
            assert "Invalid URL" not in response.json().get("detail", "")


class TestComprehensiveURLSecurity:
    """测试综合URL安全性"""

    def test_protocol_bypass_attempts(self):
        """测试协议绕过尝试"""
        bypass_attempts = [
            "JAVASCRIPT:alert('xss')",  # 大写绕过
            "Javascript:alert('xss')",  # 混合大小写
            "java\\x00script:alert('xss')",  # 空字节注入
            "java\tscript:alert('xss')",  # Tab字符
            "java\nscript:alert('xss')",  # 换行符
            "java\rscript:alert('xss')",  # 回车符
            "&#106;&#97;&#118;&#97;&#115;&#99;&#114;&#105;&#112;&#116;&#58;alert('xss')",  # HTML实体编码
            "%6A%61%76%61%73%63%72%69%70%74%3Aalert('xss')",  # URL编码
        ]

        for attempt in bypass_attempts:
            is_valid, error = validate_url_security(attempt)
            assert not is_valid, (
                f"Protocol bypass attempt should be rejected: {attempt}"
            )

    def test_private_ip_detection(self):
        """测试私有IP地址检测"""
        private_ips = [
            "http://10.0.0.1/",
            "https://172.16.0.1/",
            "http://172.31.255.255/",
            "https://192.168.0.1/",
            "http://127.0.0.1/",
            "https://169.254.169.254/",  # AWS metadata
            "http://[::1]/",  # IPv6 localhost
        ]

        for ip_url in private_ips:
            is_valid, error = validate_url_security(ip_url)
            assert not is_valid, f"Private IP should be rejected: {ip_url}"
            assert (
                "private" in error.lower()
                or "local" in error.lower()
                or "loopback" in error.lower()
                or "not allowed" in error.lower()
            )

    def test_domain_validation_integration(self):
        """测试域名验证集成"""
        # 这些URL格式有效但可能不在白名单中
        valid_format_urls = [
            "https://allowed-domain.com/video",
            "https://another-allowed.com/path/to/video",
            "https://sub.allowed-domain.com/content",
        ]

        for url in valid_format_urls:
            is_valid, error = validate_url_security(url)
            # URL安全验证应该通过，域名白名单验证是另一个步骤
            assert is_valid, (
                f"Properly formatted URL should pass security validation: {url}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
