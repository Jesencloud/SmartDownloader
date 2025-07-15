// static/script.js

// Dark mode functionality
function initializeDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    const body = document.body;
    
    if (!darkModeToggle) {
        console.error('Dark mode toggle button not found!');
        return;
    }
    
    // Check for saved theme preference or default to light mode
    const currentTheme = localStorage.getItem('theme') || 'light';
    
    if (currentTheme === 'dark') {
        body.classList.add('dark-mode');
        darkModeToggle.textContent = '☀️';
    } else {
        darkModeToggle.textContent = '🌙';
    }
    
    // Toggle dark mode
    darkModeToggle.addEventListener('click', () => {
        body.classList.toggle('dark-mode');
        
        if (body.classList.contains('dark-mode')) {
            darkModeToggle.textContent = '☀️';
            localStorage.setItem('theme', 'dark');
        } else {
            darkModeToggle.textContent = '🌙';
            localStorage.setItem('theme', 'light');
        }
    });
}

// 位置选择相关变量（已删除）
// let currentDownloadType = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize dark mode
    initializeDarkMode();
    
    // 获取DOM元素
    const urlInput = document.getElementById('videoUrl');
    const statusArea = document.getElementById('statusArea');
    const pasteButton = document.getElementById('pasteButton');
    const progressBar = document.getElementById('progressBar');
    const statusMessages = document.getElementById('statusMessages');
    const downloadVideoButton = document.getElementById('downloadVideoButton');
    const downloadAudioButton = document.getElementById('downloadAudioButton');

    // Auxiliary function: extract URL from text
    function extractUrl(text) {
        console.log('Clipboard text:', text);
        const urlRegex = /(https?:\/\/.+)/;
        const match = text.match(urlRegex);
        console.log('Regex match:', match);
        return match ? match[0] : '';
    }

    // Auto-paste functionality - 改进自动粘贴
    if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(text => {
            if (text) {
                const extracted = extractUrl(text);
                if (extracted) {
                    urlInput.value = extracted;
                    // 自动切换按钮状态
                    pasteButton.style.display = 'none';
                    clearButton.style.display = 'flex';
                    
                    // 添加轻微的视觉提示
                    urlInput.style.borderColor = '#3b82f6';
                    setTimeout(() => {
                        urlInput.style.borderColor = '';
                    }, 2000);
                    
                    console.log('Auto-pasted URL:', extracted);
                } else {
                    console.warn('Clipboard content does not contain a valid URL, not auto-pasted.');
                }
            }
        }).catch(err => {
            console.warn('Could not auto-paste clipboard content:', err);
        });
    }

    // Manual paste button functionality - 改进用户体验
    const clearButton = document.getElementById('clearButton');
    
    if (pasteButton) {
        console.log('Paste button found.');
        pasteButton.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    const extracted = extractUrl(text);
                    if (extracted) {
                        urlInput.value = extracted;
                        
                        // 切换按钮显示
                        pasteButton.style.display = 'none';
                        clearButton.style.display = 'flex';
                        
                        // 添加视觉反馈
                        urlInput.style.borderColor = '#10b981';
                        setTimeout(() => {
                            urlInput.style.borderColor = '';
                        }, 1000);
                        
                        console.log('Value after setting input:', urlInput.value);
                        console.log('Clipboard content successfully pasted and URL extracted.');
                    } else {
                        // 改进错误提示
                        showPasteError('剪贴板中没有找到有效的URL链接');
                        console.log('No recognizable URL in clipboard.');
                    }
                } else {
                    showPasteError('剪贴板为空');
                }
            } catch (err) {
                console.error('Paste failed:', err);
                showPasteError('无法访问剪贴板。请确保浏览器已授权访问剪贴板，并使用HTTPS连接。');
            }
        });
    } else {
        console.warn('Paste button not found.');
    }
    
    // 显示粘贴错误的友好提示
    function showPasteError(message) {
        // 创建临时提示元素
        const errorTip = document.createElement('div');
        errorTip.className = 'paste-error-tip';
        errorTip.textContent = message;
        errorTip.style.cssText = `
            position: absolute;
            top: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: #fee2e2;
            color: #991b1b;
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            font-size: 0.875rem;
            white-space: nowrap;
            z-index: 1000;
            margin-top: 0.5rem;
            border: 1px solid #fecaca;
        `;
        
        // 将提示添加到输入容器
        const inputContainer = document.querySelector('.input-container');
        inputContainer.style.position = 'relative';
        inputContainer.appendChild(errorTip);
        
        // 3秒后自动移除提示
        setTimeout(() => {
            if (errorTip.parentNode) {
                errorTip.parentNode.removeChild(errorTip);
            }
        }, 3000);
    }

    // Clear button functionality - 改进为清除并重新启用粘贴功能
    if (clearButton) {
        clearButton.addEventListener('click', () => {
            // 清除输入内容
            urlInput.value = '';
            
            // 切换按钮显示
            pasteButton.style.display = 'flex';
            clearButton.style.display = 'none';
            
            // 添加视觉反馈
            urlInput.style.borderColor = '#f59e0b';
            setTimeout(() => {
                urlInput.style.borderColor = '';
            }, 500);
            
            // 聚焦到输入框，方便用户重新输入或粘贴
            urlInput.focus();
            
            console.log('Input cleared, ready for new paste or input');
        });
    }

    // Input change handler - 改进输入处理
    urlInput.addEventListener('input', () => {
        if (urlInput.value.length > 0) {
            pasteButton.style.display = 'none';
            clearButton.style.display = 'flex';
        } else {
            pasteButton.style.display = 'flex';
            clearButton.style.display = 'none';
        }
    });

    // 键盘快捷键支持
    urlInput.addEventListener('keydown', (e) => {
        // Ctrl+V 或 Cmd+V 快速粘贴
        if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
            // 让浏览器默认粘贴操作执行后，再处理按钮状态
            setTimeout(() => {
                if (urlInput.value.length > 0) {
                    pasteButton.style.display = 'none';
                    clearButton.style.display = 'flex';
                    
                    // 添加视觉反馈
                    urlInput.style.borderColor = '#10b981';
                    setTimeout(() => {
                        urlInput.style.borderColor = '';
                    }, 1000);
                }
            }, 10);
        }
        
        // Escape 键清除输入
        if (e.key === 'Escape' && urlInput.value.length > 0) {
            urlInput.value = '';
            pasteButton.style.display = 'flex';
            clearButton.style.display = 'none';
            
            // 添加视觉反馈
            urlInput.style.borderColor = '#f59e0b';
            setTimeout(() => {
                urlInput.style.borderColor = '';
            }, 500);
        }
    });

    // 跳转到下载页面的函数
    function redirectToDownloadPage(downloadType) {
        const url = urlInput.value;

        if (!url) {
            alert('请输入一个URL！');
            return;
        }

        // 构建下载页面的URL参数
        const params = new URLSearchParams({
            url: url,
            type: downloadType
        });

        // 跳转到下载页面
        window.location.href = `/download?${params.toString()}`;
    }

    // Core download processing function (保留原功能供其他地方使用)
    async function startDownloadProcess(downloadType, customPath = null) {
        const url = urlInput.value;

        if (!url) {
            alert('请输入一个URL！');
            return;
        }

        // Disable all download related buttons to prevent duplicate submissions
        downloadVideoButton.disabled = true;
        downloadAudioButton.disabled = true;
        
        // Update button text
        if (downloadType === 'video') {
            downloadVideoButton.textContent = '正在请求视频...';
        } else if (downloadType === 'audio') {
            downloadAudioButton.textContent = '正在请求音频...';
        }

        // Hide status messages, show progress bar
        statusMessages.style.display = 'none';
        progressBar.style.display = 'block';
        progressBar.classList.remove('hidden');
        addStatusMessage('任务已提交，正在处理...', 'status-pending');

        try {
            const requestBody = {
                url: url,
                download_type: downloadType
            };

            // 如果提供了自定义路径，添加到请求中
            if (customPath) {
                requestBody.custom_path = customPath;
            }

            const response = await fetch('/downloads', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody),
            });

            if (!response.ok) {
                throw new Error(`服务器错误: ${response.statusText}`);
            }

            const data = await response.json();
            const taskId = data.task_id;
            
            addStatusMessage(`任务已创建 (ID: ${taskId})，开始查询状态...`, 'status-pending');
            
            pollTaskStatus(taskId);

        } catch (error) {
            console.error('请求失败:', error);
            addStatusMessage(`请求失败: ${error.message}`, 'status-failure');
            resetForm();
        }
    }

    // Add event listeners for new download buttons - 直接跳转到下载页面
    if (downloadVideoButton) {
        downloadVideoButton.addEventListener('click', () => redirectToDownloadPage('video'));
    }
    if (downloadAudioButton) {
        downloadAudioButton.addEventListener('click', () => redirectToDownloadPage('audio'));
    }

    function pollTaskStatus(taskId) {
        const intervalId = setInterval(async () => {
            try {
                const response = await fetch(`/downloads/${taskId}`);
                if (!response.ok) {
                    clearInterval(intervalId);
                    addStatusMessage(`查询状态失败 (ID: ${taskId})`, 'status-failure');
                    resetForm();
                    return;
                }

                const data = await response.json();
                
                if (data.status === 'SUCCESS') {
                    clearInterval(intervalId);
                    const result = data.result;
                    addStatusMessage(`✅ 下载成功！文件保存在: ${result.result}`, 'status-success');
                    resetForm();
                } else if (data.status === 'FAILURE') {
                    clearInterval(intervalId);
                    addStatusMessage(`❌ 下载失败: ${data.result}`, 'status-failure');
                    resetForm();
                } else {
                    addStatusMessage(`进行中 (状态: ${data.status})...`, 'status-pending');
                    progressBar.style.display = 'block';
                    progressBar.classList.remove('hidden');
                    statusMessages.style.display = 'none';
                }

            } catch (error) {
                clearInterval(intervalId);
                console.error('轮询错误:', error);
                addStatusMessage(`查询状态时出错: ${error.message}`, 'status-failure');
                resetForm();
            }
        }, 3000); // Poll every 3 seconds
    }

    function addStatusMessage(message, className) {
        statusMessages.innerHTML = ''; 
        const statusElement = document.createElement('div');
        statusElement.textContent = message;
        statusElement.className = `status-message ${className}`;
        statusMessages.appendChild(statusElement);
    }

    function resetForm() {
        urlInput.value = '';
        
        // Enable new download buttons and reset text
        if (downloadVideoButton) {
            downloadVideoButton.disabled = false;
            downloadVideoButton.textContent = '提取视频';
        }
        if (downloadAudioButton) {
            downloadAudioButton.disabled = false;
            downloadAudioButton.textContent = '提取音频';
        }

        // Hide progress bar, show initial status message
        progressBar.style.display = 'none';
        progressBar.classList.add('hidden');
        statusMessages.style.display = 'block';
        statusMessages.innerHTML = '<p class="text-gray-500">在此处查看下载状态...</p>';
    }
});