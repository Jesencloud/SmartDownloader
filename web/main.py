# web/main.py
import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union
from urllib.parse import urlparse

import psutil
from cachetools import TTLCache, cached
from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config_manager import config_manager
from core.command_builder import CommandBuilder
from core.format_analyzer import FormatAnalyzer

from .celery_app import celery_app
from .tasks import download_video_task


def get_unified_audio_formats(raw_formats):
    """
    统一的音频格式获取函数，确保视频模式和音频模式使用相同的音频格式列表
    """
    # 使用与视频模式相同的音频格式筛选逻辑
    audio_only_formats = [
        f for f in raw_formats if f.get("acodec") not in ("none", None) and f.get("vcodec") in ("none", None)
    ]

    # 如果没有明确的audio-only格式，使用更广泛的音频格式筛选
    if not audio_only_formats:
        audio_only_formats = [
            f
            for f in raw_formats
            if (
                # 条件A: 有有效的音频编解码器
                (f.get("acodec") not in ("none", None, "video only"))
                or
                # 条件B: 特殊情况 - resolution明确标记为audio only
                f.get("resolution") == "audio only"
                or
                # 条件C: format_id包含audio关键词
                "audio" in str(f.get("format_id", "")).lower()
            )
            and (
                # 确保不是视频格式
                not (f.get("width") and f.get("height"))
            )
        ]

    return audio_only_formats


def select_best_audio_with_analyzer(raw_formats):
    """
    使用FormatAnalyzer选择最佳音频格式的统一函数
    """
    # 获取统一的音频格式列表
    audio_formats = get_unified_audio_formats(raw_formats)

    if not audio_formats:
        return None

    # 使用FormatAnalyzer进行智能音频选择
    analyzer = FormatAnalyzer()

    # 将原始格式转换为FormatInfo对象
    from core.format_analyzer import FormatInfo, StreamType

    audio_format_infos = []
    for audio_fmt in audio_formats:
        audio_format_infos.append(
            FormatInfo(
                format_id=audio_fmt.get("format_id"),
                ext=audio_fmt.get("ext"),
                vcodec=audio_fmt.get("vcodec"),
                acodec=audio_fmt.get("acodec"),
                width=audio_fmt.get("width"),
                height=audio_fmt.get("height"),
                filesize=audio_fmt.get("filesize"),
                tbr=audio_fmt.get("tbr"),
                vbr=audio_fmt.get("vbr"),
                abr=audio_fmt.get("abr"),
                stream_type=StreamType.AUDIO_ONLY,
                raw_format=audio_fmt,
            )
        )

    # 使用智能算法选择最佳音频流
    best_audio_info = analyzer._select_best_audio_format(audio_format_infos)
    return best_audio_info.raw_format


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

# 专门的视频信息缓存，用于在视频和音频请求间共享数据
video_info_cache = TTLCache(maxsize=512, ttl=3600)  # 1小时缓存

# --- Pydantic Models ---


class DownloadRequest(BaseModel):
    url: str = Field(..., description="The URL of the video to download.")
    download_type: Literal["video", "audio"] = Field("video", description="The type of content to download.")
    format_id: str = Field(..., description="The specific format ID to download.")
    resolution: str = Field("", description="The resolution of the video (e.g., '1080p60').")
    title: str = Field("", description="The title of the video/audio.")


class CancelRequest(BaseModel):
    task_ids: List[str] = Field(..., description="A list of task IDs to cancel.")


class DownloadResponse(BaseModel):
    task_id: str = Field(..., description="The ID of the background download task.")
    status: str = Field("pending", description="The initial status of the task.")


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Union[Dict[str, Any], str]] = Field(None, description="Task result or error message.")


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
    needs_merge: bool = Field(default=False, description="Indicates if this format requires merging.")
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


def get_cached_video_info(url: str, download_type: str = "all") -> Optional[dict]:
    """
    智能获取缓存的视频信息，支持跨类型共享

    Args:
        url: 视频URL
        download_type: 请求类型 ("video", "audio", "all")

    Returns:
        缓存的视频信息，如果没有缓存则返回None
    """
    # 先检查完整信息缓存（download_type="all"）
    full_cache_key = f"{url}:all"
    if full_cache_key in video_info_cache:
        log.info(f"命中完整视频信息缓存: {url}")
        return video_info_cache[full_cache_key]

    # 如果请求音频，检查是否有视频缓存可以复用
    if download_type == "audio":
        video_cache_key = f"{url}:video"
        if video_cache_key in video_info_cache:
            log.info(f"音频请求复用视频缓存: {url}")
            return video_info_cache[video_cache_key]

    # 如果请求视频，检查是否有音频缓存可以复用
    if download_type == "video":
        audio_cache_key = f"{url}:audio"
        if audio_cache_key in video_info_cache:
            log.info(f"视频请求复用音频缓存: {url}")
            return video_info_cache[audio_cache_key]

    # 检查当前请求类型的缓存
    current_cache_key = f"{url}:{download_type}"
    if current_cache_key in video_info_cache:
        log.info(f"命中当前类型缓存: {url}:{download_type}")
        return video_info_cache[current_cache_key]

    return None


def set_video_info_cache(url: str, download_type: str, video_info: dict):
    """
    设置视频信息缓存

    Args:
        url: 视频URL
        download_type: 请求类型
        video_info: 视频信息数据
    """
    cache_key = f"{url}:{download_type}"
    video_info_cache[cache_key] = video_info
    log.debug(f"设置视频信息缓存: {cache_key}")


