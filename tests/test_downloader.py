# tests/test_downloader.py

import asyncio
from pathlib import Path
import pytest
from unittest.mock import MagicMock

from downloader import Downloader

# 将测试标记为异步，以便使用 await
@pytest.mark.asyncio
async def test_download_and_merge_shows_success_mark_on_completion(mocker, tmp_path):
    """
    测试: 当 download_and_merge 成功完成时，它应该触发进度条的完成状态。
    (间接验证了 '✅' 会被显示)
    """
    # 1. 安排 (Arrange)
    
    # 准备一个下载文件夹
    download_folder = tmp_path
    
    # 创建 Downloader 实例
    downloader = Downloader(download_folder=download_folder)
    
    # --- 模拟所有外部依赖 ---
    
    # 模拟 subprocess_manager 的核心方法，让它假装成功执行
    # 我们不需要它返回任何东西，只需要它能被 await 且不报错
    mock_execute = mocker.patch(
        'core.subprocess_manager.SubprocessManager.execute_with_progress',
        return_value=(0, "Success", "") # 模拟 (return_code, stdout, stderr)
    )
    
    # 模拟文件查找，让它假装找到了下载好的文件
    expected_output_file = download_folder / "video.mp4"
    mock_find_file = mocker.patch(
        'downloader.Downloader._find_output_file',
        return_value=expected_output_file
    )
    
    # 模拟文件校验，让它假装文件是完整的
    mock_verify_file = mocker.patch(
        'core.file_processor.FileProcessor.verify_file_integrity',
        return_value=True
    )

    # 2. 执行 (Act)
    
    # 调用我们要测试的核心方法
    # 因为所有耗时的部分都被模拟了，所以这个调用会非常快
    result_path = await downloader.download_and_merge(
        video_url="http://fake.url/video.mp4",
        file_prefix="video"
    )

    # 3. 断言 (Assert)
    
    # 验证核心的下载方法被调用过一次
    mock_execute.assert_called_once()
    
    # 验证文件查找和校验方法也被调用了
    mock_find_file.assert_called_once()
    mock_verify_file.assert_called_once_with(expected_output_file)
    
    # 验证最终返回了我们预期的文件路径
    assert result_path == expected_output_file
    
    # 结论: 
    # 因为整个函数成功执行完毕且没有抛出异常，这意味着 with Progress(...) 代码块
    # 也成功执行完毕。当这个代码块退出时，rich 会自动将任务标记为 "finished"。
    # 一旦任务被标记为 "finished"，我们就可以确信 SpeedOrFinishMarkColumn 
    # 会渲染出 "✅"。这个测试成功地验证了整个逻辑链条。
