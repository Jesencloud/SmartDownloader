import pytest

from core.format_analyzer import FormatAnalyzer, StreamType

# 模拟的音频格式数据，用于测试
MOCK_AUDIO_FORMATS = [
    # 0: 普通m4a流
    {"format_id": "140", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 128, "format_note": "medium"},
    # 1: 高比特率opus流
    {"format_id": "251", "ext": "webm", "acodec": "opus", "abr": 160, "format_note": "medium"},
    # 2: 低比特率，但标记为 "original (default)" -> 最高优先级
    {"format_id": "139", "ext": "m4a", "acodec": "mp4a.40.5", "abr": 48, "format_note": "low, original (default)"},
    # 3: 低比特率，但标记为 "default"
    {"format_id": "250", "ext": "webm", "acodec": "opus", "abr": 64, "format_note": "low, default"},
    # 4: 高比特率，但标记为 "original"
    {"format_id": "256", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 192, "format_note": "high, original"},
    # 5: 高音质标记
    {"format_id": "258", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 384, "format_note": "high"},
    # 6: 低音质标记
    {"format_id": "259", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 128, "format_note": "low"},
    # 7: 与场景0比特率相同，但容器和编解码器不受偏好
    {"format_id": "249", "ext": "webm", "acodec": "opus", "abr": 128, "format_note": "medium"},
    # 8: 新增：带偏好语言的音轨
    {"format_id": "300", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 128, "format_note": "medium", "language": "ja"},
    # 9: 新增：带'primary'关键字的音轨
    {"format_id": "301", "ext": "m4a", "acodec": "mp4a.40.2", "abr": 128, "format_note": "medium, primary"},
]


@pytest.fixture
def analyzer():
    """提供一个 FormatAnalyzer 实例"""
    return FormatAnalyzer()


@pytest.mark.parametrize(
    "description, formats, expected_format_id",
    [
        (
            "应优先选择 'original (default)'，即使其比特率最低",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[1], MOCK_AUDIO_FORMATS[2]],
            "139",
        ),
        (
            "在没有 'original (default)' 时，应选择 'original'",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[3], MOCK_AUDIO_FORMATS[4]],
            "256",
        ),
        (
            "在没有 'original' 标记时，应选择 'default'",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[3]],
            "140",
        ),
        (
            "在没有特殊标记时，应选择 'high' 音质标记",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[5], MOCK_AUDIO_FORMATS[6]],
            "258",
        ),
        (
            "在所有标记都相同时，应选择比特率最高的",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[1]],
            "140",
        ),
        (
            "应避免选择 'low' 音质，除非没有更好的选择",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[6]],
            "140",
        ),
        (
            "在比特率和音质标记相同时，应优先选择偏好的容器/编解码器 (m4a > opus)",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[7]],
            "140",
        ),
        (
            "在其他条件相同时，应优先选择指定语言的音轨 (ja)",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[8]],
            "300",
        ),
        (
            "在其他条件相同时，应优先选择带 'primary' 关键字的音轨",
            [MOCK_AUDIO_FORMATS[0], MOCK_AUDIO_FORMATS[9]],
            "301",
        ),
    ],
)
def test_audio_selection_logic(analyzer, description, formats, expected_format_id):
    """
    测试音频选择的核心逻辑。

    Args:
        analyzer: FormatAnalyzer 实例
        description: 测试场景的描述
        formats: 用于测试的模拟格式列表
        expected_format_id: 期望被选中的格式 ID
    """
    # 分析格式
    analyzed_formats = analyzer.analyze_formats(formats)
    audio_formats = [f for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY]

    # 选择最佳音频
    best_audio = analyzer._select_best_audio_format(audio_formats)

    # 断言
    assert best_audio.format_id == expected_format_id, description