@cached(cache)
def fetch_video_info_sync(url: str, download_type: str = "all") -> dict:
    """
    This is a SYNCHRONOUS and BLOCKING function that fetches video info.
    Its results are cached by @cached. It should be run in a thread.

    Args:
        url: Video URL to fetch info for
        download_type: "video", "audio", or "all" to optimize parsing speed
    """
    try:
        # 检测播放列表URL
        if is_playlist_url(url):
            raise ValueError("Playlists are not supported. Please enter a single video link.")

        cmd = [
            str(get_ytdlp_binary_path()),
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--socket-timeout",
            "20",  # 减少超时时间从30s到20s
        ]

        # 优化：根据下载类型跳过不必要的解析步骤来提升速度
        if download_type == "audio":
            # 音频模式：跳过缩略图、字幕和其他视频相关内容解析
            cmd.extend(
                [
                    "--skip-download",
                    "--no-write-thumbnail",
                    "--no-write-subs",
                    "--no-write-auto-subs",
                    "--no-write-description",  # 跳过描述
                    "--no-write-annotations",  # 跳过注释
                ]
            )
        elif download_type == "video":
            # 视频模式：跳过字幕但保留缩略图，跳过部分不必要内容
            cmd.extend(
                [
                    "--skip-download",
                    "--no-write-subs",
                    "--no-write-auto-subs",
                    "--no-write-annotations",  # 跳过注释
                ]
            )
        # download_type == "all" 时使用默认设置

        # 添加缓存优化
        cmd.extend(
            [
                "--no-call-home"  # 禁用调用主页功能
            ]
        )

        cmd.append(url)

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45,
            check=True,  # 减少总超时时间
        )
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


@app.get("/service-worker.js", response_class=FileResponse)
async def get_service_worker():
    return FileResponse(BASE_DIR / "static" / "service-worker.js", media_type="application/javascript")


