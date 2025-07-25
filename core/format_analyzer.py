# core/format_analyzer.py

import logging
from dataclasses import dataclass
try:
    from typing import Optional, Dict, List, Tuple, Any
except ImportError:
    # Python 3.8兼容性
    from typing import Optional, Dict, List, Any
    Tuple = tuple
from enum import Enum

log = logging.getLogger(__name__)


class StreamType(Enum):
    """视频流类型"""
    COMPLETE = "complete"      # 包含音视频的完整流
    VIDEO_ONLY = "video_only"  # 仅视频流
    AUDIO_ONLY = "audio_only"  # 仅音频流


class DownloadStrategy(Enum):
    """下载策略"""
    DIRECT = "direct"          # 直接下载完整流
    MERGE = "merge"            # 下载分离流后合并


@dataclass
class FormatInfo:
    """格式信息"""
    format_id: str
    ext: str
    vcodec: Optional[str]
    acodec: Optional[str] 
    width: Optional[int]
    height: Optional[int]
    filesize: Optional[int]
    tbr: Optional[float]  # 总比特率
    vbr: Optional[float]  # 视频比特率
    abr: Optional[float]  # 音频比特率
    stream_type: StreamType
    raw_format: Dict[str, Any]


@dataclass
class DownloadPlan:
    """下载计划"""
    strategy: DownloadStrategy
    primary_format: FormatInfo
    secondary_format: Optional[FormatInfo] = None  # 用于合并策略的音频格式
    reason: str = ""  # 选择该策略的原因


