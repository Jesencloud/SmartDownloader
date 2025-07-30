#!/usr/bin/env python3
"""
智能下载功能测试。

本文件包含对 FormatAnalyzer 的单元测试，以及对代码库的集成检查。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from core.format_analyzer import DownloadStrategy, FormatAnalyzer, StreamType
from web.main import app

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def simulate_video_formats() -> List[Dict[str, Any]]:
    """
    模拟yt-dlp返回的视频格式列表
    """
    return [
        # 完整流 (MP4, 包含音视频)
        {
            "format_id": "22",
            "ext": "mp4",
            "vcodec": "avc1.64001F",
            "acodec": "mp4a.40.2",
            "width": 1280,
            "height": 720,
            "filesize": 50000000,
        },
        # 另一个完整流
        {
            "format_id": "18",
            "ext": "mp4",
            "vcodec": "avc1.42001E",
            "acodec": "mp4a.40.2",
            "width": 640,
            "height": 360,
            "filesize": 20000000,
        },
        # 仅视频流 (WebM)
        {
            "format_id": "248",
            "ext": "webm",
            "vcodec": "vp9",
            "acodec": "none",
            "width": 1920,
            "height": 1080,
            "filesize": 100000000,
        },
        # 仅视频流 (MP4)
        {
            "format_id": "137",
            "ext": "mp4",
            "vcodec": "avc1.640028",
            "acodec": "none",
            "width": 1920,
            "height": 1080,
            "filesize": 120000000,
        },
        # 仅音频流 (M4A)
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "filesize": 5000000,
        },
        # 另一个音频流
        {
            "format_id": "141",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 256,
            "filesize": 8000000,
        },
    ]


def demo_format_analysis():
    """辅助函数：演示格式分析功能"""
    print("\n=== 智能下载策略演示 ===")

    # 创建格式分析器
    analyzer = FormatAnalyzer()
    formats = simulate_video_formats()

    # 场景1: 自动选择最佳格式
    print("场景1: 自动选择最佳格式")
    plan = analyzer.find_best_download_plan(formats)
    print(f"  - 策略: {plan.strategy.value}")
    print(f"  - 格式ID: {plan.primary_format.format_id}\n")

    # 场景2: 用户指定一个需要合并的格式
    print("场景2: 用户指定一个需要合并的格式 (1080p)")
    plan = analyzer.find_best_download_plan(formats, target_format_id="137")
    print(f"  - 策略: {plan.strategy.value}")
    print(f"  - 格式ID: {plan.primary_format.format_id}\n")

    # 场景3: 用户指定一个完整流格式
    print("场景3: 用户指定一个完整流格式 (720p)")
    plan = analyzer.find_best_download_plan(formats, target_format_id="22")
    print(f"  - 策略: {plan.strategy.value}")
    print(f"  - 格式ID: {plan.primary_format.format_id}\n")

    # 总结
    summary = """
    总结:
    - 默认情况下，优先选择最高质量的完整流 (场景1)。
    - 当用户指定分离流时，会自动匹配最佳音频进行合并 (场景2)。
    - 当用户指定完整流时，直接使用该流 (场景3)。
    """
    print(summary)


def test_demo_functions_run_without_error():
    """
    测试：演示功能应能无异常运行。
    这主要用于确保演示代码本身没有语法或逻辑错误。
    """
    print("🚀 开始智能下载策略演示")
    demo_format_analysis()
    print("\n✅ 智能下载策略演示完成!")


def create_unknown_codec_test_formats():
    """创建基于实际案例的测试格式数据"""
    return [
        # 案例1: Twitter/X.com 视频 (null 编解码器)
        {
            "format_id": "http-1280-0",
            "ext": "mp4",
            "protocol": "https",
            "width": 720,
            "height": 1280,
            "vcodec": None,
            "acodec": None,
            "filesize": 1234567,
        },
        # 案例2: 另一个平台的完整流 (unknown 编解码器)
        {
            "format_id": "720p_h264",
            "ext": "mp4",
            "protocol": "https",
            "width": 1280,
            "height": 720,
            "vcodec": "unknown",
            "acodec": "unknown",
            "filesize": 2345678,
        },
        # 案例3: 标准的仅视频流
        {
            "format_id": "137",
            "ext": "mp4",
            "protocol": "https",
            "width": 1920,
            "height": 1080,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "filesize": 3456789,
        },
        # 案例4: 标准的仅音频流
        {
            "format_id": "140",
            "ext": "m4a",
            "protocol": "https",
            "width": None,
            "height": None,
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "filesize": 456789,
        },
        # 案例5: 明确标记为 audio only 的流
        {
            "format_id": "251",
            "ext": "webm",
            "protocol": "https",
            "width": None,
            "height": None,
            "vcodec": "audio only",
            "acodec": "opus",
            "filesize": 567890,
        },
    ]


def test_stream_type_detection():
    """测试：应能正确检测具有 'unknown' 或 'null' 编解码器的流类型。"""
    analyzer = FormatAnalyzer()  # Re-create for isolation
    test_formats = create_unknown_codec_test_formats()

    expected_results = {
        "http-1280-0": StreamType.COMPLETE,
        "720p_h264": StreamType.COMPLETE,
        "137": StreamType.VIDEO_ONLY,
        "140": StreamType.AUDIO_ONLY,
        "251": StreamType.AUDIO_ONLY,
    }

    all_passed = True
    for fmt in test_formats:
        fmt_id = fmt["format_id"]
        detected_type = analyzer._determine_stream_type(fmt)
        expected_type = expected_results[fmt_id]

        if detected_type == expected_type:
            print(f"✅ {fmt_id}: 正确识别为 {detected_type.value}")
        else:
            print(f"❌ {fmt_id}: 错误! 期望 {expected_type.value}, 实际为 {detected_type.value}")
            all_passed = False

    assert all_passed


def test_unknown_codec_strategy():
    """测试：当存在 'unknown' 编解码器的完整流时，应优先选择它们。"""
    analyzer = FormatAnalyzer()  # Re-create for isolation
    test_formats = create_unknown_codec_test_formats()

    try:
        # 自动选择最佳格式
        plan = analyzer.find_best_download_plan(test_formats)

        # 期望它选择分辨率最高的完整流，即 http-1280-0
        expected_format_id = "http-1280-0"

        assert plan.strategy == DownloadStrategy.DIRECT
        assert plan.primary_format.format_id == expected_format_id

        print(f"✅ 自动策略正确选择了 {expected_format_id}")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        assert False


def test_web_api_filtering():
    """测试：模拟的 Web API 逻辑应能正确筛选出所有完整流格式。"""
    test_formats = create_unknown_codec_test_formats()  # Get fresh data

    # 模拟Web API的筛选逻辑 - 更新后包含null编解码器处理
    complete_formats_raw = []
    for f in test_formats:
        if f.get("ext") == "mp4" and f.get("width") and f.get("height"):
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")

            if (
                (vcodec not in ("none", None, "") and acodec not in ("none", None, ""))
                or (vcodec == "unknown" and acodec == "unknown")
                or (vcodec is None and acodec is None)
            ):
                if vcodec != "audio only" and acodec != "video only":
                    complete_formats_raw.append(f)

    found_formats = {f["format_id"] for f in complete_formats_raw}
    expected_complete = {"http-1280-0", "720p_h264"}

    all_found = found_formats == expected_complete

    if all_found:
        print(f"✅ Web API 筛选逻辑正确找到了所有完整流: {found_formats}")
    else:
        print("❌ Web API 筛选逻辑错误!")
        print(f"   期望找到: {expected_complete}")
        print(f"   实际找到: {found_formats}")

    assert all_found and len(found_formats) == len(expected_complete)


@pytest.mark.integration
def test_backend_code_integration():
    """集成测试：检查后端关键代码文件和其中的关键实现是否存在。"""
    print("\n=== 测试后端代码集成 ===")

    results = []

    # 1. 检查 web/main.py 是否存在
    main_py = Path("web/main.py")
    results.append(main_py.exists())
    print(f"  {'✅' if main_py.exists() else '❌'} web/main.py 文件存在")

    # 2. 检查 web/celery_app.py 是否存在
    celery_py = Path("web/celery_app.py")
    results.append(celery_py.exists())
    print(f"  {'✅' if celery_py.exists() else '❌'} web/celery_app.py 文件存在")

    # 3. 检查 web/tasks.py 是否存在
    tasks_py = Path("web/tasks.py")
    results.append(tasks_py.exists())
    print(f"  {'✅' if tasks_py.exists() else '❌'} web/tasks.py 文件存在")

    # 4. 检查核心类 FormatAnalyzer 是否存在
    core_py = Path("core/format_analyzer.py")
    results.append(core_py.exists())
    print(f"  {'✅' if core_py.exists() else '❌'} core/format_analyzer.py 文件存在")

    assert all(results)


@pytest.mark.integration
def test_frontend_code_integration():
    """集成测试：检查前端关键文件和其中的关键实现是否存在。"""
    print("\n=== 测试前端代码集成 ===")

    results = []

    # 1. 检查 static/index.html 是否存在
    index_html = Path("static/index.html")
    results.append(index_html.exists())
    print(f"  {'✅' if index_html.exists() else '❌'} static/index.html 文件存在")

    # 2. 检查 index.html 中引用的 JS 文件是否存在
    script_js = Path("static/script.js")
    results.append(script_js.exists())
    print(f"  {'✅' if script_js.exists() else '❌'} static/script.js 文件存在")

    common_js = Path("static/common.js")
    results.append(common_js.exists())
    print(f"  {'✅' if common_js.exists() else '❌'} static/common.js 文件存在")

    # 3. 确认 style.css 不应存在，因为样式是内联的
    style_css = Path("static/css/style.css")
    print(f"  {'✅' if not style_css.exists() else '❌'} static/css/style.css 文件不存在 (正确，样式是内联的)")

    # 4. 检查多语言文件是否存在
    locales_dir = Path("static/locales")
    en_json = locales_dir / "en.json"
    zh_json = locales_dir / "zh-CN.json"
    results.append(en_json.exists())
    results.append(zh_json.exists())
    print(f"  {'✅' if en_json.exists() and zh_json.exists() else '❌'} 多语言文件 (en.json, zh-CN.json) 存在")

    assert all(results)


@pytest.mark.integration
def test_api_endpoints_exist():
    """集成测试：检查关键 API 端点是否存在且不返回 404。"""
    client = TestClient(app)

    # 测试基本端点是否可访问
    endpoints = [
        ("GET", "/", "主页"),
        ("POST", "/video-info", "视频信息API"),
        ("GET", "/download-direct", "直接下载API"),
    ]

    for method, endpoint, desc in endpoints:
        if method == "GET":
            response = client.get(endpoint)
            assert response.status_code != 404, f"{desc} ({endpoint}) 不应返回 404"
        elif method == "POST":
            # 对于POST端点，发送空json，期望422（验证错误）而不是404
            response = client.post(endpoint, json={})
            assert response.status_code != 404, f"{desc} ({endpoint}) 不应返回 404"


# --- 新增: 对 FormatAnalyzer.find_best_download_plan 的详细测试 ---


def test_find_best_plan_prefers_complete_stream():
    """
    测试场景1: 自动选择时，应优先选择质量最佳的完整流。
    """
    # Arrange
    analyzer = FormatAnalyzer()
    formats = simulate_video_formats()

    # Act
    plan = analyzer.find_best_download_plan(formats)

    # Assert
    assert plan.strategy == DownloadStrategy.DIRECT
    assert plan.primary_format.format_id == "22"  # 720p的完整流，得分高于360p
    assert plan.secondary_format is None
    log.info("✅ 测试通过: 自动选择最佳完整流 '22'")


def test_find_best_plan_chooses_merge_when_no_complete():
    """
    测试场景2: 当没有完整流时，应选择最佳视频+音频组合进行合并。
    """
    # Arrange
    analyzer = FormatAnalyzer()
    # 从模拟数据中移除所有完整流
    formats_without_complete = [f for f in simulate_video_formats() if f["acodec"] == "none" or f["vcodec"] == "none"]

    # Act
    plan = analyzer.find_best_download_plan(formats_without_complete)

    # Assert
    assert plan.strategy == DownloadStrategy.MERGE
    assert plan.primary_format.format_id == "137"  # 最佳视频 (1080p, avc1)
    assert plan.secondary_format.format_id == "141"  # 最佳音频 (256k abr)
    log.info("✅ 测试通过: 在无完整流时，正确选择合并策略 '137+141'")


def test_find_best_plan_with_user_specified_video():
    """
    测试场景3: 用户指定一个视频流时，应自动匹配最佳音频进行合并。
    """
    # Arrange
    analyzer = FormatAnalyzer()
    formats = simulate_video_formats()

    # Act
    plan = analyzer.find_best_download_plan(formats, target_format_id="137")

    # Assert
    assert plan.strategy == DownloadStrategy.MERGE
    assert plan.primary_format.format_id == "137"
    assert plan.secondary_format.format_id == "141"  # 自动匹配了最佳音频
    log.info("✅ 测试通过: 用户指定视频'137'，成功匹配最佳音频'141'")


def test_find_best_plan_fallback_to_best_available():
    """
    测试场景4: 降级处理 - 在只有音频流的情况下，应选择最佳的音频流直接下载。
    """
    # Arrange
    analyzer = FormatAnalyzer()
    audio_only_formats = [f for f in simulate_video_formats() if f["vcodec"] == "none"]

    # Act
    plan = analyzer.find_best_download_plan(audio_only_formats)

    # Assert
    assert plan.strategy == DownloadStrategy.DIRECT
    assert plan.primary_format.format_id == "141"  # 最佳可用格式
    assert "降级使用最佳可用格式" in plan.reason
    log.info("✅ 测试通过: 降级策略成功选择最佳可用音频'141'")


def test_find_best_plan_raises_error_for_no_formats():
    """
    测试场景5: 异常处理 - 当没有提供任何格式时，应抛出 ValueError。
    """
    # Arrange
    analyzer = FormatAnalyzer()
    empty_formats = []

    # Act & Assert
    with pytest.raises(ValueError, match="没有找到任何可用的视频格式"):
        analyzer.find_best_download_plan(empty_formats)
    log.info("✅ 测试通过: 为空格式列表成功抛出 ValueError")
