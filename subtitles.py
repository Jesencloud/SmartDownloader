# subtitles.py
import time, re, subprocess
from pathlib import Path
from typing import Optional, List
# 【核心修复】导入并发处理所需的 ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor

try:
    from deep_translator import GoogleTranslator
    AI_LIBRARIES_AVAILABLE = True
except ImportError:
    AI_LIBRARIES_AVAILABLE = False

class SubtitleProcessor:
    """
    负责所有与AI字幕生成相关的任务。
    【最终导入修复版】
    """
    def __init__(self, download_folder: Path, proxy: Optional[str] = None):
        if not AI_LIBRARIES_AVAILABLE: raise ImportError("AI库 `deep-translator` 未安装。")
        self.download_folder = download_folder
        self.translator = GoogleTranslator(source='en', target='zh-CN', proxies={"http": proxy, "https": proxy} if proxy else None)

    def transcribe(self, audio_path: Path) -> Optional[Path]:
        print(f"    🚀 [whisper-cli] 正在从 '{audio_path.name}' 高速转录英文语音...")
        final_srt_path = self.download_folder / f"{audio_path.stem}.en.srt"
        model_path = Path.home() / ".cache/whisper/whisper.cpp/ggml-base.en.bin"
        if not model_path.exists():
            print(f"    ❌ 找不到 whisper-cli 模型文件！请手动下载。")
            return None
        
        cmd = ['whisper-cli', '-m', str(model_path.resolve()), '-l', 'en', str(audio_path.resolve())]
        try:
            process = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            stdout_content = process.stdout.strip()
            if not stdout_content: raise ValueError(f"Whisper转录输出为空。\n[STDERR]:\n{process.stderr}")
            
            with open(final_srt_path, 'w', encoding='utf-8') as f:
                for i, m in enumerate(re.finditer(r"\[(.*?)\]\s+(.*)", stdout_content), 1):
                    times, text = m.groups()
                    start, end = [t.strip().replace('.', ',') for t in times.split('-->')]
                    f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
            print(f"    ✅ [whisper-cli] 英文SRT字幕已生成: {final_srt_path.name}"); return final_srt_path
        except Exception as e:
            print(f"    ❌ [whisper-cli] 转录失败: {e}"); return None

    def process_item(self, file_prefix: str, audio_source_path: Path):
        print("\n" + "-" * 25); print("  🧠 AI字幕生成流程启动...")
        if self._check_for_existing_subs(file_prefix): return
        en_srt_path = self.transcribe(audio_source_path)
        if en_srt_path:
            zh_srt_path = self.translate(en_srt_path)
            if zh_srt_path:
                self.merge(en_srt_path, zh_srt_path)
    
    def _check_for_existing_subs(self, file_prefix: str) -> bool:
        if list(self.download_folder.glob(f"{file_prefix}*.srt")):
            print(f"    ℹ️ 检测到已有字幕，跳过AI生成。"); return True
        return False
        
    def translate(self, srt_path_in: Path) -> Optional[Path]:
        """使用线程池并发执行分块翻译任务。"""
        print(f"    ✍️ [Translator] 正在并发翻译 '{srt_path_in.name}'...")
        srt_path_out = srt_path_in.with_suffix('.zh-CN.srt')
        
        try:
            with open(srt_path_in, 'r', encoding='utf-8') as f_in:
                content = f_in.read()
            
            text_blocks = [m.group(1).replace('\n', ' ') for m in re.finditer(r'\d+\n[\d:,->\s]+\n(.*?)\n\n', content, re.DOTALL)]
            if not text_blocks:
                return srt_path_out

            chunk_size = 10
            chunks = [text_blocks[i:i+chunk_size] for i in range(0, len(text_blocks), chunk_size)]
            print(f"      -> 将 {len(text_blocks)} 句字幕分为 {len(chunks)} 个区块并行处理...")
            
            translated_blocks = []
            
            def translate_chunk_worker(chunk: List[str]) -> List[str]:
                time.sleep(0.5)
                return self.translator.translate_batch(chunk)

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = executor.map(translate_chunk_worker, chunks)
                for result_chunk in results:
                    # 检查返回的是否是None，避免错误
                    if result_chunk:
                        translated_blocks.extend(result_chunk)

            if len(text_blocks) != len(translated_blocks):
                raise ValueError(f"翻译返回的片段数({len(translated_blocks)})与原文({len(text_blocks)})不匹配。")

            it_translated = iter(translated_blocks)
            def replace_func(match): return next(it_translated, "").strip()
            new_content = re.sub(r'(\d+\n[\d:,->\s]+\n)(.+?)(\n\n)', lambda m: m.group(1) + replace_func(m) + m.group(3), content, flags=re.DOTALL)
            
            with open(srt_path_out, 'w', encoding='utf-8') as f_out:
                f_out.write(new_content)
                
            print(f"    ✅ [Translator] 中文SRT字幕已生成: {srt_path_out.name}")
            return srt_path_out
        except Exception as e:
            print(f"    ❌ [Translator] 翻译失败: {e}")
            return None

    def merge(self, en_srt_path: Path, zh_srt_path: Path) -> Optional[Path]:
        """合并中英文字幕。"""
        print(f"    🤝 [Merger] 正在合并字幕...")
        bilingual_srt_path = en_srt_path.with_suffix('.bilingual.srt')
        try:
            with open(en_srt_path, 'r', encoding='utf-8') as f: en_c = f.read()
            with open(zh_srt_path, 'r', encoding='utf-8') as f: zh_c = f.read()
            en_s = {m.group(1): m.group(3).strip() for m in re.finditer(r'(\d+)\n([\d:,->\s]+\n(.*?))\n\n', en_c, re.DOTALL)}
            zh_s = {m.group(1): m.group(3).strip() for m in re.finditer(r'(\d+)\n([\d:,->\s]+\n(.*?))\n\n', zh_c, re.DOTALL)}
            ts = {m.group(1): m.group(2).strip() for m in re.finditer(r'(\d+)\n([\d:,->\s]+\n)', en_c)}
            with open(bilingual_srt_path, 'w', encoding='utf-8') as f_out:
                for index in sorted(ts.keys(), key=int):
                    f_out.write(f"{index}\n{ts[index]}\n{zh_s.get(index, '')}\n{en_s.get(index, '')}\n\n")
            print(f"    ✅ [Merger] 双语SRT字幕已生成: {bilingual_srt_path.name}"); return bilingual_srt_path
        except Exception as e:
            print(f"    ❌ [Merger] 字幕合并失败: {e}"); return None