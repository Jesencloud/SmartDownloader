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
    const mainHeading = document.querySelector('.hero-section h1');
    const inputGroup = document.querySelector('.input-group');
    const buttonGroup = document.querySelector('.button-group');

    let currentVideoData = null; // To store fetched video data

    // --- Main Event Listeners ---
    downloadVideoButton.addEventListener('click', () => startVideoAnalysis('video'));
    downloadAudioButton.addEventListener('click', () => startVideoAnalysis('audio'));

    // --- Core Functions ---

    async function startVideoAnalysis(downloadType) {
        const url = urlInput.value.trim();
        const t = getTranslations();
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
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to fetch video info.');
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
        // Correctly select the parent of the input container to hide it
        const inputGroupContainer = document.querySelector('.input-group');
        if (inputGroupContainer) inputGroupContainer.style.display = 'none';
        
        buttonGroup.style.display = 'none';

        resultContainer.innerHTML = `
            <div class="loading-state text-center p-6 text-white">
                <div class="spinner border-4 border-t-4 border-gray-200 border-t-blue-400 rounded-full w-12 h-12 animate-spin mx-auto"></div>
                <p class="mt-4">${t.parsingVideoPleaseWait}</p>
            </div>`;
        resultContainer.style.display = 'block';
    }

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
                <div class="resolution-option bg-blue-900 bg-opacity-50 p-4 rounded-lg flex justify-between items-center cursor-pointer hover:bg-blue-800 transition-colors" data-format-id="${format.format_id}">
                    <div class="flex items-center">
                        <span class="font-semibold">${t.download} ${qualityText} ${format.ext}</span>
                    </div>
                    <div class="download-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                    </div>
                </div>`;
            // --- END NEW ---
        }).join('');

        resultContainer.innerHTML = `
            <div class="download-container bg-gray-800 bg-opacity-40 p-6 rounded-2xl text-white">
                <h3 class="text-xl font-bold mb-4">${data.download_type === 'video' ? t.selectResolution : t.selectAudioQuality}</h3>
                <div class="resolution-grid grid grid-cols-1 md:grid-cols-2 gap-4">${optionsHTML}</div>
                <div class="text-center mt-6">
                    <button id="backButton" class="button bg-gray-600 hover:bg-gray-700">${t.returnHome}</button>
                </div>
            </div>`;

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
        const t = getTranslations();
        mainHeading.textContent = t.mainHeading;
        // --- NEW: Restore original title font size ---
        mainHeading.className = 'text-4xl md:text-5xl font-bold text-white mb-8';
        
        // Correctly select the parent of the input container to show it
        const inputGroupContainer = document.querySelector('.input-group');
        if (inputGroupContainer) inputGroupContainer.style.display = 'block';
        
        buttonGroup.style.display = 'flex';
        resultContainer.style.display = 'none';
        resultContainer.innerHTML = '';
        urlInput.value = '';
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
