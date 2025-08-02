#!/usr/bin/env python3
"""
配置管理器模块
简化的配置管理器 - 保留验证功能但去掉环境复杂性
适合个人用户使用
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from rich.console import Console

# ==================== 配置模型定义 ====================


class BaseConfig(BaseModel):
    """基础配置类。

    为所有配置类提供公共的Pydantic配置选项。
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class FoldersConfig(BaseConfig):
    """文件夹配置类。

    管理下载文件夹路径、时间戳格式等文件夹相关设置。
    """

    base_download_folder: str = Field(default="downloads", description="基础下载目录")
    use_timestamp_folder: bool = Field(default=True, description="是否使用时间戳文件夹")
    timestamp_format: str = Field(default="%Y%m%d-%H%M%S", description="时间戳格式")
    custom_download_path: Optional[str] = Field(default=None, description="自定义下载路径")
    relative_to_script: bool = Field(default=True, description="是否相对于脚本路径")

    @field_validator("timestamp_format")
    def validate_timestamp_format(cls, v: str) -> str:
        try:
            datetime.now().strftime(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"无效的时间戳格式: '{v}' - {e}")
        return v


class DownloaderConfig(BaseConfig):
    """下载器配置"""

    save_path: str = Field(default="downloads", description="下载文件的保存目录")
    temp_path: str = Field(default="downloads/temp", description="下载流的临时文件目录")
    max_retries: int = Field(default=3, ge=0, le=10, description="最大重试次数")
    base_delay: float = Field(default=10.0, ge=0, description="基础延迟时间(秒)")
    max_delay: float = Field(default=300.0, ge=0, description="最大延迟时间(秒)")
    backoff_factor: float = Field(default=2.0, ge=1.0, description="退避因子")
    network_timeout: int = Field(default=60, gt=0, le=600, description="网络超时时间(秒)")

    stall_detection_time: int = Field(default=30, gt=0, description="停滞检测时间(秒)")
    stall_check_interval: int = Field(default=5, gt=0, description="停滞检查间隔(秒)")
    stall_threshold_count: int = Field(default=6, ge=0, description="停滞阈值计数")

    proxy_retry_base_delay: int = Field(default=30, ge=0, description="代理重试基础延迟(秒)")
    proxy_retry_increment: int = Field(default=10, ge=0, description="代理重试递增延迟(秒)")
    proxy_retry_max_delay: int = Field(default=120, ge=0, description="代理重试最大延迟(秒)")

    circuit_breaker_failure_threshold: int = Field(default=5, ge=1, le=20, description="熔断器失败阈值")
    circuit_breaker_timeout: int = Field(default=300, ge=60, le=3600, description="熔断器超时时间(秒)")

    # yt-dlp 下载命令配置
    ytdlp_video_format: str = Field(default="bestvideo", description="yt-dlp视频格式选择")
    ytdlp_audio_format: str = Field(default="bestaudio", description="yt-dlp音频格式选择")
    ytdlp_combined_format: str = Field(default="bestvideo+bestaudio/best", description="yt-dlp合并格式选择")
    ytdlp_merge_output_format: str = Field(default="mp4", description="yt-dlp合并输出格式")

    retry_patterns: List[str] = Field(
        default=[
            "HTTP Error 403: Forbidden",
            "HTTP Error 429",
            "HTTP Error 502",
            "HTTP Error 503",
            "HTTP Error 504",
            "Connection reset",
            "Connection timed out",
            "Network is unreachable",
            "Temporary failure",
            "fragment.*not found",
            "Unable to download.*fragment",
            "HTTP Error 5",
        ],
        description="重试模式列表",
    )

    proxy_patterns: List[str] = Field(
        default=[
            "Unable to connect to proxy",
            "Connection refused",
            "Proxy error",
            "NewConnectionError",
            "Failed to establish a new connection",
        ],
        description="代理错误模式列表",
    )

    cleanup_patterns: List[str] = Field(
        default=[
            "*.part",
            "*.temp",
            "*.ytdl",
            "*.tmp",
            "*.download",
            "*.partial",
            "*.f*",
        ],
        description="清理不完整下载文件的模式",
    )

    @field_validator("max_delay")
    def validate_max_delay(cls, v: float, info: ValidationInfo) -> float:
        if "base_delay" in info.data and v < info.data["base_delay"]:
            raise ValueError("最大延迟时间不能小于基础延迟时间")
        return v


