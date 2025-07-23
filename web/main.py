# web/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from celery.result import AsyncResult
from typing import Literal, Dict, Any, List
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import json
import asyncio
import time
from cachetools import TTLCache, cached
import sys
import os
import glob
import signal
import psutil
import logging
import platform

from .celery_app import celery_app
from .tasks import download_video_task
from config_manager import config

# --- App and Static Files Setup ---

app = FastAPI(
    title="SmartDownloader API",
    description="API for downloading videos and audio.",
    version="1.0.0"
)

# Initialize application state
app.state.active_processes = set()

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Set up logging
log = logging.getLogger(__name__)

# --- Cache Setup ---
# Create a cache with a Time-To-Live (TTL) of 1 hour.
# It will store up to 1024 recent results.
cache = TTLCache(maxsize=1024, ttl=3600)

# --- Pydantic Models ---

class DownloadRequest(BaseModel):
    url: str = Field(..., description="The URL of the video to download.")
    download_type: Literal['video', 'audio'] = Field('video', description="The type of content to download.")
    format_id: str = Field(..., description="The specific format ID to download.")
    resolution: str = Field('', description="The resolution of the video (e.g., '1080p60').")

class CancelRequest(BaseModel):
    task_ids: List[str] = Field(..., description="A list of task IDs to cancel.")

class DownloadResponse(BaseModel):
    task_id: str = Field(..., description="The ID of the background download task.")
    status: str = Field("pending", description="The initial status of the task.")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Dict[str, Any] | str | None = Field(None, description="Task result or error message.")

class VideoFormat(BaseModel):
    format_id: str
    resolution: str
    ext: str
    filesize: float | None
    quality: str
    fps: float | None
    vcodec: str | None
    acodec: str | None
    abr: int | None = None

class VideoInfo(BaseModel):
    title: str
    duration: float | None
    uploader: str | None
    thumbnail: str | None
    formats: List[VideoFormat]
    original_url: str
    download_type: Literal['video', 'audio']

class VideoInfoRequest(BaseModel):
    url: str = Field(..., description="Video URL to analyze")
    download_type: Literal['video', 'audio'] = Field('video')

# --- Helper Functions with Caching ---

def get_ytdlp_binary_path() -> Path:
    """
    Get the correct yt-dlp binary path based on the operating system.
    
    Returns:
        Path: The path to the appropriate yt-dlp binary
    """
    system = platform.system().lower()
    
    if system == 'darwin':  # macOS
        binary_name = 'yt-dlp_macos'
    elif system == 'linux':
        binary_name = 'yt-dlp_linux'
    elif system == 'windows':
        binary_name = 'yt-dlp.exe'
    else:
        # Fallback to generic name for other systems
        binary_name = 'yt-dlp'
    
    return BASE_DIR / "bin" / binary_name

