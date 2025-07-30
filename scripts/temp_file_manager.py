#!/usr/bin/env python3
"""
临时文件管理脚本
用于监控和清理SmartDownloader产生的临时文件
"""

import argparse
import glob
import os
import shutil
import tempfile
from datetime import datetime, timedelta


class TempFileManager:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()
        # 支持的媒体文件扩展名
        self.media_extensions = [
            "*.mp4",
            "*.m4a",
            "*.mp3",
            "*.webm",
            "*.mkv",
            "*.avi",
            "*.mov",
            "*.flv",
            "*.wmv",
            "*.opus",
            "*.aac",
            "*.ogg",
            "*.wav",
            "*.flac",
        ]
        # SmartDownloader临时文件模式
        self.temp_patterns = [
            "dl_*.mp4",
            "dl_*.m4a",
            "dl_*.mp3",  # SmartDownloader命名模式
            "tmp*.mp4",
            "tmp*.m4a",
            "tmp*.mp3",  # 系统临时文件
        ]

    def get_temp_files(self):
        """获取所有临时媒体文件信息"""
        files_info = []

        # 检查SmartDownloader特定模式的文件
        for pattern in self.temp_patterns:
            files = glob.glob(os.path.join(self.temp_dir, pattern))
            for file_path in files:
                try:
                    stat = os.stat(file_path)
                    files_info.append(
                        {
                            "path": file_path,
                            "name": os.path.basename(file_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime),
                            "is_smartdownloader": file_path.startswith(os.path.join(self.temp_dir, "dl_")),
                        }
                    )
                except OSError:
                    continue

        # 检查所有媒体文件（可能是其他下载工具产生的）
        for pattern in self.media_extensions:
            files = glob.glob(os.path.join(self.temp_dir, pattern))
            for file_path in files:
                # 避免重复添加已经在temp_patterns中的文件
                if any(info["path"] == file_path for info in files_info):
                    continue

                try:
                    stat = os.stat(file_path)
                    # 只显示最近24小时内修改的文件
                    if datetime.fromtimestamp(stat.st_mtime) > datetime.now() - timedelta(hours=24):
                        files_info.append(
                            {
                                "path": file_path,
                                "name": os.path.basename(file_path),
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(stat.st_mtime),
                                "is_smartdownloader": False,
                            }
                        )
                except OSError:
                    continue

        return sorted(files_info, key=lambda x: x["modified"], reverse=True)

    def format_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"

    def show_status(self):
        """显示临时文件状态"""
        print(f"📁 临时目录: {self.temp_dir}")

        # 显示磁盘使用情况
        try:
            total, used, free = shutil.disk_usage(self.temp_dir)
            print(
                f"💾 磁盘空间: 总计 {self.format_size(total)}, "
                f"已用 {self.format_size(used)}, "
                f"可用 {self.format_size(free)} ({free / total * 100:.1f}%)"
            )
        except Exception as e:
            print(f"❌ 无法获取磁盘使用情况: {e}")

        files_info = self.get_temp_files()

        if not files_info:
            print("✅ 没有发现临时媒体文件")
            return

        print(f"\n🔍 发现 {len(files_info)} 个临时媒体文件:")
        print("-" * 80)

        total_size = 0
        smartdownloader_count = 0

        for info in files_info:
            total_size += info["size"]
            if info["is_smartdownloader"]:
                smartdownloader_count += 1
                marker = "🎬"
            else:
                marker = "📄"

            age = datetime.now() - info["modified"]
            if age.total_seconds() < 3600:  # 1小时内
                age_str = f"{int(age.total_seconds() / 60)}分钟前"
            elif age.total_seconds() < 86400:  # 24小时内
                age_str = f"{int(age.total_seconds() / 3600)}小时前"
            else:
                age_str = f"{age.days}天前"

            print(f"{marker} {info['name'][:50]:<50} {self.format_size(info['size']):>8} {age_str:>10}")

        print("-" * 80)
        print(f"📊 总计: {len(files_info)} 个文件, {self.format_size(total_size)}")
        print(f"🎬 SmartDownloader: {smartdownloader_count} 个文件")
        print(f"📄 其他工具: {len(files_info) - smartdownloader_count} 个文件")

    def clean_files(self, older_than_hours=1, dry_run=False, smartdownloader_only=False):
        """清理临时文件"""
        files_info = self.get_temp_files()

        if not files_info:
            print("✅ 没有临时文件需要清理")
            return

        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        files_to_clean = []

        for info in files_info:
            # 如果只清理SmartDownloader文件
            if smartdownloader_only and not info["is_smartdownloader"]:
                continue

            # 检查文件年龄
            if info["modified"] < cutoff_time:
                files_to_clean.append(info)

        if not files_to_clean:
            print(f"✅ 没有超过 {older_than_hours} 小时的文件需要清理")
            return

        total_size = sum(info["size"] for info in files_to_clean)

        if dry_run:
            print(f"🔍 模拟清理 {len(files_to_clean)} 个文件 ({self.format_size(total_size)}):")
            for info in files_to_clean:
                print(f"  - {info['name']} ({self.format_size(info['size'])})")
            print("\n💡 使用 --execute 参数执行实际清理")
            return

        print(f"🧹 开始清理 {len(files_to_clean)} 个文件 ({self.format_size(total_size)})...")

        cleaned_count = 0
        cleaned_size = 0
        errors = []

        for info in files_to_clean:
            try:
                os.remove(info["path"])
                cleaned_count += 1
                cleaned_size += info["size"]
                print(f"✅ 已删除: {info['name']}")
            except Exception as e:
                errors.append(f"❌ 删除失败 {info['name']}: {e}")

        print("\n📊 清理完成:")
        print(f"✅ 成功删除: {cleaned_count} 个文件 ({self.format_size(cleaned_size)})")

        if errors:
            print(f"❌ 删除失败: {len(errors)} 个文件")
            for error in errors:
                print(f"  {error}")


def main():
    parser = argparse.ArgumentParser(description="SmartDownloader临时文件管理器")
    parser.add_argument("action", choices=["status", "clean"], help="操作类型")
    parser.add_argument("--older-than", type=int, default=1, help="清理超过指定小时数的文件 (默认: 1小时)")
    parser.add_argument("--dry-run", action="store_true", help="模拟清理，不实际删除文件")
    parser.add_argument("--execute", action="store_true", help="执行实际清理")
    parser.add_argument("--smartdownloader-only", action="store_true", help="只处理SmartDownloader产生的文件")

    args = parser.parse_args()

    manager = TempFileManager()

    if args.action == "status":
        manager.show_status()
    elif args.action == "clean":
        if not args.execute and not args.dry_run:
            args.dry_run = True  # 默认为模拟模式

        manager.clean_files(
            older_than_hours=args.older_than, dry_run=args.dry_run, smartdownloader_only=args.smartdownloader_only
        )


if __name__ == "__main__":
    main()
