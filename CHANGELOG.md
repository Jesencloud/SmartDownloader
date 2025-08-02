# 更新日志

所有此项目的版本变更都将记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [3.1.0] - 2025-08-02

### 修复

- **安全修复**：
  - 修复了 `web/main.py` 中 `get_downloaded_file` 和 `delete_downloaded_file` 端点存在的路径遍历漏洞，防止访问下载目录之外的文件。
  - 修复了 `web/main.py` 中 `get_downloaded_file` 端点存在的 CRLF 注入漏洞，防止恶意构造响应头。
  - 修复了 `web/main.py` 中 `get_downloaded_file` 端点存在的 TOCTOU (检查时与使用时不同) 漏洞，确保使用经过验证的文件路径。
- **功能修复**：
  - 修复了 `auto_cookies.py` 中 `_get_safari_cookies` 方法无法正确提取 Safari cookies 的问题，现已引入 `browser-cookie3` 库实现该功能。

### 重构

- **降低认知复杂度**：
  - 对 `downloader.py`、`auto_cookies.py` 和 `config_manager.py` 中的多个高复杂度函数进行了重构，将其认知复杂度降低到 SonarQube 推荐的阈值以下，显著提升了代码的可读性和可维护性。
- **代码质量**：
  - 在 `config_manager.py` 中，将硬编码的控制台输出样式字符串（如 "bold yellow"）替换为具名常量，提高了代码的一致性和可维护性。