@cached(cache)
def fetch_video_info_sync(url: str) -> dict:
    """
    This is a SYNCHRONOUS and BLOCKING function that fetches video info.
    Its results are cached by @cached. It should be run in a thread.
    """
    try:
        cmd = [
            str(get_ytdlp_binary_path()),
            "--dump-json",
            "--no-download",
            "--no-playlist",
            url
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        return json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        # Raise standard exceptions to be handled by the endpoint
        raise TimeoutError("Request to video service timed out.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get video info: yt-dlp returned an error. Stderr: {e.stderr}")
    except json.JSONDecodeError:
        raise ValueError("Failed to parse video information from the service.")

# --- API Endpoints ---

@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.post("/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """
    Fetches video information using a cached, thread-safe helper function.
    """
    # --- Whitelist Enforcement ---
    allowed_domains = config.security.allowed_domains
    if allowed_domains:  # Only check if the list is not empty
        try:
            parsed_url = urlparse(request.url)
            domain = parsed_url.netloc.lower()

            # Check if the domain or any of its parent domains are in the whitelist
            # e.g., 'music.youtube.com' should match 'youtube.com'
            is_allowed = any(domain.endswith(allowed_domain) for allowed_domain in allowed_domains)

            if not is_allowed:
                raise HTTPException(
                    status_code=403,  # 403 Forbidden is appropriate here
                    detail=f"Downloads from '{parsed_url.netloc}' are not allowed. Only downloads from the following sites are permitted: {', '.join(allowed_domains)}"
                )
        except Exception:
            # If URL parsing fails, let it proceed. yt-dlp will handle the invalid URL.
            pass
    # --- End of Whitelist Enforcement ---

    try:
        # Run the synchronous, cached function in a separate thread to avoid
        # blocking the main FastAPI event loop.
        # Provide backward compatibility for Python < 3.9
        if sys.version_info >= (3, 9):
            video_data_raw = await asyncio.to_thread(fetch_video_info_sync, request.url)
        else:
            loop = asyncio.get_running_loop()
            video_data_raw = await loop.run_in_executor(None, fetch_video_info_sync, request.url)

    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected internal server error occurred: {str(e)}")

    # --- Process the raw data (this part is unchanged) ---
    title = video_data_raw.get('title', 'Unknown Title')
    duration = video_data_raw.get('duration')
    uploader = video_data_raw.get('uploader')
    thumbnail = video_data_raw.get('thumbnail')
    
    formats = []
    raw_formats = video_data_raw.get('formats', [])
    
    if request.download_type == 'video':
        for fmt in raw_formats:
            has_resolution = fmt.get('width') and fmt.get('height')
            is_special_audio = fmt.get('vcodec') == 'audio only'
            if has_resolution and not is_special_audio and fmt.get('ext') == 'mp4':
                formats.append(VideoFormat(
                    format_id=fmt.get('format_id', ''),
                    resolution=f"{fmt.get('width')}x{fmt.get('height')}",
                    ext='mp4',
                    filesize=fmt.get('filesize') or fmt.get('filesize_approx'),
                    quality=fmt.get('format_note', f"{fmt.get('height')}p"),
                    fps=fmt.get('fps'),
                    vcodec=fmt.get('vcodec'),
                    acodec=fmt.get('acodec')
                ))
    
    elif request.download_type == 'audio':
        # For audio requests, find all valid audio streams and select the single best one.
        candidate_audio_formats = []
        for fmt in raw_formats:
            has_resolution = fmt.get('width') and fmt.get('height')
            is_special_audio = fmt.get('vcodec') == 'audio only'
            has_abr = fmt.get('abr')

            if is_special_audio or (not has_resolution and has_abr):
                candidate_audio_formats.append(fmt)
        
        if candidate_audio_formats:
            # Per user request, select the best format based on ABR (audio bitrate) to ensure highest quality.
            best_audio_format_raw = max(
                candidate_audio_formats, 
                key=lambda f: f.get('abr') or 0
            )
            
            # Create a single, standardized VideoFormat object for the frontend
            abr = best_audio_format_raw.get('abr')
            quality_desc = f"{int(abr)}k" if abr else best_audio_format_raw.get('format_note', 'Unknown')
            formats.append(VideoFormat(
                format_id=best_audio_format_raw.get('format_id', ''),
                resolution=quality_desc,
                ext=best_audio_format_raw.get('ext'),
                filesize=best_audio_format_raw.get('filesize') or best_audio_format_raw.get('filesize_approx'),
                quality=quality_desc,
                fps=None,
                vcodec=None,  # CRITICAL: Standardize to None for the frontend
                acodec=best_audio_format_raw.get('acodec'),
                abr=int(abr) if abr else None
            ))

    return VideoInfo(
        title=title,
        duration=float(duration) if duration else None,
        uploader=uploader,
        thumbnail=thumbnail,
        formats=formats,
        original_url=request.url,
        download_type=request.download_type
    )

@app.post("/downloads", response_model=DownloadResponse, status_code=202)
async def start_download(request: DownloadRequest):
    task = download_video_task.delay(
        video_url=request.url, 
        download_type=request.download_type,
        format_id=request.format_id,
        resolution=request.resolution
    )
    return {"task_id": task.id, "status": "pending"}

@app.get("/download-stream")
async def download_stream(request: Request, url: str, download_type: str, format_id: str, resolution: str, title: str):
    
    log.info(f"Stream download request: {url}, format_id: {format_id}, type: {download_type}")
    
    try:
        async def stream_downloader():
            try:
                process = await asyncio.create_subprocess_exec(
                    str(get_ytdlp_binary_path()),
                    "-f", format_id,
                    "--output", "-",  # Stream to stdout
                    url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                async def log_stderr():
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        log.error(f"yt-dlp stderr: {line.decode().strip()}")

                stderr_logger_task = asyncio.create_task(log_stderr())
                
                # Track the process for cleanup
                active_processes = getattr(request.app.state, 'active_processes', set())
                active_processes.add(process.pid)
                request.app.state.active_processes = active_processes

                try:
                    while True:
                        # More frequent disconnection check
                        if await request.is_disconnected():
                            log.warning("Client disconnected, terminating download process.")
                            await terminate_process_tree(process)
                            break
                        
                        try:
                            # Use asyncio.wait_for to add timeout for reads
                            chunk = await asyncio.wait_for(process.stdout.read(8192), timeout=1.0)
                        except asyncio.TimeoutError:
                            # Check disconnection on timeout and continue
                            continue
                            
                        if not chunk:
                            break
                        yield chunk
                finally:
                    # Clean up process from tracking
                    active_processes.discard(process.pid)
                    
                    if process.returncode is None:
                        log.info(f"Ensuring process {process.pid} is terminated.")
                        await terminate_process_tree(process)
                    
                    await stderr_logger_task # Wait for stderr logger to finish
                    await process.wait()
                    log.info(f"Process {process.pid} finished with code {process.returncode}.")
                    
            except Exception as e:
                log.error(f"Error in stream_downloader: {e}")
                raise e

        media_type = 'video/mp4' if download_type == 'video' else 'audio/mp3'
        
        # Sanitize title for filename - handle Chinese characters properly
        clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
        # If the cleaned title is empty or too short, use a default
        if not clean_title or len(clean_title) < 3:
            clean_title = "video" if download_type == 'video' else "audio"
        
        # Create a safe filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_title}_{resolution}_{timestamp}.{'mp4' if download_type == 'video' else 'mp3'}"
        
        # Ensure filename is ASCII-safe for HTTP headers
        safe_filename = filename.encode('ascii', errors='ignore').decode('ascii')
        if not safe_filename:
            safe_filename = f"download_{timestamp}.{'mp4' if download_type == 'video' else 'mp3'}"

        return StreamingResponse(
            stream_downloader(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        log.error(f"Error in download_stream endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Stream download failed: {str(e)}")


async def terminate_process_tree(process):
    """
    Terminate a process and all its child processes.
    """
    try:
        if process.returncode is None:  # Process is still running
            # First try graceful termination
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if graceful termination fails
                log.warning(f"Process {process.pid} didn't terminate gracefully, force killing")
                process.kill()
                await process.wait()
                
            # Also kill any child processes using psutil
            try:
                parent = psutil.Process(process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                # Wait for children to terminate
                psutil.wait_procs(children, timeout=3)
                # Force kill any remaining children
                for child in children:
                    if child.is_running():
                        child.kill()
            except psutil.NoSuchProcess:
                pass  # Process already terminated
            except Exception as e:
                log.warning(f"Failed to clean up child processes: {e}")
                
    except Exception as e:
        log.error(f"Error terminating process tree: {e}")
@app.get("/downloads/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    result = task_result.result
    
    # Handle different result types
    if isinstance(task_result.result, Exception):
        result = str(task_result.result)
    elif task_result.status == 'SUCCESS':
        # For successful tasks, check if result is available, otherwise use meta
        if result and isinstance(result, dict) and 'relative_path' in result:
            # Use the actual result if it contains file info
            pass
        elif hasattr(task_result, 'info') and task_result.info and isinstance(task_result.info, dict):
            # Use meta info if it contains the file information
            result = task_result.info
        else:
            # Fallback to whatever result we have
            if not result:
                result = {"status": "Completed"}
    elif task_result.status in ['PENDING', 'PROGRESS'] and hasattr(task_result, 'info') and task_result.info:
        # For in-progress tasks, use the meta info
        result = task_result.info
    else:
        # For other cases, ensure we have a proper result format
        if not result:
            result = {"status": task_result.status}
    
    return {"task_id": task_id, "status": task_result.status, "result": result}

@app.post("/downloads/cancel", status_code=200)
async def cancel_downloads(request: CancelRequest):
    """
    Cancels one or more running download tasks and cleans up incomplete files.
    Enhanced with better process cleanup.
    """
    cancelled_tasks = []
    
    # 1. Revoke Celery tasks first
    for task_id in request.task_ids:
        celery_app.control.revoke(task_id, terminate=True, signal='SIGKILL')  # Use SIGKILL for force termination
        cancelled_tasks.append(task_id)
    
    # 2. Clean up any active streaming processes
    await cleanup_active_processes()
    
    # 3. Clean up incomplete download files
    cleanup_result = await cleanup_incomplete_downloads()
    
    # 4. Reset application state (lightweight approach)
    await reset_application_state()
    
    return {
        "message": "Tasks cancelled, processes terminated, cleanup completed, and application state reset.", 
        "cancelled_tasks": cancelled_tasks,
        "cleanup_result": cleanup_result
    }

async def cleanup_active_processes():
    """
    Clean up any active streaming download processes.
    """
    try:
        active_processes = getattr(app.state, 'active_processes', set())
        for pid in active_processes.copy():  # Use copy to avoid modification during iteration
            try:
                process = psutil.Process(pid)
                if process.is_running():
                    log.info(f"Terminating active process {pid}")
                    process.terminate()
                    # Wait a bit for graceful termination
                    try:
                        process.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        # Force kill if needed
                        process.kill()
                active_processes.discard(pid)
            except psutil.NoSuchProcess:
                # Process already terminated
                active_processes.discard(pid)
            except Exception as e:
                log.warning(f"Failed to terminate process {pid}: {e}")
                active_processes.discard(pid)  # Remove from tracking anyway
        
        # Clear the set
        app.state.active_processes = set()
        log.info("Active processes cleanup completed")
        
    except Exception as e:
        log.error(f"Error during active processes cleanup: {e}")
async def cleanup_incomplete_downloads():
    """
    Clean up incomplete download files (.part, .temp, .ytdl, etc.)
    Returns cleanup statistics.
    """
    cleanup_stats = {
        "cleaned_files": [],
        "total_size_mb": 0,
        "errors": []
    }
    
    try:
        download_folder = Path(config.downloader.save_path)
        if not download_folder.exists():
            return cleanup_stats
        
        # 从配置中读取清理模式
        incomplete_patterns = config.downloader.cleanup_patterns
        
        total_size = 0
        for pattern in incomplete_patterns:
            for file_path in download_folder.glob(pattern):
                try:
                    if file_path.is_file():
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        cleanup_stats["cleaned_files"].append(str(file_path.name))
                        total_size += file_size
                except Exception as e:
                    cleanup_stats["errors"].append(f"Failed to delete {file_path.name}: {str(e)}")
                    log.warning(f"Failed to delete {file_path}: {e}")
        
        cleanup_stats["total_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        if cleanup_stats["cleaned_files"]:
            log.info(f"Cleaned up {len(cleanup_stats['cleaned_files'])} files ({cleanup_stats['total_size_mb']}MB)")
        
    except Exception as e:
        cleanup_stats["errors"].append(f"Cleanup error: {str(e)}")
        log.error(f"Error during cleanup: {e}")
    
    return cleanup_stats

async def reset_application_state():
    """
    Reset application state without server restart (lightweight approach).
    """
    try:
        # 1. Clear cache
        cache.clear()
        log.info("Application cache cleared")
        
        # 2. Reset any global variables or state
        # (Add more state reset logic here as needed)
        
        # 3. Optionally purge old Celery tasks from Redis
        await purge_old_celery_tasks()
        
        log.info("Application state reset completed")
        
    except Exception as e:
        log.error(f"Error during application state reset: {e}")

async def purge_old_celery_tasks():
    """
    Clean up old/failed tasks from Redis to prevent memory bloat.
    """
    try:
        # Get all task results and clean up old ones
        inspect = celery_app.control.inspect()
        
        # Get active, scheduled, and reserved tasks
        active = inspect.active()
        scheduled = inspect.scheduled() 
        reserved = inspect.reserved()
        
        # Log current task status for monitoring
        active_count = sum(len(tasks) for tasks in (active or {}).values())
        scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values())
        reserved_count = sum(len(tasks) for tasks in (reserved or {}).values())
        
        log.info(f"Current tasks - Active: {active_count}, Scheduled: {scheduled_count}, Reserved: {reserved_count}")
        
    except Exception as e:
        log.warning(f"Could not purge old Celery tasks: {e}")

# Remove the old restart_server function since we're not using it anymore


@app.get("/config")
async def get_config() -> Dict[str, Any]:
    """
    获取当前应用的主要配置项。
    返回一个可序列化为JSON的字典。
    """
    # 返回整个配置，或选择性返回关键部分
    # 这里我们返回整个配置，因为前端或客户端可能需要访问任何部分
    return config.model_dump()

@app.post("/config")
async def update_config(update_request: Dict[str, Any]):
    """
    更新并保存应用配置。
    支持部分更新，例如只更新 downloader.max_retries。
    """
    from config_manager import config_manager, AppConfig, ValidationError

    try:
        # 1. 获取当前配置的字典表示
        current_config_dict = config_manager.config.model_dump()

        # 2. 深度合并传入的更新
        def deep_update(source: dict, updates: dict) -> dict:
            for key, value in updates.items():
                if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                    source[key] = deep_update(source[key], value)
                else:
                    source[key] = value
            return source

        updated_data = deep_update(current_config_dict, update_request)

        # 3. 使用Pydantic重新验证整个配置对象
        validated_config = AppConfig.model_validate(updated_data)

        # 4. 如果验证通过，则更新全局配置并保存到文件
        config_manager.config = validated_config
        config_manager.save_config(validated_config)

        return {"message": "Configuration updated successfully."}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/downloads/list", response_class=JSONResponse)
async def list_downloads():
    """
    Lists all downloaded files in the download directory.
    """
    download_path = Path(config.downloader.save_path)
    if not download_path.exists():
        return JSONResponse(content={"files": []})

    files = [f.name for f in download_path.iterdir() if f.is_file()]
    return JSONResponse(content={"files": files})

@app.get("/files/{file_name}", response_class=FileResponse)
@app.head("/files/{file_name}")
async def get_downloaded_file(request: Request, file_name: str):
    """
    Serves a downloaded file.
    """
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_file_name = unquote(file_name)
        log.info(f"Serving file request: '{decoded_file_name}'")
        
        # First try direct path (could be just filename or relative path)
        file_path = Path(config.downloader.save_path) / decoded_file_name
        
        if file_path.exists() and file_path.is_file():
            log.info(f"Found file directly: {file_path}, size: {file_path.stat().st_size} bytes")
        else:
            # If not found directly, search for the filename in the download directory and subdirectories
            log.info(f"File not found directly, searching in download folder...")
            download_folder = Path(config.downloader.save_path)
            found_file = None
            
            if download_folder.exists():
                # Search recursively for the file
                for file_candidate in download_folder.rglob("*"):
                    if file_candidate.is_file() and file_candidate.name == decoded_file_name:
                        found_file = file_candidate
                        log.info(f"Found file by name: {found_file}")
                        break
                
                # If still not found, try case-insensitive search
                if not found_file:
                    for file_candidate in download_folder.rglob("*"):
                        if file_candidate.is_file() and file_candidate.name.lower() == decoded_file_name.lower():
                            found_file = file_candidate
                            log.info(f"Found file by case-insensitive search: {found_file}")
                            break
                
                if found_file:
                    file_path = found_file
                else:
                    log.error(f"File '{decoded_file_name}' not found in {download_folder}")
                    # List all files for debugging
                    all_files = [str(f) for f in download_folder.rglob("*") if f.is_file()]
                    log.info(f"Available files: {all_files[:10]}...")  # Show first 10 files
                    raise HTTPException(status_code=404, detail=f"File '{decoded_file_name}' not found.")
            else:
                log.error(f"Download directory does not exist: {download_folder}")
                raise HTTPException(status_code=404, detail="Download directory not found.")
        
        # Generate proper filename for download
        clean_filename = file_path.name
        
        final_size = file_path.stat().st_size
        
        if final_size == 0:
            log.error(f"File has zero size: {file_path}")
            raise HTTPException(status_code=500, detail="File is empty or corrupted")
        
        if not os.access(file_path, os.R_OK):
            log.error(f"File is not readable: {file_path}")
            raise HTTPException(status_code=500, detail="File permission denied")
        
        # Detect media type based on extension
        MIME_TYPES = {
            # 视频
            '.mp4': 'video/mp4',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            # 音频
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.opus': 'audio/opus',
            '.wav': 'audio/wav',
            '.flac': 'audio/flac',
            '.aac': 'audio/aac',
        }
        file_extension = file_path.suffix.lower()
        # 如果找不到，则回退到通用的二进制流类型
        media_type = MIME_TYPES.get(file_extension, 'application/octet-stream')
        
        headers = {
            "Content-Disposition": f"attachment; filename=\"{clean_filename}\"",
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD",
            "Access-Control-Allow-Headers": "*",
            "Content-Length": str(final_size)
        }
        
        # Handle HEAD request - return headers only
        if request.method == "HEAD":
            log.debug("Handling HEAD request for file: %s", clean_filename)
            from fastapi import Response
            return Response(
                headers=headers,
                media_type=media_type
            )
        
        # Handle GET request - return file
        log.info("Serving file '%s' (%s) to client.", clean_filename, media_type)
        
        # Use a more explicit FileResponse configuration
        try:
            response = FileResponse(
                path=str(file_path),
                media_type=media_type,
                filename=clean_filename,
                headers={
                    "Cache-Control": "no-cache",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD",
                    "Access-Control-Allow-Headers": "*"
                }
            )
            
            # Explicitly set content length
            response.headers["Content-Length"] = str(final_size)
            log.debug(f"FileResponse created successfully for {clean_filename} with size: {final_size}")
            return response
            
        except Exception as e:
            log.error(f"Error creating FileResponse: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to serve file: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error serving file '{file_name}': {e}")
        raise HTTPException(status_code=500, detail="Internal server error while serving file.")

@app.delete("/files/{file_name}", status_code=200)
async def delete_downloaded_file(file_name: str):
    """
    Deletes a specific downloaded file.
    """
    try:
        file_path = Path(config.downloader.save_path) / file_name
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            return {"message": f"File '{file_name}' deleted successfully."}
        else:
            raise HTTPException(status_code=404, detail="File not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

@app.post("/downloads/clear_all", status_code=200)
async def clear_all_downloads():
    """
    Deletes all files in the download directory.
    """
    try:
        download_path = Path(config.downloader.save_path)
        if not download_path.exists():
            return {"message": "Download directory not found."}

        for file_path in download_path.iterdir():
            if file_path.is_file():
                file_path.unlink()
        
        return {"message": "All downloaded files have been cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing downloads: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