class FileProcessingConfig(BaseConfig):
    """文件处理配置"""

    filename_max_length: int = Field(default=50, gt=0, le=255, description="文件名最大长度")
    filename_truncate_suffix: str = Field(default="...", description="文件名截断后缀")
    polite_wait_time: float = Field(default=3.0, ge=0, description="礼貌等待时间(秒)")

    media_extensions: List[str] = Field(
        default=[".mp4", ".avi", ".mkv", ".mov", ".mp3", ".wav", ".flac", ".m4a"],
        description="支持的媒体文件扩展名",
    )


class AISubtitlesConfig(BaseConfig):
    """人工智能字幕配置类。

    管理Whisper模型、翻译服务、字幕格式等AI相关设置。
    """

    whisper_model: str = Field(default="base.en", description="Whisper模型名称")
    whisper_device: str = Field(default="auto", description="Whisper设备")
    whisper_model_path: Optional[str] = Field(default=None, description="Whisper模型路径")

    source_language: str = Field(default="auto", description="源语言")
    translate_to_chinese: bool = Field(default=True, description="是否翻译为中文")
    translator_service: str = Field(default="google", description="翻译服务")

    translation_batch_size: int = Field(default=50, ge=1, le=200, description="翻译批次大小")
    translation_delay: float = Field(default=0.5, ge=0, description="翻译延迟(秒)")
    translation_max_retries: int = Field(default=3, ge=1, le=10, description="翻译最大重试次数")
    translation_timeout: int = Field(default=30, ge=5, le=120, description="翻译超时时间(秒)")

    subtitle_formats: List[str] = Field(default=["srt", "vtt"], description="字幕格式")


class LoggingConfig(BaseConfig):
    """日志配置"""

    level: str = Field(default="INFO", description="日志级别")
    log_filename: str = Field(default="downloader.log", description="日志文件名")

    console_keywords: List[str] = Field(
        default=["🚀 智能媒体下载", "🎉 全部任务完成", "📁 日志与所有文件保存在"],
        description="控制台关键词",
    )

    @field_validator("level")
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"日志级别必须是以下之一: {valid_levels}")
        return v.upper()


class UIConfig(BaseConfig):
    """UI配置"""

    progress_bar_width: Optional[int] = Field(default=None, ge=10, le=200, description="进度条宽度")
    show_transfer_speed: bool = Field(default=True, description="显示传输速度")
    show_time_remaining: bool = Field(default=True, description="显示剩余时间")
    show_detailed_errors: bool = Field(default=True, description="显示详细错误")
    show_network_status: bool = Field(default=True, description="显示网络状态")


class CookiesConfig(BaseConfig):
    """Cookies配置"""

    mode: str = Field(default="auto", description="Cookies获取方式")
    browser_type: str = Field(default="auto", description="浏览器类型")
    manual_cookies_file: str = Field(default="cookies.txt", description="手动cookies文件路径")
    auto_extract_enabled: bool = Field(default=True, description="是否启用自动提取")
    force_refresh: bool = Field(default=False, description="是否强制刷新cookies")

    # 缓存设置
    cache_enabled: bool = Field(default=True, description="是否启用cookies缓存")
    cache_file: str = Field(default="cookies.cache.txt", description="缓存文件路径")
    cache_duration_hours: int = Field(default=24, ge=1, le=168, description="缓存有效期（小时）")
    cache_check_interval: int = Field(default=1, ge=1, le=24, description="缓存检查间隔（小时）")

    @field_validator("mode")
    def validate_mode(cls, v: str) -> str:
        valid_modes = ["auto", "manual", "browser", "skip"]
        if v not in valid_modes:
            raise ValueError(f"Cookies获取方式必须是以下之一: {valid_modes}")
        return v

    @field_validator("browser_type")
    def validate_browser_type(cls, v: str) -> str:
        valid_browsers = ["auto", "chrome", "firefox", "edge", "safari"]
        if v not in valid_browsers:
            raise ValueError(f"浏览器类型必须是以下之一: {valid_browsers}")
        return v


