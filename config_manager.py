# config_manager.py

import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
from rich.console import Console

console = Console()

class ConfigManager:
    """配置管理器，负责加载和管理应用程序配置"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = Path(config_file)
        self.config = {}
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            if not self.config_file.exists():
                console.print(f"⚠️ 配置文件 {self.config_file} 不存在，使用默认配置", style="bold yellow")
                self._create_default_config()
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
            
            self._validate_config()
            console.print(f"✅ 配置文件加载成功: {self.config_file}", style="bold green")
            
        except yaml.YAMLError as e:
            console.print(f"❌ 配置文件格式错误: {e}", style="bold red")
            console.print("使用默认配置", style="bold yellow")
            self._create_default_config()
        except Exception as e:
            console.print(f"❌ 加载配置文件时出错: {e}", style="bold red")
            console.print("使用默认配置", style="bold yellow")
            self._create_default_config()
    
    def _create_default_config(self):
        """创建默认配置"""
        self.config = {
            'folders': {
                'base_download_folder': 'downloads',
                'use_timestamp_folder': True,
                'timestamp_format': '%Y%m%d-%H%M%S',
                'custom_download_path': None,
                'relative_to_script': True
            },
            'downloader': {
                'max_retries': 3,
                'base_delay': 10,
                'max_delay': 300,
                'backoff_factor': 2,
                'network_timeout': 60,
                'stall_detection_time': 30,
                'stall_check_interval': 5,
                'stall_threshold_count': 6,
                'proxy_retry_base_delay': 30,
                'proxy_retry_increment': 10,
                'proxy_retry_max_delay': 120
            },
            'file_processing': {
                'filename_max_length': 50,
                'filename_truncate_suffix': "...",
                'polite_wait_time': 3,
                'cleanup_patterns': ["*.part", "*.part-*", "*.ytdl", "*.tmp.*", "*.f*"]
            },
            'ai_subtitles': {
                'whisper_model': 'base.en',
                'whisper_device': 'auto',
                'translate_to_chinese': True,
                'translator_service': 'google',
                'subtitle_formats': ['srt', 'vtt']
            },
            'logging': {
                'level': 'INFO',
                'console_keywords': [
                    "🚀 智能媒体下载",
                    "🎉 全部任务完成", 
                    "📁 日志与所有文件保存在"
                ],
                'log_filename': 'downloader.log'
            },
            'ui': {
                'progress_bar_width': None,
                'show_transfer_speed': True,
                'show_time_remaining': True,
                'show_detailed_errors': True,
                'show_network_status': True
            },
            'advanced': {
                'ytdlp_extra_args': [],
                'connectivity_test_host': '8.8.8.8',
                'connectivity_test_port': 53,
                'connectivity_timeout': 5,
                'proxy_test_url': 'http://httpbin.org/ip',
                'proxy_test_timeout': 10
            }
        }
    
    def _validate_config(self):
        """验证配置的有效性"""
        errors = []
        
        # 验证文件夹配置
        folders = self.config.get('folders', {})
        
        # 验证时间戳格式
        timestamp_format = folders.get('timestamp_format', '%Y%m%d-%H%M%S')
        try:
            datetime.now().strftime(timestamp_format)
        except (ValueError, TypeError):
            errors.append(f"folders.timestamp_format 格式无效: '{timestamp_format}'")
        
        # 验证自定义路径
        custom_path = folders.get('custom_download_path')
        if custom_path is not None and not isinstance(custom_path, str):
            errors.append("folders.custom_download_path 必须是字符串或null")
        
        # 验证下载器配置
        downloader = self.config.get('downloader', {})
        if not isinstance(downloader.get('max_retries', 0), int) or downloader.get('max_retries', 0) < 0:
            errors.append("downloader.max_retries 必须是非负整数")
        
        if not isinstance(downloader.get('base_delay', 0), (int, float)) or downloader.get('base_delay', 0) < 0:
            errors.append("downloader.base_delay 必须是非负数")
        
        # 验证文件处理配置
        file_proc = self.config.get('file_processing', {})
        if not isinstance(file_proc.get('filename_max_length', 0), int) or file_proc.get('filename_max_length', 0) <= 0:
            errors.append("file_processing.filename_max_length 必须是正整数")
        
        if not isinstance(file_proc.get('polite_wait_time', 0), (int, float)) or file_proc.get('polite_wait_time', 0) < 0:
            errors.append("file_processing.polite_wait_time 必须是非负数")
        
        # 验证AI字幕配置
        ai_subs = self.config.get('ai_subtitles', {})
        valid_whisper_models = ['tiny.en', 'base.en', 'small.en', 'medium.en', 'large', 'tiny', 'base', 'small', 'medium']
        if ai_subs.get('whisper_model') not in valid_whisper_models:
            errors.append(f"ai_subtitles.whisper_model 必须是以下之一: {', '.join(valid_whisper_models)}")
        
        if errors:
            for error in errors:
                console.print(f"❌ 配置错误: {error}", style="bold red")
            console.print("请检查配置文件，使用默认值替代错误配置", style="bold yellow")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的嵌套键"""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_folders_config(self) -> Dict[str, Any]:
        """获取文件夹配置"""
        return self.config.get('folders', {})
    
    def get_downloader_config(self) -> Dict[str, Any]:
        """获取下载器配置"""
        return self.config.get('downloader', {})
    
    def get_file_processing_config(self) -> Dict[str, Any]:
        """获取文件处理配置"""
        return self.config.get('file_processing', {})
    
    def get_ai_subtitles_config(self) -> Dict[str, Any]:
        """获取AI字幕配置"""
        return self.config.get('ai_subtitles', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {})
    
    def get_ui_config(self) -> Dict[str, Any]:
        """获取UI配置"""
        return self.config.get('ui', {})
    
    def get_download_folder(self, script_path: Optional[Path] = None) -> Path:
        """
        根据配置创建并返回下载文件夹路径
        
        Args:
            script_path: 脚本文件路径，用于相对路径计算
        
        Returns:
            Path: 下载文件夹的完整路径
        """
        folders_config = self.get_folders_config()
        
        # 获取基础路径
        if script_path is None:
            script_path = Path(__file__).parent
        
        # 检查是否有自定义下载路径
        custom_path = folders_config.get('custom_download_path')
        if custom_path:
            base_folder = Path(custom_path)
            # 如果是相对路径，根据配置决定相对于脚本还是当前目录
            if not base_folder.is_absolute():
                if folders_config.get('relative_to_script', True):
                    base_folder = script_path / custom_path
                else:
                    base_folder = Path.cwd() / custom_path
        else:
            # 使用默认的base_download_folder
            base_folder_name = folders_config.get('base_download_folder', 'downloads')
            if folders_config.get('relative_to_script', True):
                base_folder = script_path / base_folder_name
            else:
                base_folder = Path.cwd() / base_folder_name
        
        # 检查是否需要添加时间戳子文件夹
        if folders_config.get('use_timestamp_folder', True):
            timestamp_format = folders_config.get('timestamp_format', '%Y%m%d-%H%M%S')
            timestamp = datetime.now().strftime(timestamp_format)
            final_folder = base_folder / timestamp
        else:
            final_folder = base_folder
        
        # 创建文件夹
        try:
            final_folder.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 下载文件夹已创建: {final_folder}", style="bold green")
        except Exception as e:
            console.print(f"❌ 创建下载文件夹失败: {e}", style="bold red")
            # 如果创建失败，回退到当前目录下的时间戳文件夹
            fallback_folder = Path.cwd() / datetime.now().strftime('%Y%m%d-%H%M%S')
            fallback_folder.mkdir(parents=True, exist_ok=True)
            console.print(f"📁 使用备用文件夹: {fallback_folder}", style="bold yellow")
            return fallback_folder
        
        return final_folder
    
    def get_advanced_config(self) -> Dict[str, Any]:
        """获取高级配置"""
        return self.config.get('advanced', {})
    
    def save_config(self):
        """保存当前配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, indent=2)
            console.print(f"✅ 配置已保存到: {self.config_file}", style="bold green")
        except Exception as e:
            console.print(f"❌ 保存配置文件失败: {e}", style="bold red")

# 全局配置实例
config = ConfigManager()