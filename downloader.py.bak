# downloader.py

import subprocess
import json
from pathlib import Path
from typing import Optional, List, Generator, Dict, Any

class Downloader:
    """
    负责执行所有与 yt-dlp 和 ffmpeg 相关的媒体处理任务。
    """
    def __init__(self, download_folder: Path, cookies_file: Optional[str] = None, proxy: Optional[str] = None):
        self.download_folder = download_folder
        self.cookies_file = cookies_file
        self.proxy = proxy

    def _build_base_yt_dlp_cmd(self) -> List[str]:
        cmd = ['yt-dlp', '--ignore-config', '--no-warnings']
        if self.proxy:
            cmd.extend(['--proxy', self.proxy])
        if self.cookies_file:
            cmd.extend(['--cookies', str(Path(self.cookies_file).resolve())])
        return cmd

    def stream_playlist_info(self, url: str) -> Generator[Dict[str, Any], None, None]:
        cmd = self._build_base_yt_dlp_cmd()
        cmd.extend(['--flat-playlist', '--print-json', '--skip-download', url])
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        for line in process.stdout:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
        process.wait()

    def download_and_merge(self, video_url: str, file_prefix: str) -> Optional[Path]:
        """下载并合并视频，处理预合并和分离的流。"""
        print("  [Step 1/3] 正在下载媒体流...")
        output_template = self.download_folder / f"{file_prefix}.%(ext)s"
        cmd = self._build_base_yt_dlp_cmd()
        cmd.extend([
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--no-overwrites', '--restrict-filenames', '-k',
            '-o', str(output_template)
        ])
        cmd.append(video_url)
        
        if not self._run_subprocess(cmd):
            print("    ❌ yt-dlp 下载步骤失败。")
            return None
        
        # 查找下载后的文件
        video_part = next(self.download_folder.glob(f"{file_prefix}.f*.mp4"), next(self.download_folder.glob(f"{file_prefix}.f*.webm"), None))
        audio_part = next(self.download_folder.glob(f"{file_prefix}.f*.m4a"), next(self.download_folder.glob(f"{file_prefix}.f*.opus"), None))
        
        if video_part and audio_part:
            print(f"    ✅ 视频部分: {video_part.name}")
            print(f"    ✅ 音频部分: {audio_part.name}")
            return self._merge_to_mp4(video_part, audio_part, file_prefix)
        else:
            merged_file = next((p for p in self.download_folder.glob(f"{file_prefix}.*") if p.suffix in ['.mp4', '.mkv', '.webm']), None)
            if merged_file:
                print("    [Info] 检测到媒体源已是合并好的文件。")
                return merged_file
        
        print(f"    ❌ 未能找到预期的下载文件。")
        return None

    def _merge_to_mp4(self, video_part: Path, audio_part: Path, file_prefix: str) -> Optional[Path]:
        """使用ffmpeg将独立的流合并为MP4。"""
        print("  [Step 2/3] 正在使用ffmpeg合并文件...")
        final_video_path = self.download_folder / f"{file_prefix}.mp4"
        cmd = ['ffmpeg', '-y', '-i', str(video_part.resolve()), '-i', str(audio_part.resolve()), '-c', 'copy', str(final_video_path.resolve())]
        if self._run_subprocess(cmd, capture_output=True):
            print(f"    ✅ 视频合并成功: {final_video_path.name}")
            return final_video_path
        print(f"    ❌ 视频合并失败。")
        return None

    def download_metadata(self, url: str, file_prefix: str) -> bool:
        """仅下载元数据和封面。"""
        print("  [Info] 正在下载元数据...")
        output_template = self.download_folder / file_prefix
        cmd = self._build_base_yt_dlp_cmd()
        cmd.extend(['--skip-download', '--write-info-json', '--write-thumbnail', '--convert-thumbnails', 'png', '--no-overwrites', '--restrict-filenames', '-o', str(output_template)])
        cmd.append(url)
        return self._run_subprocess(cmd, capture_output=True)

    def extract_audio_from_local_file(self, video_path: Path, file_prefix: str) -> Optional[Path]:
        """直接使用 ffmpeg 从本地视频文件提取音频。"""
        print(f"  [mp3] 正在从本地文件 '{video_path.name}' 提取音频...")
        mp3_path = self.download_folder / f"{file_prefix}.mp3"
        cmd = ['ffmpeg','-y', '-i', str(video_path.resolve()),'-vn','-q:a', '0', str(mp3_path.resolve())]
        if self._run_subprocess(cmd, capture_output=True):
            print(f"    ✅ 音频提取成功: {mp3_path.name}")
            return mp3_path
        print(f"    ❌ 音频提取失败。")
        return None

    def cleanup_temp_files(self, file_prefix: str):
        """清理所有下载的临时文件。"""
        print("  [Step 3/3] 正在清理临时文件...")
        for p in self.download_folder.glob(f"{file_prefix}.f*"):
            p.unlink()
            
    def _run_subprocess(self, cmd: List[str], capture_output: bool = False) -> bool:
        try:
            subprocess.run(cmd, check=True, capture_output=capture_output, text=capture_output, encoding='utf-8' if capture_output else None)
            return True
        except subprocess.CalledProcessError as e:
            print(f"    ❌ 命令 '{cmd[0]}' 执行失败，错误码: {e.returncode}")
            if capture_output and e.stderr:
                print(f"    错误信息: {e.stderr.strip()}")
        except Exception as e:
            print(f"    ❌ 执行命令 '{cmd[0]}' 时发生未知错误: {e}")
        return False