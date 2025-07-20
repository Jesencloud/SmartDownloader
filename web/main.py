# web/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from celery.result import AsyncResult
from typing import Literal, Dict, Any, List
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import json
import asyncio
from cachetools import TTLCache, cached

from .celery_app import celery_app
from .tasks import download_video_task
from config_manager import config

# --- App and Static Files Setup ---

app = FastAPI(
    title="SmartDownloader API",
    description="API for downloading videos and audio.",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

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

@cached(cache)
def fetch_video_info_sync(url: str) -> dict:
    """
    This is a SYNCHRONOUS and BLOCKING function that fetches video info.
    Its results are cached by @cached. It should be run in a thread.
    """
    try:
        cmd = [
            str(BASE_DIR / "bin" / "yt-dlp_macos"),
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
        video_data_raw = await asyncio.to_thread(fetch_video_info_sync, request.url)
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
    
    for fmt in raw_formats:
        # Only process video formats with MP4 extension
        if fmt.get('width') and fmt.get('height') and fmt.get('ext') == 'mp4':
            formats.append(VideoFormat(
                format_id=fmt.get('format_id', ''),
                resolution=f"{fmt.get('width')}x{fmt.get('height')}",
                ext='mp4',  # Force MP4 extension
                filesize=fmt.get('filesize') or fmt.get('filesize_approx'),
                quality=fmt.get('format_note', f"{fmt.get('height')}p"),
                fps=fmt.get('fps'),
                vcodec=fmt.get('vcodec'),
                acodec=fmt.get('acodec')
            ))
        elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
            abr = fmt.get('abr')
            quality_desc = f"{int(abr)}k" if abr else fmt.get('format_note', 'Unknown')
            formats.append(VideoFormat(
                format_id=fmt.get('format_id', ''),
                resolution=quality_desc,
                ext=fmt.get('ext'),
                filesize=fmt.get('filesize') or fmt.get('filesize_approx'),
                quality=quality_desc,
                fps=None,
                vcodec=None,
                acodec=fmt.get('acodec'),
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

@app.get("/downloads/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    result = task_result.result
    if isinstance(task_result.result, Exception):
        result = str(task_result.result)
    return {"task_id": task_id, "status": task_result.status, "result": result}
