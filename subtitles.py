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

class SubtitleProcessor:
    def __init__(self, download_folder: Path, proxy: Optional[str] = None):
        if not AI_LIBRARIES_AVAILABLE:
            raise ImportError("AI库 `deep-translator` 未安装。")

        self.download_folder = download_folder
        self.whisper_model = config.ai_subtitles.whisper_model
        self.translate_to_chinese = config.ai_subtitles.translate_to_chinese
        self.subtitle_formats = config.ai_subtitles.subtitle_formats

        if self.translate_to_chinese:
            self.translator = GoogleTranslator(
                source='en',
                target='zh-CN',
                proxies={"http": proxy, "https": proxy} if proxy else None
            )
        self.whisper_model_path = config.ai_subtitles.whisper_model_path

    async def _convert_to_wav(self, input_path: Path) -> Optional[Path]:
        output_path = input_path.with_suffix(".wav")
        console.print(f"🔄 正在将 {input_path.name} 转换为 WAV 格式...", style="bold yellow")
        cmd = ["ffmpeg", "-i", str(input_path.resolve()), "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(output_path.resolve())]
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

    async def transcribe(self, audio_path: Path, output_folder: Optional[Path] = None) -> Optional[Path]:
        # Convert to WAV if not already WAV
        if audio_path.suffix.lower() != ".wav":
            wav_path = await self._convert_to_wav(audio_path)
            if not wav_path:
                return None
            audio_to_transcribe = wav_path
        else:
            audio_to_transcribe = audio_path

        console.print(f"🧠 正在转录音频: {audio_to_transcribe.name}", style="bold green")
        console.print(f"🤖 使用Whisper模型: {self.whisper_model}", style="bold blue")

        base_folder = output_folder if output_folder is not None else self.download_folder
        final_srt_path = base_folder / f"{audio_path.stem}.en.srt"

        model_filename = f"ggml-{self.whisper_model}.bin"
        if self.whisper_model_path:
            model_path = Path(self.whisper_model_path) / model_filename
        else:
            model_path = Path.home() / ".cache/whisper/whisper.cpp" / model_filename

        if not model_path.exists():
            log.error(f"模型文件未找到: {model_path}")
            return None

        cmd = ['whisper-cli', '-m', str(model_path.resolve()), '-l', 'en', str(audio_to_transcribe.resolve())]
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
            log.error(f"Whisper stdout: {raw_output}")
            return None

        async with aiofiles.open(final_srt_path, 'w', encoding='utf-8') as f:
            for i, m in enumerate(re.finditer(r"\[(.*?)\]\s+(.*)", raw_output), 1):
                times, text = m.groups()
                start, end = [t.strip().replace('.', ',') for t in times.split('-->')]
                await f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

        console.print(f"✅ 英文字幕已生成: {final_srt_path.name}", style="bold green")

        # Clean up temporary WAV file if created
        if audio_path.suffix.lower() != ".wav" and wav_path and wav_path.exists():
            try:
                await asyncio.to_thread(wav_path.unlink)
                log.info(f"已清理临时WAV文件: {wav_path.name}")
            except Exception as e:
                log.warning(f"无法清理临时WAV文件 {wav_path.name}: {e}")

        return final_srt_path

    async def process_item(self, file_prefix: str, audio_source_path: Path, output_folder: Optional[Path] = None) -> None:
        console.print("[bold cyan]🧠 AI字幕生成流程启动...[/bold cyan]")
        if await self._check_for_existing_subs(file_prefix, output_folder):
            return

        en_srt_path = await self.transcribe(audio_source_path, output_folder)
        if en_srt_path:
            if self.translate_to_chinese:
                zh_srt_path = await self._translate(en_srt_path)
                if zh_srt_path:
                    await self._merge(en_srt_path, zh_srt_path)

    async def _check_for_existing_subs(self, file_prefix: str, output_folder: Optional[Path] = None) -> bool:
        base_folder = output_folder if output_folder is not None else self.download_folder
        # This part is tricky to make fully async without a library like `aiopath`.
        # For now, we can use a thread to avoid blocking.
        def _glob():
            return list(base_folder.glob(f"{file_prefix}*.srt"))
        
        existing_files = await asyncio.to_thread(_glob)
        if existing_files:
            log.info(f"    ℹ️ 检测到已有字幕，跳过AI生成。")
            return True
        return False

    async def _translate(self, srt_path_in: Path) -> Optional[Path]:
        if not self.translate_to_chinese:
            return None

        console.print(f"✍️ 正在翻译字幕: {srt_path_in.name}", style="bold blue")
        srt_path_out = srt_path_in.with_suffix('.zh-CN.srt')
        log.info(f"尝试翻译文件: {srt_path_in}, 输出路径: {srt_path_out}")
        if not srt_path_in.exists():
            log.error(f"输入SRT文件不存在: {srt_path_in}")
            return None

        try:
            async with aiofiles.open(srt_path_in, 'r', encoding='utf-8') as f_in:
                content = await f_in.read()
            log.info(f"从 {srt_path_in.name} 读取到 {len(content)} 字节内容。")

            text_blocks = [m.group(1).replace('\n', ' ') for m in re.finditer(r'[\d:,->\s]+\n(.*?)(?=\n\d+|$)', content, re.DOTALL)]
            log.info(f"提取到 {len(text_blocks)} 个文本块进行翻译。")
            if not text_blocks:
                log.warning(f"没有可翻译的文本块在 {srt_path_in.name} 中。")
                return None

            # Use asyncio.to_thread to run the synchronous translation library
            try:
                log.info(f"准备翻译 {len(text_blocks)} 个文本块...")
                translated_blocks = await asyncio.to_thread(self.translator.translate_batch, text_blocks)
                log.info(f"翻译返回 {len(translated_blocks)} 个文本块。")
            except Exception as e:
                log.error(f"deep_translator.translate_batch 调用失败: {e}")
                return None

            if len(text_blocks) != len(translated_blocks):
                log.error(f"翻译返回片段数与原文不匹配。原文: {len(text_blocks)}, 翻译: {len(translated_blocks)}")
                return None

            log.info(f"翻译后的文本块示例 (前5个): {translated_blocks[:5]}")
            log.info(f"所有翻译后的文本块: {translated_blocks}")

            new_content_parts = []
            subtitle_blocks_iter = re.finditer(r'(\d+\n[\d:,->\s]+\n)(.*?)(?=\n\n|$)', content, re.DOTALL)

            for i, match in enumerate(subtitle_blocks_iter):
                header = match.group(1)
                translated_text = translated_blocks[i].strip()
                new_content_parts.append(f"{header}{translated_text}\n\n")

            new_content = "".join(new_content_parts)

            async with aiofiles.open(srt_path_out, 'w', encoding='utf-8') as f_out:
                await f_out.write(new_content)
            log.info(f"已将翻译内容写入: {srt_path_out}")

            console.print(f"✅ 中文字幕已生成: {srt_path_out.name}", style="bold green")
            return srt_path_out
        except Exception as e:
            log.error(f"翻译失败: {e}")
            return None

    async def _merge(self, en_srt: Path, zh_srt: Path) -> Optional[Path]:
        console.print("🤝 正在合并字幕...", style="bold magenta")
        bi_srt = en_srt.with_suffix('.bilingual.srt')
        log.info(f"尝试合并字幕: 英文字幕路径: {en_srt}, 中文字幕路径: {zh_srt}")
        if not zh_srt.exists():
            log.error(f"中文字幕文件不存在，无法合并: {zh_srt}")
            return None
        try:
            async with aiofiles.open(en_srt, 'r', encoding='utf-8') as f:
                en_c = await f.read()
            async with aiofiles.open(zh_srt, 'r', encoding='utf-8') as f:
                zh_c = await f.read()

            en_s = {m[1]: m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n', en_c, re.DOTALL)}
            zh_s = {m[1]: m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n', zh_c, re.DOTALL)}
            ts = {m[1]: m[2].strip() for m in re.finditer(r'(\d+)\n(.*?)\n', en_c)}

            async with aiofiles.open(bi_srt, 'w', encoding='utf-8') as f:
                for i in sorted(ts.keys(), key=int):
                    await f.write(f"{i}\n{ts[i]}\n{zh_s.get(i, '')}\n{en_s.get(i, '')}\n\n")

            console.print(f"✅ 双语字幕已生成: {bi_srt.name}", style="bold green")
            return bi_srt
        except Exception as e:
            log.error(f"字幕合并失败: {e}")
            return None