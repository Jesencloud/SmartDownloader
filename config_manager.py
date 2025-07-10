# config_manager.py

import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime
from rich.console import Console
from pydantic import BaseModel, Field, ValidationError, validator

console = Console()
log = logging.getLogger(__name__)

# --- Pydantic Models for Configuration ---

class FoldersConfig(BaseModel):
    base_download_folder: str = 'downloads'
    use_timestamp_folder: bool = True
    timestamp_format: str = '%Y%m%d-%H%M%S'
    custom_download_path: Optional[str] = None
    relative_to_script: bool = True

    @validator('timestamp_format')
    def validate_timestamp_format(cls, v):
        try:
            datetime.now().strftime(v)
        except (ValueError, TypeError):
            raise ValueError(f"无效的时间戳格式: '{v}'")
        return v

class DownloaderConfig(BaseModel):
    max_retries: int = Field(3, ge=0)
    base_delay: float = Field(10, ge=0)
    max_delay: float = Field(300, ge=0)
    backoff_factor: float = Field(2, ge=0)
    network_timeout: int = Field(60, gt=0)
    stall_detection_time: int = Field(30, gt=0)
    stall_check_interval: int = Field(5, gt=0)
    stall_threshold_count: int = Field(6, ge=0)
    proxy_retry_base_delay: int = Field(30, ge=0)
    proxy_retry_increment: int = Field(10, ge=0)
    proxy_retry_max_delay: int = Field(120, ge=0)
    circuit_breaker_failure_threshold: int = Field(5, ge=1) # 连续失败次数阈值
    circuit_breaker_timeout: int = Field(300, ge=1) # 熔断器打开后保持的时间（秒）
    retry_patterns: List[str] = [
        "HTTP Error 403: Forbidden", "HTTP Error 429", "HTTP Error 502",
        "HTTP Error 503", "HTTP Error 504", "Connection reset",
        "Connection timed out", "Network is unreachable", "Temporary failure",
        "fragment.*not found", "Unable to download.*fragment", "HTTP Error 5",
    ]
    proxy_patterns: List[str] = [
        "Unable to connect to proxy", "Connection refused", "Proxy error",
        "NewConnectionError", "Failed to establish a new connection",
    ]

class FileProcessingConfig(BaseModel):
    filename_max_length: int = Field(50, gt=0)
    filename_truncate_suffix: str = "..."
    polite_wait_time: float = Field(3, ge=0)
    cleanup_patterns: List[str] = ["*.part", "*.part-*", "*.ytdl", "*.tmp.*", "*.f*"]
    media_extensions: List[str] = ['.mp4', '.avi', '.mkv', '.mov', '.mp3', '.wav', '.flac']

class AISubtitlesConfig(BaseModel):
    whisper_model: str = 'base.en'
    whisper_device: str = 'auto'
    translate_to_chinese: bool = True
    translator_service: str = 'google'
    subtitle_formats: List[str] = ['srt', 'vtt']
    whisper_model_path: Optional[str] = None # 新增模型路径配置

class LoggingConfig(BaseModel):
    level: str = 'INFO'
    console_keywords: List[str] = [
        "🚀 智能媒体下载",
        "🎉 全部任务完成", 
        "📁 日志与所有文件保存在"
    ]
    log_filename: str = 'downloader.log'

class UIConfig(BaseModel):
    progress_bar_width: Optional[int] = None
    show_transfer_speed: bool = True
    show_time_remaining: bool = True
    show_detailed_errors: bool = True
    show_network_status: bool = True

class AdvancedConfig(BaseModel):
    ytdlp_extra_args: List[str] = []
    connectivity_test_host: str = '8.8.8.8'
    connectivity_test_port: int = 53
    connectivity_timeout: int = 5
    proxy_test_url: str = 'http://httpbin.org/ip'
    proxy_test_timeout: int = 10

class AppConfig(BaseModel):
    folders: FoldersConfig = Field(default_factory=lambda: FoldersConfig())  # type: ignore
    downloader: DownloaderConfig = Field(default_factory=lambda: DownloaderConfig())  # type: ignore
    file_processing: FileProcessingConfig = Field(default_factory=lambda: FileProcessingConfig())  # type: ignore
    ai_subtitles: AISubtitlesConfig = Field(default_factory=lambda: AISubtitlesConfig())  # type: ignore
    logging: LoggingConfig = Field(default_factory=lambda: LoggingConfig())  # type: ignore
    ui: UIConfig = Field(default_factory=lambda: UIConfig())  # type: ignore
    advanced: AdvancedConfig = Field(default_factory=lambda: AdvancedConfig())  # type: ignore
    

# --- End of Pydantic Models ---

class ConfigManager:
    """使用 Pydantic 进行验证的配置管理器"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = Path(config_file)
        self.config: AppConfig = self._load_config()
    
    def _load_config(self) -> AppConfig:
        """加载、验证并返回配置"""
        if not self.config_file.exists():
            console.print(f"⚠️ 配置文件 {self.config_file} 不存在，将创建并使用默认配置。", style="bold yellow")
            default_config = AppConfig()
            self.save_config(default_config)
            return default_config
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f) or {}
            
            app_config = AppConfig.model_validate(raw_config)
            console.print(f"✅ 配置文件加载并验证成功: {self.config_file}", style="bold green")
            return app_config
            
        except yaml.YAMLError as e:
            log.error(f"❌ 配置文件格式错误: {e}")
        except ValidationError as e:
            log.error(f"❌ 配置内容验证失败:")
            for error in e.errors():
                loc = '.'.join(map(str, error['loc']))
                log.error(f"  - {loc}: {error['msg']}")
        except Exception as e:
            log.error(f"❌ 加载配置文件时发生未知错误: {e}")
        
        console.print("使用默认配置作为回退。", style="bold yellow")
        return AppConfig()

    def get_download_folder(self, script_path: Optional[Path] = None) -> Path:
        """根据配置创建并返回下载文件夹路径"""
        folders_config = self.config.folders
        
        if script_path is None:
            script_path = Path(__file__).parent
        
        if folders_config.custom_download_path:
            base_folder = Path(folders_config.custom_download_path)
            if not base_folder.is_absolute() and folders_config.relative_to_script:
                base_folder = script_path / folders_config.custom_download_path
        else:
            base_folder_name = folders_config.base_download_folder
            if folders_config.relative_to_script:
                base_folder = script_path / base_folder_name
            else:
                base_folder = Path.cwd() / base_folder_name
        
        final_folder = base_folder
        if folders_config.use_timestamp_folder:
            timestamp = datetime.now().strftime(folders_config.timestamp_format)
            final_folder = base_folder / timestamp
        
        try:
            final_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.error(f"❌ 创建下载文件夹失败: {e}")
            fallback_folder = Path.cwd() / datetime.now().strftime('%Y%m%d-%H%M%S')
            fallback_folder.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 使用备用文件夹: {fallback_folder}", style="bold yellow")
            return fallback_folder
        
        return final_folder
    
    def save_config(self, config_data: AppConfig) -> None:
        """将 Pydantic 模型保存到 YAML 文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_data.model_dump(), f, default_flow_style=False, allow_unicode=True, indent=2)
            console.print(f"✅ 配置已保存到: {self.config_file}", style="bold green")
        except Exception as e:
            log.error(f"❌ 保存配置文件失败: {e}")

# 全局配置实例
config_manager = ConfigManager()
config = config_manager.config # 直接暴露 pydantic 模型实例
