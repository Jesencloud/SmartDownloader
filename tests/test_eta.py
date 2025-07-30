#!/usr/bin/env python3
"""
测试ETA信息传递的脚本
"""

import time

import pytest
import requests

BASE_URL = "http://localhost:8000"


@pytest.mark.e2e
def test_eta_progress():
    """测试ETA信息是否被正确传递"""
    print("🧪 测试ETA信息传递...")

    # 测试URL
    test_url = "https://www.youtube.com/watch?v=j5c8t-GZ7_I&ab_channel=CelineDion"

    # 启动下载任务
    download_payload = {
        "url": test_url,
        "download_type": "video",
        "format_id": "best",
        "resolution": "720p",
    }

    try:
        response = requests.post(f"{BASE_URL}/downloads", json=download_payload)
        if response.status_code not in [200, 202]:
            print(f"❌ 下载请求失败: {response.status_code} - {response.text}")
            return

        task_data = response.json()
        task_id = task_data["task_id"]
        print(f"✅ 任务已启动，Task ID: {task_id}")

        # 监控任务状态，重点关注ETA信息
        attempt = 0
        max_attempts = 30
        eta_info_found = False

        while attempt < max_attempts:
            try:
                # 同时检查普通状态和调试状态
                status_response = requests.get(f"{BASE_URL}/downloads/{task_id}")
                debug_response = requests.get(f"{BASE_URL}/debug/task/{task_id}")

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    _ = debug_response.json() if debug_response.status_code == 200 else {}

                    print(f"\n--- 尝试 {attempt + 1} ---")
                    print(f"状态: {status_data['status']}")

                    if status_data["status"] == "PROGRESS":
                        result = status_data.get("result", {})
                        progress = result.get("progress", 0)
                        message = result.get("status", "未知")
                        eta_seconds = result.get("eta_seconds", 0)
                        speed = result.get("speed", "")

                        print(f"📊 进度: {progress}%")
                        print(f"💬 消息: {message}")
                        print(f"⏱️  ETA: {eta_seconds}秒")
                        print(f"🚀 速度: {speed}")

                        if eta_seconds > 0:
                            eta_info_found = True
                            print("✅ 检测到ETA信息！")

                    elif status_data["status"] in ["SUCCESS", "FAILURE"]:
                        print(f"\n🏁 任务完成，最终状态: {status_data['status']}")
                        break

                else:
                    print(f"❌ 状态查询失败: {status_response.status_code}")

            except Exception as e:
                print(f"❌ 轮询错误: {e}")

            attempt += 1
            time.sleep(2)

        # 结果分析
        if eta_info_found:
            print("\n🎉 ETA信息传递测试成功！")
        else:
            print("\n⚠️ 未检测到ETA信息，可能需要进一步调试")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


if __name__ == "__main__":
    test_eta_progress()
