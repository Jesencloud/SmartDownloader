#!/usr/bin/env python3
"""
调试X.com链接格式处理的脚本
"""

import json
import subprocess
import sys
from pathlib import Path

# 添加项目根目录到path
sys.path.insert(0, str(Path(__file__).parent))


def test_yt_dlp_raw_output():
    """测试yt-dlp的原始输出"""
    print("=== 测试yt-dlp原始输出 ===")
    
    url = "https://x.com/ilovecatlovecar/status/1948010001639014429"
    
    try:
        cmd = [
            'yt-dlp',
            '--print-json',
            '--no-download',
            '--no-warnings',
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            try:
                video_data = json.loads(result.stdout.strip())
                print("✅ yt-dlp成功获取数据")
                print(f"📊 标题: {video_data.get('title', 'N/A')}")
                print(f"🎬 格式数量: {len(video_data.get('formats', []))}")
                print(f"🆔 实际ID: {video_data.get('id', 'N/A')}")
                
                # 显示前几个格式的详细信息
                formats = video_data.get('formats', [])[:6]
                print("\n📋 格式详情:")
                for i, fmt in enumerate(formats):
                    print(f"  {i+1}. {fmt.get('format_id'):>20} | {fmt.get('ext'):>4} | {fmt.get('vcodec'):>12} | {fmt.get('acodec'):>12} | {fmt.get('width', 'N/A')}x{fmt.get('height', 'N/A')}")
                
                return video_data
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"原始输出: {result.stdout[:500]}...")
                return None
        else:
            print(f"❌ yt-dlp失败: {result.stderr}")
            return None
            
    except subprocess.TimeoutExpired:
        print("❌ yt-dlp超时")
        return None
    except Exception as e:
        print(f"❌ yt-dlp异常: {e}")
        return None