@app.post("/video-info", response_model=VideoInfo)
async def get_video_info(request: VideoInfoRequest):
    """
    Fetches video information using a cached, thread-safe helper function.
    支持智能缓存共享，视频和音频请求可以复用已缓存的数据。
    """
    # --- URL安全验证 ---
    is_valid, error_msg = validate_url_security(request.url)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {error_msg}")

    # --- Whitelist Enforcement ---
    allowed_domains = config_manager.config.security.allowed_domains
    if allowed_domains:  # Only check if the list is not empty
        try:
            parsed_url = urlparse(request.url)
            domain = parsed_url.netloc.lower()
        except Exception:
            # If URL parsing fails, let it proceed. yt-dlp will handle the invalid URL.
            # We log this as a warning for debugging purposes.
            log.warning(f"Could not parse URL '{request.url}' for domain validation. Skipping whitelist check.")
            domain = None  # Ensure domain is None if parsing fails

        if domain:  # Only proceed with the check if domain parsing was successful
            # Check if the domain or any of its parent domains are in the whitelist
            # e.g., 'music.youtube.com' should match 'youtube.com'
            is_allowed = any(domain.endswith(allowed_domain) for allowed_domain in allowed_domains)

            if not is_allowed:
                raise HTTPException(
                    status_code=403,  # 403 Forbidden is appropriate here
                    detail=f"Downloads from '{parsed_url.netloc}' are not permitted by the current configuration.",
                )
    # --- End of Whitelist Enforcement ---

    try:
        # 首先尝试从智能缓存获取数据
        cached_data = get_cached_video_info(request.url, request.download_type)

        if cached_data:
            log.info(f"使用缓存的视频信息: {request.url} ({request.download_type})")
            video_data_raw = cached_data
        else:
            # 缓存未命中，获取新数据
            log.info(f"缓存未命中，获取新的视频信息: {request.url} ({request.download_type})")

            # Run the synchronous, cached function in a separate thread to avoid
            # blocking the main FastAPI event loop.
            # Provide backward compatibility for Python < 3.9
            if sys.version_info >= (3, 9):
                video_data_raw = await asyncio.to_thread(fetch_video_info_sync, request.url, request.download_type)
            else:
                loop = asyncio.get_running_loop()
                video_data_raw = await loop.run_in_executor(
                    None, fetch_video_info_sync, request.url, request.download_type
                )

            # 将新获取的数据保存到智能缓存
            set_video_info_cache(request.url, request.download_type, video_data_raw)

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

    # 优化：根据下载类型提前过滤格式，减少后续处理开销
    if request.download_type == "video":
        # 视频模式：保留视频格式和必要的音频格式（用于合并）
        original_count = len(video_data_raw.get("formats", []))

        # 第一步：保留视频格式和音频格式
        video_audio_formats = [
            f
            for f in raw_formats
            if (
                # 保留有视频内容的格式
                f.get("vcodec") not in ("none", None, "audio only") or (f.get("width") and f.get("height"))
            )
            or (
                # 也保留纯音频格式（用于合并）
                f.get("acodec") not in ("none", None, "video only") and f.get("vcodec") in ("none", None, "audio only")
            )
        ]

        # 第二步：优先选择mp4相关格式，并在每个分辨率中选择文件大小最小的
        mp4_video_formats_raw = [
            f for f in video_audio_formats if f.get("ext") == "mp4" and f.get("width") and f.get("height")
        ]
        mp4_audio_formats = [
            f
            for f in video_audio_formats
            if f.get("ext") in ["mp4", "m4a"] and not (f.get("width") and f.get("height"))
        ]

        # 对mp4视频格式按分辨率分组，并在每组中选择文件大小最小的格式
        mp4_by_resolution = {}
        for fmt in mp4_video_formats_raw:
            resolution = f"{fmt.get('width')}x{fmt.get('height')}"
            if resolution not in mp4_by_resolution:
                mp4_by_resolution[resolution] = []
            mp4_by_resolution[resolution].append(fmt)

        # 按分辨率高低排序，只保留前3个最高分辨率进行处理
        def resolution_score(resolution_key):
            width, height = map(int, resolution_key.split("x"))
            return width * height

        # 获取前3个最高分辨率（按像素数量排序）
        top_resolutions = sorted(mp4_by_resolution.keys(), key=resolution_score, reverse=True)[:3]
        log.info(f"视频分辨率优化：从 {len(mp4_by_resolution)} 个不同分辨率中选择前3个最高分辨率: {top_resolutions}")

        # 为选中的分辨率选择文件大小最小的mp4格式
        mp4_video_formats = []
        for resolution in top_resolutions:
            formats = mp4_by_resolution[resolution]
            # 将格式分为有文件大小和无文件大小两组
            with_filesize = [f for f in formats if f.get("filesize") or f.get("filesize_approx")]
            without_filesize = [f for f in formats if not (f.get("filesize") or f.get("filesize_approx"))]

            if with_filesize:
                # 选择文件大小最小的格式
                best_format = min(
                    with_filesize,
                    key=lambda f: (f.get("filesize") or f.get("filesize_approx")),
                )
                mp4_video_formats.append(best_format)

                # 记录选择的格式信息
                filesize = best_format.get("filesize") or best_format.get("filesize_approx")
                log.info(
                    f"分辨率 {resolution} 选择最小文件大小的mp4格式: {best_format.get('format_id')} ({filesize / 1000000:.2f}MB)"
                )

                # 如果有其他被跳过的格式，记录日志
                if len(with_filesize) > 1:
                    skipped_formats = [f for f in with_filesize if f != best_format]
                    for skipped in skipped_formats:
                        skipped_size = skipped.get("filesize") or skipped.get("filesize_approx")
                        log.info(f"  跳过较大格式: {skipped.get('format_id')} ({skipped_size / 1000000:.2f}MB)")
            elif without_filesize:
                # 如果都没有文件大小信息，选择第一个
                mp4_video_formats.append(without_filesize[0])
                log.info(
                    f"分辨率 {resolution} 无文件大小信息，选择第一个mp4格式: {without_filesize[0].get('format_id')}"
                )

        if mp4_video_formats:
            # 如果有mp4视频格式，优先使用mp4格式 + 必要的音频格式
            raw_formats = mp4_video_formats + mp4_audio_formats
            # 如果没有mp4音频，添加最佳音频格式用于合并
            if not mp4_audio_formats:
                audio_formats = [
                    f
                    for f in video_audio_formats
                    if f.get("acodec") not in ("none", None, "video only")
                    and f.get("vcodec") in ("none", None, "audio only")
                ]
                if audio_formats:
                    best_audio = max(audio_formats, key=lambda f: f.get("abr", 0))
                    raw_formats.append(best_audio)

            log.info(f"视频模式优化：保留 {len(raw_formats)} 个优选mp4格式")
        else:
            # 如果没有mp4视频格式，使用所有视频和音频格式
            raw_formats = video_audio_formats
            log.info(f"视频模式混合：保留 {len(raw_formats)} 个格式")

    elif request.download_type == "audio":
        # 音频模式：优先保留高质量音频格式（m4a, aac, opus），过滤低质量格式
        original_count = len(video_data_raw.get("formats", []))

        # 第一步：只保留音频格式
        audio_formats = [
            f
            for f in raw_formats
            if (
                # 条件A: 有有效的音频编解码器（包括unknown作为特殊情况）
                (f.get("acodec") not in ("none", None, "video only"))
                or
                # 条件B: 特殊情况 - resolution明确标记为audio only
                f.get("resolution") == "audio only"
                or
                # 条件C: format_id包含audio关键词（如hls-audio-*）
                "audio" in str(f.get("format_id", "")).lower()
            )
            and (
                # 满足音频特征条件之一
                # 明确标记为仅音频的格式
                f.get("vcodec") in ("none", None, "audio only")
                or
                # 或者没有视频分辨率的格式
                (not f.get("width") or not f.get("height"))
                or
                # 或者是mp4格式的音频（某些网站的mp4音频可能有尺寸信息但实际是音频）
                (f.get("ext") == "mp4" and (not f.get("vcodec") or f.get("vcodec") == "unknown"))
                or
                # 或者是其他明确的音频格式
                (f.get("ext") in ["m4a", "aac", "opus", "mp3", "ogg", "webm"] and f.get("acodec"))
                or
                # 用户提示：resolution为audio only的是音频
                f.get("resolution") == "audio only"
                or
                # format_note包含audio关键词
                "audio" in str(f.get("format_note", "")).lower()
                or
                # format_id包含audio关键词（如hls-audio-*）
                "audio" in str(f.get("format_id", "")).lower()
            )
        ]

        log.info(f"音频模式: 从 {original_count} 个原始格式过滤到 {len(audio_formats)} 个音频格式")

        # Debug: 显示过滤后的音频格式分布
        if audio_formats:
            audio_ext_summary = {}
            for f in audio_formats:
                ext = f.get("ext", "unknown")
                audio_ext_summary[ext] = audio_ext_summary.get(ext, 0) + 1
            log.info(f"音频格式分布: {audio_ext_summary}")

        # 使用统一的音频选择函数，确保与视频模式选择一致
        best_audio_format = select_best_audio_with_analyzer(raw_formats)

        if best_audio_format:
            # 只保留统一选择的最佳音频流
            raw_formats = [best_audio_format]
            log.info(
                f"音频模式统一优化：使用与视频模式相同的智能选择算法，选择最佳音频流: {best_audio_format.get('format_id')} ({best_audio_format.get('ext')})"
            )
        else:
            # 如果没有优选格式，使用所有音频格式
            raw_formats = audio_formats
            log.info(f"音频模式保守：保留 {len(raw_formats)} 个音频格式")

    if request.download_type == "video":
        # --- NEW: Unified video format processing logic ---
        all_possible_formats = []

        # Part 1: Process pre-merged (complete) MP4 formats with improved Unknown/Null codec support
        complete_formats_raw = []
        for f in raw_formats:
            if f.get("ext") == "mp4" and f.get("width") and f.get("height"):  # 必须有分辨率信息
                vcodec = f.get("vcodec")
                acodec = f.get("acodec")

                # 包含以下情况：
                # 1. 明确的编解码器（非none）
                # 2. unknown编解码器（通常是完整流）
                # 3. null编解码器但有分辨率（X.com等平台的完整流）
                # 4. 排除明确标记为单一类型的流
                if (
                    (vcodec not in ("none", None, "") and acodec not in ("none", None, ""))
                    or (vcodec == "unknown" and acodec == "unknown")
                    or (vcodec is None and acodec is None)
                ):  # 处理null编解码器的完整流
                    # 排除明确标记为单一类型的流
                    if vcodec != "audio only" and acodec != "video only":
                        complete_formats_raw.append(f)

        for c_fmt in complete_formats_raw:
            filesize = c_fmt.get("filesize") or c_fmt.get("filesize_approx")
            is_approx = not c_fmt.get("filesize") and c_fmt.get("filesize_approx")

            # 如果mp4格式没有文件大小信息，尝试从同分辨率的其他格式获取估算值
            if filesize is None:
                width = c_fmt.get("width")
                height = c_fmt.get("height")

                # 查找相同分辨率的其他格式作为文件大小估算参考
                for alt_fmt in video_data_raw.get("formats", []):  # 使用原始未过滤的格式列表
                    if (
                        alt_fmt.get("width") == width
                        and alt_fmt.get("height") == height
                        and alt_fmt.get("format_id") != c_fmt.get("format_id")
                    ):
                        alt_filesize = alt_fmt.get("filesize") or alt_fmt.get("filesize_approx")
                        if alt_filesize:
                            filesize = alt_filesize
                            is_approx = True  # 标记为估算值
                            log.info(
                                f"mp4格式 {c_fmt.get('format_id')} 使用 {alt_fmt.get('format_id')} 的文件大小作为估算: {filesize / 1000000:.2f}MB"
                            )
                            break

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
            f for f in raw_formats if f.get("acodec") not in ("none", None) and f.get("vcodec") in ("none", None)
        ]

        if video_only_formats and audio_only_formats:
            # 使用统一的音频选择函数，确保与音频模式选择一致
            best_audio_to_merge = select_best_audio_with_analyzer(raw_formats)
            if not best_audio_to_merge:
                log.warning("统一音频选择失败，回退到简单选择")
                best_audio_to_merge = max(audio_only_formats, key=lambda f: f.get("abr", 0))

            for v_fmt in video_only_formats:
                video_size = v_fmt.get("filesize") or v_fmt.get("filesize_approx")
                audio_size = best_audio_to_merge.get("filesize") or best_audio_to_merge.get("filesize_approx")

                # 如果mp4视频格式没有文件大小，尝试从同分辨率的其他格式估算
                if video_size is None and v_fmt.get("ext") == "mp4":
                    width = v_fmt.get("width")
                    height = v_fmt.get("height")

                    # 查找相同分辨率的其他视频格式作为估算参考
                    # 优先级：mp4格式 > 其他格式
                    candidate_formats = []
                    for alt_fmt in video_data_raw.get("formats", []):  # 使用原始未过滤的格式列表
                        if (
                            alt_fmt.get("width") == width
                            and alt_fmt.get("height") == height
                            and alt_fmt.get("format_id") != v_fmt.get("format_id")
                            and alt_fmt.get("vcodec") not in ("none", None)
                        ):
                            alt_video_size = alt_fmt.get("filesize") or alt_fmt.get("filesize_approx")
                            if alt_video_size:
                                candidate_formats.append(
                                    {
                                        "format": alt_fmt,
                                        "size": alt_video_size,
                                        "is_mp4": alt_fmt.get("ext") == "mp4",
                                    }
                                )

                    if candidate_formats:
                        # 优先选择mp4格式，如果没有mp4则选择第一个可用的格式
                        mp4_candidates = [c for c in candidate_formats if c["is_mp4"]]
                        if mp4_candidates:
                            # 如果有mp4格式，选择第一个mp4格式
                            best_candidate = mp4_candidates[0]
                        else:
                            # 如果没有mp4格式，选择第一个可用格式
                            best_candidate = candidate_formats[0]

                        video_size = best_candidate["size"]
                        chosen_format = best_candidate["format"]
                        format_type = "mp4同格式" if best_candidate["is_mp4"] else f"{chosen_format.get('ext')}格式"
                        log.info(
                            f"mp4视频格式 {v_fmt.get('format_id')} 使用 {chosen_format.get('format_id')} 的文件大小作为估算({format_type}): {video_size / 1000000:.2f}MB"
                        )

                # 只有当视频和音频都有文件大小时才计算总大小
                if video_size is not None and audio_size is not None:
                    total_size = video_size + audio_size
                    # 计算是否为估算大小
                    video_is_approx = not v_fmt.get("filesize") and (
                        v_fmt.get("filesize_approx")
                        or video_size != (v_fmt.get("filesize") or v_fmt.get("filesize_approx"))
                    )
                    audio_is_approx = not best_audio_to_merge.get("filesize") and best_audio_to_merge.get(
                        "filesize_approx"
                    )
                    total_is_approx = bool(video_is_approx or audio_is_approx)
                else:
                    # 如果任一格式没有文件大小信息，总大小设为None
                    total_size = None
                    total_is_approx = False

                all_possible_formats.append(
                    VideoFormat(
                        format_id=v_fmt["format_id"],  # 只使用视频format_id，让FormatAnalyzer智能选择音频
                        resolution=f"{v_fmt.get('width')}x{v_fmt.get('height')}",
                        ext="mp4",  # Merged format will be mp4
                        filesize=total_size if total_size is not None else None,
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
            # 改进选择逻辑：优先选择有文件大小的格式，然后按文件大小排序
            # 将格式分为有文件大小和无文件大小两组
            with_filesize = [f for f in fmt_group if f.filesize is not None]
            without_filesize = [f for f in fmt_group if f.filesize is None]

            if with_filesize:
                # 如果有文件大小信息的格式，选择文件大小最大的
                best_in_group = max(with_filesize, key=lambda f: f.filesize)
            elif without_filesize:
                # 如果都没有文件大小信息，选择第一个（通常是complete stream优先）
                best_in_group = without_filesize[0]
            else:
                # 理论上不应该到这里，但为了安全起见
                best_in_group = fmt_group[0]

            final_formats.append(best_in_group)

        # Part 4: Sort the final list by resolution height (descending)
        final_formats.sort(
            key=lambda f: int(f.resolution.split("x")[1]) if "x" in f.resolution else 0,
            reverse=True,
        )

        formats = final_formats

    elif request.download_type == "audio":
        # For audio requests, use the intelligent audio selection from earlier
        if len(raw_formats) == 1:
            # We have already selected the best audio format using FormatAnalyzer
            best_audio_format_raw = raw_formats[0]
            log.info(f"使用智能选择的音频格式: {best_audio_format_raw.get('format_id')}")
        elif len(raw_formats) > 1:
            # Fallback: if we have multiple formats (shouldn't happen with smart selection), choose the best by ABR
            log.warning(f"意外情况：有 {len(raw_formats)} 个音频格式，使用ABR选择最佳")
            best_audio_format_raw = max(raw_formats, key=lambda f: f.get("abr") or 0)
        else:
            # No audio formats available
            log.error("没有可用的音频格式")
            raise HTTPException(status_code=400, detail="No suitable formats found")

        # Create a single, standardized VideoFormat object for the frontend
        abr = best_audio_format_raw.get("abr")
        filesize = best_audio_format_raw.get("filesize") or best_audio_format_raw.get("filesize_approx")
        is_approx = not best_audio_format_raw.get("filesize") and best_audio_format_raw.get("filesize_approx")
        quality_desc = f"{int(abr)}k" if abr else best_audio_format_raw.get("format_note", "Unknown")

        formats = [
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
        ]

    return VideoInfo(
        title=title,
        duration=float(duration) if duration else None,
        uploader=uploader,
        thumbnail=thumbnail,
        formats=formats,
        original_url=request.url,
        download_type=request.download_type,
    )


def is_playlist_url(url: str) -> bool:
    """
    检测URL是否为播放列表

    Args:
        url: 要检测的URL

    Returns:
        bool: 如果是播放列表URL返回True，否则返回False
    """
    import re
    from urllib.parse import parse_qs, urlparse

    try:
        parsed_url = urlparse(url.lower())
        query_params = parse_qs(parsed_url.query)

        # YouTube播放列表检测
        if "youtube.com" in parsed_url.netloc or "youtu.be" in parsed_url.netloc:
            # 检查是否有播放列表参数
            if "list" in query_params:
                return True
            # 检查URL路径是否包含播放列表标识
            if "/playlist" in parsed_url.path:
                return True

        # Bilibili播放列表检测
        if "bilibili.com" in parsed_url.netloc:
            # 检查是否为播放列表/合集页面
            if re.search(r"/video/[^/]+\?p=\d+", url):  # 分P视频
                return True
            if "/medialist/" in parsed_url.path:  # 播放列表
                return True
            if "/favlist/" in parsed_url.path:  # 收藏夹
                return True

        # 其他平台的通用播放列表检测
        playlist_indicators = [
            "playlist",
            "album",
            "collection",
            "series",
            "set",
            "channel",
            "user/",
            "/c/",
            "/channel/",
        ]

        for indicator in playlist_indicators:
            if indicator in parsed_url.path.lower():
                return True

        return False

    except Exception:
        # 如果URL解析失败，保守处理，返回False
        return False


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
        raise HTTPException(status_code=400, detail=f"Invalid format ID: {format_error}")

    # 验证下载类型
    if request.download_type not in ["video", "audio"]:
        raise HTTPException(status_code=400, detail="Invalid download type. Must be 'video' or 'audio'")

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
    audio_format: str = "mp3",
    filesize: Optional[int] = None,
):
    log.info(
        f"Stream download request: {url}, format_id: {format_id}, type: {download_type}, resolution: '{resolution}', audio_format: {audio_format}, filesize: {filesize}"
    )

    # --- Security Validations ---
    url_valid, url_error = validate_url_security(url)
    if not url_valid:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {url_error}")

    format_valid, format_error = validate_format_id(format_id)
    if not format_valid:
        raise HTTPException(status_code=400, detail=f"Invalid format ID: {format_error}")

    if download_type not in ["video", "audio"]:
        raise HTTPException(status_code=400, detail="Invalid download type. Must be 'video' or 'audio'")

    # --- Range Request Handling ---
    import re

    range_header = request.headers.get("range")
    total_size = filesize if filesize and filesize > 0 else None
    status_code = 200
    start = 0
    end = total_size - 1 if total_size is not None else None
    byte_range_tuple = None

    # --- Filename and Content-Type setup ---
    if download_type == "video":
        media_type = "video/mp4"
        file_extension = "mp4"
    else:
        audio_format_lower = audio_format.lower()
        format_map = {
            "m4a": ("audio/mp4", "m4a"),
            "mp4": ("audio/mp4", "mp4"),
            "opus": ("audio/opus", "opus"),
            "aac": ("audio/aac", "aac"),
            "ogg": ("audio/ogg", "ogg"),
            "webm": ("audio/webm", "webm"),
            "flac": ("audio/flac", "flac"),
            "wav": ("audio/wav", "wav"),
            "mp3": ("audio/mp3", "mp3"),
        }
        media_type, file_extension = format_map.get(audio_format_lower, ("audio/mp3", "mp3"))
        if media_type == "audio/mp3" and audio_format_lower != "mp3":
            log.warning(f"Unrecognized audio format: {audio_format}, defaulting to mp3")

    clean_title = sanitize_filename(title, download_type)
    if download_type == "video":
        filename = f"{clean_title}_{resolution}.{file_extension}"
    else:
        filename = f"{clean_title}.{file_extension}"

    encoded_filename, safe_filename = create_safe_filenames(filename, download_type, resolution)
    content_disposition = f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{encoded_filename}"

    # --- Prepare Headers ---
    headers = {
        "Content-Disposition": content_disposition,
        "Cache-Control": "no-cache",
        "Accept-Ranges": "bytes",
    }

    if range_header and total_size:
        range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))

            # Corrected Logic: Only treat as partial content if the start byte is greater than 0
            if start > 0:
                status_code = 206
                end_str = range_match.group(2)
                end = int(end_str) if end_str else total_size - 1

                if start >= total_size or end >= total_size or start > end:
                    raise HTTPException(status_code=416, detail="Range Not Satisfiable")

                length = (end - start) + 1
                headers["Content-Length"] = str(length)
                headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
                byte_range_tuple = (start, end)
                log.info(f"Serving partial content for resumption: bytes {start}-{end} of {total_size}")
            else:
                # If start is 0, it's a new download. Ignore the range header and send a 200 OK.
                log.info("Range header starts at 0, treating as a full download request.")
                # Keep status_code = 200, do not set Content-Length or Content-Range
        else:
            log.warning(f"Malformed Range header: {range_header}. Serving full file.")

    # For any full download (status_code == 200), we don't set Content-Length.
    # The server will automatically use Transfer-Encoding: chunked.
    if status_code == 200:
        log.info(f"Serving full content with chunked encoding (estimated size: {total_size or 'unknown'})")

    # --- Streamer Definition ---
    async def stream_downloader():
        import shutil
        import uuid

        # 1. 创建唯一的临时目录
        base_temp_dir = Path(config_manager.config.downloader.temp_path)
        unique_temp_dir = base_temp_dir / str(uuid.uuid4())
        process = None  # 确保process变量在finally块中可用

        try:
            unique_temp_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"为下载创建了唯一的临时目录: {unique_temp_dir}")

            # 2. 构建并执行命令
            command_builder = CommandBuilder()
            cmd = command_builder.build_streaming_download_cmd_to_stdout(
                url, format_spec=format_id, byte_range=byte_range_tuple, temp_dir_path=str(unique_temp_dir)
            )
            log.info(f"Executing streaming command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(unique_temp_dir),  # 设置子进程工作目录为临时目录，避免在web目录生成--Frag*文件
            )

            async def log_stderr():
                while True:
                    chunk = await process.stderr.read(1024)
                    if not chunk:
                        break
                    log.warning(f"yt-dlp stderr: {chunk.decode(errors='ignore').strip()}")

            stderr_logger_task = asyncio.create_task(log_stderr())

            # 3. 流式传输数据
            try:
                while True:
                    if await request.is_disconnected():
                        log.warning("Client disconnected, terminating download process.")
                        process.terminate()
                        break
                    chunk = await process.stdout.read(65536)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if process and process.returncode is None:
                    process.terminate()
                    await process.wait()

                stderr_logger_task.cancel()
                try:
                    await stderr_logger_task
                except asyncio.CancelledError:
                    log.debug("Stderr logger task was correctly cancelled.")

                log.info(f"yt-dlp process finished with exit code {process.returncode if process else 'N/A'}")

        finally:
            # 4. 强制清理唯一的临时目录
            if unique_temp_dir.exists():
                shutil.rmtree(unique_temp_dir, ignore_errors=True)
                log.info(f"已强制清理临时目录: {unique_temp_dir}")

    # --- Return Final Response ---
    try:
        return StreamingResponse(
            stream_downloader(),
            media_type=media_type,
            headers=headers,
            status_code=status_code,
        )
    except Exception as e:
        log.error(f"Error in download_stream endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Stream download failed: {str(e)}")


