#!/usr/bin/env python3
"""
使用真实YouTube数据测试音频流选择算法
"""

import logging
import sys
from pathlib import Path

from core.format_analyzer import FormatAnalyzer, StreamType

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(name)s: %(message)s")


def create_real_youtube_formats():
    """创建基于真实YouTube数据的格式"""

    # 140-9 (日语，不应该选择)
    format_140_9 = {
        "format_id": "140-9",
        "format_note": "Japanese, medium",
        "ext": "m4a",
        "acodec": "mp4a.40.2",
        "abr": 129.486,
        "language": "ja",
        "format": "140-9 - audio only (Japanese, medium)",
        "vcodec": "none",
        "url": "https://example.com/xtags=acont%3Ddubbed-auto%3Alang%3Dja",
    }

    # 140-10 (英语原始默认，应该选择)
    format_140_10 = {
        "format_id": "140-10",
        "format_note": "English (United States) original (default), medium",
        "ext": "m4a",
        "acodec": "mp4a.40.2",
        "abr": 129.482,
        "language": "en-US",
        "format": "140-10 - audio only (English (United States) original (default), medium)",
        "vcodec": "none",
        "url": "https://example.com/xtags=acont%3Doriginal%3Alang%3Den-US",
    }

    # 140-0 (英语，但没有特殊标记)
    format_140_0 = {
        "format_id": "140-0",
        "format_note": "medium",
        "ext": "m4a",
        "acodec": "mp4a.40.2",
        "abr": 129.482,
        "language": "en",
        "format": "140-0 - audio only (medium)",
        "vcodec": "none",
    }

    return [format_140_9, format_140_10, format_140_0]


def test_real_data_selection():
    """使用真实数据测试音频流选择"""
    print("🎬 使用真实YouTube数据测试音频流选择")
    print("=" * 60)

    # 创建格式分析器
    analyzer = FormatAnalyzer()

    # 创建真实数据
    real_formats = create_real_youtube_formats()

    print("📊 测试数据:")
    for fmt in real_formats:
        print(f"  - {fmt['format_id']}: {fmt['format_note']} (language: {fmt['language']})")

    # 分析格式
    analyzed_formats = analyzer.analyze_formats(real_formats)

    # 过滤音频格式
    audio_formats = [f for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY]

    print(f"\n🎯 找到 {len(audio_formats)} 个音频流")
    print("开始选择最佳音频流...")

    # 选择最佳音频格式
    best_audio = analyzer._select_best_audio_format(audio_formats)

    print("\n✅ 选择结果:")
    print(f"   格式ID: {best_audio.format_id}")
    print(f"   备注: {best_audio.raw_format.get('format_note', 'N/A')}")
    print(f"   语言: {best_audio.raw_format.get('language', 'N/A')}")

    # 验证结果
    assert best_audio.format_id == "140-10", f"期望选择 '140-10', 但实际选择了 '{best_audio.format_id}'"


def debug_scoring():
    """调试评分过程"""
    print("\n🔍 调试评分过程")
    print("=" * 40)

    analyzer = FormatAnalyzer()
    real_formats = create_real_youtube_formats()
    analyzed_formats = analyzer.analyze_formats(real_formats)
    audio_formats = [f for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY]

    print("各格式详细评分:")
    for fmt in audio_formats:
        score = analyzer._calculate_audio_score(fmt)
        raw = fmt.raw_format

        print(f"\n格式 {fmt.format_id}:")
        print(f"  总分: {score:.2f}")
        print(f"  比特率: {fmt.abr} -> {fmt.abr / 10:.1f}分")
        print(f"  format_note: '{raw.get('format_note', '')}'")
        print(f"  language: '{raw.get('language', '')}'")

        # 检查特殊标记
        fields_to_check = [
            raw.get("format_note", "") or "",
            raw.get("language", "") or "",
            raw.get("format", "") or "",
        ]
        combined_info = " ".join(str(field).lower() for field in fields_to_check if field)
        print(f"  检查字段: '{combined_info}'")

        if "original" in combined_info and "default" in combined_info:
            print("  🎯 包含 'original (default)' -> +50分")
        elif "default" in combined_info:
            print("  🎯 包含 'default' -> +30分")
        elif "original" in combined_info:
            print("  🎯 包含 'original' -> +20分")


if __name__ == "__main__":
    print("🧪 真实YouTube数据音频流选择测试")
    print("=" * 70)

    # 主要测试
    success = test_real_data_selection()

    # 调试评分
    debug_scoring()

    print("\n" + "=" * 70)
    if success:
        print("🎉 测试通过！算法正确选择了140-10")
    else:
        print("❌ 测试失败！需要调整算法")
