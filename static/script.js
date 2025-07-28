// static/script.js

// --- Global Configuration ---
let appConfig = {
    security: {
        allowed_domains: [] // Will be loaded from backend
    }
};

// --- Configuration Loading ---
async function loadConfiguration() {
    try {
        const response = await fetch('/config');
        if (response.ok) {
            appConfig = await response.json();
            console.log('Configuration loaded from backend:', appConfig.security?.allowed_domains);
        } else {
            console.warn('Failed to load configuration from backend, using fallback');
            // Fallback to hardcoded domains if backend config fails
            appConfig.security.allowed_domains = ["x.com", "youtube.com", "bilibili.com", "youtu.be"];
        }
    } catch (error) {
        console.error('Error loading configuration:', error);
        // Fallback to hardcoded domains if fetch fails
        appConfig.security.allowed_domains = ["x.com", "youtube.com", "bilibili.com", "youtu.be"];
    }
}

// --- Configuration Reload Function (for future use) ---
async function reloadConfiguration() {
    console.log('Reloading configuration from backend...');
    await loadConfiguration();
}

document.addEventListener('DOMContentLoaded', async () => {
    // --- Load Translations First ---
    await loadTranslations();
    
    // --- Initialize Page Elements ---
    initializeDarkMode();
    initializeLanguageSelector();
    const savedLang = localStorage.getItem('language') || 'zh';
    await switchLanguage(savedLang); // Wait for initial language to load
    
    // --- Load Configuration from Backend ---
    await loadConfiguration();

    // --- Get DOM Elements ---
    const urlInput = document.getElementById('videoUrl');
    const pasteButton = document.getElementById('pasteButton');
    const clearButton = document.getElementById('clearButton');
    const downloadVideoButton = document.getElementById('downloadVideoButton');
    const downloadAudioButton = document.getElementById('downloadAudioButton');
    const resultContainer = document.getElementById('resultContainer');
    const mainHeading = document.querySelector('.hero-section h1'); // This is fine, but for consistency let's assume it could be reused.
    const inputGroup = document.querySelector('.input-group');
    const buttonGroup = document.querySelector('.button-group');

    let currentVideoData = null; // To store fetched video data

    // --- Centralized handler for returning home and cancelling downloads ---
    async function handleReturnHome(e) {
        // Check for active downloads by looking for the .is-downloading class
        const downloadingItems = document.querySelectorAll('.is-downloading');
        
        // 停止所有平滑动画
        smoothProgressManager.stopAllAnimations();
        
        // Clear all active polling intervals first
        const pollingElements = document.querySelectorAll('[data-polling-interval]');
        console.log(`Found ${pollingElements.length} elements with active polling intervals`);
        
        pollingElements.forEach(element => {
            const timeoutId = element.dataset.pollingInterval;
            if (timeoutId) {
                clearTimeout(parseInt(timeoutId));
                element.removeAttribute('data-polling-interval');
                console.log(`Cleared polling timeout ${timeoutId}`);
            }
        });
        
        if (downloadingItems.length > 0) {
            if (e) e.preventDefault(); // Prevent default link navigation

            // Show cleanup message
            const t = getTranslations();
            showCleanupMessage(t.cleaningUp);

            // Collect all unique task IDs from the downloading items
            const taskIds = [...new Set(Array.from(downloadingItems)
                                 .map(item => item.dataset.taskId)
                                 .filter(id => id))];

            if (taskIds.length > 0) {
                try {
                    const response = await fetch('/downloads/cancel', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_ids: taskIds }),
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        console.log('Cancellation and cleanup completed:', result);
                        
                        // Show cleanup results briefly
                        if (result.cleanup_result && result.cleanup_result.cleaned_files.length > 0) {
                            showCleanupResults(result.cleanup_result);
                            await new Promise(resolve => setTimeout(resolve, 2000)); // Show for 2 seconds
                        }
                    } else {
                        console.error('Failed to cancel downloads:', response.status);
                    }
                } catch (error) {
                    console.error('Failed to send cancellation request:', error);
                }
            }
        }
        // Always reset the UI, regardless of whether cancellation succeeded
        resetUI();
    }

    function showCleanupMessage(message) {
        const resultContainer = document.getElementById('resultContainer');
        resultContainer.innerHTML = `
            <div class="cleanup-message bg-blue-100 border border-blue-400 text-blue-700 px-4 py-3 rounded-lg text-center" role="alert">
                <div class="flex items-center justify-center">
                    <div class="spinner mr-3"></div>
                    <span>${message}</span>
                </div>
            </div>
        `;
        resultContainer.style.display = 'block';
        
        // Add spinner CSS if not already present
        if (!document.getElementById('cleanup-spinner-style')) {
            const style = document.createElement('style');
            style.id = 'cleanup-spinner-style';
            style.innerHTML = `
                .spinner {
                    border: 2px solid #f3f3f3;
                    border-top: 2px solid #3498db;
                    border-radius: 50%;
                    width: 20px;
                    height: 20px;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
    }

    function showCleanupResults(cleanupResult) {
        const resultContainer = document.getElementById('resultContainer');
        const fileCount = cleanupResult.cleaned_files.length;
        const sizeInfo = cleanupResult.total_size_mb > 0 ? ` (${cleanupResult.total_size_mb}MB)` : '';
        const t = getTranslations();
        const message = t.cleanupComplete
            .replace('{fileCount}', fileCount)
            .replace('{sizeInfo}', sizeInfo);

        resultContainer.innerHTML = `
            <div class="cleanup-results bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded-lg text-center" role="alert">
                <div class="flex items-center justify-center">
                    <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                    </svg>
                    <span>${message}</span>
                </div>
            </div>
        `;
    }

    // --- Main Event Listeners ---
    downloadVideoButton.addEventListener('click', () => startVideoAnalysis('video'));
    downloadAudioButton.addEventListener('click', () => startVideoAnalysis('audio'));

    // --- Attach cancellation handler to header links ---
    // This needs to be done at a higher level since the header is always present.
    document.querySelector('.logo a').addEventListener('click', handleReturnHome);
    
    // Attach cancellation handler to the Home button in header
    const homeButton = document.querySelector('a[data-translate="homeButton"]');
    if (homeButton) {
        homeButton.addEventListener('click', handleReturnHome);
    }

    // --- Core Functions ---

    async function startVideoAnalysis(downloadType) {
        const url = urlInput.value.trim();
        const t = getTranslations();

        // --- 新的综合URL验证 ---
        const urlValidation = validateCompleteURL(url);
        if (!urlValidation.valid) {
            const errorMessage = `URL验证失败：\n${urlValidation.errors.join('\n')}`;
            alert(errorMessage);
            return;
        }
        
        const validatedUrl = urlValidation.cleanUrl;
        // --- 综合URL验证结束 ---

        // --- NEW: Developer Test Mode ---
        if (validatedUrl === 'test-video' || validatedUrl === 'test-audio') {
            showLoadingState(downloadType);

            // Simulate a short delay to mimic network latency
            await new Promise(resolve => setTimeout(resolve, 500));
            
            const mockData = validatedUrl === 'test-video' ? getMockVideoData() : getMockAudioData();
            currentVideoData = mockData; // Store it for language switching
            renderResults(mockData);
            return; // Exit the function to prevent the real fetch
        }
        // --- END: Developer Test Mode ---
        if (!validatedUrl) {
            alert(t.urlPlaceholder);
            return;
        }

        showLoadingState(downloadType);

        try {
            const response = await fetch('/video-info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: validatedUrl, download_type: downloadType }),
            });

            if (!response.ok) {
                const contentType = response.headers.get("content-type");
                let errorMessage;
                if (contentType && contentType.includes("application/json")) {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || `API Error: ${response.status}`;
                } else {
                    // If the response isn't JSON, it's likely a server error page (e.g., from a timeout or crash)
                    // This is exactly what happens with Live Server
                    const serverText = await response.text();
                    console.error("Non-JSON error response from server:", serverText);
                    errorMessage = `${t.errorTitle} (${response.status} ${response.statusText}). The server might be busy or the request timed out.`;
                }
                throw new Error(errorMessage);
            }

            currentVideoData = await response.json();
            renderResults(currentVideoData);

        } catch (error) {
            console.error('Analysis Error:', error);
            showErrorState(error.message);
        }
    }

    function showLoadingState(downloadType) {
        const t = getTranslations();
        const loadingTextKey = downloadType === 'video' ? 'videoLoading' : 'audioLoading';
        
        // Set the text directly AND set the data-translate attribute for future switches
        mainHeading.textContent = t[loadingTextKey];
        mainHeading.setAttribute('data-translate', loadingTextKey);

        if (inputGroup) inputGroup.style.display = 'none';
        buttonGroup.style.display = 'none';

        resultContainer.innerHTML = createLoadingAnimationHTML(t.parsingVideoPleaseWait);
        resultContainer.style.display = 'block';
    }

    function createLoadingAnimationHTML(text) {
 return `
     <div class="enhanced-loading-animation">  <!-- Wrapping class -->
         <div class="loading-animation-container text-center p-6 text-white">
             <div class="loading-animation flex justify-center space-x-2">
                 <div class="line h-8 w-1 bg-white rounded-full animate-pulse"></div>
                 <div class="line h-10 w-1 bg-white rounded-full animate-pulse animation-delay-100"></div>
                 <div class="line h-12 w-1 bg-white rounded-full animate-pulse animation-delay-200"></div>
                 <div class="line h-10 w-1 bg-white rounded-full animate-pulse animation-delay-300"></div>
                 <div class="line h-8 w-1 bg-white rounded-full animate-pulse animation-delay-400"></div>
             </div>
             <p class="mt-4" data-translate="parsingVideoPleaseWait">${text}</p>
         </div>
     </div>`;
 }
 
    function adjustButtonFontSize(button) {
        const maxWidth = button.offsetWidth; // Button's width
        const textWidth = button.scrollWidth;  // Text's "ideal" width

        if (textWidth > maxWidth) {
            let currentSize = parseFloat(window.getComputedStyle(button).fontSize);
            while (button.scrollWidth > maxWidth && currentSize > 10) { // Don't go below 10px
                currentSize -= 1;
                button.style.fontSize = `${currentSize}px`;
            }
        }
    }

    adjustButtonFontSize(downloadVideoButton);
    adjustButtonFontSize(downloadAudioButton);    
    adjustButtonFontSize(pasteButton);
    adjustButtonFontSize(clearButton);
    function showErrorState(message) {
        const t = getTranslations();
        mainHeading.textContent = t.analysisFailed;
        resultContainer.innerHTML = `
            <div class="error-message bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg" role="alert">
                <strong class="font-bold">${t.errorTitle}:</strong>
                <span class="block sm:inline">${message}</span>
            </div>
            <div class="text-center mt-4">                
                <button id="backButton" class="button">${t.returnHome}</button>                
            </div>`;        
        document.getElementById('backButton').addEventListener('click', resetUI);
    }

    function renderResults(data) {
    const t = getTranslations();
    mainHeading.textContent = data.title;
    // By setting the title to dynamic data, it's no longer a translatable string.
    // We must remove the attribute to prevent switchLanguage from overwriting it.
    mainHeading.removeAttribute('data-translate');
    mainHeading.className = 'text-xl font-bold text-white mb-4 break-words text-left leading-tight video-title';
    
    // --- 定义颜色主题 ---
    // 为不同选项设置不同的基色，但悬停时都统一变为紫色
    const hoverColor = 'hover:bg-purple-500 hover:bg-opacity-50';
    const defaultColorClass = `bg-gray-800 ${hoverColor}`;
    const videoColorClasses = [
        `bg-blue-800 ${hoverColor}`,   // 最高分辨率
        `bg-teal-800 ${hoverColor}`,  // 次高分辨率
        `bg-indigo-800 ${hoverColor}`  // 第三种分辨率
    ];
    const audioColorClasses = [
        `bg-teal-800 ${hoverColor}`,   // 高比特率音频
        `bg-cyan-800 ${hoverColor}`    // 兼容性音频
    ];    // --- 颜色主题结束 ---
    let optionsHTML = '';
    const headerKey = data.download_type === 'video' ? 'selectResolution' : 'selectAudioQuality';

    if (data.download_type === 'audio') {
        // The backend already classified formats as audio by setting vcodec to null.
        // We just need to trust the backend's classification and display them.
        // The previous stricter filter on `acodec` was incorrectly filtering out X.com audio streams.
        const audioFormats = data.formats.filter(f => f.vcodec === 'none' || f.vcodec == null);

        if (audioFormats.length === 0) {
            showErrorState(t.noFormats);
            return;
        }

        // 后端已经发送了最佳的音频格式，所以我们直接使用第一个
        const bestAudioFormat = audioFormats[0];

        // Get the actual audio format from the format info
        // 使用 'm4a' 作为备用格式，因为它在下载策略中具有高优先级，比 'webm' 更具代表性
        const audioFormat = bestAudioFormat.ext || 'm4a';
        const audioBitrate = bestAudioFormat.abr;

        // --- "高比特率" 选项文本 ---
        // 优先使用比特率，如果不存在则回退到文件大小
        let highBitrateText;
        if (audioBitrate) {
            highBitrateText = `${t.losslessAudio} ${audioFormat.toUpperCase()} ${audioBitrate}kbps`;
        } else {
            highBitrateText = `${t.losslessAudio} ${audioFormat.toUpperCase()} ${formatFileSize(bestAudioFormat.filesize, bestAudioFormat.filesize_is_approx)}`;
        }

        // 智能标识：音频格式支持直接下载
        const audioStreamIndicator = bestAudioFormat.supports_browser_download ? ' ⚡️' : '';

        optionsHTML += `
            <div class="resolution-option ${audioColorClasses[0] || defaultColorClass} p-4 rounded-lg flex items-center cursor-pointer transition-colors"
                 data-format-id="${bestAudioFormat.format_id}" data-audio-format="${audioFormat}" data-filesize="${bestAudioFormat.filesize || ''}" data-filesize-is-approx="${bestAudioFormat.filesize_is_approx || false}" data-abr="${audioBitrate || ''}" data-resolution="audio" data-is-complete-stream="${bestAudioFormat.is_complete_stream || false}" data-supports-browser-download="${bestAudioFormat.supports_browser_download || false}">
                <div class="option-content w-full grid grid-cols-[auto_1fr_auto] items-center gap-x-4">
                    <div class="w-6 h-6"></div>
                    <div class="text-center">
                        <span class="font-semibold" data-translate-dynamic="audio_lossless">${highBitrateText}${audioStreamIndicator}</span>
                    </div>
                    <div class="download-icon justify-self-end">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                </div>
                <div class="option-progress w-full hidden">
                    <!-- Progress bar will be injected here -->
                </div>
            </div>`;

        // --- "兼容性佳" 选项文本 ---
        const mp3FormatId = `mp3-conversion-${bestAudioFormat.format_id || 'best'}`;
        const compatibilityText = `${t.betterCompatibility} (${audioFormat.toUpperCase()} → MP3)`;
        optionsHTML += `
            <div class="resolution-option ${audioColorClasses[1] || defaultColorClass} p-4 rounded-lg flex items-center cursor-pointer transition-colors" 
                 data-format-id="${mp3FormatId}" data-audio-format-original="${audioFormat}" data-filesize="${bestAudioFormat.filesize || ''}" data-filesize-is-approx="${bestAudioFormat.filesize_is_approx || false}" data-resolution="audio">
                <div class="option-content w-full grid grid-cols-[auto_1fr_auto] items-center gap-x-4">
                    <div class="w-6 h-6"></div>
                    <div class="text-center">
                        <span class="font-semibold" data-translate-dynamic="audio_compatible">${compatibilityText}</span>
                    </div>
                    <div class="download-icon justify-self-end">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                </div>
                <div class="option-progress w-full hidden">
                    <!-- Progress bar will be injected here -->
                </div>
            </div>`;

    } else { // Video logic
        // The backend now sends a pre-filtered, pre-sorted list of the best format for each resolution.
        // We just need to render them.
        const videoFormats = data.formats;

        if (videoFormats.length === 0) {
            showErrorState(t.noFormats);
            return;
        }

        // 只显示前3个不同分辨率的视频
        const topFormats = videoFormats.slice(0, 3);

        optionsHTML = topFormats.map((format, index) => {
            const resolutionText = format.resolution;
            const formattedSize = formatFileSize(format.filesize, format.filesize_is_approx);
            
            // 智能标识系统：检测完整流并添加⚡️标识
            let streamTypeIndicator = '';
            if (format.is_complete_stream && format.supports_browser_download) {
                streamTypeIndicator = ' ⚡️'; // 完整流，可直接下载
            } else if (format.needs_merge) {
                streamTypeIndicator = ''; // 分离流，无特殊符号
            }
            
            // 从颜色数组中选择颜色，如果选项超过数组长度，则使用默认灰色
            const colorClass = videoColorClasses[index] || defaultColorClass;

            return `
                <div class="resolution-option ${colorClass} bg-opacity-70 p-4 rounded-lg flex items-center cursor-pointer transition-colors" 
                     data-format-id="${format.format_id}" 
                     data-resolution="${resolutionText}" 
                     data-formatted-size="${formattedSize}" 
                     data-ext="${format.ext}" 
                     data-filesize="${format.filesize || ''}" 
                     data-filesize-is-approx="${format.filesize_is_approx || false}" 
                     data-is-complete-stream="${format.is_complete_stream || false}" 
                     data-supports-browser-download="${format.supports_browser_download || false}">
                    <div class="option-content w-full grid grid-cols-[1fr_auto_1fr] items-center gap-x-4">
                        <div></div>
                        <div class="text-center">
                            <span class="font-semibold" data-translate-dynamic="video">${t.download} ${resolutionText} ${formattedSize} ${format.ext}${streamTypeIndicator}</span>
                        </div>
                        <div class="download-icon justify-self-end">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        </div>
                    </div>
                    <div class="option-progress w-full hidden">
                        <!-- Progress bar will be injected here -->
                    </div>
                </div>`;
        }).join('');
    }

    resultContainer.innerHTML = `
        <div class="download-container bg-gray-900 bg-opacity-50 p-6 rounded-2xl text-white relative">
            <h3 class="text-xl font-bold mb-4" data-translate="${headerKey}">${t[headerKey]}</h3>
            <div class="resolution-grid grid grid-cols-1 gap-4">${optionsHTML}</div>
            <div class="text-center mt-6">
                <button id="backButton" class="button bg-gray-600 hover:bg-gray-700" data-translate="returnHome">${t.returnHome}</button>
            </div>
            <!-- 智能下载说明 - 右下角 -->
            <div id="smartDownloadInfo" class="absolute bottom-4 right-4 text-white text-xs hidden">
                <div data-translate="smartDownloadInfoText">${t.smartDownloadInfoText}</div>
            </div>
        </div>`;

    document.querySelectorAll('.resolution-option').forEach(el => {
        el.addEventListener('click', (e) => {
            // 检查是否有文字被选中，如果有则不触发下载
            const selection = window.getSelection();
            if (selection && selection.toString().length > 0) {
                return; // 用户正在选择文字，不触发下载
            }
            
            handleDownload(el.dataset.formatId);
        });
    });
    
    // 检查是否有完整流格式或支持直接下载的格式，如果有则显示智能下载说明
    const hasCompleteStream = document.querySelector('[data-is-complete-stream="true"][data-supports-browser-download="true"]');
    const hasDirectDownload = document.querySelector('[data-supports-browser-download="true"]');
    const smartDownloadInfo = document.getElementById('smartDownloadInfo');
    if ((hasCompleteStream || hasDirectDownload) && smartDownloadInfo) {
        smartDownloadInfo.classList.remove('hidden');
    }
    
    // Use the new centralized handler for the back button
    const backButton = document.getElementById('backButton');
    if (backButton) {
        backButton.addEventListener('click', handleReturnHome);
    }
}
    
    // 通用的任务状态显示函数
    function showTaskStatus(optionElement, status, message, icon, colorClass, borderClass) {
        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');
        const t = getTranslations();
        const formatId = optionElement.dataset.formatId;
    
        // 确定状态消息的翻译键
        let translateKey = '';
        if (message === '下载完成' || message === 'Download Complete') {
            translateKey = 'download_complete';
        } else if (message === '下载失败' || message === 'Download Failed') {
            translateKey = 'download_failed';
        } else if (message === '检查超时' || message === 'Check Timeout') {
            translateKey = 'download_timeout';
        }
    
        if (status === 'failure') {
            contentDiv.classList.add('hidden');
            progressDiv.classList.remove('hidden');
            progressDiv.innerHTML = `
                <div class="flex items-center justify-between w-full">
                    <div class="flex items-center">
                        <div class="download-icon ${colorClass} mr-2">${icon}</div>
                        <span class="font-semibold ${colorClass}" data-translate-dynamic="download_failed">${message}</span>
                    </div>
                    <button class="retry-button bg-yellow-500 hover:bg-yellow-600 text-white font-bold py-1 px-3 rounded-full text-sm" data-translate="retryButton">
                        ${t.retryButton || 'Retry'}
                    </button>
                </div>
            `;
            optionElement.style.pointerEvents = 'auto';
            optionElement.style.opacity = '1';
    
            const retryButton = progressDiv.querySelector('.retry-button');
            retryButton.addEventListener('click', (e) => {
                e.stopPropagation();
                optionElement.classList.remove('border', borderClass);
                // Restore original content before retrying
                progressDiv.classList.add('hidden');
                progressDiv.innerHTML = '';
                contentDiv.classList.remove('hidden');
                handleDownload(formatId);
            });
    
        } else if (status === 'success') {
            progressDiv.classList.add('hidden');
            progressDiv.innerHTML = '';
            contentDiv.innerHTML = `
                <div class="flex-grow text-center">
                    <span class="font-semibold ${colorClass}" ${translateKey ? `data-translate-dynamic="${translateKey}"` : ''}>${message}</span>
                </div>
                <div class="download-icon ${colorClass}">
                    ${icon}
                </div>
            `;
            contentDiv.classList.remove('hidden');
        } else {
            // 对于其他状态，显示在progressDiv中
            progressDiv.innerHTML = `
                <div class="flex-grow text-center">
                    <span class="font-semibold ${colorClass}" ${translateKey ? `data-translate-dynamic="${translateKey}"` : ''}>${message}</span>
                </div>
                <div class="download-icon ${colorClass}">
                    ${icon}
                </div>
            `;
            // Keep progressDiv visible to show the message
        }
    
        optionElement.classList.remove('hover:bg-gray-700');
        if (borderClass) {
            optionElement.classList.add('border', borderClass);
        }
    }
    
    // 获取当前显示的进度百分比
    function getCurrentDisplayProgress(optionElement) {
        const progressDiv = optionElement.querySelector('.option-progress');
        if (!progressDiv || progressDiv.classList.contains('hidden')) {
            return 0;
        }
        
        const progressBar = progressDiv.querySelector('.progress-bar');
        if (!progressBar) {
            return 0;
        }
        
        const style = progressBar.style.width;
        if (style && style.includes('%')) {
            return parseInt(style.replace('%', '')) || 0;
        }
        
        return 0;
    }

    // 清理任务跟踪的通用函数
    function cleanupTaskTracking(timeoutId, optionElement) {
        if (timeoutId) {
            clearTimeout(timeoutId);
        }
        optionElement.removeAttribute('data-polling-interval');
        optionElement.classList.remove('is-downloading');
    }
    // 平滑进度动画管理器
    class SmoothProgressManager {
        constructor() {
            this.animations = new Map(); // 存储每个元素的动画状态
        }
        
        startSmoothProgress(optionElement, currentProgress, targetProgress, etaSeconds, message) {
            const elementId = optionElement.dataset.formatId;
            
            // 清除之前的动画
            if (this.animations.has(elementId)) {
                clearInterval(this.animations.get(elementId).intervalId);
            }
            
            // 确保进度数值合理
            currentProgress = Math.max(0, Math.min(100, currentProgress));
            targetProgress = Math.max(0, Math.min(100, targetProgress));
            
            // 如果进度差距很小，直接更新
            if (Math.abs(targetProgress - currentProgress) < 0.5) {
                showProgressBar(optionElement, targetProgress, message);
                return;
            }
            
            // 如果目标进度小于当前进度，直接更新（避免进度倒退）
            if (targetProgress < currentProgress) {
                showProgressBar(optionElement, targetProgress, message);
                return;
            }
            
            // 特殊处理：接近完成时（currentProgress >= 90）使用更快的动画
            if (currentProgress >= 90) {
                showProgressBar(optionElement, targetProgress, message);
                return;
            }
            
            // 计算动画参数
            const progressDiff = targetProgress - currentProgress;
            
            // 优化动画时长计算
            let animationDuration;
            if (etaSeconds > 0 && etaSeconds < 60) {
                // 有效ETA且小于60秒，使用ETA的80%作为动画时长
                animationDuration = Math.min(etaSeconds * 800, 15000); // 最多15秒
            } else {
                // 根据进度差距自适应动画时长
                animationDuration = Math.min(progressDiff * 100, 8000); // 最多8秒
            }
            
            const updateInterval = 100; // 改为每100ms更新一次，更流畅
            const totalSteps = Math.max(1, Math.floor(animationDuration / updateInterval));
            const progressStep = progressDiff / totalSteps;
            
            let currentAnimatedProgress = currentProgress;
            let stepCount = 0;
            
            const intervalId = setInterval(() => {
                stepCount++;
                
                // 使用缓动函数让动画更自然
                const easingFactor = this._easeOutQuart(stepCount / totalSteps);
                currentAnimatedProgress = currentProgress + (progressDiff * easingFactor);
                
                // 确保不超过目标进度
                const displayProgress = Math.min(currentAnimatedProgress, targetProgress);
                
                // 更新进度条显示
                showProgressBar(optionElement, Math.round(displayProgress * 10) / 10, message);
                
                // 动画完成或达到目标
                if (stepCount >= totalSteps || displayProgress >= targetProgress) {
                    clearInterval(intervalId);
                    this.animations.delete(elementId);
                    showProgressBar(optionElement, targetProgress, message);
                    console.log(`✅ 平滑动画完成: ${targetProgress}%`);
                }
            }, updateInterval);
            
            // 存储动画状态
            this.animations.set(elementId, {
                intervalId,
                currentProgress: currentAnimatedProgress,
                targetProgress,
                etaSeconds,
                startTime: Date.now()
            });
            
            console.log(`🎬 开始平滑动画: ${currentProgress}% → ${targetProgress}% (${animationDuration}ms, ${totalSteps}步)`);
        }
        
        // 缓动函数：四次方缓出
        _easeOutQuart(t) {
            return 1 - Math.pow(1 - t, 4);
        }
        
        stopAnimation(elementId) {
            if (this.animations.has(elementId)) {
                const animation = this.animations.get(elementId);
                clearInterval(animation.intervalId);
                this.animations.delete(elementId);
                console.log(`🛑 停止动画: ${elementId}`);
            }
        }
        
        stopAllAnimations() {
            console.log(`🛑 停止所有动画 (${this.animations.size}个)`);
            this.animations.forEach((animation, elementId) => {
                clearInterval(animation.intervalId);
            });
            this.animations.clear();
        }
        
        // 获取当前动画状态
        getAnimationState(elementId) {
            return this.animations.get(elementId) || null;
        }
        
        // 检查是否正在动画中
        isAnimating(elementId) {
            return this.animations.has(elementId);
        }
    }
    
    // 创建全局平滑进度管理器
    const smoothProgressManager = new SmoothProgressManager();
    
    /**
     * Triggers a browser download for the given URL.
     * @param {string} downloadUrl - The URL to the file to be downloaded.
     * @param {string} [filename] - An optional filename for the download.
     */
    function triggerBrowserDownload(downloadUrl, filename) {
        const link = document.createElement('a');
        link.href = downloadUrl;
        if (filename) {
            link.download = filename; // The browser will use the Content-Disposition header if available
        }
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        console.log(`Triggered browser download for: ${downloadUrl}`);
    }

    /**
     * Updates the UI for a completed task, showing a success message and re-download/delete buttons.
     * @param {HTMLElement} optionElement - The original element that showed the progress.
     * @param {string} taskId - The task ID for re-downloading.
     */
    function updateUIToCompleted(optionElement, taskId) {
        const t = getTranslations();
        
        // Simply restore the original text that was saved before the download started.
        const titleText = optionElement.dataset.originalText || t.downloadComplete;

        // 使用HTML模板（如果已添加）或动态创建
        const template = document.getElementById('completed-task-template');
        let completedItem;

        if (template) {
            completedItem = template.content.cloneNode(true).firstElementChild;
        } else {
            // Fallback if template doesn't exist
            completedItem = document.createElement('div');
            completedItem.className = "completed-task-item p-4 rounded-lg grid grid-cols-[1fr_auto_1fr] items-center w-full gap-x-4";
            completedItem.innerHTML = `
                <!-- Left Spacer -->
                <div></div>
                <!-- Center Content: Text + Icon -->
                <div class="text-center">
                    <span class="task-title font-semibold text-white"></span>
                    <svg class="w-5 h-5 text-green-400 inline-block ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                </div>
                <!-- Right Buttons -->
                <div class="flex items-center justify-self-end">
                    <button class="resave-button button bg-blue-600 hover:bg-blue-700 text-xs py-1 px-3 mr-2" data-translate="resaveButton"></button>
                    <button class="delete-button button bg-red-600 hover:bg-red-700 text-xs py-1 px-3" data-translate="deleteButton"></button>
                </div>
            `;
        }

        const taskTitleSpan = completedItem.querySelector('.task-title');
        taskTitleSpan.textContent = titleText;

        // Set button text from translations
        completedItem.querySelector('.resave-button').textContent = t.resaveButton || 'Resave';
        completedItem.querySelector('.delete-button').textContent = t.deleteButton || 'Delete';

        // Define variables from the original element's dataset to fix the ReferenceError
        const resolution = optionElement.dataset.resolution;
        const originalAudioFormat = optionElement.dataset.audioFormatOriginal;

        // Add data attributes to the new span for future language switching.
        if (resolution !== 'audio' && !originalAudioFormat) {
            taskTitleSpan.setAttribute('data-translate-type', 'completed-video');
            taskTitleSpan.setAttribute('data-resolution', resolution);
            taskTitleSpan.setAttribute('data-formatted-size', optionElement.dataset.formattedSize);
            taskTitleSpan.setAttribute('data-ext', optionElement.dataset.ext);
        }
        
        // 为“重新保存”按钮添加事件监听
        const resaveButton = completedItem.querySelector('.resave-button');
        resaveButton.addEventListener('click', () => {
            const downloadUrl = `/download/file/${taskId}`;
            triggerBrowserDownload(downloadUrl);
        });

        // 为"删除"按钮添加事件监听
        const deleteButton = completedItem.querySelector('.delete-button');
        deleteButton.addEventListener('click', async (e) => {
            e.stopPropagation();
            
            const t = getTranslations();
            
            // 获取任务ID
            const taskId = optionElement.dataset.taskId;
            if (!taskId) {
                alert(t.errorTitle + ': 无法找到任务ID');
                return;
            }
            
            try {
                // 显示删除进度
                deleteButton.disabled = true;
                deleteButton.textContent = t.deleting || '删除中...';
                
                // 调用删除API
                const response = await fetch(`/download/file/${taskId}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || '删除失败');
                }
                
                const result = await response.json();
                console.log('文件删除成功:', result);
                
                // 恢复到下载前的状态
                await restoreToPreDownloadState(optionElement, taskId);
                
                // 短暂显示成功消息
                setTimeout(() => {
                    const successMessage = t.fileDeletedSuccess || `文件删除成功`;
                    if (result.file_size_mb > 0) {
                        successMessage += ` (${result.file_size_mb}MB)`;
                    }
                    
                    if (typeof showTemporaryMessage === 'function') {
                        showTemporaryMessage(successMessage, 'success');
                    }
                }, 100);
                
            } catch (error) {
                console.error('删除文件失败:', error);
                alert(t.errorTitle + ': ' + error.message);
                
                // 恢复按钮状态
                deleteButton.disabled = false;
                deleteButton.textContent = t.deleteButton || 'Delete';
            }
        });

        // 替换旧的UI
        optionElement.innerHTML = ''; // 清空原内容
        optionElement.appendChild(completedItem);
        optionElement.style.pointerEvents = 'auto';
        optionElement.style.opacity = '1';
        optionElement.classList.remove('is-downloading');
    }

    /**
     * 将已完成的任务恢复到下载前的状态
     * @param {HTMLElement} optionElement - 选项元素
     * @param {string} taskId - 任务ID
     */
    async function restoreToPreDownloadState(optionElement, taskId) {
        try {
            // 获取原始保存的文本
            const originalText = optionElement.dataset.originalText;
            
            if (!originalText) {
                console.error('无法找到原始文本，使用默认文本');
                return;
            }
            
            // 清空当前内容
            optionElement.innerHTML = '';
            
            // 重建原始结构
            const contentDiv = document.createElement('div');
            contentDiv.className = 'option-content w-full grid grid-cols-[auto_1fr_auto] items-center gap-x-4';
            
            // 检查是否为音频格式（通过dataset判断）
            const isAudio = optionElement.dataset.resolution === 'audio';
            
            if (isAudio) {
                // 音频格式的原始结构
                contentDiv.innerHTML = `
                    <div class="w-6 h-6"></div>
                    <div class="text-center">
                        <span class="font-semibold">${originalText}</span>
                    </div>
                    <div class="download-icon justify-self-end">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </div>
                `;
            } else {
                // 视频格式的原始结构
                contentDiv.innerHTML = `
                    <div></div>
                    <div class="text-center">
                        <span class="font-semibold">${originalText}</span>
                    </div>
                    <div class="download-icon justify-self-end">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </div>
                `;
            }
            
            // 添加进度条容器（隐藏状态）
            const progressDiv = document.createElement('div');
            progressDiv.className = 'option-progress w-full hidden';
            
            // 重新组装元素
            optionElement.appendChild(contentDiv);
            optionElement.appendChild(progressDiv);
            
            // 恢复原始样式和状态
            optionElement.style.pointerEvents = 'auto';
            optionElement.style.opacity = '1';
            optionElement.style.animation = '';
            optionElement.classList.remove('is-downloading', 'border', 'border-green-500');
            
            // 清理任务相关的dataset
            delete optionElement.dataset.taskId;
            delete optionElement.dataset.originalText;
            
            // 重新绑定点击事件
            optionElement.addEventListener('click', (e) => {
                // 检查是否有文字被选中，如果有则不触发下载
                const selection = window.getSelection();
                if (selection && selection.toString().length > 0) {
                    return;
                }
                
                handleDownload(optionElement.dataset.formatId);
            });
            
            console.log('成功恢复下载选项到原始状态');
            
        } catch (error) {
            console.error('恢复下载前状态失败:', error);
            // 如果恢复失败，至少移除当前元素
            optionElement.remove();
        }
    }

    // 动态轮询间隔管理器
    class DynamicPollingManager {
        constructor() {
            // 轮询阶段配置
            this.phases = [
                { name: 'initial', duration: 30000, interval: 1000 },    // 初始30秒，检查很频繁
                { name: 'active', duration: 120000, interval: 2000 },    // 活跃最2分钟，正常检查
                { name: 'slow', duration: 180000, interval: 4000 },      // 缓慢最3分钟，减少检查
                { name: 'final', duration: Infinity, interval: 8000 }    // 最终阶段，很少检查
            ];
            
            this.reset();
        }
        
        reset() {
            this.startTime = Date.now();
            this.currentPhaseIndex = 0;
            this.phaseStartTime = this.startTime;
            this.attemptCount = 0;
            this.consecutiveFailures = 0;
        }
        
        getCurrentInterval() {
            const now = Date.now();
            const totalElapsed = now - this.startTime;
            const phaseElapsed = now - this.phaseStartTime;
            const currentPhase = this.phases[this.currentPhaseIndex];
            
            // 检查是否需要进入下一阶段
            if (phaseElapsed >= currentPhase.duration && this.currentPhaseIndex < this.phases.length - 1) {
                this.currentPhaseIndex++;
                this.phaseStartTime = now;
                console.log(`轮询进入下一阶段: ${this.phases[this.currentPhaseIndex].name}`);
            }
            
            let interval = this.phases[this.currentPhaseIndex].interval;
            
            // 错误自适应：连续失败时逐渐增加间隔
            if (this.consecutiveFailures > 0) {
                const backoffMultiplier = Math.min(2 * this.consecutiveFailures, 8); // 最多8倍
                interval *= backoffMultiplier;
                console.log(`由于连续${this.consecutiveFailures}次失败，轮询间隔增加到${interval}ms`);
            }
            
            // 设置最大间隔限制（防止过长）
            interval = Math.min(interval, 30000); // 最多30秒
            
            return interval;
        }
        
        recordAttempt(success = true) {
            this.attemptCount++;
            
            if (success) {
                this.consecutiveFailures = 0;
            } else {
                this.consecutiveFailures++;
            }
        }
        
        getMaxAttempts() {
            // 动态计算最大尝试次数，基于总超时时间(10分钟)
            const totalTimeoutMs = 10 * 60 * 1000; // 10分钟
            const averageInterval = this.phases.reduce((sum, phase, index) => {
                if (index === this.phases.length - 1) return sum; // 最后一个阶段不计入平均值
                return sum + (phase.duration / phase.interval);
            }, 0) / (this.phases.length - 1);
            
            return Math.ceil(totalTimeoutMs / averageInterval);
        }
        
        getPhaseInfo() {
            const currentPhase = this.phases[this.currentPhaseIndex];
            const elapsed = Date.now() - this.startTime;
            return {
                phase: currentPhase.name,
                elapsed: Math.round(elapsed / 1000),
                attempts: this.attemptCount,
                consecutiveFailures: this.consecutiveFailures
            };
        }
    }
