#!/bin/bash
# SmartDownloader 临时文件管理便捷脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP_MANAGER="$SCRIPT_DIR/temp_file_manager.py"

# 检查临时文件状态
temp-status() {
    echo "🔍 检查临时文件状态..."
    python3 "$TEMP_MANAGER" status
}

# 模拟清理（安全预览）
temp-clean-preview() {
    local hours=${1:-1}
    echo "🔍 模拟清理超过 $hours 小时的临时文件..."
    python3 "$TEMP_MANAGER" clean --older-than "$hours" --dry-run
}

# 执行清理
temp-clean() {
    local hours=${1:-1}
    echo "🧹 清理超过 $hours 小时的临时文件..."
    python3 "$TEMP_MANAGER" clean --older-than "$hours" --execute
}

# 只清理SmartDownloader的文件
temp-clean-sd() {
    local hours=${1:-1}
    echo "🎬 清理SmartDownloader超过 $hours 小时的文件..."
    python3 "$TEMP_MANAGER" clean --older-than "$hours" --execute --smartdownloader-only
}

# 显示帮助
temp-help() {
    echo "SmartDownloader 临时文件管理命令:"
    echo ""
    echo "  temp-status                    - 查看临时文件状态"
    echo "  temp-clean-preview [小时]      - 预览要清理的文件 (默认1小时)"
    echo "  temp-clean [小时]              - 清理临时文件 (默认1小时)"
    echo "  temp-clean-sd [小时]           - 只清理SmartDownloader文件"
    echo "  temp-help                      - 显示此帮助"
    echo ""
    echo "示例:"
    echo "  temp-status                    - 查看当前状态"
    echo "  temp-clean-preview 2           - 预览2小时前的文件"
    echo "  temp-clean 6                   - 清理6小时前的文件"
    echo "  temp-clean-sd 0.5              - 清理30分钟前的SD文件"
}

# 如果脚本被直接调用，显示帮助
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    temp-help
fi