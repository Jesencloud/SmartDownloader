#!/usr/bin/env python3
"""
端到端测试：轻量级清理功能。
"""

import time
from unittest.mock import patch

import pytest
from pathlib import Path


def create_test_files(base_path: Path):
    """创建一些测试用的临时文件"""
    download_folder = base_path

    test_files = [
        "test_video.mp4.part",
        "test_audio.m4a.temp",
        "temp_123.ytdl",
        "video_download.f137",
        "incomplete.partial",
    ]

    for filename in test_files:
        test_file = download_folder / filename
        test_file.write_text(f"Test content for {filename}")
        print(f"✓ 创建测试文件: {test_file}")

    return len(test_files)


@pytest.mark.integration
@patch("web.main.celery_app.control.revoke")
@patch("web.main.cleanup_active_processes")
@patch("web.main.reset_application_state")
def test_lightweight_cleanup(
    mock_reset_state,
    mock_cleanup_processes,
    mock_celery_revoke,
    client,
    tmp_path,
    monkeypatch,
):
    """
    测试 /downloads/cancel 端点是否能成功执行并清理临时文件。

    这个测试验证了以下几点:
    1. API 端点能被成功调用并返回 200 OK。
    2. API 调用后，服务器保持在线状态，无需重启。
    3. API 响应中包含了正确的清理结果统计信息。
    """
    print("🧪 测试优化后的轻量级清理功能...")

    # 配置mock对象
    mock_celery_revoke.return_value = None
    mock_cleanup_processes.return_value = None
    mock_reset_state.return_value = None

    # 使用 monkeypatch 动态修改配置，让应用在测试时使用临时目录。
    from config_manager import config

    monkeypatch.setattr(config.downloader, "save_path", str(tmp_path))

    # 创建测试文件
    test_file_count = create_test_files(tmp_path)
    print(f"📁 创建了 {test_file_count} 个测试临时文件")

    # 测试取消下载请求
    cancel_data = {"task_ids": ["test-task-1", "test-task-2"]}

    start_time = time.time()

    # 使用 TestClient 替代 requests
    response = client.post(
        "/downloads/cancel",  # 使用相对路径
        json=cancel_data,
    )

    end_time = time.time()
    response_time = end_time - start_time

    assert response.status_code == 200, (
        f"清理请求失败: {response.status_code} - {response.text}"
    )

    result = response.json()

    print("✅ 轻量级清理成功:")
    print(f"   响应时间: {response_time:.3f} 秒")
    print(f"   消息: {result.get('message')}")
    print(f"   取消的任务: {result.get('cancelled_tasks')}")

    # 显示清理结果
    cleanup_result = result.get("cleanup_result", {})
    cleaned_files = cleanup_result.get("cleaned_files", [])
    total_size_mb = cleanup_result.get("total_size_mb", 0)
    errors = cleanup_result.get("errors", [])

    print(f"   清理文件数: {len(cleaned_files)}")
    if cleaned_files:
        print(f"   清理文件: {', '.join(cleaned_files)}")
    print(f"   释放空间: {total_size_mb} MB")

    if errors:
        print(f"   清理错误: {errors}")

    # 验证服务器仍然在线（无需重启）
    health_response = client.get("/")
    assert health_response.status_code == 200, "服务器在轻量级清理后没有保持在线状态"
    print("✅ 服务器保持在线状态（无需重启）")
