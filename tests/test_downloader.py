# tests/test_downloader.py

import pytest
import os
import asyncio
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call
from downloader import Downloader
from core.exceptions import DownloaderException, AuthenticationException

@pytest.mark.asyncio
async def test_download_and_merge_success(mocker, tmp_path):
    """
    测试: 当 download_and_merge 成功完成时,返回预期的文件路径.
    """
    # 1. 准备
    download_folder = tmp_path / "downloads"
    expected_output_file = download_folder / "test_video.mp4"

    mocker.patch.object(Path, 'mkdir')
    mocker.patch.object(Path, 'exists', return_value=True)
    mocker.patch.object(Path, 'is_dir', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=1024))

    async def mock_stream_info(*args, **kwargs):
        yield {'title': 'test_video'}
    mocker.patch.object(Downloader, 'stream_playlist_info', mock_stream_info)

    mock_build_cmd = mocker.patch(
        'core.command_builder.CommandBuilder.build_combined_download_cmd',
        return_value=(['echo', 'test'], 'test_format', expected_output_file)
    )
    
    mock_executor = mocker.patch.object(Downloader, '_execute_cmd_with_auth_retry', new_callable=AsyncMock)

    # 2. 执行
    downloader = Downloader(download_folder=download_folder)
    result = await downloader.download_and_merge("https://example.com/video")

    # 3. 验证
    assert result == expected_output_file
    mock_build_cmd.assert_called_once()
    mock_executor.assert_called_once()

@pytest.mark.asyncio
async def test_download_audio_conversion_success(mocker, tmp_path):
    """
    测试: 当请求音频转换(如mp3)时,使用可预测路径策略并成功.
    """
    # 1. 准备
    download_folder = tmp_path / "downloads"
    expected_audio_file = download_folder / "test_audio.mp3"

    mocker.patch.object(Path, 'mkdir')
    mocker.patch.object(Path, 'exists', return_value=True)
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=1024))

    async def mock_stream_info(*args, **kwargs):
        yield {'title': 'test_audio'}
    mocker.patch.object(Downloader, 'stream_playlist_info', mock_stream_info)

    mock_build_audio_cmd = mocker.patch('core.command_builder.CommandBuilder.build_audio_download_cmd', return_value=['echo', 'test'])
    mock_executor = mocker.patch.object(Downloader, '_execute_cmd_with_auth_retry', new_callable=AsyncMock)

    # 2. 执行
    downloader = Downloader(download_folder=download_folder)
    result = await downloader.download_audio("https://example.com/audio", audio_format='mp3')

    # 3. 验证
    assert result == expected_audio_file
    mock_build_audio_cmd.assert_called_once()
    assert mock_build_audio_cmd.call_args.kwargs['output_template'] == str(expected_audio_file)
    mock_executor.assert_called_once()

@pytest.mark.asyncio
async def test_download_audio_direct_download_success(mocker, tmp_path):
    """
    测试: 当请求原始音频流(如format_id)时,使用stderr解析策略并成功.
    """
    # 1. 准备
    download_folder = tmp_path / "downloads"
    # yt-dlp will name this file with the correct extension
    expected_audio_file = download_folder / "test_audio.webm"

    mocker.patch.object(Path, 'mkdir')
    # Mock exists and stat for the parsed path
    mocker.patch.object(Path, 'exists', return_value=True)
    mocker.patch.object(Path, 'is_file', return_value=True)
    mocker.patch.object(Path, 'stat', return_value=MagicMock(st_size=1024))

    async def mock_stream_info(*args, **kwargs):
        yield {'title': 'test_audio'}
    mocker.patch.object(Downloader, 'stream_playlist_info', mock_stream_info)

    mock_build_audio_cmd = mocker.patch('core.command_builder.CommandBuilder.build_audio_download_cmd', return_value=['echo', 'test'])
    
    # Mock the executor to return stderr containing the destination path
    stderr_output = f"[download] Destination: {expected_audio_file}"
    mock_executor = mocker.patch.object(
        Downloader, 
        '_execute_cmd_with_auth_retry', 
        new_callable=AsyncMock,
        return_value=(0, "", stderr_output)
    )

    # 2. 执行 (using a format_id that is not a conversion format)
    downloader = Downloader(download_folder=download_folder)
    result = await downloader.download_audio("https://example.com/audio", audio_format='251')

    # 3. 验证
    assert result == expected_audio_file
    mock_build_audio_cmd.assert_called_once()
    # Verify the output template was generic
    assert mock_build_audio_cmd.call_args.kwargs['output_template'] == str(download_folder / "test_audio.%(ext)s")
    mock_executor.assert_called_once()

@pytest.mark.asyncio
async def test_download_audio_raises_exception_on_total_failure(mocker, tmp_path):
    """
    测试: 当所有策略都失败时, 抛出 DownloaderException.
    """
    # 1. 准备
    download_folder = tmp_path / "downloads"
    mocker.patch.object(Path, 'mkdir')
    mocker.patch.object(Path, 'exists', return_value=False) # All checks fail

    async def mock_stream_info(*args, **kwargs):
        yield {'title': 'test_audio'}
    mocker.patch.object(Downloader, 'stream_playlist_info', mock_stream_info)

    mocker.patch('core.command_builder.CommandBuilder.build_audio_download_cmd', return_value=['echo', 'test'])
    # Mock executor to return empty stderr
    mocker.patch.object(Downloader, '_execute_cmd_with_auth_retry', new_callable=AsyncMock, return_value=(0, "", ""))
    # Mock fallback search to also fail
    mocker.patch('downloader.Downloader._find_output_file', new_callable=AsyncMock, return_value=None)

    # 2. 执行 & 验证
    downloader = Downloader(download_folder=download_folder)
    with pytest.raises(DownloaderException, match="音频下载后未找到文件"):
        await downloader.download_audio("https://example.com/audio", audio_format='mp3')

@pytest.mark.asyncio
async def test_auth_retry_logic_rebuilds_command(mocker, tmp_path):
    """
    测试: _execute_cmd_with_auth_retry 在认证失败时会重新构建命令.
    """
    # 1. 准备
    downloader = Downloader(download_folder=tmp_path, cookies_file="cookies.txt")
    
    mocker.patch('core.cookies_manager.CookiesManager.refresh_cookies_for_url', return_value="new_cookies.txt")
    
    mock_execute = mocker.patch.object(
        downloader.subprocess_manager, 
        'execute_simple', 
        new_callable=AsyncMock,
        side_effect=[AuthenticationException("auth failed"), (0, "Success", "")]
    )
    
    cmd_builder_func = MagicMock(return_value=['rebuilt_command'])

    # 2. 执行
    await downloader._execute_cmd_with_auth_retry(
        initial_cmd=['initial_command'],
        cmd_builder_func=cmd_builder_func,
        url="https://example.com/video",
        cmd_builder_args={}
    )

    # 3. 验证
    assert cmd_builder_func.call_count == 1
    assert mock_execute.call_count == 2
    assert mock_execute.call_args_list[1].args[0] == ['rebuilt_command']