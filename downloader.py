# downloader.py

import subprocess, json, logging, re, threading, time, socket
from pathlib import Path
from typing import Optional, List, Generator, Dict, Any
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, DownloadColumn, TransferSpeedColumn, TaskID
from rich.console import Console
from rich.live import Live
import random

# 导入配置管理器
from config_manager import config

# 在模块顶部获取logger实例
log = logging.getLogger(__name__)
console = Console()

class Downloader:
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        self.download_folder = download_folder
        self.cookies_file = cookies_file
        self.proxy = proxy
        
        # 从配置文件读取重试参数
        downloader_config = config.get_downloader_config()
        self.max_retries = downloader_config.get('max_retries', 3)
        self.base_delay = downloader_config.get('base_delay', 10)
        self.max_delay = downloader_config.get('max_delay', 300)
        self.backoff_factor = downloader_config.get('backoff_factor', 2)
        
        # 网络相关配置
        self.network_timeout = downloader_config.get('network_timeout', 60)
        self.stall_detection_time = downloader_config.get('stall_detection_time', 30)
        self.stall_check_interval = downloader_config.get('stall_check_interval', 5)
        self.stall_threshold_count = downloader_config.get('stall_threshold_count', 6)
        
        # 代理相关配置
        self.proxy_retry_base_delay = downloader_config.get('proxy_retry_base_delay', 30)
        self.proxy_retry_increment = downloader_config.get('proxy_retry_increment', 10)
        self.proxy_retry_max_delay = downloader_config.get('proxy_retry_max_delay', 120)
        
        # 高级配置
        advanced_config = config.get_advanced_config()
        self.connectivity_test_host = advanced_config.get('connectivity_test_host', '8.8.8.8')
        self.connectivity_test_port = advanced_config.get('connectivity_test_port', 53)
        self.connectivity_timeout = advanced_config.get('connectivity_timeout', 5)
        self.proxy_test_url = advanced_config.get('proxy_test_url', 'http://httpbin.org/ip')
        self.proxy_test_timeout = advanced_config.get('proxy_test_timeout', 10)
        
        console.print(f"🔄 重试机制已启用: 最多 {self.max_retries} 次重试，基础延迟 {self.base_delay}s", style="bold blue")
        console.print(f"🌐 网络中断处理: 将持续重试直到网络恢复（最多50次）", style="bold cyan")
    
    def _check_network_connectivity(self) -> bool:
        """简单的网络连接检查"""
        try:
            # 使用配置的测试主机和端口
            socket.create_connection((self.connectivity_test_host, self.connectivity_test_port), 
                                   timeout=self.connectivity_timeout)
            return True
        except OSError:
            return False
    
    def _check_proxy_connectivity(self) -> bool:
        """检查代理连接是否可用"""
        if not self.proxy:
            return True  # 没有代理时返回True
        
        try:
            # 尝试通过代理连接测试
            import urllib.request
            import urllib.error
            
            # 解析代理地址
            proxy_handler = urllib.request.ProxyHandler({'http': self.proxy, 'https': self.proxy})
            opener = urllib.request.build_opener(proxy_handler)
            
            # 尝试连接
            req = urllib.request.Request(self.proxy_test_url, headers={'User-Agent': 'Mozilla/5.0'})
            response = opener.open(req, timeout=self.proxy_test_timeout)
            return response.status == 200
        except Exception:
            return False
    
    def _calculate_delay(self, attempt: int) -> int:
        """计算指数退避延迟时间"""
        # 指数退避: base_delay * (backoff_factor ^ attempt) + 随机抖动
        delay = self.base_delay * (self.backoff_factor ** attempt)
        # 添加随机抖动防止惊群效应
        jitter = random.uniform(0.5, 1.5)
        delay = min(delay * jitter, self.max_delay)
        return int(delay)
    
    def _should_retry(self, error_output: str) -> bool:
        """判断是否应该重试的错误类型"""
        retry_patterns = [
            "HTTP Error 403: Forbidden",
            "HTTP Error 429",  # Too Many Requests
            "HTTP Error 502",  # Bad Gateway
            "HTTP Error 503",  # Service Unavailable
            "HTTP Error 504",  # Gateway Timeout
            "Connection reset",
            "Connection timed out",
            "Network is unreachable",
            "Temporary failure",
            "fragment.*not found",
            "Unable to download.*fragment",
            "HTTP Error 5",  # 5xx 系列错误
            "Unable to connect to proxy",  # 代理连接失败
            "Connection refused",  # 连接被拒绝
            "Proxy error",  # 代理错误
        ]
        
        error_lower = error_output.lower()
        for pattern in retry_patterns:
            if re.search(pattern.lower(), error_lower):
                return True
        return False

    def _is_proxy_error(self, error_output: str) -> bool:
        """判断是否为代理连接错误"""
        proxy_patterns = [
            "Unable to connect to proxy",
            "Connection refused",
            "Proxy error", 
            "NewConnectionError",
            "Failed to establish a new connection",
        ]
        
        error_lower = error_output.lower()
        for pattern in proxy_patterns:
            if pattern.lower() in error_lower:
                return True
        return False

    # ... (_build_base_yt_dlp_cmd, stream_playlist_info等方法中的print都改为log.info/error等) ...
    def _build_base_yt_dlp_cmd(self) -> List[str]:
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings']
        if self.proxy: cmd.extend(['--proxy', self.proxy])
        if self.cookies_file:
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        return cmd

    def stream_playlist_info(self, url: str) -> Generator[Dict[str, Any], None, None]:
        cmd = self._build_base_yt_dlp_cmd() + ['--flat-playlist', '--print-json', '--skip-download', url]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        for line in process.stdout:
            try: yield json.loads(line)
            except json.JSONDecodeError: continue
        process.wait()
        if process.returncode != 0:
            log.error(f"解析URL '{url}' 时出错: {process.stderr.read()}")

    def download_and_merge(self, video_url: str, file_prefix: str) -> Optional[Path]:
        video_part_base, audio_part_base = f"{file_prefix}_video.tmp", f"{file_prefix}_audio.tmp"
        
        # 使用一个统一的Progress实例来显示所有任务
        with Progress(
            TextColumn("[bold blue]⬇️ {task.description}"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "|",
            DownloadColumn(),
            "|",
            TransferSpeedColumn(),
            "|",
            TimeRemainingColumn(),
            console=console,
            expand=True
        ) as progress:
            try:
                # 下载视频
                console.print("📥 正在下载视频部分...", style="bold green")
                video_task = progress.add_task("下载视频", total=100)
                vid_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestvideo[ext=mp4]/bestvideo', 
                         '--newline', '-o', f"{self.download_folder / video_part_base}.%(ext)s", video_url]
                video_success = self._run_subprocess_with_progress(vid_cmd, progress, video_task)
                
                # 如果视频下载失败，立即返回，不继续下载音频
                if not video_success:
                    console.print("❌ 视频下载失败，停止处理", style="bold red")
                    return None
                
                # 下载音频
                console.print("🔊 正在下载音频部分...", style="bold green")
                audio_task = progress.add_task("下载音频", total=100)
                aud_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestaudio[ext=m4a]/bestaudio', 
                         '--newline', '-o', f"{self.download_folder / audio_part_base}.%(ext)s", video_url]
                audio_success = self._run_subprocess_with_progress(aud_cmd, progress, audio_task)
                
                # 如果音频下载失败，也返回失败
                if not audio_success:
                    console.print("❌ 音频下载失败，停止处理", style="bold red")
                    return None
                
                vid_part = next(self.download_folder.glob(f"{video_part_base}.*"), None)
                aud_part = next(self.download_folder.glob(f"{audio_part_base}.*"), None)
                
                if not (vid_part and aud_part):
                    merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                    if merged_file: 
                        console.print("✅ 检测到媒体源已合并", style="bold green")
                        return merged_file
                    console.print("❌ 未找到下载的视频或音频文件", style="bold red")
                    return None
                
                console.print("✅ 视频/音频下载完成", style="bold green")
                
            except Exception as e:
                log.error(f"下载过程中出错: {e}")
                return None
                
        # 在进度条结束后进行合并
        return self.merge_to_mp4(vid_part, aud_part, file_prefix)

    def merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Optional[Path]:
        console.print("🔧 正在合并视频和音频...", style="bold yellow")
        final_path = self.download_folder / f"{file_prefix}.mp4"
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()), 
               '-c', 'copy', str(final_path.resolve())]
        
        if self._run_subprocess(cmd, True): 
            console.print(f"✅ 视频合并成功: {final_path.name}", style="bold green")
            return final_path
            
        log.error(f"视频合并失败")
        return None

    def download_metadata(self, url: str, file_prefix: str) -> bool:
        # 元数据下载也需要重试机制
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._calculate_delay(attempt - 1)
                    console.print(f"♾️ 元数据下载第 {attempt + 1} 次尝试，等待 {delay} 秒...", style="bold yellow")
                    time.sleep(delay)
                
                cmd = self._build_base_yt_dlp_cmd() + ['--skip-download', '--write-info-json', '--write-thumbnail', '--convert-thumbnails', 'png', '-o', str(self.download_folder / file_prefix)]
                cmd.append(url)
                
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
                
                if attempt > 0:
                    console.print(f"✅ 元数据下载第 {attempt + 1} 次尝试成功！", style="bold green")
                return True
                
            except subprocess.CalledProcessError as e:
                error_output = e.stderr if e.stderr else str(e)
                
                if attempt < self.max_retries and self._should_retry(error_output):
                    if self._is_proxy_error(error_output):
                        # 代理连接错误使用更长等待时间
                        proxy_delay = min(self.proxy_retry_base_delay + attempt * self.proxy_retry_increment, 
                                         self.proxy_retry_max_delay)
                        console.print(f"🔄 代理连接失败，元数据下载第 {attempt + 2} 次尝试，等待 {proxy_delay} 秒...", style="bold yellow")
                        time.sleep(proxy_delay)
                    else:
                        console.print(f"⚠️ 元数据下载失败，将进行第 {attempt + 2} 次尝试", style="bold yellow")
                    continue
                else:
                    if attempt == self.max_retries:
                        console.print(f"❌ 元数据下载经过 {self.max_retries + 1} 次尝试仍然失败", style="bold red")
                    return False
                    
            except Exception as e:
                log.error(f"元数据下载时发生错误: {e}")
                if attempt < self.max_retries:
                    continue
                return False
        
        return False

    def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Optional[Path]:
        console.print(f"🎥 正在提取音频: {video_path.name}", style="bold blue")
        mp3_path = self.download_folder / f"{file_prefix}.mp3"
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]
        
        if self._run_subprocess(cmd, True): 
            console.print(f"✅ 音频提取成功: {mp3_path.name}", style="bold green")
            return mp3_path
                
        log.error(f"音频提取失败")
        return None

    def cleanup_temp_files(self, file_prefix: str):
        # 不显示清理信息
        for p in self.download_folder.glob(f"{file_prefix}.f*"): p.unlink()
        for p in self.download_folder.glob(f"{file_prefix}_*.tmp.*"): p.unlink()
    
    def cleanup_all_incomplete_files(self):
        """清理所有未完成的下载文件"""
        # 从配置获取清理模式
        file_config = config.get_file_processing_config()
        patterns_to_clean = file_config.get('cleanup_patterns', [
            "*.part", "*.part-*", "*.ytdl", "*.tmp.*", "*.f*"
        ])
        
        cleaned_files = []
        for pattern in patterns_to_clean:
            for file_path in self.download_folder.glob(pattern):
                try:
                    file_path.unlink()
                    cleaned_files.append(file_path.name)
                except Exception as e:
                    log.error(f"清理文件 {file_path.name} 失败: {e}")
        
        if cleaned_files:
            console.print(f"🧹 已清理 {len(cleaned_files)} 个未完成文件", style="bold yellow")
            return cleaned_files
        return []
            
    def _run_subprocess_with_progress(self, cmd: List[str], progress: Progress, task_id: TaskID) -> bool:
        """Run subprocess with real-time progress tracking and retry mechanism"""
        attempt = 0
        network_retry_count = 0
        max_network_retries = 50  # 网络中断时允许更多重试
        
        while attempt <= self.max_retries:
            process = None
            last_progress_time = time.time()
            timeout_seconds = 30
            
            try:
                if attempt > 0 or network_retry_count > 0:
                    if network_retry_count > 0:
                        # 网络中断的重试使用更短的延迟
                        delay = min(10 + network_retry_count * 2, 60)  # 最多等待1分钟
                        console.print(f"🌐 网络中断第 {network_retry_count + 1} 次重试，等待 {delay} 秒...", style="bold cyan")
                    else:
                        delay = self._calculate_delay(attempt - 1)
                        console.print(f"♾️ 第 {attempt + 1} 次尝试，等待 {delay} 秒...", style="bold yellow")
                    
                    # 显示倒计时
                    for remaining in range(delay, 0, -1):
                        progress.update(task_id, description=f"等待重试 ({remaining}s)")
                        time.sleep(1)
                    
                    # 恢复原始描述
                    original_desc = f"下载{'视频' if 'bestvideo' in ' '.join(cmd) else '音频'}"
                    progress.update(task_id, description=original_desc, completed=0)
                
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                         text=True, encoding='utf-8', universal_newlines=True)
                
                error_output = ""
                last_percentage = 0
                stalled_count = 0
                network_interrupted = False
                
                for line in process.stdout:
                    error_output += line
                    current_time = time.time()
                    
                    # Parse yt-dlp progress lines
                    if '[download]' in line and '%' in line:
                        percent_match = re.search(r'(\d+\.\d+)%', line)
                        size_match = re.search(r'of\s+([\d.]+)(\w+)', line)
                        
                        if percent_match:
                            percentage = float(percent_match.group(1))
                            
                            # 检测进度停滞 - 改进检测逻辑
                            if percentage > last_percentage:
                                last_progress_time = current_time
                                last_percentage = percentage
                                stalled_count = 0
                            elif percentage == last_percentage and percentage > 0:
                                # 只有在进度长时间没有变化时才计为停滞
                                if current_time - last_progress_time > self.stall_check_interval:  # 使用配置的检查间隔
                                    stalled_count += 1
                                    if stalled_count > self.stall_threshold_count:  # 使用配置的阈值
                                        console.print(f"⚠️ 检测到下载停滞超过{self.stall_detection_time}秒，可能是网络问题", style="bold yellow")
                                        network_interrupted = True
                                        process.terminate()
                                        try:
                                            process.wait(timeout=5)
                                        except subprocess.TimeoutExpired:
                                            process.kill()
                                            process.wait()
                                        break
                            
                            # Update file size if found
                            if size_match:
                                size_val = float(size_match.group(1))
                                size_unit = size_match.group(2)
                                if size_unit.lower() in ['mib', 'mb']:
                                    total_bytes = int(size_val * 1024 * 1024)
                                elif size_unit.lower() in ['gib', 'gb']:
                                    total_bytes = int(size_val * 1024 * 1024 * 1024)
                                elif size_unit.lower() in ['kib', 'kb']:
                                    total_bytes = int(size_val * 1024)
                                else:
                                    total_bytes = int(size_val)
                                
                                completed_bytes = int(total_bytes * percentage / 100)
                                progress.update(task_id, total=total_bytes, completed=completed_bytes)
                            else:
                                progress.update(task_id, completed=percentage)
                    
                    # 检测超时 - 使用配置的超时时间
                    elif current_time - last_progress_time > self.network_timeout:
                        console.print(f"⚠️ 下载超时 ({self.network_timeout}s 无进度更新)", style="bold yellow")
                        network_interrupted = True
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                
                # 如果没有网络中断，等待进程正常结束
                if not network_interrupted:
                    process.wait()
                
                # 检查是否成功完成
                if not network_interrupted and process.returncode == 0:
                    progress.update(task_id, completed=progress.tasks[task_id].total or 100)
                    if attempt > 0 or network_retry_count > 0:
                        console.print(f"✅ 网络恢复，下载成功完成！", style="bold green")
                    return True
                
                # 判断重试类型
                if network_interrupted:
                    # 网络中断不计入普通重试次数
                    network_retry_count += 1
                    if network_retry_count > max_network_retries:
                        console.print(f"❌ 网络中断超过最大重试次数 ({max_network_retries})", style="bold red")
                        return False
                    
                    # 检查网络连接状态，等待网络恢复
                    network_check_attempts = 0
                    while network_check_attempts < 10:  # 最多检查10次
                        if self._check_network_connectivity():
                            console.print(f"🌐 网络已恢复，将重新尝试下载", style="bold green")
                            break
                        else:
                            network_check_attempts += 1
                            console.print(f"🌐 网络仍未恢复，等待中... ({network_check_attempts}/10)", style="bold cyan")
                            time.sleep(5)  # 等待5秒再检查
                    
                    if network_check_attempts >= 10:
                        console.print(f"❌ 网络长时间无法恢复，停止重试", style="bold red")
                        return False
                    
                    continue  # 不增加attempt计数
                elif self._should_retry(error_output):
                    # 检查是否为代理连接错误
                    if self._is_proxy_error(error_output):
                        # 代理连接错误需要更长的等待时间
                        attempt += 1
                        if attempt > self.max_retries:
                            console.print(f"❌ 代理连接经过 {self.max_retries + 1} 次尝试仍然失败", style="bold red")
                            console.print(f"💡 请检查代理服务器是否正常运行", style="bold yellow")
                            return False
                        
                        # 代理连接失败使用较长的等待时间
                        proxy_delay = min(self.proxy_retry_base_delay + attempt * self.proxy_retry_increment, 
                                         self.proxy_retry_max_delay)
                        console.print(f"🔄 代理连接失败，第 {attempt + 1} 次尝试，等待 {proxy_delay} 秒...", style="bold yellow")
                        
                        # 在等待期间检查代理连接状态
                        console.print(f"🔍 正在检查代理连接状态...", style="bold cyan")
                        
                        # 显示倒计时
                        for remaining in range(proxy_delay, 0, -1):
                            if remaining % 5 == 0 or remaining <= 10:  # 每5秒显示一次，最后10秒每秒显示
                                progress.update(task_id, description=f"等待代理连接恢复 ({remaining}s)")
                            time.sleep(1)
                        
                        # 重试前检查代理连接
                        if self._check_proxy_connectivity():
                            console.print(f"✅ 代理连接已恢复", style="bold green")
                        else:
                            console.print(f"⚠️ 代理连接仍然不可用，继续重试", style="bold yellow")
                        
                        continue
                    else:
                        # 普通错误重试
                        attempt += 1
                        if attempt > self.max_retries:
                            console.print(f"❌ 经过 {self.max_retries + 1} 次尝试仍然失败", style="bold red")
                            return False
                        console.print(f"⚠️ 下载失败，将进行第 {attempt + 1} 次尝试", style="bold yellow")
                        continue
                else:
                    # 不可重试的错误 - 提供详细错误信息
                    if "HTTP Error 404" in error_output:
                        console.print(f"❌ 视频不存在或已被删除 (404)", style="bold red")
                    elif "HTTP Error 403" in error_output:
                        console.print(f"❌ 访问被拒绝，可能需要登录或地区限制 (403)", style="bold red")
                    elif "Private video" in error_output:
                        console.print(f"❌ 这是私人视频，无法下载", style="bold red")
                    elif "Video unavailable" in error_output:
                        console.print(f"❌ 视频不可用", style="bold red")
                    elif "This video is not available" in error_output:
                        console.print(f"❌ 视频在您的地区不可用", style="bold red")
                    else:
                        console.print(f"❌ 不可重试的错误，停止下载", style="bold red")
                        log.error(f"详细错误信息: {error_output}")
                    return False
                    
            except KeyboardInterrupt:
                if process:
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                raise
            except Exception as e:
                log.error(f"执行命令 '{cmd[0]}' 时发生错误: {e}")
                attempt += 1
                if attempt > self.max_retries:
                    return False
                continue
        
        return False
                
    def _run_subprocess(self, cmd: List[str], capture_output: bool = False) -> bool:
        """Run subprocess without progress display but with retry mechanism"""
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._calculate_delay(attempt - 1)
                    console.print(f"♾️ 第 {attempt + 1} 次尝试，等待 {delay} 秒...", style="bold yellow")
                    time.sleep(delay)
                
                if capture_output:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
                else:
                    result = subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if attempt > 0:
                    console.print(f"✅ 第 {attempt + 1} 次尝试成功！", style="bold green")
                return True
                
            except subprocess.CalledProcessError as e:
                error_output = e.stderr if e.stderr else str(e)
                
                if attempt < self.max_retries and self._should_retry(error_output):
                    if self._is_proxy_error(error_output):
                        # 代理连接错误使用更长等待时间
                        proxy_delay = min(self.proxy_retry_base_delay + attempt * self.proxy_retry_increment, 
                                         self.proxy_retry_max_delay)
                        console.print(f"🔄 代理连接失败，第 {attempt + 2} 次尝试，等待 {proxy_delay} 秒...", style="bold yellow")
                        time.sleep(proxy_delay)
                    else:
                        console.print(f"⚠️ 操作失败，将进行第 {attempt + 2} 次尝试", style="bold yellow")
                    continue
                else:
                    if capture_output:
                        log.error(f"命令 '{cmd[0]}' 执行失败")
                    if attempt == self.max_retries:
                        console.print(f"❌ 经过 {self.max_retries + 1} 次尝试仍然失败", style="bold red")
                    return False
                    
            except Exception as e:
                log.error(f"执行命令 '{cmd[0]}' 时发生错误: {e}")
                if attempt < self.max_retries:
                    continue
                return False
        
        return False