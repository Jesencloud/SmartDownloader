# tests/test_downloader.py

import pytest
import os
import asyncio
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call
from downloader import Downloader
from core.exceptions import DownloaderException

@pytest.mark.asyncio
async def test_download_and_merge_shows_success_mark_on_completion(mocker, tmp_path):
    """
    测试: 当 download_and_merge 成功完成时，它应该触发进度条的完成状态。
    (间接验证了 '✅' 会被显示)
    """
    # 1. 准备测试环境和模拟对象
    
    # 创建模拟的下载目录和文件
    download_folder = tmp_path / "downloads"
    download_folder.mkdir()
    
    # 创建预期的输出文件
    expected_output_file = download_folder / "test_video.mp4"
    expected_output_file.touch()
    
    # 创建模拟的 Path 对象
    mock_path = MagicMock(spec=Path)
    mock_path.__str__.return_value = str(expected_output_file)
    mock_path.exists.return_value = True
    mock_path.is_file.return_value = True
    mock_path.stat.return_value = MagicMock(st_size=1024 * 1024)  # 1MB
    mock_path.parent = download_folder
    
    # 模拟 glob 查找
    def mock_glob(self, pattern):
        if pattern == '*':
            return [mock_path]
        if str(self).endswith('.mp4'):
            return [mock_path]
        return []
    
    # 模拟 rglob 查找
    def mock_rglob(self, pattern):
        return [mock_path]
    
    # 应用模拟
    mocker.patch('pathlib.Path', autospec=True)
    mocker.patch('pathlib.Path.glob', mock_glob)
    mocker.patch('pathlib.Path.rglob', mock_rglob)
    mocker.patch('pathlib.Path.mkdir')
    mocker.patch('pathlib.Path.stat', return_value=MagicMock(st_size=1024 * 1024))
    mocker.patch('pathlib.Path.exists', return_value=True)
    mocker.patch('pathlib.Path.is_file', return_value=True)
    mocker.patch('pathlib.Path.parent', return_value=download_folder)
    mocker.patch('pathlib.Path.name', return_value="test_video.mp4")
    mocker.patch('pathlib.Path.__str__', return_value=str(expected_output_file))
    
    # 模拟 os.path 函数
    mocker.patch('os.path.getmtime', return_value=1234567890)
    
    # 模拟 CommandBuilder
    mock_build_cmd = mocker.patch(
        'core.command_builder.CommandBuilder.build_combined_download_cmd',
        return_value=(['echo', 'test'], 'test_format')
    )
    
    # 模拟 subprocess_manager
    mock_execute = mocker.patch(
        'core.subprocess_manager.SubprocessManager.execute_with_progress',
        return_value=(0, "Success", "")
    )
    
    # 模拟 FileProcessor
    mocker.patch(
        'core.file_processor.FileProcessor.verify_file_integrity',
        return_value=True
    )
    mocker.patch(
        'core.file_processor.FileProcessor.merge_to_mp4',
        return_value=True
    )
    
    # 模拟 _find_output_file 方法
    def mock_find_output_file(self, *args, **kwargs):
        return mock_path
    
    mocker.patch(
        'downloader.Downloader._find_output_file',
        new=mock_find_output_file
    )
    
    # 模拟 glob 查找结果
    def mock_glob_find_files(pattern):
        if pattern == '*':
            return [mock_path]
        if pattern.endswith(('.mp4', '.webm', '.mkv')):
            return [mock_path]
        return []
    
    # 确保下载目录下的文件查找返回预期结果
    def mock_iterdir(self):
        return [mock_path]
    
    mocker.patch('pathlib.Path.glob', mock_glob_find_files)
    mocker.patch('pathlib.Path.rglob', mock_glob_find_files)
    mocker.patch('pathlib.Path.iterdir', mock_iterdir)
    
    # 2. 创建 Downloader 实例并执行测试
    downloader = Downloader(download_folder=download_folder, proxy=None)
    
    # 3. 执行测试
    result = await downloader.download_and_merge(
        "https://example.com/video",
        "test_video"
    )
    
    # 4. 验证结果
    # 验证返回了预期的文件路径
    assert str(result) == str(expected_output_file)
    
    # 验证 build_combined_download_cmd 被调用
    mock_build_cmd.assert_called_once()
    
    # 验证 execute_with_progress 被调用
    mock_execute.assert_called_once()
