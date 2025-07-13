# 更新日志

所有此项目的版本变更都将记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。


---

## [1.8.0] - 2025-07-13

### Changed (简化下载逻辑，不再依赖yt-dlp -F解析)
   1. 简化 `downloader.py`：移除了所有手动解析 yt-dlp -F 输出的逻辑，避免了因解析不可靠导致的各种问题。
   2. 强化 `core/command_builder.py`：在构建合并命令时，加入了 --merge-output-format mp4 标志。这个标志会强制 yt-dlp
      在合并时输出为 MP4 格式，并在需要时自动进行转码，从而解决了音视频流不兼容导致的合并失败问题。

- **优化下载进度条**:
  - 使用已用时间（`TimeElapsedColumn`）替换剩余时间，显示更直观。
  - 删除自定义速度列（`CustomSpeedColumn`），在下载完成后显示绿色的 "✅" 标志，并在下载中显示实时速度。会反复引起代码调用rich异常。

### Fixed (问题修复)

- **修复日志文件**: 解决高分辨率需要会员才能观看问题。
- 核心目标是让程序在下载前检查视频格式时，如果遇到 "become a premium
  member"（需要付费会员）的提示，能自动更新 Cookies 并重试，而不是直接失败。

  实现思路如下：

   1. 责任分离与逻辑转移：
       * 最初，获取并解析视频格式的逻辑在 core/command_builder.py
         中。为了处理需要重试的复杂情况（如刷新 Cookies），我将这部分逻辑移到了
         downloader.py 中。
       * 这样一来，command_builder.py 的职责更纯粹，只负责根据指令“构建”命令。而
         downloader.py
         作为流程的“编排者”，负责执行命令、处理输出、应对异常并决定是否重试。

   2. 实现自动刷新 Cookies：
       * 在 downloader.py 中，我创建了新的 _get_available_formats 方法，专门用于调用
         yt-dlp --list-formats。
       * 此方法会检查命令的输出。一旦发现 "become a premium member" 关键字，它会调用
         auto_cookies.py 中的 main 函数来触发浏览器 Cookies 的刷新。
       * 刷新成功后，它会用新的 Cookies 文件路径更新
         CommandBuilder，然后再次尝试获取视频格式。

   3. 修复连锁问题：
       * `ImportError`：在尝试导入 auto_cookies.py 的 main
         函数时程序失败。原因是该脚本的执行逻辑原本位于 if __name__ == '__main__':
         块中，无法被外部导入。我通过将其封装在一个 main()
         函数内解决了此问题，使其既能作为脚本独立运行，也能作为模块被导入。
       * `NameError`：在修改过程中，我发现音频下载的认证重试逻辑中，重建命令时需要一个
         file_prefix 变量，但该变量未被传入，会导致程序在特定错误路径下崩溃。我通过将其
         作为参数传入相应方法修复了此问题。

  总的来说，我通过重构代码，将特定的错误处理逻辑（付费内容检测）和重试机制集中在下载流程的编排层（downloader.py），同时修复了由此引发的两个附带Bug，最终实现了用户要求的功能。