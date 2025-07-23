#!/usr/bin/env python3
"""
测试清理和重启功能
"""
import requests
import json
import time

def test_cancel_downloads():
    """测试取消下载并清理功能"""
    base_url = "http://localhost:8000"
    
    print("🧪 测试取消下载和清理功能...")
    
    # 测试取消下载请求
    cancel_data = {
        "task_ids": ["test-task-1", "test-task-2"]
    }
    
    try:
        response = requests.post(
            f"{base_url}/downloads/cancel",
            json=cancel_data,
            timeout=10
        )
        
        assert response.status_code == 200, f"取消请求失败: {response.status_code}"

        result = response.json()
        print("✅ 取消请求成功:")
        print(f"   消息: {result.get('message')}")
        print(f"   取消的任务: {result.get('cancelled_tasks')}")
        
        # 等待服务器重启
        print("⏳ 等待服务器重启...")
        time.sleep(3)
        
        # 测试服务器是否重新在线
        server_restarted = False
        for attempt in range(10):
            try:
                health_response = requests.get(f"{base_url}/", timeout=5)
                if health_response.status_code == 200:
                    print("✅ 服务器重启成功，已恢复在线")
                    server_restarted = True
                    break
            except requests.exceptions.RequestException:
                time.sleep(1)
        
        assert server_restarted, "服务器重启超时"
            
    except requests.exceptions.RequestException as e:
        assert False, f"请求异常: {e}"

if __name__ == "__main__":
    try:
        test_cancel_downloads()
        print("\n✅ 测试通过！")
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")