# web/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from celery.result import AsyncResult
from typing import Literal, Dict, Any, List
from pathlib import Path
import subprocess
import json
import re

from .celery_app import celery_app
from .tasks import download_video_task

# --- App and Static Files Setup ---

app = FastAPI(
    title="SmartDownloader API",
    description="API for downloading videos and audio.",
    version="1.0.0"
)

# 获取项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 挂载 static 目录
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

# --- Pydantic Models ---

class DownloadRequest(BaseModel):
    url: str = Field(..., description="The URL of the video to download.")
    download_type: Literal['video', 'audio'] = Field('video', description="The type of content to download.")
    format_id: str = Field(..., description="The specific format ID to download.")

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

# --- API Endpoints ---

@app.get("/", response_class=FileResponse)
async def read_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.post("/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """
    Fetches video information using yt-dlp and returns it as JSON.
    """
    try:
        cmd = [
            str(BASE_DIR / "bin" / "yt-dlp_macos"),
            "--dump-json",
            "--no-download",
            "--no-playlist",
            request.url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        video_data_raw = json.loads(result.stdout)
        
        title = video_data_raw.get('title', 'Unknown Title')
        duration = video_data_raw.get('duration')
        uploader = video_data_raw.get('uploader')
        thumbnail = video_data_raw.get('thumbnail')
        
        formats = []
        raw_formats = video_data_raw.get('formats', [])
        
        for fmt in raw_formats:
            # Video streams
            if fmt.get('width') and fmt.get('height'):
                if fmt.get('ext') in ['mp4', 'webm']:
                    formats.append(VideoFormat(
                        format_id=fmt.get('format_id', ''),
                        resolution=f"{fmt.get('width')}x{fmt.get('height')}",
                        ext=fmt.get('ext'),
                        filesize=fmt.get('filesize') or fmt.get('filesize_approx'),
                        quality=fmt.get('format_note', f"{fmt.get('height')}p"),
                        fps=fmt.get('fps'),
                        vcodec=fmt.get('vcodec'),
                        acodec=fmt.get('acodec')
                    ))
            # Audio streams
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

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Request to video service timed out.")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=400, detail=f"Failed to get video info: {e.stderr}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse video information from service.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")


@app.post("/downloads", response_model=DownloadResponse, status_code=202)
async def start_download(request: DownloadRequest):
    task = download_video_task.delay(
        video_url=request.url, 
        download_type=request.download_type,
        format_id=request.format_id
    )
    return {"task_id": task.id, "status": "pending"}

@app.get("/downloads/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    result = task_result.result
    if isinstance(task_result.result, Exception):
        result = str(task_result.result)
    return {"task_id": task_id, "status": task_result.status, "result": result}