function pollTaskStatus(taskId, optionElement) {
    const t = getTranslations();
    
    // 创建动态轮询管理器
    const pollingManager = new DynamicPollingManager();
    const maxAttempts = pollingManager.getMaxAttempts();
    let attempts = 0;
    let timeoutId = null; // 使用setTimeout而不是setInterval
    let isPollingActive = true; // 轮询状态标记

    const contentDiv = optionElement.querySelector('.option-content');
    const progressDiv = optionElement.querySelector('.option-progress');

    const restoreOriginalContent = () => {
        progressDiv.classList.add('hidden');
        progressDiv.innerHTML = '';
        contentDiv.classList.remove('hidden');
    };
    
    const stopPolling = () => {
        isPollingActive = false;
        if (timeoutId) {
            clearTimeout(timeoutId);
            timeoutId = null;
        }
        optionElement.removeAttribute('data-polling-interval');
        optionElement.classList.remove('is-downloading');
    };
    
    // 递归轮询函数
    const performPoll = async () => {
        // 检查轮询是否应该停止
        if (!isPollingActive) {
            console.log(`Polling for task ${taskId} was stopped`);
            return;
        }
        
        // Handle immediate failure from handleDownload
        if (taskId === null) {
            stopPolling();
            restoreOriginalContent();
            optionElement.style.pointerEvents = 'auto';
            optionElement.style.opacity = '1';
            // Optionally add a temporary failure indicator
            optionElement.classList.add('border-red-500', 'border-2');
            setTimeout(() => {
                if (optionElement) { // Check if element still exists
                    optionElement.classList.remove('border-red-500', 'border-2');
                }
            }, 2000);
            return;
        }

        if (attempts++ > maxAttempts) {
            stopPolling();
            const timeoutIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
            const timeoutMessage = translateProgressMessage('检查超时', t);
            showTaskStatus(optionElement, 'timeout', timeoutMessage, timeoutIcon, 'text-yellow-400', 'border-yellow-500');
            
            // 显示轮询统计信息
            const phaseInfo = pollingManager.getPhaseInfo();
            console.log(`轮询超时 - 阶段: ${phaseInfo.phase}, 耗时: ${phaseInfo.elapsed}秒, 尝试: ${phaseInfo.attempts}次`);
            alert(`${t.downloadTimeoutMessage}\n\n轮询统计信息:\n- 阶段: ${phaseInfo.phase}\n- 耗时: ${phaseInfo.elapsed}秒\n- 尝试: ${phaseInfo.attempts}次`);
            return;
        }

        try {
            // Check if polling has been externally cancelled before making the request
            if (!optionElement.dataset.pollingInterval || !isPollingActive) {
                console.log(`Polling for task ${taskId} was cancelled, stopping`);
                stopPolling();
                return;
            }
            
            const response = await fetch(`/downloads/${taskId}`);
            
            // Check again after the async request in case it was cancelled during the fetch
            if (!optionElement.dataset.pollingInterval || !isPollingActive) {
                console.log(`Polling for task ${taskId} was cancelled during fetch, stopping`);
                stopPolling();
                return;
            }
            
            let requestSuccess = true;
            if (!response.ok) {
                console.warn(`轮询任务状态失败 ${taskId}: ${response.status}`);
                requestSuccess = false;
                pollingManager.recordAttempt(false);
                // 继续下一次轮询而不是直接返回
            } else {
                pollingManager.recordAttempt(true);
                const data = await response.json();
    
                if (data.status === 'SUCCESS') {
                    stopPolling();
                    smoothProgressManager.stopAnimation(optionElement.dataset.formatId);

                    const phaseInfo = pollingManager.getPhaseInfo();
                    console.log(`后台任务完成 - 阶段: ${phaseInfo.phase}, 耗时: ${phaseInfo.elapsed}秒, 尝试: ${phaseInfo.attempts}次`);

                    // 从Celery结果中获取任务ID，这是我们的下载凭证
                    const taskId = optionElement.dataset.taskId;
                    if (!taskId) {
                        console.error("无法找到任务ID，无法触发下载。");
                        // 显示错误状态
                        const errorIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
                        showTaskStatus(optionElement, 'failure', t.unknownError, errorIcon, 'text-red-400', 'border-red-500');
                        return;
                    }

                    // 1. 自动触发第一次下载
                    const downloadUrl = `/download/file/${taskId}`;
                    triggerBrowserDownload(downloadUrl);

                    // 2. 更新UI为“已完成”状态，并提供“重新下载”按钮
                    updateUIToCompleted(optionElement, taskId);

                    return; // 确保在这里结束函数执行
                    
                } else if (data.status === 'FAILURE') {
                    stopPolling();
                    
                    // 停止平滑动画
                    smoothProgressManager.stopAnimation(optionElement.dataset.formatId);
                    
                    const errorIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
                    const failedMessage = translateProgressMessage('下载失败', t);
                    showTaskStatus(optionElement, 'failure', failedMessage, errorIcon, 'text-red-400', 'border-red-500');
                    const errorMessage = data.result || t.unknownError;
                    
                    // Log error to console for debugging
                    console.error(`Download failed for task ${taskId}:`, errorMessage);
                    return;
                } else if (data.status === 'PROGRESS') {
                    // 处理进度更新
                    const meta = data.result || data.meta || {};
                    const progress = meta.progress || 0;
                    const etaSeconds = meta.eta_seconds || 0;
                    const speed = meta.speed || '';
                    let statusMessage = meta.status || t.downloading || '下载中...';
                    
                    // 多语言处理：将后端的中文消息翻译为当前语言
                    statusMessage = translateProgressMessage(statusMessage, t);
                    
                    // 获取当前显示的进度
                    const currentProgress = getCurrentDisplayProgress(optionElement);
                    
                    // 检查是否正在动画中
                    const isAnimating = smoothProgressManager.isAnimating(optionElement.dataset.formatId);
                    
                    // 优化平滑进度策略
                    if (isAnimating) {
                        // 如果正在动画中，检查新进度是否显著不同
                        const animationState = smoothProgressManager.getAnimationState(optionElement.dataset.formatId);
                        if (animationState && Math.abs(progress - animationState.targetProgress) > 2) {
                            // 进度跳跃较大，重新开始动画
                            smoothProgressManager.startSmoothProgress(
                                optionElement, 
                                currentProgress, 
                                progress, 
                                etaSeconds, 
                                statusMessage
                            );
                        }
                        // 否则让当前动画继续
                    } else {
                        // 使用平滑进度动画的条件优化
                        const progressDiff = progress - currentProgress;
                        
                        // 特殊处理：接近完成时（>=95%）直接更新，避免ETA=0导致的问题
                        if (progress >= 95) {
                            showProgressBar(optionElement, progress, statusMessage);
                        } else if (etaSeconds > 0 && progressDiff > 0.5 && progressDiff < 30) {
                            // 有ETA且进度差距合理时使用平滑动画
                            smoothProgressManager.startSmoothProgress(
                                optionElement, 
                                currentProgress, 
                                progress, 
                                etaSeconds, 
                                statusMessage
                            );
                        } else {
                            // 其他情况直接更新
                            showProgressBar(optionElement, progress, statusMessage);
                        }
                    }
                    
                    console.log(`📊 进度更新: ${progress}% (当前: ${currentProgress}%, 动画中: ${isAnimating})${etaSeconds > 0 ? ` ETA: ${etaSeconds}s` : ''}`);
                }
                // 如果状态是 PENDING 或 STARTED，则不执行任何操作，让加载动画继续
            }

        } catch (error) {
            console.error('轮询过程中发生错误:', error);
            pollingManager.recordAttempt(false);
        }
        
        // 检查是否应该继续轮询
        if (!isPollingActive) {
            console.log(`Polling stopped for task ${taskId}`);
            return;
        }
        
        // 获取下一次轮询的动态间隔
        const nextInterval = pollingManager.getCurrentInterval();
        const phaseInfo = pollingManager.getPhaseInfo();
        
        // 记录轮询信息用于调试
        if (attempts % 10 === 0) { // 每10次轮询记录一次
            console.log(`轮询进度 - 阶段: ${phaseInfo.phase}, 下次间隔: ${nextInterval}ms, 尝试: ${phaseInfo.attempts}次`);
        }
        
        // 设置下一次轮询
        timeoutId = setTimeout(performPoll, nextInterval);
        
        // 更新元素的跟踪数据
        optionElement.dataset.pollingInterval = timeoutId;
    };
    
    // 开始第一次轮询
    const initialInterval = pollingManager.getCurrentInterval();
    console.log(`开始动态轮询 - 任务ID: ${taskId}, 初始间隔: ${initialInterval}ms`);
    
    timeoutId = setTimeout(performPoll, initialInterval);
    optionElement.dataset.pollingInterval = timeoutId;
    
    console.log(`Started dynamic polling for task ${taskId} with timeout ID ${timeoutId}`);
}

    // URL安全验证函数
    function validateURL(url) {
        const errors = [];
        
        // 基础验证
        if (!url || url.trim() === '') {
            errors.push('链接不能为空');
            return { valid: false, errors };
        }
        
        const trimmedUrl = url.trim();
        
        // 长度限制（防止DoS攻击）
        if (trimmedUrl.length > 2048) {
            errors.push('链接长度超过限制（最大2048字符）');
        }
        
        // 安全协议验证
        const dangerousProtocols = [
            'javascript:',
            'data:',
            'file:',
            'ftp:',
            'mailto:',
            'tel:',
            'sms:',
            'vbscript:',
            'about:',
            'chrome:',
            'chrome-extension:',
            'moz-extension:',
            'ms-appx:',
            'x-javascript:'
        ];
        
        const lowerUrl = trimmedUrl.toLowerCase();
        for (const protocol of dangerousProtocols) {
            if (lowerUrl.startsWith(protocol)) {
                errors.push(`不允许的协议类型: ${protocol}`);
                break;
            }
        }
        
        // XSS防护：检查危险字符
        const dangerousPatterns = [
            /<script[^>]*>/i,
            /<\/script>/i,
            /<iframe[^>]*>/i,
            /<object[^>]*>/i,
            /<embed[^>]*>/i,
            /<link[^>]*>/i,
            /<meta[^>]*>/i,
            /on\w+\s*=/i,  // 事件处理器
            /\x00/,         // 空字节
            /[\r\n]/,       // 换行符
        ];
        
        for (const pattern of dangerousPatterns) {
            if (pattern.test(trimmedUrl)) {
                errors.push('链接包含危险字符或标签');
                break;
            }
        }
        
        // URL格式验证
        try {
            const parsedUrl = new URL(trimmedUrl);
            
            // 只允许HTTP/HTTPS协议
            if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
                errors.push('只支持HTTP和HTTPS协议的链接');
            }
            
            // 防止内网IP地址攻击（SSRF防护）
            const hostname = parsedUrl.hostname.toLowerCase();
            const forbiddenHosts = [
                'localhost',
                '127.0.0.1',
                '0.0.0.0',
                '::1',
                '[::1]'
            ];
            
            if (forbiddenHosts.includes(hostname)) {
                errors.push('不允许访问本地地址');
            }
            
            // 检查内网IP段
            if (hostname.match(/^10\.|^172\.(1[6-9]|2[0-9]|3[01])\.|^192\.168\./)) {
                errors.push('不允许访问内网地址');
            }
            
            // 检查端口安全性
            if (parsedUrl.port) {
                const port = parseInt(parsedUrl.port);
                const dangerousPorts = [22, 23, 25, 53, 110, 143, 993, 995, 1433, 3306, 5432, 6379, 27017];
                if (dangerousPorts.includes(port)) {
                    errors.push(`不允许访问端口: ${port}`);
                }
            }
            
        } catch (e) {
            errors.push('无效的URL格式');
        }
        
        return {
            valid: errors.length === 0,
            errors,
            cleanUrl: trimmedUrl
        };
    }
    
    // 域名白名单验证函数（保留原有逻辑）
    function validateDomainWhitelist(url) {
        const allowedDomains = appConfig.security?.allowed_domains || [];
        
        if (allowedDomains.length === 0) {
            return { valid: true, errors: [] };
        }
        
        try {
            const urlHostname = new URL(url).hostname.toLowerCase();
            const isAllowed = allowedDomains.some(domain => urlHostname.endsWith(domain.toLowerCase()));
            
            if (!isAllowed) {
                const domainList = allowedDomains.join(', ');
                return {
                    valid: false,
                    errors: [`不支持从 "${urlHostname}" 下载。只支持以下网站: ${domainList}`]
                };
            }
            
            return { valid: true, errors: [] };
        } catch (e) {
            return { valid: false, errors: ['无法解析链接域名'] };
        }
    }
    
    // 综合URL验证函数
    function validateCompleteURL(url) {
        const errors = [];
        
        // 1. 基础安全验证
        const securityValidation = validateURL(url);
        if (!securityValidation.valid) {
            errors.push(...securityValidation.errors);
        }
        
        // 2. 域名白名单验证
        if (securityValidation.valid) {
            const whitelistValidation = validateDomainWhitelist(securityValidation.cleanUrl);
            if (!whitelistValidation.valid) {
                errors.push(...whitelistValidation.errors);
            }
        }
        
        return {
            valid: errors.length === 0,
            errors,
            cleanUrl: securityValidation.cleanUrl
        };
    }
    function validateFormatId(formatId, currentVideoData) {
        const errors = [];
        
        // 基础验证
        if (!formatId || formatId === 'undefined' || formatId === 'null' || formatId.trim() === '') {
            errors.push('Format ID cannot be empty');
            return { valid: false, errors };
        }
        
        // 安全性验证：防止路径遍历和注入攻击
        const dangerousPatterns = [
            /\.\.\//,  // 路径遍历
            /\\\.\.\\/, // Windows路径遍历
            /[<>"'\\]/,  // HTML/JS注入字符
            /\x00/,      // 空字节
            /[\r\n]/,    // 换行符
            /[;&|`$]/    // 命令注入字符
        ];
        
        for (const pattern of dangerousPatterns) {
            if (pattern.test(formatId)) {
                errors.push('Format ID contains dangerous characters');
                break;
            }
        }
        
        // 长度验证
        if (formatId.length > 100) {
            errors.push('Format ID too long');
        }
        
        // 格式验证：只允许字母、数字、连字符、下划线和加号
        if (!/^[a-zA-Z0-9_+-]+$/.test(formatId)) {
            errors.push('Format ID contains invalid characters');
        }
        
        // 视频数据可用性验证
        if (!currentVideoData || !currentVideoData.formats) {
            errors.push('No video data available');
            return { valid: false, errors };
        }
        
        // 检查formatId是否存在于可用格式列表中
        const formatExists = currentVideoData.formats.some(f => f.format_id === formatId);
        if (!formatExists) {
            // 特殊情况：MP3转换格式
            if (formatId.startsWith('mp3-conversion-')) {
                const baseFormatId = formatId.replace('mp3-conversion-', '');
                const baseExists = currentVideoData.formats.some(f => f.format_id === baseFormatId);
                if (!baseExists) {
                    errors.push(`Base format for MP3 conversion not found: ${baseFormatId}`);
                }
            } else {
                errors.push(`Format ${formatId} not found in available formats`);
            }
        }
        
        return {
            valid: errors.length === 0,
            errors
        };
    }
    
    // 下载请求验证函数
    function validateDownloadRequest(formatId, downloadType, currentVideoData) {
        const errors = [];
        
        // 验证格式ID
        const formatValidation = validateFormatId(formatId, currentVideoData);
        if (!formatValidation.valid) {
            errors.push(...formatValidation.errors);
        }
        
        // 验证下载类型
        if (!downloadType || !['video', 'audio'].includes(downloadType)) {
            errors.push('Invalid download type');
        }
        
        // 验证URL
        if (!currentVideoData || !currentVideoData.original_url) {
            errors.push('No video URL available');
        }
        
        return {
            valid: errors.length === 0,
            errors
        };
    }
    function handleDownload(formatId) {
        if (!currentVideoData) {
            console.error('No video data available');
            alert('错误：没有可用的视频数据');
            return;
        }
        
        const t = getTranslations();
        
        // 验证下载请求
        const validation = validateDownloadRequest(formatId, currentVideoData.download_type, currentVideoData);
        if (!validation.valid) {
            const errorMessage = `下载验证失败：\n${validation.errors.join('\n')}`;
            console.error('Download validation failed:', validation.errors);
            alert(errorMessage);
            return;
        }
        const optionElement = document.querySelector(`[data-format-id="${formatId}"]`);

        // Save the original descriptive text before showing the progress bar
        const textSpan = optionElement.querySelector('.option-content span');
        if (textSpan) {
            optionElement.dataset.originalText = textSpan.textContent.trim();
        }

        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');

        optionElement.classList.add('is-downloading');
        const resolution = optionElement.dataset.resolution || '';

        // Check if this supports direct download (either complete stream or audio with browser download support)
        const isCompleteStream = optionElement.dataset.isCompleteStream === 'true';
        const supportsBrowserDownload = optionElement.dataset.supportsBrowserDownload === 'true';
        
        if (supportsBrowserDownload) {
            // 直接下载模式：完整流可以直接通过浏览器下载
            handleDirectDownload(formatId, optionElement, currentVideoData.download_type);
        } else {
            // 后台下载模式：需要合并的视频/音频流，服务器处理完后弹出浏览器另存为
            handleBackgroundDownload(formatId, optionElement);
        }
    }

    // 统一的直接下载处理函数
    function handleDirectDownload(formatId, optionElement, downloadType) {
        // 验证格式ID
        const validation = validateFormatId(formatId, currentVideoData);
        if (!validation.valid) {
            console.error('Direct download validation failed:', validation.errors);
            alert(`直接下载验证失败：\n${validation.errors.join('\n')}`);
            return;
        }
        
        const t = getTranslations();
        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');
        
        // 保存原始内容的文本
        const originalText = contentDiv.querySelector('span').textContent;
        
        // 根据下载类型设置不同的显示内容
        const isVideo = downloadType === 'video';
        const statusText = isVideo ? 
            (t.directDownloading || '直接下载中...') : 
            (t.directAudioDownloading || '音频流传输中...');
        const statusIcon = isVideo ? '⚡' : '🎵';
        const delay = isVideo ? 1500 : 1200;
        
        // 显示下载状态
        contentDiv.classList.add('hidden');
        progressDiv.innerHTML = `
            <div class="flex-grow text-center">
                <span class="font-semibold text-blue-400">${statusText}</span>
            </div>
            <div class="download-icon text-blue-400">
                ${statusIcon}
            </div>
        `;
        progressDiv.classList.remove('hidden');
        
        // 构建下载参数
        const originalUrl = currentVideoData.original_url;
        const title = currentVideoData.title || (isVideo ? 'video' : 'audio');
        const resolution = isVideo ? (optionElement.dataset.resolution || '') : 'audio';
        
        // 构建下载URL
        const downloadParams = {
            url: originalUrl,
            download_type: downloadType,
            format_id: formatId,
            resolution: resolution,
            title: title
        };
        
        // 如果是音频下载，添加音频格式参数
        if (!isVideo) {
            const audioFormat = optionElement.dataset.audioFormat || 'm4a';
            downloadParams.audio_format = audioFormat;
            console.log(`🎵 直接下载音频格式: ${audioFormat}`, downloadParams);
        }
        
        const downloadUrl = `/download-stream?${new URLSearchParams(downloadParams).toString()}`;
        
        // 文件名由后端处理，前端不再构建
        // 后端会在HTTP响应头中设置正确的文件名（包括Unicode支持和智能截断）
        const filename = 'download'; // 临时文件名，实际由后端Content-Disposition头决定
        
        // 触发浏览器下载
        triggerBrowserDownload(downloadUrl, filename);
        
        // 延迟显示完成状态
        setTimeout(() => {
            showDownloadComplete(contentDiv, progressDiv, originalText, optionElement);
        }, delay);
    }
    
    // 通用的浏览器下载触发函数
    function triggerBrowserDownload(downloadUrl, filename) {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    // 通用的下载完成状态显示函数
    function showDownloadComplete(contentDiv, progressDiv, originalText, optionElement) {
        progressDiv.classList.add('hidden');
        
        // Instead of replacing the entire innerHTML, just update the icon.
        // This preserves the grid layout and ensures text alignment remains correct.
        const iconContainer = contentDiv.querySelector('.download-icon');
        if (iconContainer) {
            iconContainer.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="text-green-400">
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            `;
        }
        
        contentDiv.classList.remove('hidden');
        optionElement.classList.remove('is-downloading');
        optionElement.classList.add('border', 'border-green-500');
    }

    // 通用的进度条样式初始化函数
    function initializeIndeterminateProgressStyle() {
        if (!document.getElementById('indeterminate-progress-style')) {
            const style = document.createElement('style');
            style.id = 'indeterminate-progress-style';
            style.innerHTML = `
                .progress-bar-indeterminate {
                    width: 40%;
                    animation: indeterminate-progress 2s infinite ease-in-out;
                }
                @keyframes indeterminate-progress {
                    0% { margin-left: -40%; }
                    100% { margin-left: 100%; }
                }
                /* 添加轻微的脉冲动画 */
                @keyframes subtle-pulse {
                    0%, 100% { 
                        transform: scale(1);
                        box-shadow: 0 0 0 0 rgba(168, 85, 247, 0.4);
                    }
                    50% { 
                        transform: scale(1.02);
                        box-shadow: 0 0 0 8px rgba(168, 85, 247, 0.1);
                    }
                }
                /* 进度条完成时的庆祝动画 */
                @keyframes progress-complete {
                    0% { transform: scale(1); }
                    50% { transform: scale(1.05); }
                    100% { transform: scale(1); }
                }
                .progress-complete-animation {
                    animation: progress-complete 0.6s ease-out;
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    // 通用的不确定进度条显示函数
    function showIndeterminateProgress(optionElement) {
        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');
        
        initializeIndeterminateProgressStyle();
        
        contentDiv.classList.add('hidden');
        progressDiv.innerHTML = `
            <div class="progress-bar-container w-full bg-gray-700 rounded-full h-2.5 overflow-hidden">
                <div class="progress-bar-indeterminate bg-purple-500 h-2.5 rounded-full"></div>
            </div>
        `;
        progressDiv.classList.remove('hidden');
        optionElement.style.pointerEvents = 'none';
        optionElement.style.opacity = '0.7';
    }

    // 显示具体进度的进度条函数
    function showProgressBar(optionElement, progress, message) {
        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');
        
        contentDiv.classList.add('hidden');
        
        // 确保progress在0-100范围内
        const clampedProgress = Math.max(0, Math.min(100, progress));
        
        // 简化的翻译键判断
        let translateKey = '';
        if (message === '正在下载中' || message === 'Downloading') {
            translateKey = 'downloading';
        } else if (message === '下载完成' || message === 'Download Complete') {
            translateKey = 'downloadComplete';
        }
        
        progressDiv.innerHTML = `
            <div class="flex flex-col w-full space-y-3">
                <!-- 进度条容器，包含居中文本 -->
                <div class="progress-bar-container w-full bg-gray-600 rounded-full h-8 overflow-hidden shadow-inner relative">
                    <!-- 进度条背景 -->
                    <div class="progress-bar bg-gradient-to-r from-purple-500 via-blue-500 to-purple-600 h-8 rounded-full transition-all duration-500 ease-out relative overflow-hidden" 
                         style="width: ${clampedProgress}%">
                        <!-- 添加闪烁效果 -->
                        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-20 animate-pulse"></div>
                    </div>
                    <!-- 居中的状态文本和百分比 -->
                    <div class="absolute inset-0 flex items-center justify-center">
                        <div class="flex items-center space-x-2">
                            <span class="text-sm font-medium text-white drop-shadow-lg" style="text-shadow: 1px 1px 2px rgba(0,0,0,0.8);" ${translateKey ? `data-translate-dynamic="${translateKey}"` : ''}>${message}</span>
                            <span class="text-sm font-bold text-purple-200 drop-shadow-lg" style="text-shadow: 1px 1px 2px rgba(0,0,0,0.8);">${clampedProgress}%</span>
                        </div>
                    </div>
                </div>
                <!-- 小的状态指示器 -->
                <div class="flex items-center justify-center">
                    <div class="w-2 h-2 bg-purple-400 rounded-full animate-pulse"></div>
                </div>
            </div>
        `;
        progressDiv.classList.remove('hidden');
        optionElement.style.pointerEvents = 'none';
        optionElement.style.opacity = '0.9';
        
        // 添加轻微的脉冲动画效果
        optionElement.style.animation = 'subtle-pulse 2s ease-in-out infinite';
    }
    
    // 翻译后端进度消息的辅助函数
    function translateProgressMessage(message, translations) {
        const progressTranslations = {
            // 中文到多语言的映射
            '正在下载中': {
                zh: '正在下载中',
                en: 'Downloading'
            },
            '下载完成': {
                zh: '下载完成',
                en: 'Download Complete'
            },
            '下载失败': {
                zh: '下载失败',
                en: 'Download Failed'
            },
            '检查超时': {
                zh: '检查超时',
                en: 'Check Timeout'
            },
            // 英文到多语言的映射（逆向翻译）
            'Downloading': {
                zh: '正在下载中',
                en: 'Downloading'
            },
            'Download Complete': {
                zh: '下载完成',
                en: 'Download Complete'
            },
            'Download Failed': {
                zh: '下载失败',
                en: 'Download Failed'
            },
            'Check Timeout': {
                zh: '检查超时',
                en: 'Check Timeout'
            }
        };
        
        // 获取当前语言设置
        const currentLang = localStorage.getItem('language') || 'zh';
        
        // 查找并翻译消息
        const translation = progressTranslations[message];
        if (translation && translation[currentLang]) {
            return translation[currentLang];
        }
        
        // 如果没有找到翻译，返回原消息
        return message;
    }
    
    // 更新进行中下载的进度条消息语言显示
    function updateProgressLanguage() {
        // 进度消息现在使用data-translate-dynamic系统，不需要特殊处理
        // 该函数保留以防将来需要处理其他进度相关的语言更新
    }

    function handleBackgroundDownload(formatId, optionElement) {
        // 验证格式ID
        const validation = validateFormatId(formatId, currentVideoData);
        if (!validation.valid) {
            console.error('Background download validation failed:', validation.errors);
            alert(`后台下载验证失败：\n${validation.errors.join('\n')}`);
            return;
        }
        
        const t = getTranslations();
        const resolution = optionElement.dataset.resolution || '';

        // 显示初始进度条（0%）
        const initialMessage = translateProgressMessage(t.downloading || '正在下载中', t);
        showProgressBar(optionElement, 0, initialMessage);
        
        // 确保进度条样式已初始化
        initializeIndeterminateProgressStyle();
        fetch('/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentVideoData.original_url,
                download_type: currentVideoData.download_type,
                format_id: formatId,
                resolution: resolution,
                title: currentVideoData.title || 'download'
            }),
        })
        .then(response => {
            if (!response.ok) return response.json().then(err => Promise.reject(err));
            return response.json();
        })
        .then(data => {
            // Store the task_id on the element for cancellation
            optionElement.dataset.taskId = data.task_id;
            pollTaskStatus(data.task_id, optionElement);
        })
        .catch(error => {
            const errorMessage = error.detail || error.message || t.unknownError;
            alert(t.errorTitle + ': ' + errorMessage);
            // 失败时也调用轮询函数来恢复UI
            pollTaskStatus(null, optionElement);
        });
    }

    function resetUI() {
    currentVideoData = null; // Clear any stored video data

    // Restore the main heading's original class and translation key
    const mainHeading = document.querySelector('.hero-section h1');
    if (mainHeading) {
        mainHeading.className = 'text-4xl md:text-5xl font-bold text-white mt-8 mb-8';
        mainHeading.setAttribute('data-translate', 'mainHeading');
    }

    // Show the main input and buttons, hide the results container
    const inputGroup = document.querySelector('.input-group');
    if (inputGroup) inputGroup.style.display = 'block';
    
    const buttonGroup = document.querySelector('.button-group');
    if (buttonGroup) buttonGroup.style.display = 'flex';

    const resultContainer = document.getElementById('resultContainer');
    if (resultContainer) {
        resultContainer.style.display = 'none';
        resultContainer.innerHTML = '';
    }
    
    // Clear the URL input field
    const urlInput = document.getElementById('videoUrl');
    if (urlInput) {
        urlInput.value = '';
        urlInput.dispatchEvent(new Event('input')); // Trigger event to reset paste/clear buttons
    }

    // Re-apply translations for the entire page to ensure consistency
    const lang = localStorage.getItem('language') || 'zh';
    switchLanguage(lang);
}

    // --- URL History Management ---
    const URL_HISTORY_KEY = 'smartDownloader_urlHistory';
    const MAX_HISTORY_ITEMS = 10;

    function saveUrlToHistory(url) {
        if (!url || url.trim() === '') return;
        
        const history = getUrlHistory();
        const cleanUrl = url.trim();
        
        // Remove if already exists (to move to top)
        const filteredHistory = history.filter(item => item !== cleanUrl);
        
        // Add to beginning
        filteredHistory.unshift(cleanUrl);
        
        // Keep only MAX_HISTORY_ITEMS
        const newHistory = filteredHistory.slice(0, MAX_HISTORY_ITEMS);
        
        localStorage.setItem(URL_HISTORY_KEY, JSON.stringify(newHistory));
    }

    function getUrlHistory() {
        try {
            const history = localStorage.getItem(URL_HISTORY_KEY);
            return history ? JSON.parse(history) : [];
        } catch (error) {
            console.error('Error loading URL history:', error);
            return [];
        }
    }

    function clearUrlHistory() {
        localStorage.removeItem(URL_HISTORY_KEY);
        hideUrlHistory();
    }

    function removeUrlFromHistory(urlToRemove) {
        const history = getUrlHistory();
        const newHistory = history.filter(url => url !== urlToRemove);
        localStorage.setItem(URL_HISTORY_KEY, JSON.stringify(newHistory));
        
        // Refresh the history display
        showUrlHistory();
    }

    function showUrlHistory() {
        const historyContainer = document.getElementById('urlHistory');
        if (!historyContainer) return;

        const history = getUrlHistory();
        const t = getTranslations();
        
        if (history.length === 0) {
            historyContainer.innerHTML = `<div class="url-history-empty">${t.noHistoryRecord || '暂无历史记录'}</div>`;
        } else {
            historyContainer.innerHTML = history
                .map(url => `
                    <div class="url-history-item" data-url="${encodeURIComponent(url)}">
                        <span class="url-text" title="${url}">${url}</span>
                        <span class="url-delete" data-url="${encodeURIComponent(url)}">×</span>
                    </div>
                `).join('');
            
            // Add click handlers for history items (clicking on URL text)
            historyContainer.querySelectorAll('.url-text').forEach(item => {
                item.addEventListener('click', () => {
                    const historyItem = item.closest('.url-history-item');
                    const url = decodeURIComponent(historyItem.dataset.url);
                    urlInput.value = url;
                    hideUrlHistory();
                    
                    // Update paste/clear buttons
                    if (url.length > 0) {
                        pasteButton.style.display = 'none';
                        clearButton.style.display = 'flex';
                    }
                });
            });
            
            // Add click handlers for delete buttons
            historyContainer.querySelectorAll('.url-delete').forEach(deleteBtn => {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation(); // Prevent triggering the URL selection
                    const url = decodeURIComponent(deleteBtn.dataset.url);
                    removeUrlFromHistory(url);
                });
            });
        }
        
        historyContainer.style.display = 'block';
    }

    function hideUrlHistory() {
        const historyContainer = document.getElementById('urlHistory');
        if (historyContainer) {
            historyContainer.style.display = 'none';
        }
    }

    // Add URL history event listeners
    urlInput.addEventListener('focus', () => {
        showUrlHistory();
    });

    urlInput.addEventListener('blur', (e) => {
        // Delay hiding to allow clicking on history items
        setTimeout(() => {
            const historyContainer = document.getElementById('urlHistory');
            if (historyContainer && !historyContainer.contains(e.relatedTarget)) {
                hideUrlHistory();
            }
        }, 150);
    });

    // Save URL to history when analysis starts
    const originalStartVideoAnalysis = startVideoAnalysis;
    startVideoAnalysis = function(downloadType) {
        const url = urlInput.value.trim();
        if (url && url !== 'test-video' && url !== 'test-audio') {
            saveUrlToHistory(url);
        }
        return originalStartVideoAnalysis(downloadType);
    };

    // --- Clipboard and Input Handling ---
    function extractUrl(text) {
        const urlRegex = /(https?:\/\/[^\s]+)/;
        const match = text.match(urlRegex);
        return match ? match[0] : '';
    }
    if (pasteButton) {
        pasteButton.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                if (text) {
                    const extracted = extractUrl(text);
                    if (extracted) {
                        urlInput.value = extracted;
                        pasteButton.style.display = 'none';
                        clearButton.style.display = 'flex';
                    }
                }
            } catch (err) {
                console.error('Failed to read clipboard:', err);
            }
        });
    }
    if (clearButton) {
        clearButton.addEventListener('click', () => {
            urlInput.value = '';
            pasteButton.style.display = 'flex';
            clearButton.style.display = 'none';
            urlInput.focus();
        });
    }
    urlInput.addEventListener('input', () => {
        if (urlInput.value.length > 0) {
            pasteButton.style.display = 'none';
            clearButton.style.display = 'flex';
        } else {
            pasteButton.style.display = 'flex';
            clearButton.style.display = 'none';
        }
    });
});

// --- NEW: Mock Data for Developer Testing ---
function getMockVideoData() {
    return {
        title: "【本地测试视频】一个非常精彩的演示视频",
        original_url: "local-test-video",
        download_type: "video",
        formats: [
            {
                format_id: "test-vid-1080p",
                resolution: "1920x1080",
                vcodec: "avc1.640028",
                acodec: "mp4a.40.2",
                ext: "mp4",
                fps: 60,
            },
            {
                format_id: "test-vid-720p",
                resolution: "1280x720",
                vcodec: "avc1.4d401f",
                acodec: "mp4a.40.2",
                ext: "mp4",
                fps: 30,
            },
            {
                format_id: "test-vid-360p",
                resolution: "640x360",
                vcodec: "avc1.42c01e",
                acodec: "mp4a.40.2",
                ext: "mp4",
                fps: 30,
            }
        ]
    };
}

function getMockAudioData() {
    return {
        title: "【本地测试音频】轻松愉快的背景音乐",
        original_url: "local-test-audio",
        download_type: "audio",
       formats: [
           { format_id: "test-aud-high", quality: "高品质", ext: "m4a", abr: 128, filesize: 5 * 1024 * 1024 }, // 5MB
           { format_id: "test-aud-medium", quality: "中等品质", ext: "m4a", abr: 96, filesize: 3.5 * 1024 * 1024 }, // 3.5MB
           { format_id: "test-aud-low", quality: "普通品质", ext: "m4a", abr: 64, filesize: 2 * 1024 * 1024 }, // 2MB
       ]
   };
}


// --- Helper functions for dark mode and language ---
function initializeDarkMode() {
    const darkModeToggle = document.getElementById('darkModeToggle');
    const body = document.body;
    if (!darkModeToggle) return;
    const currentTheme = localStorage.getItem('theme') || 'light';
    if (currentTheme === 'dark') {
        body.classList.add('dark-mode');
        darkModeToggle.textContent = '☀️';
    } else {
        darkModeToggle.textContent = '🌙';
    }
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

function initializeLanguageSelector() {
    const languageToggle = document.getElementById('languageToggle');
    const languageMenu = document.getElementById('languageMenu');
    const languageOptions = document.querySelectorAll('.language-option');
    if (!languageToggle || !languageMenu) return;
    languageToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        languageMenu.classList.toggle('hidden');
    });
    document.addEventListener('click', (e) => {
        if (!languageToggle.contains(e.target) && !languageMenu.contains(e.target)) {
            languageMenu.classList.add('hidden');
        }
    });
    languageOptions.forEach(option => {
        option.addEventListener('click', (e) => {
            const selectedLang = e.target.dataset.lang;
            switchLanguage(selectedLang);
            languageMenu.classList.add('hidden');
        });
    });
}

// Download functions (adapted from download.js)
function generateSafeFilename(title, resolution, type) {
    const extension = type === 'video' ? 'mp4' : 'mp3';
    const cleanTitle = sanitizeFilename(title);
    const cleanResolution = sanitizeFilename(resolution);
    
    if (type === 'video') {
        // 视频文件格式：标题_分辨率.扩展名
        return `${cleanTitle}_${cleanResolution}.${extension}`;
    } else {
        // 音频文件格式：标题.扩展名
        return `${cleanTitle}.${extension}`;
    }
}

function sanitizeFilename(filename) {
    if (!filename) return 'untitled';
    
    // 前端文件名清理 - 与后端保持一致
    // 只替换文件系统绝对不支持的字符
    const cleaned = filename
        .replace(/[<>:"/\\|?*]/g, '_')    // 替换文件系统禁用字符
        .replace(/[\x00-\x1F\x7F-\x9F]/g, '')  // 移除控制字符
        .replace(/\s+/g, ' ')             // 合并多个空格为一个（保持空格而不是下划线）
        .replace(/^\.|\.$/g, '_')         // 不能以点开头或结尾
        .trim()                           // 移除首尾空格
        .substring(0, 100);               // 前端使用相对宽松的限制，实际限制由后端配置控制
    
    // Ensure filename is not empty
    return cleaned || 'untitled';
}

function get_query_params(url, type, formatId, resolution, title) {
    return new URLSearchParams({
        url,
        download_type: type,
        format_id: formatId,
        resolution,
        title
    });
}

// 统一的文件下载触发函数（替换triggerFileDownload和triggerTraditionalDownload）
function triggerStreamDownload(url, type, formatId, resolution, title, optionElement = null) {
    // 基础参数验证
    if (!url || !type || !formatId) {
        console.error('Missing required parameters for stream download:', { url, type, formatId });
        alert('下载参数不完整，无法继续下载');
        return;
    }
    
    // 验证formatId安全性
    if (currentVideoData) {
        const validation = validateFormatId(formatId, currentVideoData);
        if (!validation.valid) {
            console.error('Stream download format validation failed:', validation.errors);
            alert(`流式下载格式验证失败：\n${validation.errors.join('\n')}`);
            return;
        }
    }
    
    // 构建下载参数，支持音频格式
    const downloadParams = {
        url: url,
        download_type: type, 
        format_id: formatId,
        resolution: resolution,
        title: title
    };
    
    // 如果是音频下载且有optionElement，添加音频格式参数
    if (type === 'audio' && optionElement) {
        const audioFormat = optionElement.dataset.audioFormat || 'm4a';
        downloadParams.audio_format = audioFormat;
    }
    
    const downloadUrl = `/download-stream?${new URLSearchParams(downloadParams).toString()}`;
    
    // 生成统一格式的文件名
    let extension = '.mp4'; // 默认视频扩展名
    if (type === 'audio') {
        if (optionElement && optionElement.dataset.audioFormat) {
            extension = '.' + optionElement.dataset.audioFormat;
        } else {
            extension = '.mp3'; // 备用音频扩展名
        }
    }
    
    const safeTitle = sanitizeFilename(title || 'download');
    let filename;
    if (type === 'video') {
        // 视频文件格式：标题_分辨率.扩展名
        filename = `${safeTitle}_${resolution}${extension}`;
    } else {
        // 音频文件格式：标题.扩展名
        filename = `${safeTitle}${extension}`;
    }
    
    triggerBrowserDownload(downloadUrl, filename);
}
