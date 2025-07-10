# subtitles.py
import time, re, subprocess, logging
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn
from rich.console import Console

# 导入配置管理器
from config_manager import config

log = logging.getLogger(__name__)
console = Console()

try:
    from deep_translator import GoogleTranslator
    AI_LIBRARIES_AVAILABLE = True
except ImportError:
    AI_LIBRARIES_AVAILABLE = False

class SubtitleProcessor:
    """
    负责所有与AI字幕生成相关的任务。
    【内部调用修复版】
    """
    def __init__(self, download_folder: Path, proxy: Optional[str] = None):
        if not AI_LIBRARIES_AVAILABLE: 
            raise ImportError("AI库 `deep-translator` 未安装。")
        
        self.download_folder = download_folder
        
        # 从配置获取AI字幕设置
        ai_config = config.get_ai_subtitles_config()
        self.whisper_model = ai_config.get('whisper_model', 'base.en')
        self.whisper_device = ai_config.get('whisper_device', 'auto')
        self.translate_to_chinese = ai_config.get('translate_to_chinese', True)
        self.translator_service = ai_config.get('translator_service', 'google')
        self.subtitle_formats = ai_config.get('subtitle_formats', ['srt', 'vtt'])
        
        # 初始化翻译器
        if self.translate_to_chinese:
            self.translator = GoogleTranslator(
                source='en', 
                target='zh-CN', 
                proxies={"http": proxy, "https": proxy} if proxy else None
            )

    def transcribe(self, audio_path: Path) -> Optional[Path]:
        console.print(f"🧠 正在转录音频: {audio_path.name}", style="bold green")
        console.print(f"🤖 使用Whisper模型: {self.whisper_model}", style="bold blue")
        
        final_srt_path = self.download_folder / f"{audio_path.stem}.en.srt"
        # 根据配置的模型构建模型路径
        model_filename = f"ggml-{self.whisper_model}.bin"
        model_path = Path.home() / ".cache/whisper/whisper.cpp" / model_filename
        
        if not model_path.exists():
            log.error(f"模型文件未找到: {model_path}")
            console.print(f"❌ 请确保Whisper模型 '{self.whisper_model}' 已下载", style="bold red")
            return None
        
        cmd = ['whisper-cli', '-m', str(model_path.resolve()), '-l', 'en', str(audio_path.resolve())]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            if not res.stdout.strip(): 
                raise ValueError(f"Whisper转录输出为空。\nSTDERR: {res.stderr}")
            
            with open(final_srt_path, 'w', encoding='utf-8') as f:
                for i, m in enumerate(re.finditer(r"\[(.*?)\]\s+(.*)", res.stdout), 1):
                    times, text = m.groups()
                    start, end = [t.strip().replace('.', ',') for t in times.split('-->')]
                    f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                    
            console.print(f"✅ 英文字幕已生成: {final_srt_path.name}", style="bold green")
            return final_srt_path
        except Exception as e:
            log.error(f"转录失败: {e}")
            return None

    def process_item(self, file_prefix: str, audio_source_path: Path):
        console.print("[bold cyan]🧠 AI字幕生成流程启动...[/bold cyan]")
        if self._check_for_existing_subs(file_prefix): 
            return
        
        en_srt_path = self.transcribe(audio_source_path)
        if en_srt_path:
            # 根据配置决定是否翻译
            if self.translate_to_chinese:
                zh_srt_path = self._translate(en_srt_path)
                if zh_srt_path:
                    self._merge(en_srt_path, zh_srt_path)
            else:
                console.print(f"✅ 英文字幕生成完成，根据配置跳过翻译", style="bold green")
    
    def _check_for_existing_subs(self, file_prefix: str) -> bool:
        if list(self.download_folder.glob(f"{file_prefix}*.srt")):
            log.info(f"    ℹ️ 检测到已有字幕，跳过AI生成。")
            return True
        return False
        
    def _translate(self, srt_path_in: Path) -> Optional[Path]:
        if not self.translate_to_chinese:
            return None
            
        console.print(f"✍️ 正在翻译字幕: {srt_path_in.name}", style="bold blue")
        
        srt_path_out = srt_path_in.with_suffix('.zh-CN.srt')
        try:
            with open(srt_path_in, 'r', encoding='utf-8') as f_in: content = f_in.read()
            text_blocks = [m.group(1).replace('\n', ' ') for m in re.finditer(r'\d+\n[\d:,->\s]+\n(.*?)\n\n', content, re.DOTALL)]
            if not text_blocks: return srt_path_out
            
            chunk_size = 10
            chunks = [text_blocks[i:i+chunk_size] for i in range(0, len(text_blocks), 10)]
            translated_blocks = []
            
            def worker(chunk: List[str]):
                time.sleep(0.5)
                return self.translator.translate_batch(chunk)
                
            with ThreadPoolExecutor(max_workers=5) as executor:
                for res_chunk in executor.map(worker, chunks):
                    if res_chunk: translated_blocks.extend(res_chunk)
                    
            if len(text_blocks) != len(translated_blocks): 
                raise ValueError(f"翻译返回片段数({len(translated_blocks)})与原文({len(text_blocks)})不匹配。")
                
            it = iter(translated_blocks)
            new_content = re.sub(r'(\d+\n[\d:,->\s]+\n)(.+?)(\n\n)', 
                               lambda m: m.group(1) + next(it, "").strip() + m.group(3), 
                               content, flags=re.DOTALL)
                               
            with open(srt_path_out, 'w', encoding='utf-8') as f_out: f_out.write(new_content)
            console.print(f"✅ 中文字幕已生成: {srt_path_out.name}", style="bold green")
            return srt_path_out
        except Exception as e:
            log.error(f"翻译失败: {e}")
            return None

    def _merge(self, en_srt: Path, zh_srt: Path) -> Optional[Path]:
        console.print("🤝 正在合并字幕...", style="bold magenta")
        
        bi_srt = en_srt.with_suffix('.bilingual.srt')
        try:
            with open(en_srt, 'r', encoding='utf-8') as f: en_c = f.read()
            with open(zh_srt, 'r', encoding='utf-8') as f: zh_c = f.read()
            # 修复：正确解析SRT格式 - 序号\n时间戳\n字幕文本\n\n
            en_s = {m[1]:m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n',en_c,re.DOTALL)}
            zh_s = {m[1]:m[3].strip() for m in re.finditer(r'(\d+)\n(.*?)\n(.*?)\n\n',zh_c,re.DOTALL)}
            ts = {m[1]:m[2].strip() for m in re.finditer(r'(\d+)\n(.*?)\n',en_c)}
            with open(bi_srt, 'w', encoding='utf-8') as f:
                for i in sorted(ts.keys(), key=int):
                    f.write(f"{i}\n{ts[i]}\n{zh_s.get(i, '')}\n{en_s.get(i, '')}\n\n")
            console.print(f"✅ 双语字幕已生成: {bi_srt.name}", style="bold green")
            return bi_srt
        except Exception as e:
            log.error(f"字幕合并失败: {e}")
            return None