class AdvancedConfig(BaseConfig):
    """高级配置"""

    ytdlp_extra_args: List[str] = Field(default=[], description="yt-dlp额外参数")

    connectivity_test_host: str = Field(default="8.8.8.8", description="连接测试主机")
    connectivity_test_port: int = Field(default=53, gt=0, le=65535, description="连接测试端口")
    connectivity_timeout: int = Field(default=5, gt=0, le=30, description="连接测试超时(秒)")

    proxy_test_url: str = Field(default="http://httpbin.org/ip", description="代理测试URL")
    proxy_test_timeout: int = Field(default=10, gt=0, le=60, description="代理测试超时(秒)")


class FileManagementConfig(BaseConfig):
    """文件管理配置"""

    redis_expiry_seconds: int = Field(default=3600, gt=0, le=86400, description="Redis记录过期时间（秒）")
    orphan_cleanup_seconds: int = Field(default=5400, gt=0, le=86400, description="孤立文件清理时间（秒）")
    cleanup_interval_seconds: int = Field(default=1800, gt=0, le=86400, description="定时清理频率（秒）")

    @field_validator("orphan_cleanup_seconds")
    def validate_orphan_cleanup_time(cls, v: int, info: ValidationInfo) -> int:
        if "redis_expiry_seconds" in info.data and v < info.data["redis_expiry_seconds"]:
            raise ValueError("孤立文件清理时间不能小于Redis记录过期时间")
        return v


class SecurityConfig(BaseConfig):
    """安全相关配置"""

    allowed_domains: List[str] = Field(
        default=[],
        description="允许下载的网站域名白名单。如果列表为空，则允许所有网站。",
    )


class CeleryConfig(BaseConfig):
    """Celery配置"""

    broker_url: str = Field(default="redis://localhost:6379/0", description="Celery消息代理URL")
    result_backend: str = Field(default="redis://localhost:6379/0", description="Celery结果后端URL")


