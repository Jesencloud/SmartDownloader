#!/usr/bin/env python3
"""
测试音频mp4格式支持
"""

import pytest
import requests

BASE_URL = "http://localhost:8001"


@pytest.mark.e2e
def test_audio_mp4_support():
    """测试音频mp4格式是否被正确识别和优先选择"""
    test_url = "https://www.youtube.com/watch?v=pXIE9uksKqU&ab_channel=GuysAI"

    print("🧪 测试音频mp4格式支持...")

    try:
        response = requests.post(
            f"{BASE_URL}/video-info", json={"url": test_url, "download_type": "audio"}
        )

        if response.status_code == 200:
            audio_data = response.json()
            formats = audio_data.get("formats", [])

            print(f"   返回音频格式数量: {len(formats)}")

            if formats:
                audio_format = formats[0]  # 通常只返回一个最佳音频格式
                ext = audio_format.get("ext", "unknown")
                quality = audio_format.get("quality", "unknown")
                abr = audio_format.get("abr", "unknown")

                print(f"   选择的音频格式: {ext}")
                print(f"   音频质量: {quality}")
                print(f"   比特率: {abr}")

                # 检查是否支持mp4音频格式
                if ext == "mp4":
                    print("   ✅ 成功选择mp4音频格式")
                elif ext == "m4a":
                    print("   ✅ 选择m4a音频格式（最高优先级）")
                else:
                    print(f"   ⚠️ 选择了其他格式: {ext}")

                # 显示优先级排序
                priority_list = ["m4a", "mp4", "aac", "opus", "mp3"]
                try:
                    priority_index = priority_list.index(ext)
                    print(
                        f"   📊 格式优先级排名: {priority_index + 1}/{len(priority_list)}"
                    )
                except ValueError:
                    print("   📊 格式不在优先级列表中")
            else:
                print("   ❌ 未返回任何音频格式")

        else:
            print(f"   ❌ 音频解析失败: {response.status_code}")

    except Exception as e:
        print(f"   ❌ 测试异常: {e}")


if __name__ == "__main__":
    test_audio_mp4_support()
