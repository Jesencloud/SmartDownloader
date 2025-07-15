# web/main.py
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# 挂载 static 目录，让 FastAPI 可以直接提供静态文件服务
# /static 是URL路径，directory是文件系统中的路径
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

# --- Pydantic Models for Request and Response ---

class DownloadRequest(BaseModel):
    url: str = Field(..., description="The URL of the video to download.", example="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    download_type: Literal['video', 'audio'] = Field('video', description="The type of content to download.")
    custom_path: str = Field(None, description="Custom download path (optional).")

class DownloadResponse(BaseModel):
    task_id: str = Field(..., description="The ID of the background download task.")
    status: str = Field("pending", description="The initial status of the task.")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Dict[str, Any] | str | None = Field(None, description="The result of the task. If successful, it's a dictionary. If failed, it's an error message.")

class VideoFormat(BaseModel):
    format_id: str = Field(..., description="Format ID from yt-dlp")
    resolution: str = Field(..., description="Resolution like '1080p', '720p'")
    ext: str = Field(..., description="File extension")
    filesize: float | None = Field(None, description="File size in bytes")
    quality: str = Field(..., description="Quality description")
    fps: float | None = Field(None, description="Frames per second")
    vcodec: str | None = Field(None, description="Video codec")
    acodec: str | None = Field(None, description="Audio codec")

class VideoInfo(BaseModel):
    title: str = Field(..., description="Video title")
    duration: float | None = Field(None, description="Duration in seconds")
    uploader: str | None = Field(None, description="Uploader name")
    thumbnail: str | None = Field(None, description="Thumbnail URL")
    formats: List[VideoFormat] = Field(..., description="Available formats")

class VideoInfoRequest(BaseModel):
    url: str = Field(..., description="Video URL to analyze")


# --- API Endpoints ---

@app.get("/", response_class=FileResponse)
async def read_index():
    """
    提供前端主页 (index.html)。
    """
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/download", response_class=FileResponse)
async def read_download():
    """
    提供下载页面 (download.html)。
    """
    return FileResponse(BASE_DIR / "static" / "download.html")

@app.post("/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """
    获取视频信息和可用格式。
    """
    try:
        # 使用yt-dlp获取视频信息
        cmd = [
            "yt-dlp", 
            "--dump-json", 
            "--no-download",
            "--no-playlist",
            request.url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Failed to get video info: {result.stderr}"
            )
        
        # 解析JSON输出
        video_data = json.loads(result.stdout)
        
        # 提取视频信息
        title = video_data.get('title', 'Unknown Title')
        duration = video_data.get('duration')
        uploader = video_data.get('uploader')
        thumbnail = video_data.get('thumbnail')
        
        # 处理格式信息
        formats = []
        raw_formats = video_data.get('formats', [])
        
        print(f"Found {len(raw_formats)} formats for video: {title}")
        
        # 过滤和处理格式
        for fmt in raw_formats:
            try:
                # 对于视频，只处理有视频流的格式
                # 对于音频，只处理有音频流的格式
                if fmt.get('vcodec') != 'none' and fmt.get('height'):
                    # 视频格式
                    resolution = f"{fmt.get('height')}p"
                    
                    # 计算文件大小（估算）
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                    
                    # 获取文件扩展名
                    ext = fmt.get('ext', 'mp4')
                    
                    # 过滤条件：只保留mp4格式且有文件大小信息的视频
                    if ext == 'mp4' and filesize and filesize > 0:
                        format_info = VideoFormat(
                            format_id=fmt.get('format_id', ''),
                            resolution=resolution,
                            ext=ext,
                            filesize=filesize,
                            quality=fmt.get('format_note', resolution),
                            fps=fmt.get('fps'),
                            vcodec=fmt.get('vcodec'),
                            acodec=fmt.get('acodec')
                        )
                        formats.append(format_info)
                elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    # 纯音频格式
                    # 构建质量描述
                    abr = fmt.get('abr', 0)
                    if abr:
                        quality_desc = f"{int(abr)}kbps"
                    else:
                        quality_desc = fmt.get('format_note', 'Unknown')
                    
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                    ext = fmt.get('ext', 'mp3')
                    
                    # 对于音频，保留有文件大小信息的格式
                    if filesize and filesize > 0:
                        format_info = VideoFormat(
                            format_id=fmt.get('format_id', ''),
                            resolution=quality_desc,  # 对于音频，用质量代替分辨率
                            ext=ext,
                            filesize=filesize,
                            quality=quality_desc,
                            fps=None,
                            vcodec=None,
                            acodec=fmt.get('acodec')
                        )
                        formats.append(format_info)
            except Exception as format_error:
                print(f"Error processing format {fmt.get('format_id', 'unknown')}: {format_error}")
                continue
        
        # 去重并按分辨率排序
        unique_formats = {}
        for fmt in formats:
            key = (fmt.resolution, fmt.ext)
            if key not in unique_formats or (fmt.filesize and fmt.filesize > (unique_formats[key].filesize or 0)):
                unique_formats[key] = fmt
        
        # 按分辨率排序（从高到低）
        sorted_formats = sorted(
            unique_formats.values(),
            key=lambda x: int(re.findall(r'\d+', x.resolution)[0]) if re.findall(r'\d+', x.resolution) else 0,
            reverse=True
        )
        
        print(f"Processed {len(sorted_formats)} unique formats after filtering")
        
        # 如果没有找到符合条件的格式，提供一些提示
        if not sorted_formats:
            print("No formats found matching criteria (MP4 with known file size)")
            print("Trying fallback: allowing other video formats with known file size")
            
            # 备选逻辑：允许其他视频格式，但仍要求有文件大小
            fallback_formats = []
            for fmt in raw_formats:
                try:
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):
                        resolution = f"{fmt.get('height')}p"
                        filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                        ext = fmt.get('ext', 'mp4')
                        
                        # 放宽条件：允许常见的视频格式，但仍要求有文件大小
                        if ext in ['mp4', 'webm', 'mkv', 'avi'] and filesize and filesize > 0:
                            format_info = VideoFormat(
                                format_id=fmt.get('format_id', ''),
                                resolution=resolution,
                                ext=ext,
                                filesize=filesize,
                                quality=fmt.get('format_note', resolution),
                                fps=fmt.get('fps'),
                                vcodec=fmt.get('vcodec'),
                                acodec=fmt.get('acodec')
                            )
                            fallback_formats.append(format_info)
                except Exception as e:
                    continue
            
            if fallback_formats:
                # 去重并排序备选格式
                fallback_unique = {}
                for fmt in fallback_formats:
                    key = (fmt.resolution, fmt.ext)
                    if key not in fallback_unique or (fmt.filesize and fmt.filesize > (fallback_unique[key].filesize or 0)):
                        fallback_unique[key] = fmt
                
                sorted_formats = sorted(
                    fallback_unique.values(),
                    key=lambda x: int(re.findall(r'\d+', x.resolution)[0]) if re.findall(r'\d+', x.resolution) else 0,
                    reverse=True
                )
                print(f"Found {len(sorted_formats)} fallback formats")
            else:
                print("No suitable video formats found even with fallback")
        
        # 确保数据类型正确
        duration_value = duration
        if duration_value is not None:
            try:
                duration_value = float(duration_value)
            except (ValueError, TypeError):
                duration_value = None
        
        return VideoInfo(
            title=title,
            duration=duration_value,
            uploader=uploader,
            thumbnail=thumbnail,
            formats=sorted_formats
        )
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Request timeout")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse video information")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/downloads", response_model=DownloadResponse, status_code=202)
async def start_download(request: DownloadRequest):
    """
    在后台启动一个新的下载任务。
    
    这个端点会立即返回一个任务ID，客户端可以使用这个ID来查询下载状态。
    """
    # `.delay()` 是启动Celery任务的关键，它会将任务发送到队列中。
    task = download_video_task.delay(
        video_url=request.url, 
        download_type=request.download_type,
        custom_path=request.custom_path
    )
    return {"task_id": task.id, "status": "pending"}

@app.get("/downloads/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    检索下载任务的状态和结果。
    """
    # 使用任务ID从Celery后端获取任务结果对象。
    task_result = AsyncResult(task_id, app=celery_app)
    
    result = task_result.result
    # 如果任务失败，结果会是一个Exception对象，我们需要将它转换为字符串以便JSON序列化。
    if isinstance(task_result.result, Exception):
        result = str(task_result.result)

    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": result
    }