def sanitize_filename(title_str: str, download_type: str) -> str:
    if not title_str:
        return ""
    import re

    title_str = re.sub(r"https?://[^\s]+", "", title_str)
    forbidden_chars = {
        "<": "",
        ">": "",
        ":": "",
        '"': "",
        "/": "",
        "\\": "",
        "|": "",
        "?": "",
        "*": "",
        "【": "",
        "】": "",
        "（": "(",
        "）": ")",
    }
    for forbidden, replacement in forbidden_chars.items():
        title_str = title_str.replace(forbidden, replacement)
    title_str = "".join(" " if char in "\n\t\r" else char for char in title_str if ord(char) >= 32 or char in "\n\t\r")
    title_str = " ".join(title_str.split()).strip()
    title_str = re.sub(r"[-_\s]{2,}", " ", title_str).strip()
    if not title_str or len(title_str.strip()) < 2:
        return "video" if download_type == "video" else "audio"
    max_length = config_manager.config.file_processing.filename_max_length
    if len(title_str) > max_length:
        suffix = config_manager.config.file_processing.filename_truncate_suffix
        available_length = max_length - len(suffix)
        if available_length > 10:
            if " " in title_str[:available_length]:
                last_space = title_str.rfind(" ", 0, available_length)
                title_str = (
                    title_str[: last_space if last_space > available_length * 0.7 else available_length] + suffix
                )
            else:
                title_str = title_str[:available_length] + suffix
        else:
            title_str = title_str[:available_length] + suffix
    return title_str


