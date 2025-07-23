# tests/test_main_api.py
import pytest
from unittest.mock import patch

# 使用 conftest.py 中定义的 client fixture
def test_get_video_info_handles_runtime_error(client):
    """
    测试: 当 fetch_video_info_sync 抛出 RuntimeError 时,
    /video-info 端点应返回 500 错误和详细信息。
    这是一个典型的 "不快乐路径" 测试。
    """
    # 1. 准备 (Arrange)
    # 使用 patch 来模拟 `fetch_video_info_sync` 函数，使其在被调用时抛出异常。
    # 我们 patch 'web.main.fetch_video_info_sync' 因为这是它在 main 模块中被引用的地方。
    with patch('web.main.fetch_video_info_sync', side_effect=RuntimeError("yt-dlp crashed")):
        
        # 2. 执行 (Act)
        response = client.post(
            "/video-info",
            json={"url": "https://example.com/video", "download_type": "video"}
        )

        # 3. 验证 (Assert)
        # 验证 HTTP 状态码是否为 500 (Internal Server Error)
        assert response.status_code == 500
        
        # 验证响应体是否包含了我们预期的错误信息
        json_response = response.json()
        assert "detail" in json_response
        assert "yt-dlp crashed" in json_response["detail"]
        print(f"✅ 成功捕获并验证了预期的 500 错误: {json_response['detail']}")