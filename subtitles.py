# subtitles.py
import asyncio
import re
import logging
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import aiofiles
from rich.console import Console

from config_manager import config

log = logging.getLogger(__name__)
console = Console()

try:
    from deep_translator import GoogleTranslator
    AI_LIBRARIES_AVAILABLE = True
except ImportError:
    AI_LIBRARIES_AVAILABLE = False


class AudioProcessor:
    """专门处理音频转换的处理器"""
    
    async def convert_to_wav(self, input_path: Path) -> Optional[Path]:
        """将音频文件转换为 WAV 格式"""
        output_path = input_path.with_suffix(".wav")
        console.print(f"🔄 正在将 {input_path.name} 转换为 WAV 格式...", style="bold yellow")
        
        cmd = ["ffmpeg", "-i", str(input_path.resolve()), "-acodec", "pcm_s16le", 
               "-ar", "16000", "-ac", "1", str(output_path.resolve())]
        
        log.info(f"执行FFmpeg命令: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            log.error(f"FFmpeg命令执行失败，返回码: {process.returncode}")
            log.error(f"FFmpeg stderr: {stderr.decode()}")
            return None
            
        console.print(f"✅ 转换完成: {output_path.name}", style="bold green")
        return output_path

    async def cleanup_temp_wav(self, wav_path: Path) -> None:
        """清理临时WAV文件"""
        if wav_path and wav_path.exists():
            try:
                await asyncio.to_thread(wav_path.unlink)
                log.info(f"已清理临时WAV文件: {wav_path.name}")
            except Exception as e:
                log.warning(f"无法清理临时WAV文件 {wav_path.name}: {e}")


class TranscriptionProcessor:
    """专门处理语音转录的处理器"""
    
    def __init__(self):
        self.whisper_model = config.ai_subtitles.whisper_model
        self.source_language = config.ai_subtitles.source_language
        self.whisper_model_path = config.ai_subtitles.whisper_model_path
    
    async def transcribe_audio(self, audio_path: Path, output_folder: Path) -> Optional[Path]:
        """使用Whisper转录音频文件"""
        console.print(f"🧠 正在转录音频: {audio_path.name}", style="bold green")
        console.print(f"🤖 使用Whisper模型: {self.whisper_model}", style="bold blue")

        final_srt_path = output_folder / f"{audio_path.stem}.en.srt"
        
        model_path = self._get_model_path()
        if not model_path or not model_path.exists():
            log.error(f"模型文件未找到: {model_path}")
            return None

        cmd = ['whisper-cli', '-m', str(model_path.resolve()), 
               '-l', self.source_language, str(audio_path.resolve())]
        
        log.info(f"执行Whisper命令: {' '.join(cmd)}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            log.error(f"Whisper命令执行失败，返回码: {process.returncode}")
            log.error(f"Whisper stderr: {stderr.decode()}")
            return None

        raw_output = stdout.decode()
        if not raw_output.strip():
            log.error("Whisper转录输出为空。")
            return None

        await self._write_srt_file(raw_output, final_srt_path)
        console.print(f"✅ 英文字幕已生成: {final_srt_path.name}", style="bold green")
        return final_srt_path
    
    def _get_model_path(self) -> Optional[Path]:
        """获取Whisper模型路径"""
        model_filename = f"ggml-{self.whisper_model}.bin"
        
        if self.whisper_model_path:
            return Path(self.whisper_model_path) / model_filename
        else:
            return Path.home() / ".cache/whisper/whisper.cpp" / model_filename
    
    async def _write_srt_file(self, raw_output: str, srt_path: Path) -> None:
        """将Whisper输出写入SRT文件"""
        async with aiofiles.open(srt_path, 'w', encoding='utf-8') as f:
            for i, m in enumerate(re.finditer(r"\[(.*?)\]\s+(.*)", raw_output), 1):
                times, text = m.groups()
                start, end = [t.strip().replace('.', ',') for t in times.split('-->')]
                await f.write(f"{i}\n{start} --> {end}\n{text}\n\n")


class TranslationProcessor:
    """专门处理文本翻译的处理器"""
    
    def __init__(self, proxy: Optional[str] = None):
        self.translate_to_chinese = config.ai_subtitles.translate_to_chinese
        self.translator = None
        
        if self.translate_to_chinese:
            translator_service = config.ai_subtitles.translator_service.lower()
            if translator_service == "google":
                self.translator = GoogleTranslator(
                    source='en',
                    target='zh-CN',
                    proxies={"http": proxy, "https": proxy} if proxy else None
                )
            else:
                log.warning(f"不支持的翻译服务: {translator_service}。将回退到Google翻译。")
                self.translator = GoogleTranslator(
                    source='en',
                    target='zh-CN',
                    proxies={"http": proxy, "https": proxy} if proxy else None
                )
    
    async def translate_subtitle(self, srt_path_in: Path) -> Optional[Path]:
        """翻译字幕文件"""
        if not self.translate_to_chinese or not self.translator:
            return None

        console.print(f"✍️ 正在翻译字幕: {srt_path_in.name}", style="bold blue")
        srt_path_out = srt_path_in.with_suffix('.zh-CN.srt')
        
        if not srt_path_in.exists():
            log.error(f"输入SRT文件不存在: {srt_path_in}")
            return None

        try:
            content = await self._read_srt_file(srt_path_in)
            text_blocks = self._extract_text_blocks(content)
            
            if not text_blocks:
                log.warning(f"没有可翻译的文本块在 {srt_path_in.name} 中。")
                return None

            translated_blocks = await self._translate_text_blocks(text_blocks)
            
            if not translated_blocks:
                return None
                
            await self._write_translated_srt(content, translated_blocks, srt_path_out)
            console.print(f"✅ 中文字幕已生成: {srt_path_out.name}", style="bold green")
            return srt_path_out
            
        except Exception as e:
            log.error(f"翻译失败: {e}")
            return None
    
    async def _read_srt_file(self, srt_path: Path) -> str:
        """读取SRT文件内容"""
        async with aiofiles.open(srt_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        log.info(f"从 {srt_path.name} 读取到 {len(content)} 字节内容。")
        return content
    
    def _extract_text_blocks(self, content: str) -> List[str]:
        """从SRT内容中提取文本块"""
        text_blocks = [m.group(1).replace('\n', ' ') 
                      for m in re.finditer(r'[\d:,-\s>]+\n(.*?)(?=\n\d+|$)', content, re.DOTALL)]
        log.info(f"提取到 {len(text_blocks)} 个文本块进行翻译。")
        return text_blocks
    
    async def _translate_text_blocks(self, text_blocks: List[str]) -> Optional[List[str]]:
        """批量翻译文本块"""
        all_translated_blocks = []
        batch_size = config.ai_subtitles.translation_batch_size
        delay = config.ai_subtitles.translation_delay

        log.info(f"准备翻译 {len(text_blocks)} 个文本块，分批大小: {batch_size}，批次间延迟: {delay}秒...")

        for i in range(0, len(text_blocks), batch_size):
            batch = text_blocks[i:i + batch_size]
            try:
                log.info(f"正在翻译批次 {i // batch_size + 1}/{(len(text_blocks) + batch_size - 1) // batch_size} (包含 {len(batch)} 个文本块)...")
                translated_batch = await asyncio.to_thread(self.translator.translate_batch, batch)
                all_translated_blocks.extend(translated_batch)
                log.info(f"批次翻译完成。")
            except Exception as e:
                log.error(f"deep_translator.translate_batch 调用失败 (批次 {i // batch_size + 1}): {e}")
                return None

            if i + batch_size < len(text_blocks):
                await asyncio.sleep(delay)

        if len(text_blocks) != len(all_translated_blocks):
            log.error(f"翻译返回片段数与原文不匹配。原文: {len(text_blocks)}, 翻译: {len(all_translated_blocks)}")
            return None

        return all_translated_blocks
    
    async def _write_translated_srt(self, original_content: str, translated_blocks: List[str], output_path: Path) -> None:
        """写入翻译后的SRT文件"""
        new_content_parts = []
        subtitle_blocks_iter = re.finditer(r'(\d+\n[\d:,-\s>]+\n)(.*?)(?=\n\n|$)', original_content, re.DOTALL)

        for i, match in enumerate(subtitle_blocks_iter):
            header = match.group(1)
            translated_text = translated_blocks[i].strip()
            new_content_parts.append(f"{header}{translated_text}\n\n")

        new_content = "".join(new_content_parts)

        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f_out:
            await f_out.write(new_content)
        log.info(f"已将翻译内容写入: {output_path}")


class SubtitleMerger:
    """专门处理字幕合并的处理器"""
    
    async def merge_subtitles(self, en_srt: Path, zh_srt: Path) -> Optional[Path]:
        """合并英文和中文字幕为双语字幕"""
        console.print("🤝 正在合并字幕...", style="bold magenta")
        bi_srt = en_srt.with_suffix('.bilingual.srt')
        
        log.info(f"尝试合并字幕: 英文字幕路径: {en_srt}, 中文字幕路径: {zh_srt}")
        
        if not zh_srt.exists():
            log.error(f"中文字幕文件不存在，无法合并: {zh_srt}")
            return None
            
        try:
            en_content, zh_content = await self._read_subtitle_files(en_srt, zh_srt)
            merged_content = await self._create_merged_content(en_content, zh_content)
            
            async with aiofiles.open(bi_srt, 'w', encoding='utf-8') as f:
                await f.write(merged_content)

            console.print(f"✅ 双语字幕已生成: {bi_srt.name}", style="bold green")
            return bi_srt
            
        except Exception as e:
            log.error(f"字幕合并失败: {e}")
            return None
    
    async def _read_subtitle_files(self, en_srt: Path, zh_srt: Path) -> tuple[str, str]:
        """读取英文和中文字幕文件"""
        async with aiofiles.open(en_srt, 'r', encoding='utf-8') as f:
            en_content = await f.read()
        async with aiofiles.open(zh_srt, 'r', encoding='utf-8') as f:
            zh_content = await f.read()
        return en_content, zh_content
    
    async def _create_merged_content(self, en_content: str, zh_content: str) -> str:
        """创建合并的字幕内容"""
        en_subtitles = {m[1]: m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n', en_content, re.DOTALL)}
        zh_subtitles = {m[1]: m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n', zh_content, re.DOTALL)}
        timestamps = {m[1]: m[2].strip() for m in re.finditer(r'(\d+)\n(.*?)\n', en_content)}

        merged_parts = []
        for i in sorted(timestamps.keys(), key=int):
            zh_text = zh_subtitles.get(i, '')
            en_text = en_subtitles.get(i, '')
            timestamp = timestamps[i]
            merged_parts.append(f"{i}\n{timestamp}\n{zh_text}\n{en_text}\n\n")

        return "".join(merged_parts)

class SubtitleProcessor:
    """简化的字幕处理器，协调各个专门的处理器"""
    
    def __init__(self, download_folder: Path, proxy: Optional[str] = None):
        if not AI_LIBRARIES_AVAILABLE:
            raise ImportError("AI库 `deep-translator` 未安装。")

        self.download_folder = download_folder
        self.subtitle_formats = config.ai_subtitles.subtitle_formats
        
        # 初始化专门的处理器
        self.audio_processor = AudioProcessor()
        self.transcription_processor = TranscriptionProcessor()
        self.translation_processor = TranslationProcessor(proxy)
        self.subtitle_merger = SubtitleMerger()

    async def process_item(self, file_prefix: str, audio_source_path: Path, output_folder: Optional[Path] = None) -> None:
        """处理单个项目的字幕生成流程"""
        console.print("[bold cyan]🧠 AI字幕生成流程启动...[/bold cyan]")
        
        if await self._check_for_existing_subs(file_prefix, output_folder):
            return

        base_folder = output_folder if output_folder is not None else self.download_folder
        
        # 步骤1: 音频格式转换
        audio_to_transcribe = await self._prepare_audio(audio_source_path)
        if not audio_to_transcribe:
            return
            
        # 步骤2: 语音转录
        en_srt_path = await self.transcription_processor.transcribe_audio(audio_to_transcribe, base_folder)
        
        # 清理临时音频文件
        if audio_to_transcribe != audio_source_path:
            await self.audio_processor.cleanup_temp_wav(audio_to_transcribe)
        
        if not en_srt_path:
            return
            
        # 步骤3: 翻译字幕
        if self.translation_processor.translate_to_chinese:
            zh_srt_path = await self.translation_processor.translate_subtitle(en_srt_path)
            if zh_srt_path:
                # 步骤4: 合并字幕
                await self.subtitle_merger.merge_subtitles(en_srt_path, zh_srt_path)

    async def _prepare_audio(self, audio_source_path: Path) -> Optional[Path]:
        """准备音频文件用于转录"""
        if audio_source_path.suffix.lower() != ".wav":
            return await self.audio_processor.convert_to_wav(audio_source_path)
        return audio_source_path

    async def _check_for_existing_subs(self, file_prefix: str, output_folder: Optional[Path] = None) -> bool:
        """检查是否已存在字幕文件"""
        base_folder = output_folder if output_folder is not None else self.download_folder
        
        def _glob():
            return list(base_folder.glob(f"{file_prefix}*.srt"))
        
        existing_files = await asyncio.to_thread(_glob)
        if existing_files:
            log.info(f"    ℹ️ 检测到已有字幕，跳过AI生成。")
            return True
        return False