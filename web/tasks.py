# web/tasks.py
import sys
import logging
import json
from pathlib import Path
import asyncio

# Set up logging
log = logging.getLogger(__name__)

# 这是一个常见的模式，以确保当Celery worker在不同环境中启动时，
# 它仍然可以找到项目根目录下的模块（如`downloader`, `core`等）。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.append(project_root)

from downloader import Downloader
from config_manager import config
from .celery_app import celery_app

# 将任务改回一个普通的同步函数
@celery_app.task(bind=True, name="create_download_task")
def download_video_task(self, video_url: str, download_type: str, format_id: str, resolution: str = '', custom_path: str = None):
    """
    一个同步的Celery任务，它在内部创建一个新的事件循环来运行异步下载逻辑。
    
    Args:
        video_url: 要下载的视频URL
        download_type: 下载类型 ('video' 或 'audio')
        format_id: 视频格式ID
        resolution: 视频分辨率 (例如: '1080p60')
        custom_path: 自定义下载路径 (可选)
    """
    async def _async_download():
        download_folder = Path(custom_path) if custom_path else Path(config.downloader.save_path)
        # ... [Path validation logic remains the same] ...
        
        file_prefix = self.request.id 
        downloader = Downloader(download_folder=download_folder)

        if download_type == 'video':
            # Pass the format_id and resolution to ensure the correct video quality is downloaded
            output_file = await downloader.download_and_merge(
                video_url=video_url,
                file_prefix=file_prefix,
                format_id=format_id if format_id != 'best' else None,
                resolution=resolution  # Pass the resolution to the downloader
            )
        elif download_type == 'audio':
            # For audio downloads, we first get the best audio format
            # then download and convert it to MP3
            log.info(f'Starting audio download for {video_url}')
            
            # Get video info to find the best audio format and title
            info_cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-warnings',
                '--skip-download',
                '--no-playlist',
                video_url
            ]
            
            # Execute the command to get video info
            process = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                raise Exception(f'Failed to get video info: {error_msg}')
            
            # Parse the JSON output to get available formats and video info
            video_info = json.loads(stdout)
            formats = video_info.get('formats', [])
            
            # Get video title and sanitize it for filename
            video_title = video_info.get('title', 'audio')
            # Sanitize the title to be filesystem-safe
            import re
            safe_title = re.sub(r'[\\/*?:"<>|]', '', video_title)  # Remove invalid filename characters
            safe_title = re.sub(r'\s+', ' ', safe_title).strip()  # Normalize whitespace
            safe_title = safe_title[:100]  # Limit length to 100 characters
            
            # Find the best audio format based on quality and format
            best_audio = None
            audio_formats = []
            
            # Get the best audio format
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            
            if not audio_formats:
                raise Exception('No audio formats found for this video')
                
            # Sort by quality scorefer higher bitrate and better formats)
            def get_quality_score(fmt):
                score = 0
                # Prefer formats with known good codecs
                if 'opus' in str(fmt.get('acodec', '')).lower():
                    score += 1000
                if 'aac' in str(fmt.get('acodec', '')).lower():
                    score += 800
                if 'mp3' in str(fmt.get('ext', '')).lower():
                    score += 600
                # Add points for higher bitrate
                score += int(fmt.get('tbr', 0) or 0)
                # Add points for larger files (generally higher quality)
                score += int((fmt.get('filesize', 0) or 0) / 1024)  # Convert to KB to avoid huge numbers
                return score
                
            # Sort by quality score
            audio_formats.sort(key=get_quality_score, reverse=True)
            best_audio = audio_formats[0]
            
            log.info(f'Selected best audio format: {best_audio.get("ext")} (format_id: {best_audio.get("format_id")}, tbr: {best_audio.get("tbr", "N/A")})')
            
            # Check if MP3 conversion was requested (format_id starts with 'mp3-conversion-')
            if format_id and format_id.startswith('mp3-conversion-'):
                # Extract the original format ID
                original_format_id = format_id.replace('mp3-conversion-', '')
                target_format = 'mp3'
                output_ext = 'mp3'  # Set output extension for MP3 conversion
                log.info(f'Converting audio to MP3 (original format: {best_audio.get("ext")})')
                
                # Build the audio download command with MP3 conversion
                audio_cmd = [
                    'yt-dlp',
                    '--ignore-config',
                    '--no-warnings',
                    '--no-color',
                    '--force-overwrites',
                    '--progress',
                    '--progress-template', '%(progress)j',
                    '-f', original_format_id,  # Use the original format ID
                    '--extract-audio',
                    '--audio-format', 'mp3',  # Force MP3 format
                    '--audio-quality', '0',   # Best quality
                    '--embed-thumbnail',
                    '--embed-metadata',
                    '--embed-chapters',
                    '--postprocessor-args', '-id3v2_version 3',  # Better ID3 tag support
                    '-o', f'downloads/{safe_title}.%(ext)s',  # Use video title as filename
                    '--no-simulate',
                    video_url
                ]
                output_file = Path('downloads') / f'{safe_title}.{output_ext}'
            else:
                # Use the best format directly without conversion
                audio_format_id = best_audio.get('format_id')
                target_format = 'best'  # Keep original format
                output_ext = best_audio.get('ext', 'webm')
                log.info(f'Downloading audio in original format: {output_ext}')
                
                # Build the audio download command
                audio_cmd = [
                    'yt-dlp',
                    '--ignore-config',
                    '--no-warnings',
                    '--no-color',
                    '--force-overwrites',
                    '--progress',
                    '--progress-template', '%(progress)j',
                    '-f', audio_format_id,  # Only download the selected audio format
                    '--extract-audio',
                    '--audio-format', target_format,
                    '--audio-quality', '0',  # Best quality
                    '--embed-thumbnail',
                    '--embed-metadata',
                    '--embed-chapters',
                    '-o', f'downloads/{safe_title}.%(ext)s',  # Use video title as filename
                    '--no-simulate',
                    video_url
                ]
                output_file = Path('downloads') / f'{safe_title}.{output_ext}'
            
            log.info(f'Audio download command: {" ".join(audio_cmd)}')
            
            # Execute the audio download command
            process = await asyncio.create_subprocess_exec(
                *audio_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Collect all output for better error reporting
            stdout_chunks = []
            stderr_chunks = []
            
            # Read both stdout and stderr
            while True:
                # Read from stdout
                stdout_chunk = await process.stdout.read(1024)
                if stdout_chunk:
                    stdout_chunks.append(stdout_chunk)
                    try:
                        log.debug(f'yt-dlp stdout: {stdout_chunk.decode("utf-8", errors="replace")}')
                    except Exception as e:
                        log.debug(f'Error decoding stdout: {e}')
                
                # Read from stderr
                stderr_chunk = await process.stderr.read(1024)
                if stderr_chunk:
                    stderr_chunks.append(stderr_chunk)
                    try:
                        log.debug(f'yt-dlp stderr: {stderr_chunk.decode("utf-8", errors="replace")}')
                    except Exception as e:
                        log.debug(f'Error decoding stderr: {e}')
                
                # Check if process has completed
                if process.returncode is not None:
                    # Read any remaining output
                    remaining_stdout, remaining_stderr = await asyncio.wait_for(process.communicate(), timeout=5)
                    if remaining_stdout:
                        stdout_chunks.append(remaining_stdout)
                    if remaining_stderr:
                        stderr_chunks.append(remaining_stderr)
                    break
                
                # Small sleep to prevent busy-waiting
                await asyncio.sleep(0.1)
            
            # Process collected output
            stdout = b''.join(stdout_chunks).decode('utf-8', errors='replace') if stdout_chunks else ''
            stderr = b''.join(stderr_chunks).decode('utf-8', errors='replace') if stderr_chunks else ''
            
            if process.returncode != 0:
                error_details = f"""
                Audio download failed with return code: {process.returncode}
                Command: {' '.join(audio_cmd)}
                
                === STDOUT ===
                {stdout}
                
                === STDERR ===
                {stderr}
                """
                log.error(error_details)
                raise Exception(f"Audio download failed. Return code: {process.returncode}\n{stderr[:500]}" if stderr else "Unknown error")
            
            # Find the downloaded file with common audio extensions
            audio_extensions = ('.mp3', '.webm', '.m4a', '.opus', '.aac', '.ogg', '.wav', '.flac')
            output_file = await downloader._find_output_file(file_prefix, audio_extensions)
            
            if not output_file:
                # Try to find any file with the given prefix regardless of extension
                log.warning(f'Could not find file with prefix {file_prefix} and known extensions {audio_extensions}')
                all_files = list(Path('downloads').glob(f'{file_prefix}.*'))
                if all_files:
                    output_file = max(all_files, key=lambda f: f.stat().st_mtime)
                    log.warning(f'Found potentially matching file by prefix and modification time: {output_file}')
            
            if not output_file:
                raise Exception(f'Failed to find the downloaded audio file. Checked extensions: {audio_extensions}')
                
            log.info(f'Found downloaded audio file: {output_file}')
            
            # Verify file integrity
            if not await downloader.file_processor.verify_file_integrity(output_file):
                log.warning(f'File integrity check failed, but continuing anyway: {output_file}')
                # Continue even if verification fails, as some audio files might not pass verification
                # but are still playable
        else:
            raise ValueError(f"无效的下载类型: {download_type}")

        if output_file:
            return {
                "status": "Completed", 
                "result": str(output_file),
                "relative_path": str(output_file.relative_to(download_folder)),
                "download_folder": str(download_folder)
            }
        else:
            raise FileNotFoundError("下载后未找到输出文件。")

    try:
        return asyncio.run(_async_download())
    except Exception as e:
        clean_exception = type(e)(f"Task failed: {e}")
        raise clean_exception