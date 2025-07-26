#!/usr/bin/env python3
"""
寻找包含mp4音频格式的URL进行测试
"""

import pytest
import requests

BASE_URL = "http://localhost:8001"


@pytest.mark.e2e
def test_find_mp4_audio():
    """尝试寻找包含mp4音频格式的URL"""

    # 测试更多可能有mp4音频的URL
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # Me at the zoo (first YouTube video)
        "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # Despacito
    ]

    print("🔍 寻找包含mp4音频格式的URL...")

    for i, test_url in enumerate(test_urls, 1):
        print(f"\n📺 测试URL {i}: {test_url.split('v=')[1][:11]}...")

        try:
            response = requests.post(
                f"{BASE_URL}/video-info",
                json={"url": test_url, "download_type": "audio"},
            )

            if response.status_code == 200:
                audio_data = response.json()
                formats = audio_data.get("formats", [])

                if formats:
                    fmt = formats[0]
                    ext = fmt.get("ext", "unknown")
                    print(f"   音频格式: {ext}")

                    if ext == "mp4":
                        print("   🎯 找到mp4音频格式！")
                        print(f"   质量: {fmt.get('quality', 'unknown')}")
                        print(f"   比特率: {fmt.get('abr', 'unknown')}")
                        return  # 找到就停止
                    else:
                        print(f"   - 当前格式: {ext}")
                else:
                    print("   ❌ 无音频格式")
            else:
                print(f"   ❌ 解析失败: {response.status_code}")

        except Exception as e:
            print(f"   ❌ 异常: {e}")

    print("\n📊 测试总结:")
    print("   所有测试URL都没有返回mp4音频格式")
    print("   这可能表明:")
    print("   1. 这些URL确实没有mp4音频格式")
    print("   2. mp4音频在这些网站上不常见")
    print("   3. 我们的过滤逻辑工作正常，优先选择了更高质量的格式（如m4a）")


if __name__ == "__main__":
    test_find_mp4_audio()