class FormatAnalyzer:
    """格式分析器 - 智能判断最佳下载策略"""
    
    def __init__(self):
        self.preferred_video_codecs = ['avc1', 'h264', 'mp4v']
        self.preferred_audio_codecs = ['mp4a', 'aac', 'm4a']
        self.preferred_containers = ['mp4', 'm4v']
    
    def analyze_formats(self, formats: List[Dict[str, Any]]) -> List[FormatInfo]:
        """
        分析格式列表，提取详细信息
        
        Args:
            formats: yt-dlp返回的格式列表
            
        Returns:
            FormatInfo对象列表
        """
        analyzed_formats = []
        
        for fmt in formats:
            # 跳过无效格式
            if not fmt.get('format_id'):
                continue
                
            format_info = FormatInfo(
                format_id=fmt.get('format_id', ''),
                ext=fmt.get('ext', ''),
                vcodec=fmt.get('vcodec'),
                acodec=fmt.get('acodec'),
                width=fmt.get('width'),
                height=fmt.get('height'),
                filesize=fmt.get('filesize'),
                tbr=fmt.get('tbr'),
                vbr=fmt.get('vbr'),
                abr=fmt.get('abr'),
                stream_type=self._determine_stream_type(fmt),
                raw_format=fmt
            )
            
            analyzed_formats.append(format_info)
            
        return analyzed_formats
    
    def _determine_stream_type(self, fmt: Dict[str, Any]) -> StreamType:
        """
        判断流类型
        
        Args:
            fmt: 格式字典
            
        Returns:
            StreamType枚举值
        """
        vcodec = fmt.get('vcodec')
        acodec = fmt.get('acodec')
        
        # 改进的编解码器检测逻辑：
        # 1. 'none' 明确表示没有该类型的流
        # 2. 'unknown' 表示编解码器未知但流可能存在
        # 3. None/空字符串也视为可能的完整流（X.com等平台）
        has_video = vcodec not in ('none', None, '') and vcodec != 'audio only'
        has_audio = acodec not in ('none', None, '') and acodec != 'video only'
        
        # 特殊处理：如果有宽高信息，通常表示有视频流
        has_dimensions = fmt.get('width') and fmt.get('height')
        
        # 如果vcodec和acodec都是unknown，但有分辨率信息，很可能是完整流
        if vcodec == 'unknown' and acodec == 'unknown' and has_dimensions:
            return StreamType.COMPLETE
        
        # 如果vcodec和acodec都是null，但有分辨率信息，很可能是完整流（X.com等）
        if vcodec is None and acodec is None and has_dimensions:
            return StreamType.COMPLETE
            
        # 如果是"audio only"明确标记，则为音频流
        if vcodec == 'audio only':
            return StreamType.AUDIO_ONLY
            
        # 如果是"video only"明确标记，则为视频流  
        if acodec == 'video only':
            return StreamType.VIDEO_ONLY
        
        if has_video and has_audio:
            return StreamType.COMPLETE
        elif has_video and not has_audio:
            return StreamType.VIDEO_ONLY
        elif not has_video and has_audio:
            return StreamType.AUDIO_ONLY
        else:
            # 如果都没有明确信息，但有分辨率，可能是完整流
            if has_dimensions:
                return StreamType.COMPLETE
            # 否则默认按完整流处理（保守策略）
            return StreamType.COMPLETE
    
    def find_best_download_plan(self, formats: List[Dict[str, Any]], 
                               target_format_id: Optional[str] = None) -> DownloadPlan:
        """
        智能选择最佳下载策略
        
        Args:
            formats: yt-dlp返回的格式列表
            target_format_id: 用户指定的格式ID（如果有）
            
        Returns:
            DownloadPlan对象，包含推荐的下载策略
        """
        analyzed_formats = self.analyze_formats(formats)
        
        # 分类格式
        complete_formats = [f for f in analyzed_formats if f.stream_type == StreamType.COMPLETE]
        video_only_formats = [f for f in analyzed_formats if f.stream_type == StreamType.VIDEO_ONLY]
        audio_only_formats = [f for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY]
        
        log.debug(f"格式分析结果: 完整流={len(complete_formats)}, 视频流={len(video_only_formats)}, 音频流={len(audio_only_formats)}")
        
        # 如果用户指定了格式ID
        if target_format_id:
            return self._create_plan_for_target_format(
                target_format_id, analyzed_formats, complete_formats, 
                video_only_formats, audio_only_formats
            )
        
        # 策略1: 优先选择高质量的完整流
        if complete_formats:
            best_complete = self._select_best_complete_format(complete_formats)
            return DownloadPlan(
                strategy=DownloadStrategy.DIRECT,
                primary_format=best_complete,
                reason=f"发现完整流({best_complete.format_id})，直接下载最高效"
            )
        
        # 策略2: 如果没有完整流，选择最佳视频+音频组合
        if video_only_formats and audio_only_formats:
            best_video = self._select_best_video_format(video_only_formats)
            best_audio = self._select_best_audio_format(audio_only_formats)
            
            return DownloadPlan(
                strategy=DownloadStrategy.MERGE,
                primary_format=best_video,
                secondary_format=best_audio,
                reason=f"需要合并视频流({best_video.format_id})和音频流({best_audio.format_id})"
            )
        
        # 策略3: 降级处理，使用最佳可用格式
        if analyzed_formats:
            # 选择质量最好的格式，不管是什么类型
            best_format = max(analyzed_formats, key=self._calculate_format_score)
            return DownloadPlan(
                strategy=DownloadStrategy.DIRECT,
                primary_format=best_format,
                reason=f"降级使用最佳可用格式({best_format.format_id})"
            )
        
        # 如果没有任何可用格式，抛出异常
        raise ValueError("没有找到任何可用的视频格式")
    
    def _create_plan_for_target_format(self, target_format_id: str, 
                                     analyzed_formats: List[FormatInfo],
                                     complete_formats: List[FormatInfo],
                                     video_only_formats: List[FormatInfo],
                                     audio_only_formats: List[FormatInfo]) -> DownloadPlan:
        """为指定的格式ID创建下载计划"""
        
        # 检查是否是合并格式 (video_id+audio_id)
        if '+' in target_format_id:
            video_id, audio_id = target_format_id.split('+', 1)
            
            video_format = next((f for f in video_only_formats if f.format_id == video_id), None)
            audio_format = next((f for f in audio_only_formats if f.format_id == audio_id), None)
            
            if video_format and audio_format:
                return DownloadPlan(
                    strategy=DownloadStrategy.MERGE,
                    primary_format=video_format,
                    secondary_format=audio_format,
                    reason=f"用户指定合并格式: {video_id}+{audio_id}"
                )
        
        # 查找目标格式
        target_format = next((f for f in analyzed_formats if f.format_id == target_format_id), None)
        
        if target_format:
            if target_format.stream_type == StreamType.COMPLETE:
                return DownloadPlan(
                    strategy=DownloadStrategy.DIRECT,
                    primary_format=target_format,
                    reason=f"用户指定完整流格式: {target_format_id}"
                )
            elif target_format.stream_type == StreamType.VIDEO_ONLY and audio_only_formats:
                # 为指定的视频格式匹配最佳音频
                best_audio = self._select_best_audio_format(audio_only_formats)
                return DownloadPlan(
                    strategy=DownloadStrategy.MERGE,
                    primary_format=target_format,
                    secondary_format=best_audio,
                    reason=f"用户指定视频格式{target_format_id}，匹配音频流{best_audio.format_id}"
                )
            elif target_format.stream_type == StreamType.AUDIO_ONLY:
                # 用户指定音频格式，直接下载
                return DownloadPlan(
                    strategy=DownloadStrategy.DIRECT,
                    primary_format=target_format,
                    reason=f"用户指定音频流格式: {target_format_id}"
                )
        
        # 如果找不到指定格式，降级到自动选择
        log.warning(f"找不到指定格式 {target_format_id}，降级到自动选择")
        # 递归调用时需要传递原始格式数据
        original_formats = [f.raw_format for f in analyzed_formats]
        return self.find_best_download_plan(original_formats, None)
    
    def _select_best_complete_format(self, complete_formats: List[FormatInfo]) -> FormatInfo:
        """选择最佳完整流格式"""
        return max(complete_formats, key=self._calculate_format_score)
    
    def _select_best_video_format(self, video_formats: List[FormatInfo]) -> FormatInfo:
        """选择最佳视频格式"""
        return max(video_formats, key=self._calculate_video_score)
    
    def _select_best_audio_format(self, audio_formats: List[FormatInfo]) -> FormatInfo:
        """选择最佳音频格式"""
        return max(audio_formats, key=self._calculate_audio_score)
    
    def _calculate_format_score(self, fmt: FormatInfo) -> float:
        """计算格式综合得分"""
        score = 0.0
        
        # 基础质量分数
        if fmt.width and fmt.height:
            # 分辨率分数 (4K=100, 1080p=80, 720p=60, 等等)
            resolution_score = min(100, (fmt.width * fmt.height) / (1920 * 1080) * 80)
            score += resolution_score
        
        # 比特率分数
        if fmt.tbr:
            # 归一化比特率分数 (0-20分)
            bitrate_score = min(20, fmt.tbr / 100)
            score += bitrate_score
        
        # 容器格式偏好 (0-10分)
        if fmt.ext in self.preferred_containers:
            score += 10
        elif fmt.ext in ['webm', 'mkv']:
            score += 5
        
        # 编解码器偏好 (0-10分)
        if fmt.vcodec and any(codec in fmt.vcodec for codec in self.preferred_video_codecs):
            score += 5
        if fmt.acodec and any(codec in fmt.acodec for codec in self.preferred_audio_codecs):
            score += 5
        
        # 完整流奖励 (0-20分)
        if fmt.stream_type == StreamType.COMPLETE:
            score += 20
        
        return score
    
    def _calculate_video_score(self, fmt: FormatInfo) -> float:
        """计算视频格式得分"""
        score = 0.0
        
        if fmt.width and fmt.height:
            score += (fmt.width * fmt.height) / 10000  # 分辨率分数
        
        if fmt.vbr:
            score += fmt.vbr / 100  # 视频比特率分数
        elif fmt.tbr:
            score += fmt.tbr / 150  # 总比特率分数（降权）
        
        # 编解码器偏好
        if fmt.vcodec and any(codec in fmt.vcodec for codec in self.preferred_video_codecs):
            score += 10
        
        return score
    
    def _calculate_audio_score(self, fmt: FormatInfo) -> float:
        """计算音频格式得分"""
        score = 0.0
        
        if fmt.abr:
            score += fmt.abr / 10  # 音频比特率分数
        elif fmt.tbr:
            score += fmt.tbr / 20  # 总比特率分数（降权）
        
        # 编解码器偏好
        if fmt.acodec and any(codec in fmt.acodec for codec in self.preferred_audio_codecs):
            score += 10
        
        # 容器格式偏好
        if fmt.ext in ['m4a', 'aac']:
            score += 5
        elif fmt.ext in ['mp3', 'opus']:
            score += 3
        
        return score
    
    def get_format_summary(self, formats: List[Dict[str, Any]]) -> str:
        """
        获取格式摘要信息，用于调试
        
        Args:
            formats: yt-dlp返回的格式列表
            
        Returns:
            格式摘要字符串
        """
        analyzed_formats = self.analyze_formats(formats)
        
        complete_count = sum(1 for f in analyzed_formats if f.stream_type == StreamType.COMPLETE)
        video_count = sum(1 for f in analyzed_formats if f.stream_type == StreamType.VIDEO_ONLY)
        audio_count = sum(1 for f in analyzed_formats if f.stream_type == StreamType.AUDIO_ONLY)
        
        summary = f"格式分析: 总数={len(analyzed_formats)}, 完整流={complete_count}, 视频流={video_count}, 音频流={audio_count}"
        
        # 添加推荐计划
        try:
            plan = self.find_best_download_plan(formats)
            summary += f"\n推荐策略: {plan.strategy.value} - {plan.reason}"
        except Exception as e:
            summary += f"\n策略分析失败: {e}"
        
        return summary