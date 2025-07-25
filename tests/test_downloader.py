# tests/test_downloader.py

import pytest
from unittest.mock import MagicMock, AsyncMock

from downloader import Downloader


@pytest.fixture
def mock_downloader(mocker, tmp_path):
    """A pytest fixture to create a Downloader instance with mocked dependencies."""
    download_folder = tmp_path / "downloads"
    download_folder.mkdir()

    # Mock the classes where they are looked up (in the downloader module)
    # This is the key to fixing previous AttributeErrors.
    mock_command_builder_instance = MagicMock()
    mocker.patch(
        "downloader.CommandBuilder", return_value=mock_command_builder_instance
    )

    mock_subprocess_manager_instance = MagicMock()
    mocker.patch(
        "downloader.SubprocessManager", return_value=mock_subprocess_manager_instance
    )

    mock_file_processor_instance = MagicMock()
    mocker.patch("downloader.FileProcessor", return_value=mock_file_processor_instance)

    mocker.patch("downloader.CookiesManager")

    # Create the downloader instance, which will now receive the mocked instances
    downloader = Downloader(download_folder=download_folder)

    # Now we can mock methods on the downloader instance itself and its components
    mocks = {
        # Patch the method on the instance. We will set its return_value in each test.
        # Do NOT use AsyncMock for async generators.
        "stream_playlist_info": mocker.patch.object(downloader, "stream_playlist_info"),
        "execute_cmd": mocker.patch.object(
            downloader, "_execute_cmd_with_auth_retry", new_callable=AsyncMock
        ),
        "find_file": mocker.patch.object(
            downloader, "_find_and_verify_output_file", new_callable=AsyncMock
        ),
        "command_builder": mock_command_builder_instance,  # Expose the mocked instance for tests
    }

    return downloader, mocks, download_folder


@pytest.mark.asyncio
async def test_download_and_merge_success_with_resolution_in_filename(mock_downloader):
    """
    测试: 视频下载成功时，应返回一个包含正确标题和分辨率的文件名。
    """
    # 1. 准备
    downloader, mocks, download_folder = mock_downloader
    video_title = "My Awesome Video"
    format_id = "vid-1080p"
    # The downloader now sanitizes and adds resolution
    sanitized_title = downloader._sanitize_filename(video_title)
    file_prefix = f"{sanitized_title}_1920x1080"
    expected_output_path = download_folder / f"{file_prefix}.mp4"

    # 模拟 stream_playlist_info to return an async generator
    async def mock_info_gen():
        yield {
            "title": video_title,
            "formats": [{"format_id": format_id, "width": 1920, "height": 1080}],
        }

    # Set the return_value to an EXECUTED async generator
    mocks["stream_playlist_info"].return_value = mock_info_gen()

    # 模拟 CommandBuilder 返回确切路径
    mocks["command_builder"].build_combined_download_cmd.return_value = (
        ["yt-dlp", "..."],
        "bestvideo+bestaudio",
        expected_output_path,
    )

    # 模拟下载执行，并真实地创建文件
    async def mock_execute_and_create_file(*args, **kwargs):
        expected_output_path.touch()
        expected_output_path.write_text("dummy video")
        return (0, "", "")

    mocks["execute_cmd"].side_effect = mock_execute_and_create_file

    # 2. 执行
    result = await downloader.download_and_merge(
        "https://example.com/video", format_id=format_id
    )

    # 3. 验证
    assert result == expected_output_path
    mocks["execute_cmd"].assert_called_once()
    mocks["command_builder"].build_combined_download_cmd.assert_called_once()


@pytest.mark.asyncio
async def test_download_audio_conversion_success(mock_downloader):
    """
    测试: 当请求音频转换为MP3时，应采用“主动指定”策略并成功。
    """
    # 1. 准备
    downloader, mocks, download_folder = mock_downloader
    video_title = "Cool Podcast"
    audio_format = "mp3"
    sanitized_title = downloader._sanitize_filename(video_title)
    # 修正：输出文件名不应包含 audio_format 作为前缀的一部分，以匹配 downloader.py 的逻辑
    expected_output_path = download_folder / f"{sanitized_title}.{audio_format}"

    # 模拟 stream_playlist_info
    async def mock_info_gen():
        yield {"title": video_title}

    mocks["stream_playlist_info"].return_value = mock_info_gen()

    # 模拟下载执行，并真实地创建文件
    async def mock_execute_and_create_file(*args, **kwargs):
        expected_output_path.touch()
        expected_output_path.write_text("dummy audio")
        return (0, "", "")

    mocks["execute_cmd"].side_effect = mock_execute_and_create_file

    # 2. 执行
    result = await downloader.download_audio(
        "https://example.com/audio", audio_format=audio_format
    )

    # 3. 验证
    assert result == expected_output_path
    mocks["command_builder"].build_audio_download_cmd.assert_called_once_with(
        url="https://example.com/audio",
        output_template=str(expected_output_path),
        audio_format=audio_format,
    )
    mocks["execute_cmd"].assert_called_once()


@pytest.mark.asyncio
async def test_download_audio_direct_download_success(mock_downloader):
    """
    测试: 当直接下载原始音频流时，应采用“主动搜索”策略并成功。
    """
    # 1. 准备
    downloader, mocks, download_folder = mock_downloader
    video_title = "Bilibili Audio"
    audio_format_id = "30232"
    sanitized_title = downloader._sanitize_filename(video_title)
    # The expected output path is based on the sanitized title, not the complex prefix.
    expected_output_path = download_folder / f"{sanitized_title}.m4a"

    # 模拟 stream_playlist_info
    async def mock_info_gen():
        yield {"title": video_title}

    mocks["stream_playlist_info"].return_value = mock_info_gen()

    # 模拟 _find_output_file 返回成功找到的文件
    mocks["find_file"].return_value = expected_output_path

    # 模拟 CommandBuilder 返回模板路径
    mocks["command_builder"].build_audio_download_cmd.return_value = ["yt-dlp", "..."]

    # 2. 执行
    # CORRECTED: Call download_audio, not download_and_merge
    result = await downloader.download_audio(
        "https://bilibili.com/video/BV1xx", audio_format=audio_format_id
    )

    # 3. 验证
    assert result == expected_output_path
    mocks["execute_cmd"].assert_called_once()
    # 验证 _find_and_verify_output_file 被调用，因为这是直接下载策略
    mocks["find_file"].assert_called_once_with(
        sanitized_title,  # The call uses the sanitized title directly
        (
            ".m4a",
            ".mp4",
            ".webm",
            ".opus",
            ".ogg",
            ".mp3",
        ),  # The correct list of extensions
    )
