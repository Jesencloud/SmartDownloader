#!/usr/bin/env python3
"""
测试音频流选择优化 - 验证 "original (default)" 优先级
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


def create_mock_audio_formats():
    """创建模拟的音频格式数据"""
    mock_formats = [
        {
            # 普通音频流
            "format_id": "140",
            "ext": "m4a",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "format_note": "medium, m4a_dash",
            "language": None,
            "format": "140 - audio only (medium)",
        },
        {
            # 高质量音频流
            "format_id": "251",
            "ext": "webm",
            "acodec": "opus",
            "abr": 160,
            "format_note": "medium, webm_dash",
            "language": None,
            "format": "251 - audio only (medium)",
        },
        {
            # 标记为 "original (default)" 的音频流
            "format_id": "139",
            "ext": "m4a",
            "acodec": "mp4a.40.5",
            "abr": 48,
            "format_note": "low, m4a_dash, original (default)",
            "language": "en",
            "format": "139 - audio only (low, original default)",
        },
        {
            # 只有 "default" 标记的音频流
            "format_id": "250",
            "ext": "webm",
            "acodec": "opus",
            "abr": 64,
            "format_note": "low, webm_dash, default",
            "language": "en",
            "format": "250 - audio only (low, default)",
        },
        {
            # 只有 "original" 标记的音频流
            "format_id": "256",
            "ext": "m4a",
            "acodec": "mp4a.40.2",
            "abr": 192,
            "format_note": "high, m4a_dash, original",
            "language": "zh",
            "format": "256 - audio only (high, original)",
        },
    ]

    return mock_formats


def test_audio_selection():
    """测试音频流选择逻辑"""
    print("🧪 测试音频流选择优化")
    print("=" * 50)

    # 创建格式分析器
    analyzer = FormatAnalyzer()

    # 创建模拟数据
    mock_formats = create_mock_audio_formats()

    # 分析格式
    analyzed_formats = analyzer.analyze_formats(mock_formats)

    # 过滤出音频格式
    audio_formats = [f for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY]

    print(f"📊 找到 {len(audio_formats)} 个音频流:")
    for fmt in audio_formats:
        raw = fmt.raw_format
        print(f"  - {fmt.format_id}: {raw.get('format_note', 'N/A')} (abr: {fmt.abr})")

    print("\n🎯 开始选择最佳音频流...")

    # 选择最佳音频格式
    best_audio = analyzer._select_best_audio_format(audio_formats)

    print("\n✅ 选择结果:")
    print(f"   格式ID: {best_audio.format_id}")
    print(f"   比特率: {best_audio.abr} kbps")
    print(f"   编解码器: {best_audio.acodec}")
    print(f"   扩展名: {best_audio.ext}")
    print(f"   备注: {best_audio.raw_format.get('format_note', 'N/A')}")

    # 验证是否选择了 "original (default)"
    raw_format = best_audio.raw_format
    format_note = raw_format.get("format_note", "").lower()

    assert "original" in format_note and "default" in format_note, (
        f"选择的音频备注 '{format_note}' 不包含 'original (default)'"
    )


def test_edge_cases():
    """测试边缘情况"""
    print("\n🧪 测试边缘情况")
    print("=" * 30)

    analyzer = FormatAnalyzer()

    # 测试1: 没有特殊标记的情况
    print("测试1: 没有特殊标记，应该选择最高比特率")
    normal_formats = [
        {
            "format_id": "140",
            "ext": "m4a",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "format_note": "medium",
        },
        {
            "format_id": "251",
            "ext": "webm",
            "acodec": "opus",
            "abr": 160,  # 最高比特率
            "format_note": "medium",
        },
    ]

    analyzed = analyzer.analyze_formats(normal_formats)
    audio_only = [f for f in analyzed if f.stream_type == StreamType.AUDIO_ONLY]
    best = analyzer._select_best_audio_format(audio_only)

    expected_format = "251"  # 最高比特率
    if best.format_id == expected_format:
        print(f"✅ 正确选择了最高比特率格式: {best.format_id}")
    else:
        print(f"❌ 错误选择: 期望 {expected_format}, 实际 {best.format_id}")


if __name__ == "__main__":
    print("🚀 音频流选择优化测试")
    print("=" * 60)

    # 主要测试
    success = test_audio_selection()

    # 边缘情况测试
    test_edge_cases()

    print("\n" + "=" * 60)
    if success:
        print("🎉 测试通过！音频流选择优化工作正常")
    else:
        print("⚠️  测试未完全通过，需要进一步调试")
