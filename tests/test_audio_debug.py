#!/usr/bin/env python3
"""
测试音频mp4格式过滤调试
"""

import requests
import pytest

BASE_URL = "http://localhost:8001"


@pytest.mark.e2e
def test_audio_mp4_filtering():
    """测试音频mp4格式过滤是否正确工作"""

    # 测试多个可能有mp4音频的URL
    test_urls = [
        "https://www.youtube.com/watch?v=pXIE9uksKqU&ab_channel=GuysAI",
        "https://www.youtube.com/watch?v=j5c8t-GZ7_I&ab_channel=CelineDion",
    ]

    print("🧪 测试音频mp4格式过滤调试...")

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

                print(f"   返回音频格式数量: {len(formats)}")

                if formats:
                    for j, fmt in enumerate(formats, 1):
                        ext = fmt.get("ext", "unknown")
                        quality = fmt.get("quality", "unknown")
                        abr = fmt.get("abr", "unknown")

                        print(f"     {j}. 格式: {ext}, 质量: {quality}, 比特率: {abr}")

                        if ext == "mp4":
                            print("       ✅ 发现mp4音频格式！")
                        elif ext == "m4a":
                            print("       ✅ 发现m4a音频格式（最高优先级）")
                else:
                    print("   ❌ 未返回任何音频格式")
            else:
                print(f"   ❌ 音频解析失败: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   错误详情: {error_data.get('detail', 'Unknown error')}")
                except Exception:
                    pass

        except Exception as e:
            print(f"   ❌ 测试异常: {e}")


if __name__ == "__main__":
    test_audio_mp4_filtering()
