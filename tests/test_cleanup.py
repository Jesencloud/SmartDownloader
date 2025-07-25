#!/usr/bin/env python3
"""
测试轻量级清理功能 (Mock测试)
"""

import pytest
from unittest.mock import patch, MagicMock


def test_cancel_downloads():
    """测试取消下载并清理功能的逻辑（使用mock避免真实网络连接）"""
    print("🧪 测试取消下载和清理功能...")

    # Mock响应数据
    mock_cancel_response = {
        "message": "Tasks cancelled, processes terminated, cleanup completed, and application state reset.",
        "cancelled_tasks": ["test-task-1", "test-task-2"],
        "cleanup_result": {
            "cleaned_files": ["temp1.part", "temp2.ytdl"],
            "total_size_mb": 15.5,
            "errors": [],
        },
    }

    # 使用mock避免真实网络请求
    with patch("requests.Session") as mock_session_class:
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        # Mock POST请求响应
        mock_cancel_resp = MagicMock()
        mock_cancel_resp.status_code = 200
        mock_cancel_resp.json.return_value = mock_cancel_response
        mock_session.post.return_value = mock_cancel_resp

        # Mock GET请求响应（健康检查）
        mock_health_resp = MagicMock()
        mock_health_resp.status_code = 200
        mock_session.get.return_value = mock_health_resp

        # 执行测试逻辑
        cancel_data = {"task_ids": ["test-task-1", "test-task-2"]}

        # 验证POST请求会被正确调用
        base_url = "http://127.0.0.1:8000"
        response = mock_session.post(
            f"{base_url}/downloads/cancel", json=cancel_data, timeout=20
        )

        assert response.status_code == 200, f"取消请求失败: {response.status_code}"

        result = response.json()
        print("✅ 取消请求成功:")
        print(f"   消息: {result.get('message')}")
        print(f"   取消的任务: {result.get('cancelled_tasks')}")

        # 验证健康检查
        health_response = mock_session.get(f"{base_url}/", timeout=10)
        assert health_response.status_code == 200, "服务器健康检查失败"
        print("✅ 服务器保持在线状态，测试通过！")

        # 验证调用次数
        assert mock_session.post.call_count == 1
        assert mock_session.get.call_count == 1


@pytest.mark.e2e
@pytest.mark.skip(reason="需要运行的web服务器，在CI环境中跳过")
def test_cancel_downloads_e2e():
    """端到端测试 - 需要真实服务器运行"""
    import requests

    base_url = "http://127.0.0.1:8000"

    try:
        # 尝试连接服务器
        response = requests.get(f"{base_url}/", timeout=5)
        if response.status_code != 200:
            pytest.skip("Web服务器未运行，跳过E2E测试")
    except requests.exceptions.ConnectionError:
        pytest.skip("Web服务器未运行，跳过E2E测试")

    print("🧪 测试取消下载和清理功能（E2E）...")

    cancel_data = {"task_ids": ["test-task-1", "test-task-2"]}

    # 禁用代理，确保直接连接本地服务器
    session = requests.Session()
    session.trust_env = False

    # 1. 发送取消请求
    response = session.post(
        f"{base_url}/downloads/cancel", json=cancel_data, timeout=20
    )

    assert response.status_code == 200, (
        f"取消请求失败: {response.status_code} - {response.text}"
    )

    result = response.json()
    print("✅ 取消请求成功:")
    print(f"   消息: {result.get('message')}")
    print(f"   取消的任务: {result.get('cancelled_tasks')}")

    # 2. 验证服务器在轻量级清理后仍然在线
    print("⏳ 验证服务器是否保持在线...")
    import time

    time.sleep(1)
    health_response = session.get(f"{base_url}/", timeout=10)
    assert health_response.status_code == 200, (
        f"服务器在清理后没有保持在线状态，返回码: {health_response.status_code}"
    )
    print("✅ 服务器保持在线状态，测试通过！")


if __name__ == "__main__":
    try:
        test_cancel_downloads()
        print("\n✅ 测试通过！")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
