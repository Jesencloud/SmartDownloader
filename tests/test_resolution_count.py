#!/usr/bin/env python3
"""
测试视频分辨率输出数量
"""

import pytest
import requests

BASE_URL = "http://localhost:8001"


@pytest.mark.e2e
def test_video_resolution_count():
    """测试视频分辨率输出数量"""
    test_urls = [
        "https://www.youtube.com/watch?v=pXIE9uksKqU&ab_channel=GuysAI",
        "https://www.youtube.com/watch?v=j5c8t-GZ7_I&ab_channel=CelineDion",
    ]

    print("🧪 测试视频分辨率输出数量...")

    for i, test_url in enumerate(test_urls, 1):
        print(f"\n📺 测试视频 {i}: {test_url.split('v=')[1][:11]}...")

        try:
            response = requests.post(
                f"{BASE_URL}/video-info",
                json={"url": test_url, "download_type": "video"},
            )

            if response.status_code == 200:
                video_data = response.json()
                formats = video_data.get("formats", [])

                print(f"   返回格式数量: {len(formats)}")

                if formats:
                    print("   可用分辨率:")
                    for j, fmt in enumerate(formats, 1):
                        resolution = fmt.get("resolution", "unknown")
                        quality = fmt.get("quality", "unknown")
                        ext = fmt.get("ext", "unknown")
                        filesize = fmt.get("filesize", 0)
                        needs_merge = fmt.get("needs_merge", False)

                        size_mb = round(filesize / (1024 * 1024), 1) if filesize else "unknown"
                        merge_status = "(需合并)" if needs_merge else "(直接下载)"

                        print(f"     {j}. {quality} ({resolution}) - {ext} - {size_mb}MB {merge_status}")

                # 分析分辨率多样性
                resolutions = [f.get("resolution") for f in formats]
                unique_resolutions = set(resolutions)

                print(f"   不同分辨率数量: {len(unique_resolutions)}")

                if len(formats) >= 3:
                    print("   ✅ 输出3个或更多格式选项")
                elif len(formats) >= 2:
                    print("   ⚠️ 输出2个格式选项")
                else:
                    print("   ❌ 仅输出1个格式选项")

            else:
                print(f"   ❌ 解析失败: {response.status_code}")
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        print(f"   错误详情: {error_data.get('detail', 'Unknown error')}")
                    except Exception:
                        pass

        except Exception as e:
            print(f"   ❌ 请求异常: {e}")


if __name__ == "__main__":
    test_video_resolution_count()
