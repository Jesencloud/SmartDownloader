# web/main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from celery.result import AsyncResult
from typing import Literal, Dict, Any, List, Optional, Union, Tuple
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import json
import asyncio
from cachetools import TTLCache, cached
import sys
import os
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
    version="1.0.0",
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
    download_type: Literal["video", "audio"] = Field(
        "video", description="The type of content to download."
    )
    format_id: str = Field(..., description="The specific format ID to download.")
    resolution: str = Field(
        "", description="The resolution of the video (e.g., '1080p60')."
    )
    title: str = Field("", description="The title of the video/audio.")


class CancelRequest(BaseModel):
    task_ids: List[str] = Field(..., description="A list of task IDs to cancel.")


class DownloadResponse(BaseModel):
    task_id: str = Field(..., description="The ID of the background download task.")
    status: str = Field("pending", description="The initial status of the task.")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Union[Dict[str, Any], str]] = Field(
        None, description="Task result or error message."
    )


class VideoFormat(BaseModel):
    format_id: str
    resolution: str
    ext: str
    filesize: Optional[float]
    filesize_is_approx: bool = False
    quality: str
    vcodec: Optional[str]
    acodec: Optional[str]
    abr: Optional[int] = None
    needs_merge: bool = Field(
        default=False, description="Indicates if this format requires merging."
    )
    is_complete_stream: bool = Field(
        default=False,
        description="Indicates if this format contains both video and audio.",
    )
    supports_browser_download: bool = Field(
        default=False,
        description="Indicates if this format supports direct browser download.",
    )


class VideoInfo(BaseModel):
    title: str
    duration: Optional[float]
    uploader: Optional[str]
    thumbnail: Optional[str]
    formats: List[VideoFormat]
    original_url: str
    download_type: Literal["video", "audio"]


class VideoInfoRequest(BaseModel):
    url: str = Field(..., description="Video URL to analyze")
    download_type: Literal["video", "audio"] = Field("video")


# --- Helper Functions with Caching ---


