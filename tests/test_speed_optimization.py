#!/usr/bin/env python3
"""
测试解析速度优化效果
"""

import pytest
import time
import requests

BASE_URL = "http://localhost:8001"


@pytest.mark.e2e
def test_parsing_speed():
    """测试不同下载类型的解析速度"""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # 经典测试视频

    print("🧪 测试解析速度优化效果...")

    # 测试视频解析速度
    print("\n📺 测试视频信息解析...")
    start_time = time.time()

    video_response = requests.post(
        f"{BASE_URL}/video-info", json={"url": test_url, "download_type": "video"}
    )

    video_time = time.time() - start_time
    print(f"   视频解析时间: {video_time:.2f}秒")

    if video_response.status_code == 200:
        video_data = video_response.json()
        print(f"   视频格式数量: {len(video_data.get('formats', []))}")
    else:
        print(f"   ❌ 视频解析失败: {video_response.status_code}")

    # 测试音频解析速度
    print("\n🎵 测试音频信息解析...")
    start_time = time.time()

    audio_response = requests.post(
        f"{BASE_URL}/video-info", json={"url": test_url, "download_type": "audio"}
    )

    audio_time = time.time() - start_time
    print(f"   音频解析时间: {audio_time:.2f}秒")

    if audio_response.status_code == 200:
        audio_data = audio_response.json()
        print(f"   音频格式数量: {len(audio_data.get('formats', []))}")
    else:
        print(f"   ❌ 音频解析失败: {audio_response.status_code}")

    # 比较速度提升
    if video_response.status_code == 200 and audio_response.status_code == 200:
        print("\n📊 性能对比:")
        print(f"   视频解析: {video_time:.2f}秒")
        print(f"   音频解析: {audio_time:.2f}秒")

        if video_time < audio_time:
            improvement = ((audio_time - video_time) / audio_time) * 100
            print(f"   ✅ 视频模式比音频模式快 {improvement:.1f}%")
        elif audio_time < video_time:
            improvement = ((video_time - audio_time) / video_time) * 100
            print(f"   ✅ 音频模式比视频模式快 {improvement:.1f}%")
        else:
            print("   ⚖️ 两种模式速度相当")


if __name__ == "__main__":
    test_parsing_speed()
