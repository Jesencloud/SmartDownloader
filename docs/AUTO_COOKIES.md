# 自动Cookies功能使用说明

## 功能概述

SmartDownloader现在支持自动从浏览器获取cookies，无需手动导出cookies.txt文件。

## 支持的浏览器

- **Chrome** (推荐)
- **Firefox** 
- **Edge**
- **Safari** (macOS，基础支持)

## 使用方法

### 1. 默认行为（推荐）
```bash
python main.py urls.txt -b --mode video
```
- 优先使用手动cookies.txt文件（如果存在）
- 如果没有cookies.txt文件，自动从浏览器获取

### 2. 强制自动获取cookies
```bash
python main.py urls.txt -b --mode video --auto-cookies
```
- 即使存在cookies.txt文件，也强制从浏览器获取新的cookies

### 3. 指定浏览器类型
```bash
python main.py urls.txt -b --mode video --auto-cookies --browser chrome
```
支持的浏览器类型：
- `auto` (默认，自动检测)
- `chrome`
- `firefox` 
- `edge`
- `safari`

### 4. 跳过所有cookies
```bash
python main.py urls.txt -b --mode video --no-cookies
```
- 完全跳过cookies（手动和自动）

## 工作原理

1. **自动检测**：程序会尝试从系统中找到浏览器的cookies数据库
2. **安全读取**：复制数据库到临时文件进行读取，不影响浏览器使用
3. **域名过滤**：只提取与下载URL相关的cookies
4. **格式转换**：自动转换为yt-dlp兼容的Netscape格式
5. **文件保存**：保存为cookies.txt文件供下载使用

## 优势

- ✅ **自动化**：无需手动导出cookies
- ✅ **实时**：每次下载都获取最新的cookies
- ✅ **安全**：只读取必要的cookies信息
- ✅ **兼容**：支持多种主流浏览器
- ✅ **智能**：自动检测和回退机制

## 注意事项

1. **权限要求**：首次使用可能需要授权访问浏览器数据
2. **浏览器状态**：建议在浏览器登录状态下使用
3. **macOS安全**：可能需要在系统设置中授权终端访问
4. **备份建议**：重要cookies建议手动备份

## 故障排除

### 无法获取cookies
1. 确保浏览器已登录目标网站
2. 检查系统权限设置
3. 尝试指定具体浏览器类型
4. 使用`--no-cookies`跳过cookies

### 权限被拒绝
1. **macOS**: 系统设置 > 安全性与隐私 > 完全磁盘访问权限 > 添加终端
2. **Windows**: 以管理员身份运行命令行
3. **Linux**: 检查cookies文件夹权限

## 示例输出

```
🔍 用户指定自动获取cookies (--auto-cookies)...
🍪 正在为 https://www.bilibili.com/video/xxx 从chrome浏览器自动提取cookies...
✅ 成功自动获取cookies: /path/to/cookies.txt
```

## 兼容性

- ✅ 与现有手动cookies.txt完全兼容
- ✅ 支持所有现有下载模式
- ✅ 不影响其他功能的使用