def create_safe_filenames(original_filename: str, download_type: str, resolution: str) -> Tuple[str, str]:
    import urllib.parse

    encoded_filename = urllib.parse.quote(original_filename, safe="")

    try:
        original_filename.encode("ascii")
        return encoded_filename, original_filename
    except UnicodeEncodeError:
        name_part, ext_part = os.path.splitext(original_filename)
        import re

        ascii_pattern = r"[a-zA-Z0-9\s\-_\(\)\[\]&+\.\,\!\?]+"
        ascii_parts = re.findall(ascii_pattern, name_part)
        if ascii_parts:
            ascii_combined = "".join(ascii_parts).strip()
            ascii_combined = re.sub(r"\s+", " ", ascii_combined)
            ascii_combined = re.sub(r"[-_]{2,}", "-", ascii_combined).strip(" -_")
            meaningful_chars = re.sub(r"[\s\-_\(\)\[\]]+", "", ascii_combined)
            if len(meaningful_chars) >= 3:
                max_ascii_length = 50
                if len(ascii_combined) > max_ascii_length:
                    truncated = ascii_combined[:max_ascii_length]
                    if " " in truncated:
                        truncated = truncated.rsplit(" ", 1)[0]
                    ascii_combined = truncated
                if ascii_combined and len(ascii_combined) >= 3:
                    return encoded_filename, ascii_combined + ext_part

        fallback_name = f"video_{resolution}" if download_type == "video" else "audio"
        return encoded_filename, fallback_name + ext_part


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

    # 安全地获取任务结果和状态，避免异常信息解析错误
    try:
        result = task_result.result
        status = task_result.status
    except (ValueError, KeyError) as e:
        # 处理 Celery 异常信息解析错误
        log.error(f"Failed to get task result for {task_id}: {e}")
        try:
            status = task_result.status
        except (ValueError, KeyError):
            status = "FAILURE"

        if status == "FAILURE":
            # 对于失败的任务，尝试从其他来源获取错误信息
            try:
                result = getattr(task_result, "info", None) or str(e)
            except (ValueError, KeyError):
                result = str(e)
        else:
            result = None

    # 安全地获取任务info信息
    task_info = None
    try:
        task_info = task_result.info if hasattr(task_result, "info") else None
    except (ValueError, KeyError):
        task_info = None

    # 添加详细调试信息
    # log.info("=== TASK STATUS DEBUG ===")
    # log.info(f"Task ID: {task_id}")
    log.debug(f"Task status: {status}")  # 改为DEBUG级别，减少日志冗余
    # log.info(f"Task result type: {type(result)}")
    # log.info(f"Task result: {result}")
    # log.info(f"Task info: {task_info}")
    # log.info("========================")

    # Handle different result types
    if isinstance(result, Exception):
        result = str(result)
    elif status == "SUCCESS":
        # For successful tasks, check if result is available, otherwise use meta
        if result and isinstance(result, dict) and "relative_path" in result:
            # Use the actual result if it contains file info
            pass
        elif task_info and isinstance(task_info, dict):
            # Use meta info if it contains the file information
            result = task_info
        else:
            # Fallback to whatever result we have
            if not result:
                result = {"status": "Completed"}
    elif status in ["PENDING", "PROGRESS"] and task_info:
        # For in-progress tasks, use the meta info
        result = task_info
    else:
        # For other cases, ensure we have a proper result format
        if not result:
            result = {"status": status}

    # 后备检查：如果状态是FAILURE，但Redis中有下载记录，可能是状态更新异常
    if status == "FAILURE":
        try:
            import redis

            redis_client = redis.Redis.from_url(config_manager.config.celery.broker_url, decode_responses=True)
            download_key = f"download:{task_id}"
            if redis_client.exists(download_key):
                file_info = redis_client.hgetall(download_key)
                if file_info and "relative_path" in file_info:
                    log.info(f"Found successful download in Redis despite FAILURE status: {task_id}")
                    # 覆盖状态和结果
                    status = "SUCCESS"
                    result = {
                        "status": "Completed",
                        "relative_path": file_info["relative_path"],
                        "file_size": int(file_info.get("file_size", 0)),
                        "download_folder": file_info.get("download_folder", ""),
                    }
        except Exception as redis_check_error:
            log.debug(f"Redis fallback check failed: {redis_check_error}")

    return {"task_id": task_id, "status": status, "result": result}


