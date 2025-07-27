# 更新日志

所有此项目的版本变更都将记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

## [2.9.0] - 2025-07-26


  // 实现思路：
  // 1. 用户体验：点击 -> 进度条 -> 自动下载，无额外操作
  // 2. 后台智能：自动判断下载成功/失败，智能清理
  // 3. 容错机制：失败时提供简单重试，5分钟自动清理

  async function handleSmartDownload(formatId, optionElement) {
      // 检查5分钟内的缓存
      const cached = await checkRecentCache(formatId);
      if (cached) {
          // 直接下载缓存文件，用户无感知
          return triggerDirectDownload(cached.url);
      }

      // 显示统一的下载进度
      showDownloadProgress(optionElement);

      try {
          // 后台处理
          const result = await processDownload(formatId);

          // 智能下载尝试
          const downloadSuccess = await smartDownloadAttempt(result.fileUrl);

          if (downloadSuccess) {
              // 成功：显示完成，立即清理服务器文件
              showDownloadComplete(optionElement);
              await cleanupServerFile(result.taskId);
          } else {
              // 失败：显示简单重试按钮，5分钟后自动清理
              showSimpleRetryButton(optionElement, result.fileUrl, result.taskId);
              scheduleAutoCleanup(result.taskId, 5 * 60 * 1000);
          }

      } catch (error) {
          showDownloadError(optionElement);
      }
  }

  // 智能下载检测
  async function smartDownloadAttempt(fileUrl) {
      // 方法1：检测页面焦点变化
      // 方法2：监听unload事件
      // 方法3：使用fetch检测文件是否被访问
      // 综合判断下载是否真正开始
  }

  