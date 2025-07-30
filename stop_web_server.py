#!/usr/bin/env python3
"""
快速停止所有 Uvicorn Web 服务器进程
"""

import logging
import os
import signal
import subprocess
import sys

import psutil

# 设置日志
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Web服务器监听的端口
SERVER_PORT = 8000


def _find_pids_by_port_lsof(port: int) -> set[int]:
    """使用 `lsof` 命令查找监听指定端口的进程ID (仅限Unix-like系统)"""
    pids = set()
    if sys.platform == "win32":
        return pids

    try:
        # -t: terse output (PIDs only)
        # -i :<port>: network interface on port
        # -sTCP:LISTEN: only listening TCP connections
        # -P: inhibit port name conversion (e.g., 8000 instead of http-alt)
        # -n: inhibit network number conversion (no DNS lookup)
        command = ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-P", "-n", "-t"]
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=5)

        if result.returncode == 0 and result.stdout.strip():
            found_pids = {int(pid) for pid in result.stdout.strip().split("\n")}
            log.info(f"     [lsof] 发现进程 PID(s): {list(found_pids)}")
            pids.update(found_pids)
        elif result.returncode != 0 and result.stderr:
            # lsof returns 1 if nothing is found, which is not an error for us.
            if "can't be stated" in result.stderr:  # Common permission error on macOS
                log.warning("     [lsof] 权限不足，无法检查所有文件。结果可能不完整。")
            elif "command not found" not in result.stderr:  # Ignore "not found" as we handle it below
                log.warning(f"     [lsof] 命令执行时返回非零值，stderr: {result.stderr.strip()}")

    except FileNotFoundError:
        log.warning("     [lsof] `lsof` 命令未找到，跳过此策略。")
    except subprocess.TimeoutExpired:
        log.warning("     [lsof] `lsof` 命令执行超时。")
    except Exception as e:
        log.warning(f"     [lsof] 查找端口时发生未知错误: {e}")

    return pids


def stop_uvicorn_processes():
    """查找并停止与 SmartDownloader 相关的 Uvicorn 进程"""
    log.info("🔍 查找 Uvicorn Web 服务器进程...")
    pids_to_stop = set()

    # --- 策略1: `lsof` (最可靠的Unix方法) ---
    if sys.platform != "win32":
        log.info(f"   - 策略1: 使用 `lsof` 按监听端口查找 (Port {SERVER_PORT})")
        pids_to_stop.update(_find_pids_by_port_lsof(SERVER_PORT))

    # --- 策略2: 通过命令行查找 ---
    log.info("   - 策略2: 按命令行查找 ('uvicorn' 和 'web.main:app')")
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if not proc.is_running():
                continue
            cmdline = " ".join(proc.info["cmdline"]) if proc.info["cmdline"] else ""
            if "uvicorn" in cmdline and "web.main:app" in cmdline:
                log.info(f"     [命令行] 发现进程 PID: {proc.pid}")
                pids_to_stop.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # --- 策略3: 通过 psutil.net_connections 查找 (作为备用) ---
    if not pids_to_stop:  # Only run if other methods failed
        log.info(f"   - 策略3: 使用 `psutil` 按监听端口查找 (Port {SERVER_PORT})")
        try:
            for conn in psutil.net_connections(kind="inet"):
                try:
                    if conn.laddr.port == SERVER_PORT and conn.status == psutil.CONN_LISTEN and conn.pid:
                        log.info(f"     [psutil-net] 发现进程 PID: {conn.pid}")
                        pids_to_stop.add(conn.pid)
                except psutil.AccessDenied:
                    # This can happen on macOS for some processes, just ignore them.
                    continue
        except psutil.AccessDenied:
            log.warning("     [psutil-net] 权限不足，无法扫描所有网络连接。")
        except Exception as e:
            log.warning(f"     [psutil-net] 查找端口占用时出错: {e}")

    if not pids_to_stop:
        log.info("✅ 没有找到正在运行的 Uvicorn Web 服务器进程。")
        return

    # 获取 Process 对象
    found_processes = []
    for pid in pids_to_stop:
        try:
            found_processes.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            log.warning(f"进程 {pid} 在获取详情前已消失。")

    # --- 终止进程 ---
    for proc in found_processes:
        try:
            log.info(f"🛑 正在停止进程 {proc.pid}: {' '.join(proc.cmdline())}")

            # 在非 Windows 系统上，使用进程组终止来确保 reloader 也被关闭
            if sys.platform != "win32":
                try:
                    pgid = os.getpgid(proc.pid)
                    log.info(f"   - 终止进程组 {pgid}...")
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    log.info(f"   - 进程组 {proc.pid} 查找失败，可能已停止。尝试终止单个进程...")
                    proc.terminate()
            else:
                # 在 Windows 上，直接终止主进程
                proc.terminate()

        except (psutil.NoSuchProcess, ProcessLookupError):
            log.info(f"   - 进程 {proc.pid} 已经不存在。")
        except Exception as e:
            log.error(f"   - 停止进程 {proc.pid} 时出错: {e}")

    # 等待进程终止
    log.info("⏳ 等待进程优雅退出...")
    gone, alive = psutil.wait_procs(found_processes, timeout=3)

    # 强制终止仍然存在的进程
    if alive:
        log.warning(f"以下进程未能优雅退出: {[p.pid for p in alive]}")
        for proc in alive:
            force_kill_process(proc)


def force_kill_process(proc: psutil.Process):
    """强制终止一个进程及其进程组"""
    try:
        log.warning(f"⚡ 进程 {proc.pid} 仍在运行，强制终止...")
        if sys.platform != "win32":
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                log.info(f"   - 进程组 {proc.pid} 查找失败，可能已停止。尝试强制终止单个进程...")
                proc.kill()
        else:
            proc.kill()
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass  # 进程已经消失
    except Exception as e:
        log.error(f"   - 强制终止进程 {proc.pid} 时出错: {e}")


def main():
    """主函数"""
    print("🛑 停止 SmartDownloader Web 服务器")
    print("=" * 40)
    stop_uvicorn_processes()
    print("=" * 40)
    log.info("✅ 操作完成。")


if __name__ == "__main__":
    main()
