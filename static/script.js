// static/script.js

// Helper to get current translations
function getTranslations() {
    const lang = localStorage.getItem('language') || 'zh';
    // 'translations' is defined in common.js, which is loaded before this script
    return translations[lang] || translations.zh;
}

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

    // Listen for the custom languageChanged event dispatched from common.js
    document.addEventListener('languageChanged', () => {
        // If video data exists, it means we are in the results view.
        // Re-render the results to apply the new translations.
        if (currentVideoData) {
            renderResults(currentVideoData);
        }
    });
    // --- Main Event Listeners ---
    downloadVideoButton.addEventListener('click', () => startVideoAnalysis('video'));
    downloadAudioButton.addEventListener('click', () => startVideoAnalysis('audio'));

    // --- Core Functions ---

    async function startVideoAnalysis(downloadType) {
        const url = urlInput.value.trim();
        const t = getTranslations();

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
        const loadingText = downloadType === 'video' ? t.videoLoading : t.audioLoading;
        
        mainHeading.textContent = loadingText;
        if (inputGroup) inputGroup.style.display = 'none';
        
        buttonGroup.style.display = 'none';

        resultContainer.innerHTML = `
            <div class="loading-state text-center p-6 text-white">
                <div class="spinner border-4 border-t-4 border-gray-200 border-t-blue-400 rounded-full w-12 h-12 animate-spin mx-auto"></div>
                <p class="mt-4">${t.parsingVideoPleaseWait}</p>
            </div>`;
        resultContainer.style.display = 'block';
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
        // --- NEW: Adjust title font size ---
        mainHeading.className = 'text-xl font-bold text-white mb-4 break-words text-left';

        const formatsToShow = data.formats.filter(f => {
            return data.download_type === 'video' ? f.vcodec !== 'none' : f.acodec !== 'none';
        });

        if (formatsToShow.length === 0) {
            showErrorState(t.noFormats);
            return;
        }

        // --- NEW: Filter for unique resolutions ---
        const uniqueFormats = [];
        const seenResolutions = new Set();
        for (const format of formatsToShow) {
            if (!seenResolutions.has(format.resolution)) {
                seenResolutions.add(format.resolution);
                uniqueFormats.push(format);
            }
        }
        // --- END NEW ---

        // Sort formats
        uniqueFormats.sort((a, b) => {
            if (data.download_type === 'video') {
                const aHeight = a.resolution ? parseInt(a.resolution.split('x')[1]) : 0;
                const bHeight = b.resolution ? parseInt(b.resolution.split('x')[1]) : 0;
                if (bHeight !== aHeight) return bHeight - aHeight;
                return (b.fps || 0) - (a.fps || 0);
            } else {
                return (b.abr || 0) - (a.abr || 0);
            }
        });

        // --- NEW: Keep only the top 3 ---
        const topFormats = uniqueFormats.slice(0, 3);

        let optionsHTML = topFormats.map(format => {
            const qualityText = data.download_type === 'video' ? format.resolution : format.quality;
            // --- NEW: Updated display format ---
            return `
                <div class="resolution-option bg-gray-800 bg-opacity-70 p-4 rounded-lg flex items-center cursor-pointer hover:bg-gray-700 transition-colors" data-format-id="${format.format_id}">
                    <div class="flex-grow text-center">
                        <span class="font-semibold">${t.download} ${qualityText} ${format.ext}</span>
                    </div>
                    <div class="download-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                </div>`;
            // --- END NEW ---
        }).join('');

        resultContainer.innerHTML = `
            <div class="download-container bg-gray-900 bg-opacity-50 p-6 rounded-2xl text-white">
                <h3 class="text-xl font-bold mb-4">${data.download_type === 'video' ? t.selectResolution : t.selectAudioQuality}</h3>
                <div class="resolution-grid grid grid-cols-1 gap-4">${optionsHTML}</div>
                <div class="text-center mt-6">
                    <button id="backButton" class="button bg-gray-600 hover:bg-gray-700">${t.returnHome}</button>
                </div>
            </div>`;

        // --- NEW: Adjust back button font size after it's created ---
        const backButton = document.getElementById('backButton');
        if (backButton) adjustButtonFontSize(backButton);

        document.querySelectorAll('.resolution-option').forEach(el => {
            el.addEventListener('click', () => handleDownload(el.dataset.formatId));
        });
        document.getElementById('backButton').addEventListener('click', resetUI);
    }
    
    function handleDownload(formatId) {
        if (!currentVideoData) return;
        const t = getTranslations();
        const optionElement = document.querySelector(`[data-format-id="${formatId}"]`);
        const iconElement = optionElement.querySelector('.download-icon');

        iconElement.innerHTML = `<div class="spinner border-2 border-t-2 border-gray-200 border-t-blue-400 rounded-full w-6 h-6 animate-spin"></div>`;
        optionElement.style.pointerEvents = 'none';
        optionElement.style.opacity = '0.7';

        fetch('/downloads', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentVideoData.original_url,
                download_type: currentVideoData.download_type,
                format_id: formatId
            }),
        })
        .then(response => {
            if (!response.ok) return response.json().then(err => Promise.reject(err));
            return response.json();
        })
        .then(data => {
            iconElement.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`; // Checkmark
            optionElement.classList.add('bg-green-700', 'hover:bg-green-700');
            console.log('Download started:', data.task_id);
        })
        .catch(error => {
            const errorMessage = error.detail || error.message || t.unknownError;
            iconElement.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`; // X mark
            optionElement.classList.add('bg-red-700', 'hover:bg-red-700');
            alert(`${t.errorTitle}: ${errorMessage}`);
            setTimeout(() => {
                optionElement.style.pointerEvents = 'auto';
                optionElement.style.opacity = '1';
                optionElement.classList.remove('bg-red-700', 'hover:bg-red-700');
                iconElement.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
            }, 2000);
        });
    }

    function resetUI() {
        currentVideoData = null; // 清除已存储的视频数据
        const t = getTranslations();
        mainHeading.textContent = t.mainHeading;
        // --- NEW: Restore original title font size ---
        mainHeading.className = 'text-4xl md:text-5xl font-bold text-white mb-8';
        
        if (inputGroup) inputGroup.style.display = 'block';
        
        buttonGroup.style.display = 'flex';
        resultContainer.style.display = 'none';
        resultContainer.innerHTML = '';
        urlInput.value = '';
        urlInput.dispatchEvent(new Event('input')); // Trigger input event to update button visibility
    }

    function formatFileSize(bytes) {
        const t = getTranslations();
        if (!bytes || bytes < 0) return t.unknownSize;
        if (bytes === 0) return '0 Bytes';
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return `${parseFloat((bytes / Math.pow(1024, i)).toFixed(2))} ${['Bytes', 'KB', 'MB', 'GB', 'TB'][i]}`;
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
