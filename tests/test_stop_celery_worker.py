import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from unittest.mock import MagicMock

import psutil
import pytest

# 确保可以导入 stop_celery_worker 模块
from stop_celery_worker import stop_celery_workers


@pytest.fixture
def mock_process():
    """创建一个模拟的 psutil.Process 对象。"""
    process = MagicMock(spec=psutil.Process)
    process.pid = 1234
    process.name.return_value = "celery"
    process.info = {
        "pid": 1234,
        "name": "celery",
        "cmdline": ["python", "-m", "celery", "worker"],
    }
    return process


def test_stop_workers_no_workers_found(mocker, caplog):
    """
    测试：当没有找到任何 worker 进程时，脚本应正确报告且不执行任何操作。
    """
    # 1. 准备 (Arrange)
    # 模拟 pkill 失败
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)
    # 模拟 psutil 未找到任何进程
    mocker.patch("stop_celery_worker._find_celery_worker_processes", return_value=[])

    # 2. 执行 (Act)
    with caplog.at_level(logging.INFO):
        stop_celery_workers()

    # 3. 断言 (Assert)
    assert "没有找到运行中的Celery worker进程" in caplog.text


def test_stop_workers_graceful_shutdown(mocker, mock_process, caplog):
    """
    测试：当 worker 进程可以被优雅地终止时，不应调用 kill()。
    """
    # 1. 准备 (Arrange)
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)
    mocker.patch("stop_celery_worker._find_celery_worker_processes", return_value=[mock_process])

    # 模拟 wait() 正常返回，不抛出 TimeoutExpired
    mock_process.wait.return_value = None

    # 2. 执行 (Act)
    with caplog.at_level(logging.INFO):
        stop_celery_workers()

    # 3. 断言 (Assert)
    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_not_called()
    assert f"终止进程 {mock_process.pid}" in caplog.text
    assert "共停止了 1 个进程" in caplog.text


def test_stop_workers_force_kill_on_timeout(mocker, mock_process, caplog):
    """
    测试：当优雅终止超时后，应调用 kill() 来强制终止。
    """
    # 1. 准备 (Arrange)
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)
    mocker.patch("stop_celery_worker._find_celery_worker_processes", return_value=[mock_process])

    # 模拟 wait() 抛出超时异常
    mock_process.wait.side_effect = psutil.TimeoutExpired(seconds=5, pid=mock_process.pid)

    # 2. 执行 (Act)
    with caplog.at_level(logging.WARNING):
        stop_celery_workers()

    # 3. 断言 (Assert)
    mock_process.terminate.assert_called_once()
    mock_process.kill.assert_called_once()
    assert f"强制杀死进程 {mock_process.pid}" in caplog.text


def test_stop_workers_uses_pkill_if_available(mocker, caplog):
    """
    测试：如果 pkill 命令可用，脚本会优先使用它。
    """
    # 1. 准备 (Arrange)
    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mocker.patch("subprocess.run", return_value=mock_run_result)
    mock_find_procs = mocker.patch("stop_celery_worker._find_celery_worker_processes", return_value=[])

    # 2. 执行 (Act)
    with caplog.at_level(logging.INFO):
        stop_celery_workers()

    # 3. 断言 (Assert)
    assert "使用pkill命令停止了Celery worker" in caplog.text
    # 验证因为 pkill 成功了，所以没有再用 psutil 去查找
    mock_find_procs.assert_not_called()
