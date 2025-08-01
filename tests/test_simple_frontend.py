import json
import subprocess
import time
from multiprocessing import Process

import pytest
import uvicorn
from playwright.sync_api import Page, expect

# --- 服务器设置 ---
# 这部分代码是为了在测试时自动启动和关闭您的Web应用
HOST = "127.0.0.1"
PORT = 8001  # 使用一个专用的测试端口
BASE_URL = f"http://{HOST}:{PORT}"


def _run_server():
    """在一个独立的进程中运行 uvicorn 服务器。"""
    # 确保 web.main 可以被导入
    from web.main import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


@pytest.fixture(scope="module", autouse=True)
def live_server():
    """
    一个自动运行的fixture，在所有测试开始前启动服务器，结束后关闭。
    `scope="module"` 意味着它对于此文件中的所有测试只运行一次。
    """
    proc = Process(target=_run_server, daemon=True)

    proc.start()

    # 等待服务器准备就绪
    for _ in range(15):
        try:
            # 使用 curl 检查服务器是否响应
            subprocess.run(
                ["curl", "-sSf", f"{BASE_URL}/"],
                check=True,
                capture_output=True,
                timeout=1,
            )
            print(f"\n✅ Live server is ready at {BASE_URL}")
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(0.5)
    else:
        pytest.fail("Server did not start in time.")

    yield  # 这里是测试运行的地方

    print("\n🛑 Tearing down live server...")
    proc.terminate()
    proc.join(timeout=5)


# --- Mock Data ---
MOCK_CONFIG = {"security": {"allowed_domains": ["youtube.com"]}}

MOCK_VIDEO_INFO = {
    "title": "【本地测试视频】一个非常精彩的演示视频",
    "duration": None,
    "uploader": None,
    "thumbnail": None,
    "original_url": "local-test-video",
    "download_type": "video",
    "formats": [
        {
            "format_id": "test-vid-1080p",
            "resolution": "1920x1080",
            "ext": "mp4",
            "filesize": 15000000,
            "filesize_is_approx": False,
            "quality": "1080p",
            "vcodec": "avc1.640028",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "needs_merge": False,
            "is_complete_stream": True,
            "supports_browser_download": True,
        },
        {
            "format_id": "test-vid-720p",
            "resolution": "1280x720",
            "ext": "mp4",
            "filesize": 8000000,
            "filesize_is_approx": False,
            "quality": "720p",
            "vcodec": "avc1.4d401f",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "needs_merge": False,
            "is_complete_stream": True,
            "supports_browser_download": True,
        },
        {
            "format_id": "test-vid-360p",
            "resolution": "640x360",
            "ext": "mp4",
            "filesize": 2000000,
            "filesize_is_approx": False,
            "quality": "360p",
            "vcodec": "avc1.42c01e",
            "acodec": "mp4a.40.2",
            "abr": 128,
            "needs_merge": False,
            "is_complete_stream": True,
            "supports_browser_download": True,
        },
    ],
}

# --- 简化的前端测试 ---


@pytest.mark.e2e
def test_main_download_flow(page: Page):
    """
    一个简单的E2E测试，验证核心用户流程。
    此测试使用Playwright的网络拦截功能来模拟后端API响应，
    使得测试快速、可靠，且无需外部服务或前端代码中的模拟数据。
    """
    print("\n🧪 [E2E Test] Verifying the main download flow with API mocking...")

    # --- 模拟API响应 ---
    def handle_route(route, request):
        # 模拟配置接口，为前端提供一个有效的域名白名单
        if "/config_manager.config" in request.url:
            print("   - Intercepted API call for '/config_manager.config', returning mock config.")
            route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_CONFIG))
            return

        # 使用一个格式有效且在白名单中的URL来触发模拟
        mock_url = "https://www.youtube.com/watch?v=test-mock-video"
        if "/video-info" in request.url and request.method == "POST":
            request_body = json.loads(request.post_data)
            if request_body.get("url") == mock_url:
                print(f"   - Intercepted API call for video info '{mock_url}', returning mock data.")
                route.fulfill(status=200, content_type="application/json", body=json.dumps(MOCK_VIDEO_INFO))
                return
        # 对于所有其他请求，让它们继续到真实的服务器
        route.continue_()

    # 设置网络拦截
    page.route("**/*", handle_route)
    # --- 模拟结束 ---

    # 1. 访问主页
    page.goto(BASE_URL)
    expect(page.locator('h1[data-translate="mainHeading"]')).to_be_visible()
    print("   - Step 1: Page loaded successfully.")

    # 2. 输入一个格式有效且在白名单中的URL来触发模拟
    page.locator("#videoUrl").fill("https://www.youtube.com/watch?v=test-mock-video")
    print("   - Step 2: Entered mock video URL.")

    # 3. 点击页面标题以关闭可能出现的URL历史记录下拉菜单
    page.locator('h1[data-translate="mainHeading"]').click()
    print("   - Step 3: Clicked heading to dismiss any popups.")

    # 4. 点击“提取视频”按钮
    page.locator("#downloadVideoButton").click()
    print("   - Step 4: Clicked 'Extract Video' button.")

    # 5. 等待并验证来自模拟数据的结果
    expect(page.locator(".resolution-option")).to_have_count(3, timeout=10000)
    print("   - Step 5: Verified that 3 download options are displayed from mocked data.")

    # 可选：检查模拟数据中的标题是否已显示
    expect(page.locator(".video-title")).to_have_text(MOCK_VIDEO_INFO["title"])
    print("   - Step 6: Verified video title is displayed correctly.")

    print("✅ Test passed!")
