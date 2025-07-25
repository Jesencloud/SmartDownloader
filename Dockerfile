# 使用一个轻量级的官方 Python 镜像作为基础
FROM python:3.11-slim

# 设置环境变量，防止 Python 写入 .pyc 文件
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 设置工作目录
WORKDIR /app

# 安装系统依赖，包括 redis-cli 用于调试
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    bash \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 准备 yt-dlp 二进制文件
# 从本地上下文复制，而不是在构建时下载，以提高构建的稳定性和可重复性。
# 请确保在运行 `docker-compose build` 之前，`bin/yt-dlp_linux` 文件已存在。
COPY bin/yt-dlp_linux /app/bin/yt-dlp_linux
RUN chmod +x /app/bin/yt-dlp_linux

# 复制所有应用代码到工作目录
COPY . .