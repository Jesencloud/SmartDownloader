#!/bin/bash

# ==============================================================================
#  SmartDownloader - yt-dlp Binary Updater
# ==============================================================================
#
#  This script automates the process of downloading the latest yt-dlp binaries
#  for macOS, Linux, and Windows, placing them in the `bin/` directory with
#  the correct platform-specific names expected by the application.
#
#  Usage:
#  Run this script from the project root directory:
#  ./update_binaries.sh
#
# ==============================================================================

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
BASE_URL="https://github.com/yt-dlp/yt-dlp/releases"
BIN_DIR="bin"

# Define platform-specific binaries in a single string for better compatibility.
# Format: "platform_name:source_filename:target_filename"
PLATFORMS="
linux:yt-dlp:yt-dlp_linux
macos:yt-dlp_macos:yt-dlp_macos
windows:yt-dlp.exe:yt-dlp.exe
"

echo "🚀 Starting yt-dlp binary update for all platforms..."
mkdir -p "$BIN_DIR" # Ensure the bin directory exists

# Use a standard `for` loop over the multi-line string
for entry in $PLATFORMS; do
    # Use IFS to split the entry by ':'
    IFS=':' read -r platform source_file target_file <<< "$entry"

    download_url="$BASE_URL/$source_file"

    echo "   -> Downloading for ${platform}... (${target_file})"
    curl -L --progress-bar "$download_url" -o "${BIN_DIR}/${target_file}"

    # Make Linux and macOS binaries executable
    if [[ "$platform" == "linux" || "$platform" == "macos" ]]; then
        chmod +x "${BIN_DIR}/${target_file}"
    fi
done

echo ""
echo "🎉 All binaries updated successfully in the '${BIN_DIR}' directory!"