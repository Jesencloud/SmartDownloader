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
    const pasteButton = document.getElementById('pasteButton');
    const clearButton = document.getElementById('clearButton');
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
        safeClipboardRead().then(text => {
            if (text) {
                const extracted = extractUrl(text);
                if (extracted) {
                    urlInput.value = extracted;
                    // 自动切换按钮状态
                    if (pasteButton && clearButton) {
                        pasteButton.style.display = 'none';
                        clearButton.style.display = 'flex';
                    }
                    
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
            // 对于自动粘贴失败，不显示错误提示，因为这是静默操作
        });
    }

    if (pasteButton) {
        console.log('Paste button found.');
        pasteButton.addEventListener('click', async () => {
            try {
                const text = await safeClipboardRead();
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
                const userMessage = getClipboardErrorMessage(err);
                showPasteError(userMessage);
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
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        `;
        
        // 将提示添加到输入容器
        const inputContainer = document.querySelector('.input-container');
        if (inputContainer) {
            inputContainer.style.position = 'relative';
            
            // 移除之前的错误提示
            const existingTip = inputContainer.querySelector('.paste-error-tip');
            if (existingTip) {
                existingTip.remove();
            }
            
            inputContainer.appendChild(errorTip);
            
            // 3秒后自动移除提示
            setTimeout(() => {
                if (errorTip.parentNode) {
                    errorTip.parentNode.removeChild(errorTip);
                }
            }, 3000);
        }
    }

    // 改进的剪贴板访问函数
    async function safeClipboardRead() {
        try {
            // 首先检查剪贴板API是否可用
            if (!navigator.clipboard) {
                throw new Error('CLIPBOARD_NOT_SUPPORTED');
            }
            
            // 检查权限
            const permission = await navigator.permissions.query({name: 'clipboard-read'});
            if (permission.state === 'denied') {
                throw new Error('CLIPBOARD_PERMISSION_DENIED');
            }
            
            const text = await navigator.clipboard.readText();
            return text;
        } catch (error) {
            console.error('Clipboard read error:', error);
            
            // 根据错误类型返回不同的错误信息
            if (error.name === 'NotAllowedError' || error.message === 'CLIPBOARD_PERMISSION_DENIED') {
                throw new Error('CLIPBOARD_PERMISSION_DENIED');
            } else if (error.message === 'CLIPBOARD_NOT_SUPPORTED') {
                throw new Error('CLIPBOARD_NOT_SUPPORTED');
            } else {
                throw new Error('CLIPBOARD_ACCESS_FAILED');
            }
        }
    }

    // 获取用户友好的错误消息
    function getClipboardErrorMessage(error) {
        switch (error.message) {
            case 'CLIPBOARD_PERMISSION_DENIED':
                return '剪贴板访问被拒绝。请在浏览器设置中允许访问剪贴板权限。';
            case 'CLIPBOARD_NOT_SUPPORTED':
                return '当前浏览器不支持剪贴板功能。请手动复制粘贴链接。';
            case 'CLIPBOARD_ACCESS_FAILED':
                return '无法访问剪贴板。请确保使用HTTPS连接并重试。';
            default:
                return '剪贴板访问失败。请手动输入链接。';
        }
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

    // Add event listeners for new download buttons - 直接跳转到下载页面
    if (downloadVideoButton) {
        downloadVideoButton.addEventListener('click', () => redirectToDownloadPage('video'));
    }
    if (downloadAudioButton) {
        downloadAudioButton.addEventListener('click', () => redirectToDownloadPage('audio'));
    }

    // FAQ functionality
    function initializeFAQ() {
        document.querySelectorAll('.faq-question').forEach(button => {
            button.addEventListener('click', () => {
                const answer = button.nextElementSibling;
                const isCurrentlyOpen = answer.style.display === 'block';
                
                // Close all other answers
                document.querySelectorAll('.faq-answer').forEach(ans => {
                    ans.style.display = 'none';
                });
                document.querySelectorAll('.faq-question').forEach(q => {
                    q.classList.remove('active');
                });
                
                // Toggle current answer
                if (!isCurrentlyOpen) {
                    answer.style.display = 'block';
                    button.classList.add('active');
                }
            });
        });
    }

    // Initialize FAQ if on main page
    if (document.querySelector('.faq-container')) {
        initializeFAQ();
    }
});