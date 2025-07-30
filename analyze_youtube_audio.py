#!/usr/bin/env python3
"""
分析具体YouTube视频的音频流信息
"""

import json
import subprocess
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def get_video_formats(url):
    """获取视频的所有格式信息"""
    print(f"🔍 分析视频: {url}")

    try:
        # 使用项目中的yt-dlp二进制文件
        yt_dlp_path = project_root / "bin" / "yt-dlp_macos"
        if not yt_dlp_path.exists():
            yt_dlp_path = project_root / "bin" / "yt-dlp"

        if not yt_dlp_path.exists():
            print(f"❌ 找不到yt-dlp二进制文件: {yt_dlp_path}")
            print("尝试使用系统yt-dlp...")
            yt_dlp_path = "yt-dlp"

        # 使用dump-json获取完整的视频信息
        cmd = [str(yt_dlp_path), "--dump-json", "--no-download", url]

        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            print(f"❌ yt-dlp执行失败: {result.stderr}")
            print(f"stdout: {result.stdout}")
            return None

        if not result.stdout.strip():
            print("❌ yt-dlp返回空输出")
            return None

        # 解析JSON输出
        video_info = json.loads(result.stdout)
        return video_info

    except subprocess.TimeoutExpired:
        print("❌ 请求超时")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        print(f"原始输出: {result.stdout[:500]}...")
        return None
    except Exception as e:
        print(f"❌ 获取格式信息失败: {e}")
        return None


def analyze_audio_streams(video_info):
    """分析音频流信息"""
    if not video_info or "formats" not in video_info:
        print("❌ 无效的视频信息")
        return

    print("\n📊 音频流分析:")
    print("=" * 80)

    # 找出所有音频流
    audio_formats = []
    for fmt in video_info["formats"]:
        format_id = fmt.get("format_id", "")

        # 检查是否是音频流（特别关注140开头的格式）
        if fmt.get("vcodec") == "none" or fmt.get("acodec") and fmt.get("acodec") != "none" and not fmt.get("vcodec"):
            audio_formats.append(fmt)

    # 按format_id排序
    audio_formats.sort(key=lambda x: x.get("format_id", ""))

    # 特别查找140-9和140-10
    target_formats = []
    for fmt in audio_formats:
        format_id = fmt.get("format_id", "")
        if format_id in ["140-9", "140-10"] or format_id.startswith("140"):
            target_formats.append(fmt)

    print(f"找到 {len(audio_formats)} 个音频流")
    print(f"其中 {len(target_formats)} 个140系列音频流")

    print("\n🎯 140系列音频流详情:")
    print("-" * 80)

    for i, fmt in enumerate(target_formats):
        format_id = fmt.get("format_id", "unknown")
        abr = fmt.get("abr", "N/A")
        acodec = fmt.get("acodec", "N/A")
        ext = fmt.get("ext", "N/A")
        format_note = fmt.get("format_note", "N/A")
        language = fmt.get("language", "N/A")
        format_desc = fmt.get("format", "N/A")

        print(f"\n格式 {i + 1}: {format_id}")
        print(f"  比特率: {abr} kbps")
        print(f"  编解码器: {acodec}")
        print(f"  扩展名: {ext}")
        print(f"  备注: {format_note}")
        print(f"  语言: {language}")
        print(f"  描述: {format_desc}")

        # 检查所有可能包含"original (default)"的字段
        print("  所有字段检查:")
        for key, value in fmt.items():
            if value and isinstance(value, str):
                value_lower = value.lower()
                if any(keyword in value_lower for keyword in ["original", "default", "main", "primary"]):
                    print(f"    🎯 {key}: {value}")

    return target_formats


def main():
    url = "https://youtu.be/1IHOyqN2XPA?si=Lm_XER1WSFn21PGr"

    print("🎬 YouTube音频流分析工具")
    print("=" * 60)

    # 获取视频信息
    video_info = get_video_formats(url)

    if video_info:
        # 分析音频流
        target_formats = analyze_audio_streams(video_info)

        # 如果找到了140-9和140-10，进行详细比较
        format_140_9 = None
        format_140_10 = None

        for fmt in target_formats if target_formats else []:
            format_id = fmt.get("format_id", "")
            if format_id == "140-9":
                format_140_9 = fmt
            elif format_id == "140-10":
                format_140_10 = fmt

        if format_140_9 and format_140_10:
            print("\n🔍 140-9 vs 140-10 详细比较:")
            print("=" * 60)

            print("140-9:")
            print(json.dumps(format_140_9, indent=2, ensure_ascii=False))

            print("\n140-10:")
            print(json.dumps(format_140_10, indent=2, ensure_ascii=False))

        elif format_140_10:
            print("\n🎯 找到140-10格式:")
            print(json.dumps(format_140_10, indent=2, ensure_ascii=False))

        elif format_140_9:
            print("\n⚠️  只找到140-9格式:")
            print(json.dumps(format_140_9, indent=2, ensure_ascii=False))

        else:
            print("\n❌ 没有找到140-9或140-10格式")

    else:
        print("❌ 无法获取视频信息")


if __name__ == "__main__":
    main()
