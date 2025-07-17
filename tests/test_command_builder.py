# tests/test_command_builder.py

from core.command_builder import CommandBuilder
from config_manager import config

def test_build_combined_download_cmd_basic():
    """
    测试 build_combined_download_cmd 在没有代理和cookies时的基本功能
    """
    # 1. 安排 (Arrange)
    builder = CommandBuilder(proxy=None, cookies_file=None)
    download_folder = "/path/to/downloads"
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 定义我们期望得到的命令
    expected_command = [
        'yt-dlp',
        '--ignore-config',
        '--no-warnings',
        '--no-color',
        '--force-overwrites',
        '--progress',
        '--progress-template', '%(progress)j',
        '-f', config.downloader.ytdlp_combined_format,
        '--merge-output-format', config.downloader.ytdlp_merge_output_format,
        '--newline',
        '-o', f'{download_folder}/%(title)s.%(ext)s',
        video_url
    ]

    # 2. 执行 (Act)
    actual_command, _ = builder.build_combined_download_cmd(download_folder, video_url)

    # 3. 断言 (Assert)
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
    assert '--proxy' in actual_command
    proxy_index = actual_command.index('--proxy')
    assert actual_command[proxy_index + 1] == proxy_address

def test_build_combined_download_cmd_with_cookies(tmp_path):
    """
    测试 build_combined_download_cmd 在有cookies时是否正确添加了cookies参数
    """
    # 1. 安排 (Arrange)
    # 使用 tmp_path 创建一个临时的 cookies 文件
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.touch() # 创建一个空的临时文件

    builder = CommandBuilder(proxy=None, cookies_file=str(cookies_file))
    download_folder = "/path/to/downloads"
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, _ = builder.build_combined_download_cmd(download_folder, video_url)

    # 3. 断言 (Assert)
    assert '--cookies' in actual_command
    cookies_index = actual_command.index('--cookies')
    # CommandBuilder 会解析为绝对路径
    assert actual_command[cookies_index + 1] == str(cookies_file.resolve())
