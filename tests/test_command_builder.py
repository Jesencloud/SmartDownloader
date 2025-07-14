# tests/test_command_builder.py

from core.command_builder import CommandBuilder

def test_build_combined_download_cmd_basic():
    """
    测试 build_combined_download_cmd 在没有代理和cookies时的基本功能
    """
    # 1. 安排 (Arrange)
    # 创建 CommandBuilder 实例，不带代理和cookies
    builder = CommandBuilder(proxy=None, cookies_file=None)
    download_folder = "/path/to/downloads"
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 定义我们期望得到的命令
    expected_command = [
        'yt-dlp',
        '--verbose',
        '--progress',
        '--progress-template', '%(progress)j',
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '--merge-output-format', 'mp4',
        '-o', '/path/to/downloads/%(title)s.%(ext)s',
        video_url
    ]

    # 2. 执行 (Act)
    # 调用我们想要测试的方法
    actual_command, _ = builder.build_combined_download_cmd(download_folder, video_url)

    # 3. 断言 (Assert)
    # 验证实际生成的命令是否与我们期望的完全一致
    assert actual_command == expected_command

def test_build_combined_download_cmd_with_proxy():
    """
    测试 build_combined_download_cmd 在有代理时是否正确添加了代理参数
    """
    # 1. 安排 (Arrange)
    proxy_address = "http://127.0.0.1:7890"
    builder = CommandBuilder(proxy=proxy_address, cookies_file=None)
    download_folder = "/path/to/downloads"
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, _ = builder.build_combined_download_cmd(download_folder, video_url)

    # 3. 断言 (Assert)
    # 验证命令中是否包含了代理参数
    assert '--proxy' in actual_command
    # 验证代理地址是否紧跟在 --proxy 后面
    proxy_index = actual_command.index('--proxy')
    assert actual_command[proxy_index + 1] == proxy_address

def test_build_combined_download_cmd_with_cookies():
    """
    测试 build_combined_download_cmd 在有cookies时是否正确添加了cookies参数
    """
    # 1. 安排 (Arrange)
    cookies_path = "/path/to/cookies.txt"
    builder = CommandBuilder(proxy=None, cookies_file=cookies_path)
    download_folder = "/path/to/downloads"
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, _ = builder.build_combined_download_cmd(download_folder, video_url)

    # 3. 断言 (Assert)
    # 验证命令中是否包含了cookies参数
    assert '--cookies' in actual_command
    # 验证cookies路径是否紧跟在 --cookies 后面
    cookies_index = actual_command.index('--cookies')
    assert actual_command[cookies_index + 1] == cookies_path
