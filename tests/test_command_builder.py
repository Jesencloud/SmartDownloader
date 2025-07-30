# tests/test_command_builder.py

from pathlib import Path

from core.command_builder import CommandBuilder


def test_build_combined_download_cmd_basic(tmp_path):
    """
    测试 build_combined_download_cmd 在没有代理和cookies时的基本功能
    """
    # 1. 安排 (Arrange)
    builder = CommandBuilder(proxy=None, cookies_file=None)
    download_folder = str(tmp_path / "downloads")  # 使用临时目录
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, format_used, _ = builder.build_combined_download_cmd(download_folder, video_url, "test_prefix")

    # 3. 断言 (Assert)
    # 检查基本命令部分
    assert actual_command[0] == "yt-dlp"
    assert "--ignore-config" in actual_command
    assert "--no-warnings" in actual_command
    assert "--no-color" in actual_command
    assert "--force-overwrites" in actual_command
    assert "--progress" in actual_command
    assert "--progress-template" in actual_command
    assert "%(progress)j" in actual_command
    assert "-f" in actual_command
    assert "--merge-output-format" in actual_command
    assert "mp4" in actual_command  # 默认合并格式
    assert "--newline" in actual_command
    assert "-o" in actual_command
    assert str(Path(download_folder).resolve() / "test_prefix.mp4") in " ".join(actual_command)
    assert "--" in actual_command
    assert video_url in actual_command

    # 检查格式是否正确
    assert format_used == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" or format_used.startswith(
        "bestvideo"
    )


def test_build_combined_download_cmd_with_proxy(tmp_path):
    """
    测试 build_combined_download_cmd 在有代理时是否正确添加了代理参数
    """
    # 1. 安排 (Arrange)
    proxy_address = "http://127.0.0.1:7890"
    builder = CommandBuilder(proxy=proxy_address, cookies_file=None)
    download_folder = str(tmp_path / "downloads")  # 使用临时目录
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, _, _ = builder.build_combined_download_cmd(download_folder, video_url, "test_prefix")

    # 3. 断言 (Assert)
    assert "--proxy" in actual_command
    proxy_index = actual_command.index("--proxy")
    assert actual_command[proxy_index + 1] == proxy_address

    # 确保代理参数在基础命令部分
    assert proxy_index < actual_command.index("--progress")  # 代理应该在基础命令部分


def test_build_combined_download_cmd_with_cookies(tmp_path):
    """
    测试 build_combined_download_cmd 在有cookies时是否正确添加了cookies参数
    """
    # 1. 安排 (Arrange)
    # 使用 tmp_path 创建一个临时的 cookies 文件
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.touch()  # 创建一个空的临时文件
    cookies_file_path = str(cookies_file.resolve())

    builder = CommandBuilder(proxy=None, cookies_file=cookies_file_path)
    download_folder = str(tmp_path / "downloads")  # 使用临时目录
    video_url = "https://www.youtube.com/watch?v=some_video_id"

    # 2. 执行 (Act)
    actual_command, _, _ = builder.build_combined_download_cmd(download_folder, video_url, "test_prefix")

    # 3. 断言 (Assert)
    assert "--cookies" in actual_command
    cookies_index = actual_command.index("--cookies")
    # CommandBuilder 会解析为绝对路径
    assert actual_command[cookies_index + 1] == cookies_file_path

    # 确保cookies参数在基础命令部分
    assert cookies_index < actual_command.index("--progress")  # cookies应该在基础命令部分
