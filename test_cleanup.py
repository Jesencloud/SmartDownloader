#!/usr/bin/env python3
"""
测试轻量级清理功能 (E2E)
"""
import requests
import json
import time
import pytest

@pytest.mark.e2e
def test_cancel_downloads():
    """测试取消下载并清理功能，并验证服务器保持在线"""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 测试取消下载和清理功能...")
    
    cancel_data = {
        "task_ids": ["test-task-1", "test-task-2"]
    }
    
    # 1. 发送取消请求
    response = requests.post(
        f"{base_url}/downloads/cancel",
        json=cancel_data,
        timeout=20  # 为 CI 环境稍微增加超时时间
    )
    
    assert response.status_code == 200, f"取消请求失败: {response.status_code} - {response.text}"

    result = response.json()
    print("✅ 取消请求成功:")
    print(f"   消息: {result.get('message')}")
    print(f"   取消的任务: {result.get('cancelled_tasks')}")
    
    # 2. 验证服务器在轻量级清理后仍然在线
    print("⏳ 验证服务器是否保持在线...")
    time.sleep(1) # 短暂等待，以防万一
    health_response = requests.get(f"{base_url}/", timeout=10)
    assert health_response.status_code == 200, f"服务器在清理后没有保持在线状态，返回码: {health_response.status_code}"
    print("✅ 服务器保持在线状态，测试通过！")

if __name__ == "__main__":
    try:
        test_cancel_downloads()
        print("\n✅ 测试通过！")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")