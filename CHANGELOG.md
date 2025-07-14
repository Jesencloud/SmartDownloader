# 更新日志

所有此项目的版本变更都将记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。


---

## [1.9.0] - 2025-07-14

### Changed (简化下载逻辑，不再依赖yt-dlp -F解析)
   1. 简化 `downloader.py`：移除了所有手动解析 yt-dlp -F 输出的逻辑，避免了因解析不可靠导致的各种问题。
   2. 强化 `core/command_builder.py`：在构建合并命令时，加入了 --merge-output-format mp4 标志。这个标志会强制 yt-dlp
      在合并时输出为 MP4 格式，并在需要时自动进行转码，从而解决了音视频流不兼容导致的合并失败问题。

### 优化
-  视频音频进度条显示问题，回归下载完显示“✅”标记


### Fixed (问题修复)
-   config.yaml调整下载参数，修复AuthenticationException抛出的cookies刷新功能  
  
### 重大变化
-   版本号管理：release版本以x.x.0,如1.9.0。分支如1.9.1之类。
