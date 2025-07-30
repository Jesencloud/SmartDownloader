#!/usr/bin/env python3
"""
测试URL简化标识符功能
"""

import re
from urllib.parse import urlparse

import pytest


def create_simplified_identifier(url: str, title: str = "") -> str:
    """
    为视频创建简化的标识符，用于文件来源显示

    Args:
        url: 原始视频URL
        title: 视频标题（可选）

    Returns:
        简化的标识符，格式如: "平台名-ID" 或 "标题-ID"
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path

        # 提取平台名称
        platform_map = {
            "youtube.com": "youtube",
            "youtu.be": "youtube",
            "x.com": "x",
            "twitter.com": "x",
            "bilibili.com": "bilibili",
            "weibo.com": "weibo",
            "douyin.com": "douyin",
            "tiktok.com": "tiktok",
        }

        platform = platform_map.get(domain, domain.split(".")[0] if "." in domain else domain)

        # 尝试从URL中提取ID
        video_id = ""

        # X/Twitter URL pattern: /username/status/1234567890
        if "x.com" in domain or "twitter.com" in domain:
            match = re.search(r"/status/(\d+)", path)
            if match:
                video_id = match.group(1)

        # YouTube URL patterns
        elif "youtube.com" in domain or "youtu.be" in domain:
            # youtube.com/watch?v=ID or youtu.be/ID
            match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]+)", url)
            if match:
                video_id = match.group(1)

        # Bilibili URL pattern
        elif "bilibili.com" in domain:
            match = re.search(r"/video/([a-zA-Z0-9_-]+)", path)
            if match:
                video_id = match.group(1)

        # 通用ID提取 - 寻找路径中的数字ID
        if not video_id:
            # 寻找长数字串（通常是视频ID）
            match = re.search(r"/(\d{8,})", path)
            if match:
                video_id = match.group(1)
            else:
                # 寻找字母数字组合的ID
                match = re.search(r"/([a-zA-Z0-9_-]{6,})", path)
                if match:
                    video_id = match.group(1)

        # 如果有标题且比较短，优先使用标题
        if title and len(title) <= 20:
            # 清理标题中的特殊字符
            clean_title = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", title)
            clean_title = re.sub(r"\s+", "-", clean_title.strip())
            if clean_title and video_id:
                return f"{clean_title}-{video_id[-8:]}"  # 使用标题+ID后8位
            elif clean_title:
                return clean_title

        # 构建标识符
        if video_id:
            # 如果ID太长，只取后面部分
            short_id = video_id[-10:] if len(video_id) > 10 else video_id
            return f"{platform}-{short_id}"

        # 兜底方案：使用域名
        return platform

    except Exception:
        # 出错时返回域名或简单标识
        try:
            return urlparse(url).netloc.split(".")[0]
        except Exception:
            return "video"


class TestURLIdentifier:
    """测试URL简化标识符功能"""

    def test_x_com_url_with_long_title(self):
        """测试X.com URL和长标题（用户提供的例子）"""
        url = "https://x.com/Morris_LT/status/1950001642440429675"
        title = "Morris - 日本任何庙堂没有门票，都不需要强制消费，全凭自己心意，一炷香 才100 日元。"

        result = create_simplified_identifier(url, title)

        # 长标题应该被忽略，使用平台标识符
        assert result == "x-2440429675"
        assert len(result) <= 20

    def test_x_com_url_with_short_title(self):
        """测试X.com URL和短标题"""
        url = "https://x.com/lidangzzz/status/1930492927299490249"
        title = "测试视频"

        result = create_simplified_identifier(url, title)

        # 短标题应该被使用
        assert result == "测试视频-99490249"
        assert "测试视频" in result
        assert result.split("-")[-1] == "99490249"

    def test_youtube_url_standard(self):
        """测试标准YouTube URL"""
        url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        title = "Never Gonna Give You Up"

        result = create_simplified_identifier(url, title)

        # 标题长度刚好20字符，应该被使用
        assert "youtube" in result or "Never" in result
        assert "WgXcQ" in result

    def test_youtube_short_url(self):
        """测试YouTube短链接"""
        url = "https://youtu.be/dQw4w9WgXcQ"
        title = "Rick Roll"

        result = create_simplified_identifier(url, title)

        # 短标题应该被使用
        assert "Rick-Roll" in result
        assert "WgXcQ" in result

    def test_bilibili_url(self):
        """测试Bilibili URL"""
        url = "https://bilibili.com/video/BV1234567890"
        title = "测试B站视频"

        result = create_simplified_identifier(url, title)

        # 短标题应该被使用
        assert "测试B站视频" in result
        assert "67890" in result or "BV1234567890" in result.split("-")[-1]

    def test_long_title_fallback_to_platform(self):
        """测试长标题回退到平台标识符"""
        url = "https://x.com/user/status/1234567890123456789"
        title = "这是一个非常非常长的视频标题，超过了20个字符的限制，所以应该使用平台标识符"

        result = create_simplified_identifier(url, title)

        # 应该使用平台标识符
        assert result.startswith("x-")
        assert "0123456789" in result
        assert "非常" not in result  # 长标题不应该被包含

    def test_unknown_platform(self):
        """测试未知平台"""
        url = "https://unknown-site.com/video/123456"
        title = ""

        result = create_simplified_identifier(url, title)

        # 应该使用域名和ID的组合
        assert result.startswith("unknown-site")
        assert "123456" in result

    def test_platform_mapping(self):
        """测试平台映射"""
        test_cases = [
            ("https://youtube.com/watch?v=abc123", "", "youtube"),
            ("https://youtu.be/abc123", "", "youtube"),
            ("https://x.com/user/status/123", "", "x"),
            ("https://twitter.com/user/status/123", "", "x"),
            ("https://bilibili.com/video/BV123", "", "bilibili"),
        ]

        for url, title, expected_platform in test_cases:
            result = create_simplified_identifier(url, title)
            assert result.startswith(expected_platform)

    def test_error_handling(self):
        """测试错误处理"""
        error_cases = [
            ("", "", ""),
            ("invalid-url", "", ""),
            ("https://", "", ""),
        ]

        for url, title, expected in error_cases:
            result = create_simplified_identifier(url, title)
            # 不应该抛出异常，应该返回某种默认值
            assert isinstance(result, str)
            if expected:
                assert result == expected

    def test_id_extraction_patterns(self):
        """测试不同ID提取模式"""
        test_cases = [
            # X.com status ID
            ("https://x.com/user/status/1234567890", "", r"x-\d{10}"),
            # YouTube video ID
            ("https://youtube.com/watch?v=abc123XYZ", "", r"youtube-[\w-]+"),
            # Generic long number ID
            ("https://example.com/video/12345678901234", "", r"example-\d+"),
        ]

        for url, title, pattern in test_cases:
            result = create_simplified_identifier(url, title)
            assert re.match(pattern, result), f"Result '{result}' doesn't match pattern '{pattern}'"

    def test_chinese_title_handling(self):
        """测试中文标题处理"""
        url = "https://bilibili.com/video/BV1234567890"
        title = "中文测试标题"

        result = create_simplified_identifier(url, title)

        assert "中文测试标题" in result
        assert len(result) <= 30  # 合理长度


if __name__ == "__main__":
    # 兼容直接运行
    pytest.main([__file__, "-v"])