@app.post("/downloads/cancel", status_code=200)
async def cancel_downloads(request: CancelRequest):
    """
    Cancels one or more running download tasks and cleans up incomplete files.
    Enhanced with better process cleanup.
    """
    cancelled_tasks = []

    # 1. Revoke Celery tasks first
    for task_id in request.task_ids:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGKILL")  # Use SIGKILL for force termination
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
    cleanup_stats = {"cleaned_files": [], "total_size_mb": 0, "errors": []}

    try:
        download_folder = Path(config_manager.config.downloader.save_path)
        if not download_folder.exists():
            return cleanup_stats

        # 从配置中读取清理模式
        incomplete_patterns = config_manager.config.downloader.cleanup_patterns

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

        cleanup_stats["total_size_mb"] = round(total_size / (1000 * 1000), 2)

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


@app.get("/config_manager.config")
async def get_config() -> Dict[str, Any]:
    """
    获取当前应用的主要配置项。
    返回一个可序列化为JSON的字典。
    """
    # 返回整个配置，或选择性返回关键部分
    # 这里我们返回整个配置，因为前端或客户端可能需要访问任何部分
    return config_manager.config.model_dump()


@app.post("/config_manager.config")
async def update_config(update_request: Dict[str, Any]):
    """
    更新并保存应用配置。
    支持部分更新，例如只更新 downloader.max_retries。
    """
    from config_manager import AppConfig, ValidationError, config_manager

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