def get_ytdlp_binary_path() -> Path:
    """
    Get the correct yt-dlp binary path based on the operating system.

    Returns:
        Path: The path to the appropriate yt-dlp binary
    """
    system = platform.system().lower()

    if system == "darwin":  # macOS
        binary_name = "yt-dlp_macos"
    elif system == "linux":
        binary_name = "yt-dlp_linux"
    elif system == "windows":
        binary_name = "yt-dlp.exe"
    else:
        # Fallback to generic name for other systems
        binary_name = "yt-dlp"

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
            "--socket-timeout",
            "30",
            url,
        ]
        process = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=True
        )
        return json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        # Raise standard exceptions to be handled by the endpoint
        raise TimeoutError("Request to video service timed out.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to get video info: yt-dlp returned an error. Stderr: {e.stderr}"
        )
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
    # --- URL安全验证 ---
    is_valid, error_msg = validate_url_security(request.url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {error_msg}")

    # --- Whitelist Enforcement ---
    allowed_domains = config.security.allowed_domains
    if allowed_domains:  # Only check if the list is not empty
        try:
            parsed_url = urlparse(request.url)
            domain = parsed_url.netloc.lower()

            # Check if the domain or any of its parent domains are in the whitelist
            # e.g., 'music.youtube.com' should match 'youtube.com'
            is_allowed = any(
                domain.endswith(allowed_domain) for allowed_domain in allowed_domains
            )

            if not is_allowed:
                raise HTTPException(
                    status_code=403,  # 403 Forbidden is appropriate here
                    detail=f"Downloads from '{parsed_url.netloc}' are not allowed. Only downloads from the following sites are permitted: {', '.join(allowed_domains)}",
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
            video_data_raw = await loop.run_in_executor(
                None, fetch_video_info_sync, request.url
            )

    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected internal server error occurred: {str(e)}",
        )

    # --- Process the raw data (this part is unchanged) ---
    title = video_data_raw.get("title", "Unknown Title")
    duration = video_data_raw.get("duration")
    uploader = video_data_raw.get("uploader")
    thumbnail = video_data_raw.get("thumbnail")

    formats = []
    raw_formats = video_data_raw.get("formats", [])

    if request.download_type == "video":
        # --- NEW: Unified video format processing logic ---
        all_possible_formats = []

        # Part 1: Process pre-merged (complete) MP4 formats with improved Unknown/Null codec support
        complete_formats_raw = []
        for f in raw_formats:
            if (
                f.get("ext") == "mp4" and f.get("width") and f.get("height")
            ):  # 必须有分辨率信息
                vcodec = f.get("vcodec")
                acodec = f.get("acodec")

                # 包含以下情况：
                # 1. 明确的编解码器（非none）
                # 2. unknown编解码器（通常是完整流）
                # 3. null编解码器但有分辨率（X.com等平台的完整流）
                # 4. 排除明确标记为单一类型的流
                if (
                    (
                        vcodec not in ("none", None, "")
                        and acodec not in ("none", None, "")
                    )
                    or (vcodec == "unknown" and acodec == "unknown")
                    or (vcodec is None and acodec is None)
                ):  # 处理null编解码器的完整流
                    # 排除明确标记为单一类型的流
                    if vcodec != "audio only" and acodec != "video only":
                        complete_formats_raw.append(f)
        for c_fmt in complete_formats_raw:
            filesize = c_fmt.get("filesize") or c_fmt.get("filesize_approx")
            is_approx = not c_fmt.get("filesize") and c_fmt.get("filesize_approx")
            all_possible_formats.append(
                VideoFormat(
                    format_id=c_fmt.get("format_id", ""),
                    resolution=f"{c_fmt.get('width')}x{c_fmt.get('height')}",
                    ext="mp4",
                    filesize=filesize,
                    filesize_is_approx=bool(is_approx),
                    quality=f"{c_fmt.get('height')}p",
                    vcodec=c_fmt.get("vcodec"),
                    acodec=c_fmt.get("acodec"),
                    needs_merge=False,
                    is_complete_stream=True,  # Complete stream with both video and audio
                    supports_browser_download=True,  # MP4 complete streams support direct download
                )
            )

        # Part 2: Process formats that need merging into MP4
        video_only_formats = [
            f
            for f in raw_formats
            if f.get("vcodec") not in ("none", None)
            and f.get("acodec") in ("none", None)
            and f.get("width")
            and f.get("height")
        ]
        audio_only_formats = [
            f
            for f in raw_formats
            if f.get("acodec") not in ("none", None)
            and f.get("vcodec") in ("none", None)
        ]

        if video_only_formats and audio_only_formats:
            best_audio_to_merge = max(audio_only_formats, key=lambda f: f.get("abr", 0))

            for v_fmt in video_only_formats:
                video_size = v_fmt.get("filesize") or v_fmt.get("filesize_approx") or 0
                audio_size = (
                    best_audio_to_merge.get("filesize")
                    or best_audio_to_merge.get("filesize_approx")
                    or 0
                )
                total_size = video_size + audio_size

                video_is_approx = not v_fmt.get("filesize") and v_fmt.get(
                    "filesize_approx"
                )
                audio_is_approx = not best_audio_to_merge.get(
                    "filesize"
                ) and best_audio_to_merge.get("filesize_approx")
                total_is_approx = bool(video_is_approx or audio_is_approx)

                all_possible_formats.append(
                    VideoFormat(
                        format_id=f"{v_fmt['format_id']}+{best_audio_to_merge['format_id']}",
                        resolution=f"{v_fmt.get('width')}x{v_fmt.get('height')}",
                        ext="mp4",  # Merged format will be mp4
                        filesize=total_size if total_size > 0 else None,
                        filesize_is_approx=total_is_approx,
                        quality=f"{v_fmt.get('height')}p (需合并)",
                        vcodec=v_fmt.get("vcodec"),
                        acodec=best_audio_to_merge.get("acodec"),
                        needs_merge=True,
                        is_complete_stream=False,  # Needs merging, so not a complete stream by itself
                        supports_browser_download=False,  # Merged formats need processing, can't be directly downloaded
                    )
                )

        # Part 3: Group by resolution and select the best by filesize
        formats_by_resolution = {}
        for fmt in all_possible_formats:
            if fmt.resolution not in formats_by_resolution:
                formats_by_resolution[fmt.resolution] = []
            formats_by_resolution[fmt.resolution].append(fmt)

        final_formats = []
        for resolution, fmt_group in formats_by_resolution.items():
            best_in_group = max(fmt_group, key=lambda f: f.filesize or 0)
            final_formats.append(best_in_group)

        # Part 4: Sort the final list by resolution height (descending)
        final_formats.sort(
            key=lambda f: int(f.resolution.split("x")[1]) if "x" in f.resolution else 0,
            reverse=True,
        )

        formats = final_formats

    elif request.download_type == "audio":
        # For audio requests, find all valid audio streams and select the single best one.
        candidate_audio_formats = []
        for fmt in raw_formats:
            has_resolution = fmt.get("width") and fmt.get("height")
            is_special_audio = fmt.get("vcodec") == "audio only"
            has_abr = fmt.get("abr")

            if is_special_audio or (not has_resolution and has_abr):
                candidate_audio_formats.append(fmt)

        if candidate_audio_formats:
            # Per user request, select the best format based on ABR (audio bitrate) to ensure highest quality.
            best_audio_format_raw = max(
                candidate_audio_formats, key=lambda f: f.get("abr") or 0
            )

            # Create a single, standardized VideoFormat object for the frontend
            abr = best_audio_format_raw.get("abr")
            filesize = best_audio_format_raw.get(
                "filesize"
            ) or best_audio_format_raw.get("filesize_approx")
            is_approx = not best_audio_format_raw.get(
                "filesize"
            ) and best_audio_format_raw.get("filesize_approx")
            quality_desc = (
                f"{int(abr)}k"
                if abr
                else best_audio_format_raw.get("format_note", "Unknown")
            )

            formats.append(
                VideoFormat(
                    format_id=best_audio_format_raw.get("format_id", ""),
                    resolution=quality_desc,
                    ext=best_audio_format_raw.get("ext"),
                    filesize=filesize,
                    filesize_is_approx=bool(is_approx),
                    quality=quality_desc,
                    vcodec=None,  # CRITICAL: Standardize to None for the frontend
                    acodec=best_audio_format_raw.get("acodec"),
                    abr=int(abr) if abr else None,
                    is_complete_stream=False,  # Audio only streams are not complete
                    supports_browser_download=True,  # Audio formats generally support direct download
                )
            )

    return VideoInfo(
        title=title,
        duration=float(duration) if duration else None,
        uploader=uploader,
        thumbnail=thumbnail,
        formats=formats,
        original_url=request.url,
        download_type=request.download_type,
    )


def validate_url_security(url: str) -> Tuple[bool, str]:
    """
    验证URL的安全性

    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "URL cannot be empty"

    url = url.strip()

    # 长度限制
    if len(url) > 2048:
        return False, "URL too long (max 2048 characters)"

    # 安全协议检查
    dangerous_protocols = [
        "javascript:",
        "data:",
        "file:",
        "ftp:",
        "mailto:",
        "tel:",
        "sms:",
        "vbscript:",
        "about:",
        "chrome:",
        "chrome-extension:",
        "moz-extension:",
        "ms-appx:",
        "x-javascript:",
    ]

    url_lower = url.lower()
    for protocol in dangerous_protocols:
        if url_lower.startswith(protocol):
            return False, f"Dangerous protocol not allowed: {protocol}"

    # XSS防护
    import re

    dangerous_patterns = [
        r"<script[^>]*>",
        r"</script>",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<link[^>]*>",
        r"<meta[^>]*>",
        r"on\w+\s*=",  # 事件处理器
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return False, "URL contains dangerous characters or tags"

    # 检查空字节和换行符
    if "\x00" in url or "\r" in url or "\n" in url:
        return False, "URL contains dangerous characters or tags"

    # URL格式验证和SSRF防护
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # 只允许HTTP/HTTPS
        if parsed.scheme not in ["http", "https"]:
            return False, "Only HTTP and HTTPS protocols are allowed"

        # 防止SSRF攻击
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid hostname"

        hostname_lower = hostname.lower()

        # 禁止本地地址
        forbidden_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]

        if hostname_lower in forbidden_hosts:
            return False, "Access to local addresses is not allowed"

        # 检查内网IP段
        import ipaddress

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, "Access to private network addresses is not allowed"
        except ValueError:
            # 不是IP地址，是域名，继续检查
            pass

        # 检查端口安全性
        if parsed.port:
            dangerous_ports = [
                22,
                23,
                25,
                53,
                110,
                143,
                993,
                995,
                1433,
                3306,
                5432,
                6379,
                27017,
            ]
            if parsed.port in dangerous_ports:
                return False, f"Access to port {parsed.port} is not allowed"

    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"

    return True, ""


def validate_format_id(format_id: str) -> Tuple[bool, str]:
    """
    验证格式ID的安全性和有效性

    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    if not format_id or not format_id.strip():
        return False, "Format ID cannot be empty"

    # 防止路径遍历和注入攻击
    dangerous_patterns = [
        "../",  # 路径遍历
        "..\\",  # Windows路径遍历
        "<",
        ">",
        '"',
        "'",
        "\\",  # HTML/JS注入字符
        "\x00",  # 空字节
        "\r",
        "\n",  # 换行符
        ";",
        "&",
        "|",
        "`",
        "$",  # 命令注入字符
    ]

    for pattern in dangerous_patterns:
        if pattern in format_id:
            return False, f"Format ID contains dangerous characters: {pattern}"

    # 长度限制
    if len(format_id) > 100:
        return False, "Format ID too long (max 100 characters)"

    # 只允许字母、数字、连字符、下划线和加号
    import re

    if not re.match(r"^[a-zA-Z0-9_+-]+$", format_id):
        return (
            False,
            "Format ID contains invalid characters (only alphanumeric, _, +, - allowed)",
        )

    return True, ""


@app.post("/downloads", response_model=DownloadResponse, status_code=202)
async def start_download(request: DownloadRequest):
    # 验证URL安全性
    url_valid, url_error = validate_url_security(request.url)
    if not url_valid:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {url_error}")

    # 验证格式ID
    format_valid, format_error = validate_format_id(request.format_id)
    if not format_valid:
        raise HTTPException(
            status_code=400, detail=f"Invalid format ID: {format_error}"
        )

    # 验证下载类型
    if request.download_type not in ["video", "audio"]:
        raise HTTPException(
            status_code=400, detail="Invalid download type. Must be 'video' or 'audio'"
        )

    task = download_video_task.delay(
        video_url=request.url,
        download_type=request.download_type,
        format_id=request.format_id,
        resolution=request.resolution,
        title=request.title,
    )
    return {"task_id": task.id, "status": "pending"}


@app.get("/download-stream")
async def download_stream(
    request: Request,
    url: str,
    download_type: str,
    format_id: str,
    resolution: str,
    title: str,
    audio_format: str = "mp3",  # 添加音频格式参数，默认为mp3保持向后兼容
):
    log.info(
        f"Stream download request: {url}, format_id: {format_id}, type: {download_type}, resolution: '{resolution}', audio_format: {audio_format}"
    )

    # 验证URL安全性
    url_valid, url_error = validate_url_security(url)
    if not url_valid:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {url_error}")

    # 验证格式ID
    format_valid, format_error = validate_format_id(format_id)
    if not format_valid:
        raise HTTPException(
            status_code=400, detail=f"Invalid format ID: {format_error}"
        )

    # 验证下载类型
    if download_type not in ["video", "audio"]:
        raise HTTPException(
            status_code=400, detail="Invalid download type. Must be 'video' or 'audio'"
        )

    try:

        async def stream_downloader():
            try:
                process = await asyncio.create_subprocess_exec(
                    str(get_ytdlp_binary_path()),
                    "-f",
                    format_id,
                    "--output",
                    "-",  # Stream to stdout
                    url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                async def log_stderr():
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        log.error(f"yt-dlp stderr: {line.decode().strip()}")

                stderr_logger_task = asyncio.create_task(log_stderr())

                # Track the process for cleanup
                active_processes = getattr(request.app.state, "active_processes", set())
                active_processes.add(process.pid)
                request.app.state.active_processes = active_processes

                try:
                    while True:
                        # More frequent disconnection check
                        if await request.is_disconnected():
                            log.warning(
                                "Client disconnected, terminating download process."
                            )
                            await terminate_process_tree(process)
                            break

                        try:
                            # Use asyncio.wait_for to add timeout for reads
                            chunk = await asyncio.wait_for(
                                process.stdout.read(8192), timeout=1.0
                            )
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

                    await stderr_logger_task  # Wait for stderr logger to finish
                    await process.wait()
                    log.info(
                        f"Process {process.pid} finished with code {process.returncode}."
                    )

            except Exception as e:
                log.error(f"Error in stream_downloader: {e}")
                raise e

        # 动态确定媒体类型和文件扩展名
        if download_type == "video":
            media_type = "video/mp4"
            file_extension = "mp4"
        else:
            # 根据音频格式确定正确的媒体类型
            audio_format_lower = audio_format.lower()
            if audio_format_lower == "m4a":
                media_type = "audio/mp4"  # m4a使用audio/mp4媒体类型
                file_extension = "m4a"
            elif audio_format_lower == "mp4":
                media_type = "audio/mp4"  # mp4音频也使用audio/mp4媒体类型
                file_extension = "mp4"
            elif audio_format_lower == "opus":
                media_type = "audio/opus"
                file_extension = "opus"
            elif audio_format_lower == "aac":
                media_type = "audio/aac"
                file_extension = "aac"
            elif audio_format_lower == "ogg":
                media_type = "audio/ogg"
                file_extension = "ogg"
            elif audio_format_lower == "webm":
                media_type = "audio/webm"
                file_extension = "webm"
            elif audio_format_lower == "flac":
                media_type = "audio/flac"
                file_extension = "flac"
            elif audio_format_lower == "wav":
                media_type = "audio/wav"
                file_extension = "wav"
            elif audio_format_lower == "mp3":
                media_type = "audio/mp3"
                file_extension = "mp3"
            else:
                # 未识别格式使用mp3作为默认值，但添加日志以便调试
                log.warning(f"未识别的音频格式: {audio_format}，使用mp3作为默认值")
                media_type = "audio/mp3"
                file_extension = "mp3"

        # 添加详细的格式映射日志
        if download_type == "audio":
            log.info(f"音频格式映射: {audio_format} → {media_type} | .{file_extension}")

        # Sanitize title for filename - improved to handle Chinese and Unicode characters
        def sanitize_filename(title_str):
            """改进的文件名清理函数，使用配置文件中的长度限制"""
            if not title_str:
                return ""

            # 只移除文件系统绝对不支持的字符，保留其他所有字符
            # Windows/MacOS/Linux 都不支持的字符
            forbidden_chars = {
                "<": "＜",  # 替换为全角字符
                ">": "＞",
                ":": "：",
                '"': '"',
                "/": "／",
                "\\": "＼",
                "|": "｜",
                "?": "？",
                "*": "＊",
            }

            for forbidden, replacement in forbidden_chars.items():
                title_str = title_str.replace(forbidden, replacement)

            # 只移除控制字符（保留换行符和制表符转为空格）
            title_str = "".join(
                " " if char in "\n\t\r" else char
                for char in title_str
                if ord(char) >= 32 or char in "\n\t\r"
            )

            # 清理多余的空格但保留标点
            title_str = " ".join(title_str.split())  # 合并多个空格为一个
            title_str = title_str.strip()  # 只移除首尾空格

            # 使用配置文件中的长度限制
            max_length = config.file_processing.filename_max_length
            if len(title_str) > max_length:
                # 改进的截断策略：优先保留前面的内容，因为通常标题的前半部分更重要
                suffix = config.file_processing.filename_truncate_suffix

                # 计算可用的主要内容长度
                available_length = max_length - len(suffix)

                if available_length > 20:  # 确保有足够空间保留有意义的内容
                    # 尝试在合适的位置截断（句号、问号、感叹号等）
                    truncate_chars = [
                        "。",
                        "！",
                        "？",
                        ".",
                        "!",
                        "?",
                        "】",
                        ")",
                        "]",
                        "；",
                        ";",
                    ]
                    truncated = False

                    # 在可用长度的80%-100%范围内寻找截断点
                    search_start = int(available_length * 0.8)
                    for i in range(available_length, search_start, -1):
                        if i < len(title_str) and title_str[i] in truncate_chars:
                            title_str = title_str[: i + 1] + suffix
                            truncated = True
                            break

                    if not truncated:
                        # 如果没找到合适的标点截断点，尝试在空格处截断
                        truncate_at = available_length
                        if " " in title_str[:truncate_at]:
                            # 找到最后一个空格位置
                            last_space = title_str.rfind(" ", 0, truncate_at)
                            if last_space > available_length * 0.7:  # 确保不会截断太多
                                title_str = title_str[:last_space] + suffix
                            else:
                                title_str = title_str[:available_length] + suffix
                        else:
                            title_str = title_str[:available_length] + suffix
                else:
                    # 如果配置的长度过短，强制截断
                    title_str = title_str[:available_length] + suffix

            return title_str

        clean_title = sanitize_filename(title)

        # 添加文件名处理日志
        log.info(
            f"文件名处理: '{title}' → '{clean_title}' (max_length: {config.file_processing.filename_max_length})"
        )

        # If the cleaned title is empty or too short, use a default
        if not clean_title or len(clean_title) < 2:
            clean_title = "video" if download_type == "video" else "audio"
            log.info(f"使用默认文件名: '{clean_title}'")

        # Create a safe filename - unified format for both video and audio
        if download_type == "video":
            # 视频文件包含分辨率，格式：标题_分辨率.扩展名
            log.info(f"视频下载 - 分辨率参数: '{resolution}', 标题: '{clean_title}'")
            filename = f"{clean_title}_{resolution}.{file_extension}"
        else:
            # 音频文件不包含分辨率，格式：标题.扩展名
            log.info(f"音频下载 - 标题: '{clean_title}'")
            filename = f"{clean_title}.{file_extension}"

        log.info(f"生成完整文件名: '{filename}'")

        # 使用RFC 6266标准处理Unicode文件名
        import urllib.parse

        # 对文件名进行URL编码以支持Unicode字符
        encoded_filename = urllib.parse.quote(filename, safe="")

        # 创建符合RFC 6266的Content-Disposition头
        # 改进的ASCII备用文件名生成策略
        def create_ascii_safe_filename(original_filename):
            """为包含Unicode字符的文件名创建ASCII兼容的备用文件名"""
            # 分离文件名和扩展名
            name_part = original_filename
            ext_part = ""
            if "." in original_filename:
                name_part = original_filename.rsplit(".", 1)[0]
                ext_part = "." + original_filename.rsplit(".", 1)[1]

            # 策略1: 尽可能保留ASCII字符和数字
            import re

            # 提取所有ASCII字母、数字、基本符号和空格
            ascii_pattern = r"[a-zA-Z0-9\s\-_\(\)\[\]&+\.\,\!\?]+"
            ascii_parts = re.findall(ascii_pattern, name_part)

            if ascii_parts:
                # 合并所有ASCII部分
                ascii_combined = "".join(ascii_parts).strip()
                # 清理多余的空格和符号
                ascii_combined = re.sub(r"\s+", " ", ascii_combined)  # 合并空格
                ascii_combined = re.sub(r"[-_]{2,}", "-", ascii_combined)  # 合并连字符
                ascii_combined = ascii_combined.strip(" -_")  # 移除首尾的空格和符号

                # 检查是否有足够的有意义内容
                meaningful_chars = re.sub(r"[\s\-_\(\)\[\]]+", "", ascii_combined)
                if len(meaningful_chars) >= 3:  # 至少3个有意义的字符
                    # 控制ASCII文件名长度，但比原来更宽松
                    max_ascii_length = 50  # 最多50字符
                    if len(ascii_combined) > max_ascii_length:
                        # 尝试在单词边界截断
                        truncated = ascii_combined[:max_ascii_length]
                        if " " in truncated:
                            truncated = truncated.rsplit(" ", 1)[0]
                        ascii_combined = truncated

                    if ascii_combined and len(ascii_combined) >= 3:
                        log.info(f"ASCII备用文件名策略1成功: 提取到 '{ascii_combined}'")
                        return ascii_combined + ext_part

            # 策略2: 回退到通用文件名
            if download_type == "video":
                fallback_name = f"video_{resolution}"
            else:
                fallback_name = "audio"

            log.info(f"ASCII备用文件名策略2: 通用名称回退 '{fallback_name}'")
            return fallback_name + ext_part

        # 检查文件名是否包含非ASCII字符
        try:
            filename.encode("ascii")
            # 如果编码成功，说明都是ASCII字符，直接使用
            safe_filename = filename
            log.info(f"文件名为纯ASCII字符，直接使用: '{safe_filename}'")
        except UnicodeEncodeError:
            # 包含非ASCII字符，生成ASCII兼容的备用文件名
            safe_filename = create_ascii_safe_filename(filename)
            log.info(
                f"文件名包含Unicode字符，生成ASCII备用: '{filename}' → '{safe_filename}'"
            )

        # 构建完整的Content-Disposition头，支持Unicode
        content_disposition = f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded_filename}"

        log.info(f"HTTP文件名头部: {content_disposition}")

        return StreamingResponse(
            stream_downloader(),
            media_type=media_type,
            headers={
                "Content-Disposition": content_disposition,
                "Cache-Control": "no-cache",
            },
        )

    except Exception as e:
        log.error(f"Error in download_stream endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Stream download failed: {str(e)}")


@app.get("/download-direct")
async def download_direct():
    """
    Direct download endpoint for complete streams that support browser downloads.
    This endpoint is used for formats with is_complete_stream=True and supports_browser_download=True.
    """
    return {
        "status": "Direct download endpoint is available",
        "description": "This endpoint supports direct downloads for complete video streams.",
    }


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
                log.warning(
                    f"Process {process.pid} didn't terminate gracefully, force killing"
                )
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


@app.get("/debug/task/{task_id}")
async def debug_task_status(task_id: str):
    """Debug endpoint to examine task status in detail"""
    task_result = AsyncResult(task_id, app=celery_app)

    debug_info = {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result,
        "info": getattr(task_result, "info", None),
        "result_type": str(type(task_result.result)),
        "backend": str(task_result.backend),
        "traceback": getattr(task_result, "traceback", None),
        "successful": task_result.successful(),
        "failed": task_result.failed(),
        "ready": task_result.ready(),
        "state": task_result.state,
    }

    return JSONResponse(content=debug_info)


@app.get("/downloads/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    result = task_result.result

    # 添加详细调试信息
    # log.info(f"=== TASK STATUS DEBUG ===")
    # log.info(f"Task ID: {task_id}")
    # log.info(f"Task status: {task_result.status}")
    # log.info(f"Task result type: {type(task_result.result)}")
    # log.info(f"Task result: {task_result.result}")
    # log.info(f"Task info: {getattr(task_result, 'info', 'No info')}")
    # log.info(f"========================")

    # Handle different result types
    if isinstance(task_result.result, Exception):
        result = str(task_result.result)
    elif task_result.status == "SUCCESS":
        # For successful tasks, check if result is available, otherwise use meta
        if result and isinstance(result, dict) and "relative_path" in result:
            # Use the actual result if it contains file info
            pass
        elif (
            hasattr(task_result, "info")
            and task_result.info
            and isinstance(task_result.info, dict)
        ):
            # Use meta info if it contains the file information
            result = task_result.info
        else:
            # Fallback to whatever result we have
            if not result:
                result = {"status": "Completed"}
    elif (
        task_result.status in ["PENDING", "PROGRESS"]
        and hasattr(task_result, "info")
        and task_result.info
    ):
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
        celery_app.control.revoke(
            task_id, terminate=True, signal="SIGKILL"
        )  # Use SIGKILL for force termination
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
        "cleanup_result": cleanup_result,
    }


async def cleanup_active_processes():
    """
    Clean up any active streaming download processes.
    """
    try:
        active_processes = getattr(app.state, "active_processes", set())
        for (
            pid
        ) in active_processes.copy():  # Use copy to avoid modification during iteration
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
    cleanup_stats = {"cleaned_files": [], "total_size_mb": 0, "errors": []}

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
                    cleanup_stats["errors"].append(
                        f"Failed to delete {file_path.name}: {str(e)}"
                    )
                    log.warning(f"Failed to delete {file_path}: {e}")

        cleanup_stats["total_size_mb"] = round(total_size / (1000 * 1000), 2)

        if cleanup_stats["cleaned_files"]:
            log.info(
                f"Cleaned up {len(cleanup_stats['cleaned_files'])} files ({cleanup_stats['total_size_mb']}MB)"
            )

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

        log.info(
            f"Current tasks - Active: {active_count}, Scheduled: {scheduled_count}, Reserved: {reserved_count}"
        )

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
                if (
                    isinstance(value, dict)
                    and key in source
                    and isinstance(source[key], dict)
                ):
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

        # First try direct path (could be just filename or relative path)
        file_path = Path(config.downloader.save_path) / decoded_file_name

        if file_path.exists() and file_path.is_file():
            pass  # File found directly
        else:
            # If not found directly, search for the filename in the download directory and subdirectories
            download_folder = Path(config.downloader.save_path)
            found_file = None

            if download_folder.exists():
                # Search recursively for the file
                for file_candidate in download_folder.rglob("*"):
                    if (
                        file_candidate.is_file()
                        and file_candidate.name == decoded_file_name
                    ):
                        found_file = file_candidate
                        break

                # If still not found, try case-insensitive search
                if not found_file:
                    for file_candidate in download_folder.rglob("*"):
                        if (
                            file_candidate.is_file()
                            and file_candidate.name.lower() == decoded_file_name.lower()
                        ):
                            found_file = file_candidate
                            break

                if found_file:
                    file_path = found_file
                else:
                    log.error(
                        f"File '{decoded_file_name}' not found in {download_folder}"
                    )
                    raise HTTPException(
                        status_code=404, detail=f"File '{decoded_file_name}' not found."
                    )
            else:
                log.error(f"Download directory does not exist: {download_folder}")
                raise HTTPException(
                    status_code=404, detail="Download directory not found."
                )

        # Generate proper filename for download
        clean_filename = file_path.name

        # Final file validation
        final_size = file_path.stat().st_size
        if final_size == 0:
            log.error(f"File has zero size: {file_path}")
            raise HTTPException(status_code=500, detail="File is empty or corrupted")

        if not os.access(file_path, os.R_OK):
            log.error(f"File is not readable: {file_path}")
            raise HTTPException(status_code=500, detail="File permission denied")

        # Detect media type based on extension
        media_type = "application/octet-stream"
        if file_path.suffix.lower() == ".mp4":
            media_type = "video/mp4"
        elif file_path.suffix.lower() == ".mp3":
            media_type = "audio/mpeg"

        headers = {
            "Content-Disposition": f'attachment; filename="{clean_filename}"',
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD",
            "Access-Control-Allow-Headers": "*",
            "Content-Length": str(final_size),
        }

        # Handle HEAD request - return headers only
        if request.method == "HEAD":
            from fastapi import Response

            return Response(headers=headers, media_type=media_type)

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
                    "Access-Control-Allow-Headers": "*",
                },
            )

            # Explicitly set content length
            response.headers["Content-Length"] = str(final_size)
            return response

        except Exception as e:
            log.error(f"Error creating FileResponse: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to serve file: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error serving file '{file_name}': {e}")
        raise HTTPException(
            status_code=500, detail="Internal server error while serving file."
        )


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
        raise HTTPException(
            status_code=500, detail=f"Error clearing downloads: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
