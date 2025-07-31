#!/usr/bin/env python3
"""
测试音频mp4格式过滤调试
"""

import pytest
import requests

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

                print(f"   返回音频格式数量: {len(formats)}")  # 打印语句可以保留用于调试

                # 断言1：确保至少返回了一个格式
                assert len(formats) > 0, f"URL {test_url} 未返回任何音频格式"

                if formats:
                    has_mp4_audio = False
                    for j, fmt in enumerate(formats, 1):
                        ext = fmt.get("ext", "unknown")
                        quality = fmt.get("quality", "unknown")
                        abr = fmt.get("abr", "unknown")

                        print(f"     {j}. 格式: {ext}, 质量: {quality}, 比特率: {abr}")
                        if ext == "mp4":
                            has_mp4_audio = True

                    # 断言2：根据你的业务逻辑，断言是否应该包含mp4格式
                    # 例如，如果你的目标是过滤掉所有mp4音频，可以这样写：
                    assert not has_mp4_audio, f"URL {test_url} 的结果中不应包含mp4音频格式"

                else:
                    print("   ❌ 未返回任何音频格式")
            else:
                print(f"   ❌ 音频解析失败: {response.status_code}")
                # 断言3：确保API调用成功
                assert response.status_code == 200, (
                    f"API请求失败，状态码: {response.status_code}, 详情: {response.text}"
                )

        except Exception as e:
            print(f"   ❌ 测试异常: {e}")


if __name__ == "__main__":
    test_audio_mp4_filtering()