def test_web_api_processing():
    """测试Web API的处理逻辑"""
    print("\n=== 测试Web API处理逻辑 ===")
    
    # 使用实际的X.com格式数据进行测试
    mock_video_data_raw = {
        'title': '阿米爱猫咪 - 好乖，给我rua一下🥰🥰',
        'formats': [
            # 音频流
            {
                "format_id": "hls-audio-32000-Audio",
                "ext": "mp4",
                "vcodec": "none",
                "acodec": None,
                "width": None,
                "height": None
            },
            {
                "format_id": "hls-audio-64000-Audio",
                "ext": "mp4",
                "vcodec": "none",
                "acodec": None,
                "width": None,
                "height": None
            },
            {
                "format_id": "hls-audio-128000-Audio",
                "ext": "mp4",
                "vcodec": "none",
                "acodec": None,
                "width": None,
                "height": None
            },
            # 完整流 - null编解码器
            {
                "format_id": "http-632",
                "ext": "mp4",
                "vcodec": None,
                "acodec": None,
                "width": 320,
                "height": 568
            },
            {
                "format_id": "http-950",
                "ext": "mp4",
                "vcodec": None,
                "acodec": None,
                "width": 480,
                "height": 852
            },
            {
                "format_id": "http-2176",
                "ext": "mp4",
                "vcodec": None,
                "acodec": None,
                "width": 720,
                "height": 1280
            },
            # 视频流 - video only
            {
                "format_id": "hls-347",
                "ext": "mp4",
                "vcodec": "avc1.4D401E",
                "acodec": "none",
                "width": 320,
                "height": 568
            },
            {
                "format_id": "hls-688",
                "ext": "mp4",
                "vcodec": "avc1.4D401F",
                "acodec": "none",
                "width": 480,
                "height": 852
            },
            {
                "format_id": "hls-1416",
                "ext": "mp4",
                "vcodec": "avc1.640020",
                "acodec": "none",
                "width": 720,
                "height": 1280
            }
        ]
    }
    
    try:
        print("✅ 使用模拟数据测试Web API处理逻辑")
        print(f"📊 标题: {mock_video_data_raw.get('title', 'N/A')}")
        print(f"🎬 原始格式数量: {len(mock_video_data_raw.get('formats', []))}")
        
        # 模拟Web API的格式处理逻辑
        raw_formats = mock_video_data_raw.get('formats', [])
        
        # Part 1: Process pre-merged (complete) MP4 formats
        complete_formats_raw = []
        for f in raw_formats:
            if (f.get('ext') == 'mp4' and 
                f.get('width') and f.get('height')):  # 必须有分辨率信息
                
                vcodec = f.get('vcodec')
                acodec = f.get('acodec')
                
                # 包含以下情况：
                # 1. 明确的编解码器（非none）
                # 2. unknown编解码器（通常是完整流）
                # 3. null编解码器但有分辨率（X.com等平台的完整流）
                # 4. 排除明确标记为单一类型的流
                if ((vcodec not in ('none', None, '') and acodec not in ('none', None, '')) or
                    (vcodec == 'unknown' and acodec == 'unknown') or
                    (vcodec is None and acodec is None)):  # 处理null编解码器的完整流
                    # 排除明确标记为单一类型的流
                    if vcodec != 'audio only' and acodec != 'video only':
                        complete_formats_raw.append(f)
        
        print(f"🚀 筛选出的完整流: {len(complete_formats_raw)}")
        for fmt in complete_formats_raw:
            vcodec_str = str(fmt.get('vcodec')) if fmt.get('vcodec') is not None else 'null'
            acodec_str = str(fmt.get('acodec')) if fmt.get('acodec') is not None else 'null'
            print(f"  - {fmt.get('format_id'):>15} | {vcodec_str:>12} | {acodec_str:>12} | {fmt.get('width')}x{fmt.get('height')}")
        
        # Part 2: Process formats that need merging into MP4
        video_only_formats = [f for f in raw_formats if f.get('vcodec') not in ('none', None) and f.get('acodec') in ('none', None) and f.get('width') and f.get('height')]
        audio_only_formats = [f for f in raw_formats if f.get('acodec') not in ('none', None) and f.get('vcodec') in ('none', None)]
        
        print(f"⚡ 视频流: {len(video_only_formats)}")
        print(f"🎵 音频流: {len(audio_only_formats)}")
        
        # 计算最终格式数量
        final_format_count = len(complete_formats_raw)
        if video_only_formats and audio_only_formats:
            final_format_count += len(video_only_formats)  # 每个视频流都会与最佳音频流配对
        
        print(f"📊 最终格式数量: {final_format_count}")
        
        if final_format_count == 0:
            print("❌ 没有可用格式！这就是问题所在。")
            return False
        else:
            print("✅ 有可用格式。")
            return True
            
    except Exception as e:
        print(f"❌ Web API处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_format_filtering_issue():
    """测试格式筛选问题"""
    print("\n=== 分析格式筛选问题 ===")
    
    # 根据实际X.com的格式数据，测试null编解码器处理
    mock_formats = [
        # 音频流 - vcodec为none，acodec为null
        {
            "format_id": "hls-audio-32000-Audio",
            "ext": "mp4",
            "vcodec": "none",
            "acodec": None,
            "width": None,
            "height": None
        },
        {
            "format_id": "hls-audio-64000-Audio", 
            "ext": "mp4",
            "vcodec": "none",
            "acodec": None,
            "width": None,
            "height": None
        },
        {
            "format_id": "hls-audio-128000-Audio",
            "ext": "mp4",
            "vcodec": "none", 
            "acodec": None,
            "width": None,
            "height": None
        },
        # 完整流 - vcodec和acodec都是null，但有分辨率
        {
            "format_id": "http-632",
            "ext": "mp4",
            "vcodec": None,
            "acodec": None, 
            "width": 320,
            "height": 568
        },
        {
            "format_id": "http-950",
            "ext": "mp4",
            "vcodec": None,
            "acodec": None,
            "width": 480,
            "height": 852
        },
        {
            "format_id": "http-2176",
            "ext": "mp4",
            "vcodec": None,
            "acodec": None,
            "width": 720,
            "height": 1280
        },
        # 视频流 - video only
        {
            "format_id": "hls-347",
            "ext": "mp4", 
            "vcodec": "avc1.4D401E",
            "acodec": "none",
            "width": 320,
            "height": 568
        },
        {
            "format_id": "hls-688",
            "ext": "mp4",
            "vcodec": "avc1.4D401F",
            "acodec": "none",
            "width": 480,
            "height": 852
        },
        {
            "format_id": "hls-1416",
            "ext": "mp4",
            "vcodec": "avc1.640020", 
            "acodec": "none",
            "width": 720,
            "height": 1280
        }
    ]
    
    print("测试筛选逻辑...")
    
    # 测试完整流筛选 - 更新后的逻辑
    complete_formats = []
    for f in mock_formats:
        if (f.get('ext') == 'mp4' and 
            f.get('width') and f.get('height')):  # 必须有分辨率信息
            
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            
            # 包含以下情况：
            # 1. 明确的编解码器（非none）
            # 2. unknown编解码器（通常是完整流）
            # 3. null编解码器但有分辨率（X.com等平台的完整流）
            if ((vcodec not in ('none', None, '') and acodec not in ('none', None, '')) or
                (vcodec == 'unknown' and acodec == 'unknown') or
                (vcodec is None and acodec is None)):  # 处理null编解码器的完整流
                if vcodec != 'audio only' and acodec != 'video only':
                    complete_formats.append(f)
    
    print(f"完整流筛选结果: {len(complete_formats)}")
    for fmt in complete_formats:
        vcodec_str = str(fmt['vcodec']) if fmt['vcodec'] is not None else 'null'
        acodec_str = str(fmt['acodec']) if fmt['acodec'] is not None else 'null'
        print(f"  ✅ {fmt['format_id']}: {vcodec_str} + {acodec_str}")
    
    # 测试视频流筛选
    video_only = [f for f in mock_formats if f.get('vcodec') not in ('none', None) and f.get('acodec') in ('none', None) and f.get('width') and f.get('height')]
    audio_only = [f for f in mock_formats if f.get('acodec') not in ('none', None) and f.get('vcodec') in ('none', None)]
    
    print(f"视频流: {len(video_only)}")
    print(f"音频流: {len(audio_only)}")
    
    total_final_formats = len(complete_formats)
    if video_only and audio_only:
        total_final_formats += len(video_only)
    
    print(f"最终可用格式: {total_final_formats}")
    
    return total_final_formats > 0

def main():
    """主函数"""
    print("🔍 调试X.com链接格式处理问题\n")
    
    # 测试1: yt-dlp原始输出
    raw_data = test_yt_dlp_raw_output()
    
    # 测试2: Web API处理
    api_success = test_web_api_processing()
    
    # 测试3: 格式筛选逻辑
    filter_success = test_format_filtering_issue()
    
    print(f"\n{'='*50}")
    print("📊 调试结果总结")
    print('='*50)
    
    print(f"yt-dlp原始数据: {'✅' if raw_data else '❌'}")
    print(f"Web API处理: {'✅' if api_success else '❌'}")
    print(f"格式筛选逻辑: {'✅' if filter_success else '❌'}")
    
    if not api_success:
        print("\n🔍 问题分析:")
        print("   Web API无法正确处理X.com格式")
        print("   可能原因:")
        print("   1. 筛选条件过于严格")
        print("   2. 格式处理逻辑存在bug")
        print("   3. 缓存或其他异常问题")
        
        return False
    else:
        print("\n✅ 格式处理逻辑正常，问题可能在其他地方")
        return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  调试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 调试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)