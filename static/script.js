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
    // --- Initialize Page Elements ---
    initializeDarkMode();
    initializeLanguageSelector();
    const savedLang = localStorage.getItem('language') || 'zh';
    switchLanguage(savedLang);
    
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
        
        // Clear all active polling intervals first
        const pollingElements = document.querySelectorAll('[data-polling-interval]');
        console.log(`Found ${pollingElements.length} elements with active polling intervals`);
        
        pollingElements.forEach(element => {
            const intervalId = element.dataset.pollingInterval;
            if (intervalId) {
                clearInterval(parseInt(intervalId));
                element.removeAttribute('data-polling-interval');
                console.log(`Cleared polling interval ${intervalId}`);
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

        // --- Frontend Whitelist Check ---
        // Use dynamically loaded configuration from backend
        // NOTE: This is NOT a security measure, just a user-friendly check.
        // The real enforcement is on the backend.
        const allowedDomains = appConfig.security?.allowed_domains || [];
        
        if (url && allowedDomains.length > 0) {
            try {
                const urlHostname = new URL(url).hostname.toLowerCase();
                // Use the same logic as backend: check if domain ends with any allowed domain
                const isAllowed = allowedDomains.some(domain => urlHostname.endsWith(domain.toLowerCase()));
                
                if (!isAllowed) {
                    const t = getTranslations();
                    const domainList = allowedDomains.join(', ');
                    alert(`${t.domainNotAllowed || 'Sorry, downloads from'} "${urlHostname}" ${t.notAllowedSuffix || 'are not allowed. Only downloads from the following sites are permitted:'} ${domainList}`);
                    return; // Stop processing
                }
            } catch (e) { /* Invalid URL, let the backend handle it. */ }
        }
        // --- End of Frontend Whitelist Check ---

        // --- NEW: Developer Test Mode ---
        if (url === 'test-video' || url === 'test-audio') {
            showLoadingState(downloadType);

            // Simulate a short delay to mimic network latency
            await new Promise(resolve => setTimeout(resolve, 500));
            
            const mockData = url === 'test-video' ? getMockVideoData() : getMockAudioData();
            currentVideoData = mockData; // Store it for language switching
            renderResults(mockData);
            return; // Exit the function to prevent the real fetch
        }
        // --- END: Developer Test Mode ---
        if (!url) {
            alert(t.urlPlaceholder);
            return;
        }

        showLoadingState(downloadType);

        try {
            const response = await fetch('/video-info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url, download_type: downloadType }),
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
    mainHeading.className = 'text-xl font-bold text-white mb-4 break-words text-left';// --- 定义颜色主题 ---
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
                <div class="option-content w-full flex items-center">
                    <div class="flex-grow text-center">
                        <span class="font-semibold" data-translate-dynamic="audio_lossless">${highBitrateText}${audioStreamIndicator}</span>
                    </div>
                    <div class="download-icon">
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
                <div class="option-content w-full flex items-center">
                    <div class="flex-grow text-center">
                        <span class="font-semibold" data-translate-dynamic="audio_compatible">${compatibilityText}</span>
                    </div>
                    <div class="download-icon">
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
            // 格式化显示文本为: {resolution} {filesize}
            const displayText = `${resolutionText} ${formattedSize}`;
            
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
                     data-format-id="${format.format_id}" data-resolution="${resolutionText}" data-display-text="${displayText}" data-ext="${format.ext}" data-filesize="${format.filesize || ''}" data-filesize-is-approx="${format.filesize_is_approx || false}" data-is-complete-stream="${format.is_complete_stream || false}" data-supports-browser-download="${format.supports_browser_download || false}">
                    <div class="option-content w-full flex items-center">
                        <div class="flex-grow text-center">
                            <!-- 显示格式: 下载 {resolution} {filesize} {ext} {⚡️标识} -->
                            <span class="font-semibold" data-translate-dynamic="video">${t.download} ${displayText} ${format.ext}${streamTypeIndicator}</span>
                        </div>
                        <div class="download-icon">
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
        el.addEventListener('click', () => handleDownload(el.dataset.formatId));
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
        
        if (status === 'success') {
            progressDiv.classList.add('hidden');
            progressDiv.innerHTML = '';
            contentDiv.innerHTML = `
                <div class="flex-grow text-center">
                    <span class="font-semibold ${colorClass}">${message}</span>
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
                    <span class="font-semibold ${colorClass}">${message}</span>
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
    
    // 通用的任务清理函数
    function cleanupTaskTracking(intervalId, optionElement) {
        clearInterval(intervalId);
        optionElement.removeAttribute('data-polling-interval');
        optionElement.classList.remove('is-downloading');
    }
function pollTaskStatus(taskId, optionElement) {
    const t = getTranslations();
    const pollingInterval = 2000; // 每2秒轮询一次
    const maxAttempts = 150; // 2秒 * 150次 = 300秒 = 5分钟超时
    let attempts = 0;

    const contentDiv = optionElement.querySelector('.option-content');
    const progressDiv = optionElement.querySelector('.option-progress');

    const restoreOriginalContent = () => {
        progressDiv.classList.add('hidden');
        progressDiv.innerHTML = '';
        contentDiv.classList.remove('hidden');
    };

    const intervalId = setInterval(async () => {
        // Handle immediate failure from handleDownload
        if (taskId === null) {
            cleanupTaskTracking(intervalId, optionElement);
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
            cleanupTaskTracking(intervalId, optionElement);
            const timeoutIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
            showTaskStatus(optionElement, 'timeout', t.downloadTimeout, timeoutIcon, 'text-yellow-400', 'border-yellow-500');
            alert(t.downloadTimeoutMessage);
            return;
        }

        try {
            // Check if polling has been externally cancelled before making the request
            if (!optionElement.dataset.pollingInterval) {
                console.log(`Polling for task ${taskId} was cancelled, stopping`);
                clearInterval(intervalId);
                return;
            }
            
            const response = await fetch(`/downloads/${taskId}`);
            
            // Check again after the async request in case it was cancelled during the fetch
            if (!optionElement.dataset.pollingInterval) {
                console.log(`Polling for task ${taskId} was cancelled during fetch, stopping`);
                clearInterval(intervalId);
                return;
            }
            if (!response.ok) {
                console.warn(`轮询任务状态失败 ${taskId}: ${response.status}`);
                return; // 暂时不处理，等待下一次轮询
            }

            const data = await response.json();

            if (data.status === 'SUCCESS') {
                cleanupTaskTracking(intervalId, optionElement);
                
                // Use the downloaded file from Celery task result
                const result = data.result;
                if (result && result.relative_path) {
                    // Use the complete relative_path from Celery result
                    const actualFileName = result.relative_path;
                    const downloadUrl = `/files/${encodeURIComponent(actualFileName)}`;
                    const displayFileName = actualFileName.split('/').pop().split('\\').pop();
                    
                    // 触发浏览器下载
                    triggerBrowserDownload(downloadUrl, displayFileName);
                } else {
                    // Fallback to stream download if no cached file
                    const formatId = optionElement.dataset.formatId;
                    const resolution = optionElement.dataset.resolution || 'unknown';
                    triggerStreamDownload(currentVideoData.original_url, currentVideoData.download_type, formatId, resolution, currentVideoData.title);
                }
                
                // 显示下载完成状态
                const successIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
                showTaskStatus(optionElement, 'success', t.downloadComplete, successIcon, 'text-green-400', 'border-green-500');
                
            } else if (data.status === 'FAILURE') {
                cleanupTaskTracking(intervalId, optionElement);
                const errorIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
                showTaskStatus(optionElement, 'failure', t.downloadFailed, errorIcon, 'text-red-400', 'border-red-500');
                const errorMessage = data.result || t.unknownError;
                alert(`${t.errorTitle}: ${errorMessage}`);
            }
            // 如果状态是 PENDING 或 STARTED，则不执行任何操作，让加载动画继续

        } catch (error) {
            console.error('轮询过程中发生错误:', error);
        }
    }, pollingInterval);
    
    // Store interval ID for external cancellation after setInterval is created
    optionElement.dataset.pollingInterval = intervalId;
    console.log(`Started polling for task ${taskId} with interval ID ${intervalId}`);
}

    // 格式ID验证函数
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
        const downloadUrl = `/download-stream?${new URLSearchParams({
            url: originalUrl,
            download_type: downloadType,
            format_id: formatId,
            resolution: resolution,
            title: title
        }).toString()}`;
        
        // 构建文件名
        let filename;
        if (isVideo) {
            filename = `${title}_${resolution}.mp4`;
        } else {
            const audioFormat = optionElement.dataset.audioFormat || 'm4a';
            filename = `${title}.${audioFormat}`;
        }
        
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
        contentDiv.innerHTML = `
            <div class="flex-grow text-center">
                <span class="font-semibold">${originalText}</span>
            </div>
            <div class="download-icon text-green-400">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
        `;
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

        // 显示不确定进度条
        showIndeterminateProgress(optionElement);
        fetch('/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentVideoData.original_url,
                download_type: currentVideoData.download_type,
                format_id: formatId,
                resolution: resolution
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
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const extension = type === 'video' ? 'mp4' : 'mp3';
    const cleanTitle = sanitizeFilename(title);
    const cleanResolution = sanitizeFilename(resolution);
    
    return `${cleanTitle}_${cleanResolution}_${timestamp}.${extension}`;
}

function sanitizeFilename(filename) {
    if (!filename) return 'untitled';
    
    // Remove or replace dangerous characters
    const cleaned = filename
        .replace(/[<>:"/\\|?*\x00-\x1F\x7F-\x9F]/g, '_')  // Replace illegal characters
        .replace(/^\./g, '_')                              // Cannot start with dot
        .replace(/\s+/g, '_')                             // Replace spaces with underscores
        .replace(/_{2,}/g, '_')                           // Merge multiple underscores
        .replace(/^_+|_+$/g, '')                          // Remove leading and trailing underscores
        .substring(0, 200);                               // Limit length
    
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
function triggerStreamDownload(url, type, formatId, resolution, title) {
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
    
    const query_params = get_query_params(url, type, formatId, resolution, title);
    const downloadUrl = `/download-stream?${query_params.toString()}`;
    
    // 生成带时间戳的文件名
    const extension = type === 'video' ? '.mp4' : '.mp3';
    const safeTitle = sanitizeFilename(title || 'download');
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const filename = `${safeTitle}_${resolution}_${timestamp}${extension}`;
    
    triggerBrowserDownload(downloadUrl, filename);
}
