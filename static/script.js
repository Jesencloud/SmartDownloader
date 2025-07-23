// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Initialize Page Elements ---
    initializeDarkMode();
    initializeLanguageSelector();
    const savedLang = localStorage.getItem('language') || 'zh';
    switchLanguage(savedLang);

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
        // This list should ideally be fetched from the backend to stay in sync.
        // NOTE: This is NOT a security measure, just a user-friendly check.
        // The real enforcement is on the backend.
        const allowedDomains = ["x.com", "youtube.com", "bilibili.com", "youtu.be"]; 
        
        if (url && allowedDomains.length > 0) {
            try {
                const urlHostname = new URL(url).hostname.toLowerCase();
                const isAllowed = allowedDomains.some(domain => urlHostname.endsWith(domain));
                
                if (!isAllowed) {
                    alert(`Sorry, downloads from "${urlHostname}" are not allowed by the site administrator.`);
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
    mainHeading.className = 'text-xl font-bold text-white mb-4 break-words text-left';

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

        const bestAudioFormat = audioFormats.reduce((best, current) => {
            return (current.filesize || 0) > (best.filesize || 0) ? current : best;
        }, audioFormats[0]);

        // Get the actual audio format from the format info
        const audioFormat = bestAudioFormat.ext || 'webm'; // Fallback to 'webm' if not specified
        const highBitrateText = `${t.losslessAudio} ${audioFormat.toUpperCase()} ${formatFileSize(bestAudioFormat.filesize)}`;
        optionsHTML += `
            <div class="resolution-option bg-gray-800 bg-opacity-70 p-4 rounded-lg flex items-center cursor-pointer hover:bg-gray-700 transition-colors" 
                 data-format-id="${bestAudioFormat.format_id}" data-audio-format="${audioFormat}" data-filesize="${bestAudioFormat.filesize}" data-resolution="audio">
                <div class="option-content w-full flex items-center">
                    <div class="flex-grow text-center">
                        <span class="font-semibold" data-translate-dynamic="audio_lossless">${highBitrateText}</span>
                    </div>
                    <div class="download-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                </div>
                <div class="option-progress w-full hidden">
                    <!-- Progress bar will be injected here -->
                </div>
            </div>`;

        const mp3FormatId = `mp3-conversion-${bestAudioFormat.format_id}`;
        const compatibilityText = `${t.betterCompatibility} (${audioFormat.toUpperCase()} → MP3) < ${formatFileSize(bestAudioFormat.filesize)}`;
        optionsHTML += `
            <div class="resolution-option bg-gray-800 bg-opacity-70 p-4 rounded-lg flex items-center cursor-pointer hover:bg-gray-700 transition-colors" 
                 data-format-id="${mp3FormatId}" data-audio-format-original="${audioFormat}" data-filesize="${bestAudioFormat.filesize}" data-resolution="audio">
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
        // Filter for video formats that have video codec and are in MP4 format
        const videoFormats = data.formats.filter(f => f.vcodec !== 'none' && f.vcodec != null && f.ext === 'mp4');

        if (videoFormats.length === 0) {
            showErrorState(t.noFormats);
            return;
        }

        // Group formats by resolution and select the best quality (highest FPS) for each.
        const bestFormatsByResolution = new Map();
        for (const format of videoFormats) {
            if (!format.resolution) continue;

            const existing = bestFormatsByResolution.get(format.resolution);
            if (!existing || (format.fps || 0) > (existing.fps || 0)) {
                bestFormatsByResolution.set(format.resolution, format);
            }
        }

        // Convert map back to an array and sort by resolution height
        const uniqueBestFormats = Array.from(bestFormatsByResolution.values());
        uniqueBestFormats.sort((a, b) => {
            const aHeight = parseInt(a.resolution.split('x')[1], 10);
            const bHeight = parseInt(b.resolution.split('x')[1], 10);
            return bHeight - aHeight;
        });

        // Take the top 3 distinct resolutions
        const topFormats = uniqueBestFormats.slice(0, 3);

        optionsHTML = topFormats.map(format => {
            let displayText = format.resolution;
            let resolutionText = format.resolution;
            if (format.fps) {
                displayText += ` ${Math.round(format.fps)}fps`;
                // Convert resolution to 1080p60 format if it's in 1920x1080 format
                if (resolutionText.includes('x')) {
                    const [width, height] = resolutionText.split('x').map(Number);
                    resolutionText = `${height}p${Math.round(format.fps) > 30 ? Math.round(format.fps) : ''}`;
                }
            }
            
            return `
                <div class="resolution-option bg-gray-800 bg-opacity-70 p-4 rounded-lg flex items-center cursor-pointer hover:bg-gray-700 transition-colors" 
                     data-format-id="${format.format_id}" data-resolution="${resolutionText}" data-display-text="${displayText}" data-ext="${format.ext}">
                    <div class="option-content w-full flex items-center">
                        <div class="flex-grow text-center">
                            <span class="font-semibold" data-translate-dynamic="video">${t.download} ${displayText} ${format.ext}</span>
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
        <div class="download-container bg-gray-900 bg-opacity-50 p-6 rounded-2xl text-white">
            <h3 class="text-xl font-bold mb-4" data-translate="${headerKey}">${t[headerKey]}</h3>
            <div class="resolution-grid grid grid-cols-1 gap-4">${optionsHTML}</div>
            <div class="text-center mt-6">
                <button id="backButton" class="button bg-gray-600 hover:bg-gray-700" data-translate="returnHome">${t.returnHome}</button>
            </div>
        </div>`;

    document.querySelectorAll('.resolution-option').forEach(el => {
        el.addEventListener('click', () => handleDownload(el.dataset.formatId));
    });
    // Use the new centralized handler for the back button
    const backButton = document.getElementById('backButton');
    if (backButton) {
        backButton.addEventListener('click', handleReturnHome);
    }
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
            clearInterval(intervalId);
            // Remove from tracking
            optionElement.removeAttribute('data-polling-interval');
            optionElement.classList.remove('is-downloading');
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
            clearInterval(intervalId);
            // Remove from tracking
            optionElement.removeAttribute('data-polling-interval');
            optionElement.classList.remove('is-downloading');
            progressDiv.innerHTML = `
                <div class="flex-grow text-center">
                    <span class="font-semibold text-yellow-400" data-translate="downloadTimeout">${t.downloadTimeout}</span>
                </div>
                <div class="download-icon text-yellow-400">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </div>
            `;
            optionElement.classList.remove('hover:bg-gray-700');
            optionElement.classList.add('border', 'border-yellow-500');
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
                console.log('Task completed successfully, triggering download...');
                console.log('Full task data received:', data);
                console.log('Task result:', data.result);
                
                clearInterval(intervalId);
                // Remove from tracking
                optionElement.removeAttribute('data-polling-interval');
                optionElement.classList.remove('is-downloading');
                
                // Use the downloaded file from Celery task result
                const result = data.result;
                if (result && result.relative_path) {
                    console.log('Using cached file with relative_path:', result.relative_path);
                    console.log('Full result object:', result);
                    
                    // Use the complete relative_path from Celery result
                    // This should be the actual filename that was saved
                    const actualFileName = result.relative_path;
                    const downloadUrl = `/files/${encodeURIComponent(actualFileName)}`;
                    
                    console.log('Actual filename from Celery:', actualFileName);
                    console.log('Download URL:', downloadUrl);
                    
                    // For download attribute, use just the filename part (for browser save dialog)
                    const displayFileName = actualFileName.split('/').pop().split('\\').pop();
                    
                    // Directly trigger download - if file doesn't exist, browser will show error
                    const link = document.createElement('a');
                    link.href = downloadUrl;
                    link.download = displayFileName;
                    
                    // Add error handling for download failures
                    link.addEventListener('error', function(e) {
                        console.error('Download failed:', e);
                        alert('缓存文件下载失败，正在尝试流式下载...');
                        // Fallback to stream download
                        const formatId = optionElement.dataset.formatId;
                        const resolution = optionElement.dataset.resolution || 'unknown';
                        triggerFileDownload(currentVideoData.original_url, currentVideoData.download_type, formatId, resolution, currentVideoData.title);
                    });
                    
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    console.log('Cached file download triggered with actual filename');
                } else {
                    console.warn('No cached file found in result. Result structure:', result);
                    console.log('Falling back to stream download');
                    // Fallback to stream download if no cached file
                    const formatId = optionElement.dataset.formatId;
                    const resolution = optionElement.dataset.resolution || 'unknown';
                    triggerFileDownload(currentVideoData.original_url, currentVideoData.download_type, formatId, resolution, currentVideoData.title);
                }
                
                progressDiv.classList.add('hidden');
                progressDiv.innerHTML = '';
                contentDiv.innerHTML = `
                    <div class="flex-grow text-center">
                        <span class="font-semibold text-green-400" data-translate="downloadComplete">${t.downloadComplete}</span>
                    </div>
                    <div class="download-icon text-green-400">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                `;
                contentDiv.classList.remove('hidden');
                optionElement.classList.remove('hover:bg-gray-700');
                optionElement.classList.add('border', 'border-green-500');
            } else if (data.status === 'FAILURE') {
                clearInterval(intervalId);
                // Remove from tracking
                optionElement.removeAttribute('data-polling-interval');
                optionElement.classList.remove('is-downloading');
                progressDiv.innerHTML = `
                    <div class="flex-grow text-center">
                        <span class="font-semibold text-red-400" data-translate="downloadFailed">${t.downloadFailed}</span>
                    </div>
                    <div class="download-icon text-red-400">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                `;
                // Keep progressDiv visible to show the failure message
                optionElement.classList.remove('hover:bg-gray-700');
                optionElement.classList.add('border', 'border-red-500');
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

    function handleDownload(formatId) {
        if (!currentVideoData) return;
        const t = getTranslations();
        const optionElement = document.querySelector(`[data-format-id="${formatId}"]`);
        const contentDiv = optionElement.querySelector('.option-content');
        const progressDiv = optionElement.querySelector('.option-progress');

        optionElement.classList.add('is-downloading');
        const resolution = optionElement.dataset.resolution || '';

        // 动态注入不确定进度条的CSS动画
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

        // 将下载选项替换为不确定进度条
        contentDiv.classList.add('hidden');
        progressDiv.innerHTML = `
            <div class="progress-bar-container w-full bg-gray-700 rounded-full h-2.5 overflow-hidden"><div class="progress-bar-indeterminate bg-purple-500 h-2.5 rounded-full" style="background-color: #8B5CF6 !important;"></div></div>
        `;
        progressDiv.classList.remove('hidden');
        optionElement.style.pointerEvents = 'none';
        optionElement.style.opacity = '0.7';

        fetch('/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentVideoData.original_url,
                download_type: currentVideoData.download_type,
                format_id: formatId,
                resolution: resolution  // Send the resolution to the backend
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

function triggerFileDownload(url, type, formatId, resolution, title) {
    console.log('triggerFileDownload called with:', { url, type, formatId, resolution, title });
    triggerTraditionalDownload(url, type, formatId, resolution, title);
}

function triggerTraditionalDownload(url, type, formatId, resolution, title) {
    console.log('triggerTraditionalDownload called with:', { url, type, formatId, resolution, title });
    const query_params = get_query_params(url, type, formatId, resolution, title);
    const downloadUrl = `/download-stream?${query_params.toString()}`;
    
    console.log('Generated download URL:', downloadUrl);
    
    // Generate a proper filename with extension
    const extension = type === 'video' ? '.mp4' : '.mp3';
    const safeTitle = sanitizeFilename(title);
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const filename = `${safeTitle}_${resolution}_${timestamp}${extension}`;
    
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    
    console.log('Triggering download link click with filename:', filename);
    link.click();
    document.body.removeChild(link);
    console.log('Download link clicked and removed');
}