@app.delete("/download/file/{task_id}")
async def delete_file_by_task_id(task_id: str):
    """
    通过任务ID立即删除文件并清理相关记录。
    这个接口支持delete按钮的立即删除功能。
    """
    # 在函数内部初始化 Redis 客户端
    import redis

    redis_client = redis.Redis.from_url(config_manager.config.celery.broker_url, decode_responses=True)

    download_key = f"download:{task_id}"

    try:
        # 1. 从 Redis 获取文件信息
        file_info = redis_client.hgetall(download_key)

        if not file_info:
            raise HTTPException(status_code=404, detail="下载记录不存在或已过期。")

        file_path_str = file_info.get("file_path")
        filename = file_info.get("filename", "unknown")

        if not file_path_str:
            raise HTTPException(status_code=500, detail="服务器内部错误：找不到文件路径记录。")

        file_path = Path(file_path_str)

        # 2. 删除文件（如果存在）
        file_deleted = False
        file_size = 0
        if file_path.is_file():
            try:
                file_size = file_path.stat().st_size
                file_path.unlink()
                file_deleted = True
                log.info(f"成功删除文件: {filename} ({file_size / (1024 * 1024):.2f}MB)")
            except Exception as e:
                log.error(f"删除文件失败: {filename} - {e}")
                raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")

        # 3. 清理 Redis 记录
        redis_deleted = redis_client.delete(download_key)

        # 4. 返回删除结果
        result = {
            "message": "文件删除成功",
            "task_id": task_id,
            "filename": filename,
            "file_deleted": file_deleted,
            "file_size_mb": round(file_size / (1024 * 1024), 2) if file_size > 0 else 0,
            "redis_record_deleted": bool(redis_deleted),
        }

        log.info(
            f"删除操作完成: 任务ID={task_id}, 文件={filename}, "
            f"文件删除={file_deleted}, Redis记录删除={bool(redis_deleted)}"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"删除文件时发生错误 (任务ID: {task_id}): {e}")
        raise HTTPException(status_code=500, detail=f"删除操作失败: {str(e)}")


