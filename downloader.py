# downloader.py

import subprocess, json, logging
from pathlib import Path
from typing import Optional, List, Generator, Dict, Any

# 在模块顶部获取logger实例
log = logging.getLogger(__name__)

class Downloader:
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        self.download_folder = download_folder
        self.cookies_file = cookies_file
        self.proxy = proxy

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
        log.info("  [Step 1/2] 正在下载独立的视频和音频流...")
        video_part_base, audio_part_base = f"{file_prefix}_video.tmp", f"{file_prefix}_audio.tmp"
        try:
            log.info("    -> 正在下载视频部分...")
            vid_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestvideo[ext=mp4]/bestvideo', '-o', f"{self.download_folder / video_part_base}.%(ext)s", video_url]
            self._run_subprocess(vid_cmd)
            
            log.info("    -> 正在下载音频部分...")
            aud_cmd = self._build_base_yt_dlp_cmd() + ['-f', 'bestaudio[ext=m4a]/bestaudio', '-o', f"{self.download_folder / audio_part_base}.%(ext)s", video_url]
            self._run_subprocess(aud_cmd)
            
            vid_part = next(self.download_folder.glob(f"{video_part_base}.*"), None)
            aud_part = next(self.download_folder.glob(f"{audio_part_base}.*"), None)
            
            if not (vid_part and aud_part):
                merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") if p.suffix in ['.mp4', '.mkv', '.webm']), None)
                if merged_file: log.info("    [Info] 检测到媒体源已合并。"); return merged_file
                raise FileNotFoundError("未能找到下载的视频或音频临时文件。")
            
            log.info(f"    ✅ 视频/音频部分下载成功。")
            return self.merge_to_mp4(vid_part, aud_part, file_prefix)
        except Exception as e:
            log.error(f"    下载或合并过程中出错: {e}"); return None

    def merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Optional[Path]:
        log.info("  [Step 2/2] 正在使用ffmpeg合并文件...")
        final_path = self.download_folder / f"{file_prefix}.mp4"
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()), '-c', 'copy', str(final_path.resolve())]
        if self._run_subprocess(cmd, True): log.info(f"    ✅ 视频合并成功: {final_path.name}"); return final_path
        log.error(f"    视频合并失败。"); return None

    def download_metadata(self, url: str, file_prefix: str) -> bool:
        log.info("  [Info] 正在下载元数据...")
        cmd = self._build_base_yt_dlp_cmd() + ['--skip-download', '--write-info-json', '--write-thumbnail', '--convert-thumbnails', 'png', '-o', str(self.download_folder / file_prefix)]
        cmd.append(url)
        return self._run_subprocess(cmd, capture_output=True)

    def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Optional[Path]:
        log.info(f"  [mp3] 正在从本地文件 '{video_path.name}' 提取音频...")
        mp3_path = self.download_folder / f"{file_prefix}.mp3"
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]
        if self._run_subprocess(cmd, True): log.info(f"    ✅ 音频提取成功: {mp3_path.name}"); return mp3_path
        log.error(f"    音频提取失败。"); return None

    def cleanup_temp_files(self, file_prefix: str):
        log.info("  [Cleaner] 正在清理临时文件...")
        for p in self.download_folder.glob(f"{file_prefix}.f*"): p.unlink()
        for p in self.download_folder.glob(f"{file_prefix}_*.tmp.*"): p.unlink()
            
    def _run_subprocess(self, cmd: List[str], capture_output: bool = False) -> bool:
        try:
            subprocess.run(cmd, check=True, capture_output=capture_output, text=capture_output, encoding='utf-8' if capture_output else None)
            return True
        except subprocess.CalledProcessError as e:
            log.error(f"命令 '{cmd[0]}' 执行失败，错误码: {e.returncode}")
            if capture_output and e.stderr: log.error(f"    错误信息: {e.stderr.strip()}")
        except Exception as e:
            log.error(f"执行命令 '{cmd[0]}' 时发生未知错误: {e}")
        return False