class AppConfig(BaseConfig):
    """应用完整配置"""

    folders: FoldersConfig = Field(default_factory=FoldersConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    file_processing: FileProcessingConfig = Field(default_factory=FileProcessingConfig)
    ai_subtitles: AISubtitlesConfig = Field(default_factory=AISubtitlesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    cookies: CookiesConfig = Field(default_factory=CookiesConfig)
    advanced: AdvancedConfig = Field(default_factory=AdvancedConfig)
    file_management: FileManagementConfig = Field(default_factory=FileManagementConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)


# ==================== 配置管理器 ====================

console = Console()
log = logging.getLogger(__name__)


# ==================== 样式常量 ====================
STYLE_SUCCESS = "bold green"
STYLE_WARNING = "bold yellow"


class ConfigManager:
    """简化的配置管理器。

    负责加载、保存和管理应用程序配置，包括配置验证、
    错误处理和默认值回退。

    Attributes:
        config_file (Path): 配置文件路径。
        config (AppConfig): 当前加载的配置实例。
    """

    def __init__(self, config_file: str = "config.yaml"):
        """初始化配置管理器。

        Args:
            config_file (str): 配置文件路径，默认为"config.yaml"。
        """
        self.config_file = Path(config_file)
        self.config: AppConfig = self._load_config()

    def _load_config(self) -> AppConfig:
        """加载、验证并返回配置。

        Returns:
            AppConfig: 加载并验证后的配置实例。

        如果配置文件不存在或加载失败，将创建或返回默认配置。
        """
        if not self.config_file.exists():
            console.print(
                f"⚠️ 配置文件 {self.config_file} 不存在，将创建默认配置",
                style=STYLE_WARNING,
            )
            default_config = AppConfig()
            self.save_config(default_config)
            return default_config

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f) or {}

            app_config = AppConfig.model_validate(raw_config)
            console.print(f"✅ 配置文件加载并验证成功: {self.config_file}", style=STYLE_SUCCESS)
            return app_config

        except yaml.YAMLError as e:
            log.error(f"❌ 配置文件格式错误: {e}")
        except ValidationError as e:
            log.error("❌ 配置内容验证失败:")
            for error in e.errors():
                loc = ".".join(map(str, error["loc"]))
                log.error(f"  - {loc}: {error['msg']}")
        except (OSError, IOError, PermissionError) as e:
            log.error(f"❌ 无法访问配置文件 {self.config_file}: {e}")
        except Exception as e:
            log.error(f"❌ 加载配置文件时发生未知错误: {e}", exc_info=True)

        console.print("使用默认配置作为回退", style=STYLE_WARNING)
        return AppConfig()

    def save_config(self, config_data: AppConfig) -> None:
        """保存配置到文件。

        Args:
            config_data (AppConfig): 要保存的配置数据。
        """
        try:
            config_dict = config_data.model_dump(exclude_none=True)

            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    indent=2,
                    sort_keys=False,
                )  # 保持原有顺序

            console.print(f"✅ 配置已保存到: {self.config_file}", style=STYLE_SUCCESS)
        except (OSError, IOError, PermissionError) as e:
            log.error(f"❌ 无法写入配置文件 {self.config_file}: {e}")
        except yaml.YAMLError as e:
            log.error(f"❌ YAML序列化失败: {e}")
        except Exception as e:
            log.error(f"❌ 保存配置文件时发生未知错误: {e}", exc_info=True)

    def get_download_folder(self, script_path: Optional[Path] = None) -> Path:
        """根据配置创建并返回下载文件夹路径。

        Args:
            script_path (Optional[Path]): 脚本文件路径，用作相对路径的基准。

        Returns:
            Path: 创建好的下载文件夹路径。
        """
        if script_path is None:
            script_path = Path(__file__).parent

        base_folder = self._get_base_folder_path(script_path)

        # 添加时间戳文件夹
        final_folder = base_folder
        if self.config.folders.use_timestamp_folder:
            timestamp = datetime.now().strftime(self.config.folders.timestamp_format)
            final_folder = base_folder / timestamp

        return self._create_folder_with_fallback(final_folder)

    def _get_base_folder_path(self, script_path: Path) -> Path:
        """根据配置确定基础下载文件夹的路径。"""
        folders_config = self.config.folders
        if folders_config.custom_download_path:
            base_folder = Path(folders_config.custom_download_path)
            if not base_folder.is_absolute() and folders_config.relative_to_script:
                return script_path / folders_config.custom_download_path
            return base_folder

        base_folder_name = folders_config.base_download_folder
        if folders_config.relative_to_script:
            return script_path / base_folder_name

        return Path.cwd() / base_folder_name

    def _create_folder_with_fallback(self, folder_path: Path) -> Path:
        """尝试创建指定文件夹，如果失败则回退到备用文件夹。"""
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
            return folder_path
        except (OSError, PermissionError) as e:
            log.error(f"❌ 创建下载文件夹失败，权限不足: {e}")
        except Exception as e:
            log.error(f"❌ 创建下载文件夹时发生未知错误: {e}", exc_info=True)

        # 回退逻辑
        fallback_folder = Path.cwd() / datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            fallback_folder.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 使用备用文件夹: {fallback_folder}", style=STYLE_WARNING)
            return fallback_folder
        except Exception as fallback_error:
            log.critical(f"致命错误：无法创建任何文件夹: {fallback_error}")
            raise

    def reload_config(self) -> bool:
        """重新加载配置。

        Returns:
            bool: 如果重新加载成功返回True，否则返回False。
        """
        try:
            self.config = self._load_config()
            console.print("✅ 配置重新加载成功", style=STYLE_SUCCESS)
            return True
        except Exception as e:
            log.error(f"❌ 重新加载配置时发生未知错误: {e}", exc_info=True)
            return False


# 创建全局配置实例
config_manager = ConfigManager()
config = config_manager.config

# 导出符号
__all__ = ["ConfigManager", "config_manager", "config"]