@app.get("/download/file/{task_id}")
async def download_file_by_task_id(task_id: str):
    """
    通过任务ID提供文件下载。
    这是新的、有状态的下载接口。
    """
    # 在函数内部初始化 Redis 客户端
    import redis

    redis_client = redis.Redis.from_url(config_manager.config.celery.broker_url, decode_responses=True)

    download_key = f"download:{task_id}"

    # 1. 从 Redis 获取文件信息
    file_info = redis_client.hgetall(download_key)

    if not file_info:
        raise HTTPException(status_code=404, detail="下载链接已过期或无效。请重新发起下载。")

    file_path_str = file_info.get("file_path")
    filename = file_info.get("filename", "download")
    media_type = file_info.get("media_type", "application/octet-stream")

    if not file_path_str:
        raise HTTPException(status_code=500, detail="服务器内部错误：找不到文件路径记录。")

    file_path = Path(file_path_str)

    # 2. 安全检查：确保文件存在
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件已从服务器清理，请重新发起下载。")

    # 3. 使用 FileResponse 提供下载
    # FileResponse 会自动设置 Content-Disposition 和 Content-Type
    return FileResponse(path=file_path, filename=filename, media_type=media_type)


@app.get("/downloads/list", response_class=JSONResponse)
async def list_downloads():
    """
    Lists all downloaded files in the download directory.
    """
    download_path = Path(config_manager.config.downloader.save_path)
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
        file_path = Path(config_manager.config.downloader.save_path) / decoded_file_name

        if file_path.exists() and file_path.is_file():
            pass  # File found directly
        else:
            # If not found directly, search for the filename in the download directory and subdirectories
            download_folder = Path(config_manager.config.downloader.save_path)
            found_file = None

            if download_folder.exists():
                # Search recursively for the file
                for file_candidate in download_folder.rglob("*"):
                    if file_candidate.is_file() and file_candidate.name == decoded_file_name:
                        found_file = file_candidate
                        break

                # If still not found, try case-insensitive search
                if not found_file:
                    for file_candidate in download_folder.rglob("*"):
                        if file_candidate.is_file() and file_candidate.name.lower() == decoded_file_name.lower():
                            found_file = file_candidate
                            break

                if found_file:
                    file_path = found_file
                else:
                    log.error(f"File '{decoded_file_name}' not found in {download_folder}")
                    raise HTTPException(status_code=404, detail=f"File '{decoded_file_name}' not found.")
            else:
                log.error(f"Download directory does not exist: {download_folder}")
                raise HTTPException(status_code=404, detail="Download directory not found.")

        # --- Security Check: Path Traversal ---
        # Resolve both paths to their absolute form to prevent traversal attacks.
        download_dir_resolved = Path(config_manager.config.downloader.save_path).resolve()
        file_path_resolved = file_path.resolve()

        # Check if the resolved file path is within the download directory.
        # This is a robust way to prevent directory traversal.
        if not str(file_path_resolved).startswith(str(download_dir_resolved)):
            log.error(
                f"Path traversal attempt blocked. Requested file: '{file_name}', Resolved path: '{file_path_resolved}'"
            )
            raise HTTPException(status_code=403, detail="Access to the requested file is forbidden.")

        # Generate proper filename for download
        clean_filename = file_path.name
        # Security: Sanitize filename to prevent CRLF injection in headers.
        clean_filename = clean_filename.replace("\r", "").replace("\n", "")

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

        # Use a more explicit FileResponse config_manager.configuration
        try:
            response = FileResponse(
                path=file_path_resolved,
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
        from urllib.parse import unquote

        decoded_file_name = unquote(file_name)

        download_folder = Path(config_manager.config.downloader.save_path)
        file_path = download_folder / decoded_file_name

        # --- Security Check: Path Traversal ---
        download_dir_resolved = download_folder.resolve()
        file_path_resolved = file_path.resolve()

        if not str(file_path_resolved).startswith(str(download_dir_resolved)):
            log.error(
                f"Path traversal attempt blocked during delete. "
                f"Requested file: '{decoded_file_name}', Resolved path: '{file_path_resolved}'"
            )
            raise HTTPException(status_code=403, detail="Access to the requested file is forbidden.")

        if file_path_resolved.is_file():
            file_path_resolved.unlink()
            return {"message": f"File '{decoded_file_name}' deleted successfully."}
        else:
            raise HTTPException(status_code=404, detail="File not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")


@app.post("/downloads/clear_all", status_code=200)
async def clear_all_downloads():
    """
    Deletes all files in the download directory.
    """
    try:
        download_path = Path(config_manager.config.downloader.save_path)
        if not download_path.exists():
            return {"message": "Download directory not found."}

        for file_path in download_path.iterdir():
            if file_path.is_file():
                file_path.unlink()

        return {"message": "All downloaded files have been cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing downloads: {str(e)}")


# --- Catch-all route for SPA ---
# This must be the LAST route defined to avoid overriding other API endpoints.
@app.get("/{full_path:path}", response_class=FileResponse, include_in_schema=False)
async def catch_all_spa_route(full_path: str):
    """
    Catch-all route for SPA (Single Page Application) support.
    Returns index.html for any unmatched routes to handle client-side routing.
    """
    # Check if the path looks like a static file request that was missed
    if "." in full_path and full_path.split(".")[-1] in [
        "js",
        "css",
        "ico",
        "png",
        "jpg",
        "gif",
        "svg",
    ]:
        raise HTTPException(status_code=404, detail="Static file not found")

    # For all other paths, return index.html to support SPA routing
    return FileResponse(BASE_DIR / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn

    # 配置日志，减少访问日志的冗余输出
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False,  # 禁用访问日志
        log_level="warning",  # 只显示警告及以上级别的uvicorn日志
    )
