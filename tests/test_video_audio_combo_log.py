#!/usr/bin/env python3
"""
测试视频音频组合日志输出
"""

import logging

from core.command_builder import CommandBuilder

# 设置详细日志
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")


def test_combo_logging():
    """测试视频音频组合日志输出"""
    print("🧪 测试视频音频组合日志输出")
    print("=" * 50)

    builder = CommandBuilder()

    print("\n1️⃣ 测试传统组合下载命令:")
    print("-" * 30)

    # 测试指定format_id的情况
    cmd, format_str, path = builder.build_combined_download_cmd(
        output_path="/tmp/test",
        url="https://youtu.be/1IHOyqN2XPA",
        file_prefix="test_video",
        format_id="401",
    )
    print(f"传统模式格式: {format_str}")

    print("\n2️⃣ 测试智能组合下载命令:")
    print("-" * 30)

    # 创建模拟格式数据
    mock_formats = [
        {
            "format_id": "401",
            "ext": "mp4",
            "vcodec": "avc1.640028",
            "acodec": "none",
            "width": 1920,
            "height": 1080,
            "vbr": 3000,
            "tbr": 3000,
        },
        {
            "format_id": "140-10",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "format_note": "English (United States) original (default), medium",
            "language": "en-US",
        },
        {
            "format_id": "140-9",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "format_note": "Japanese, medium",
            "language": "ja",
        },
    ]

    try:
        cmd, format_str, path, strategy = builder.build_smart_download_cmd(
            output_path="/tmp/test",
            url="https://youtu.be/1IHOyqN2XPA",
            file_prefix="smart_video",
            formats=mock_formats,
            format_id="401",
        )
        print(f"智能模式格式: {format_str}")
        print(f"使用策略: {strategy.value}")

    except Exception as e:
        print(f"智能模式测试失败: {e}")


if __name__ == "__main__":
    test_combo_logging()
