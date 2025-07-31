// static/common.js

// --- Translation System ---
let translations = {};

async function loadTranslations() {
    try {
        // 加载中文翻译
        const zhResponse = await fetch('/static/locales/zh-CN.json');
        const zhData = await zhResponse.json();
        translations.zh = zhData;
        
        // 加载英文翻译
        const enResponse = await fetch('/static/locales/en.json');
        const enData = await enResponse.json();
        translations.en = enData;
        
        console.log('Translation files loaded successfully');
    } catch (error) {
        console.error('Failed to load translation files:', error);
        // Fallback empty translations
        translations = { zh: {}, en: {} };
    }
}

function getTranslations() {
    const currentLang = localStorage.getItem('language') || 'zh';
    return translations[currentLang] || translations.zh || {};
}



function formatFileSize(bytes, is_approx = false) {
    const t = getTranslations();

    // Explicitly check for non-truthy values or string representations of them
    // This handles null, undefined, "null", "undefined" from data attributes.
    if (!bytes || bytes === 'null' || bytes === 'undefined') {
        return t.unknownSize || 'Unknown size';
    }

    const numericBytes = Number(bytes);

    // Check if the result is not a number (NaN) or if it's negative.
    if (isNaN(numericBytes) || numericBytes < 0) {
        return t.unknownSize || 'Unknown size';
    }

    if (numericBytes === 0) return '0 Bytes';

    const k = 1000; // 使用1000作为基数来计算KB, MB, GB
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(numericBytes) / Math.log(k));

    const formattedString = `${parseFloat((numericBytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    
    return is_approx ? `≈ ${formattedString}` : formattedString;
}

async function switchLanguage(lang) {
    // Ensure translations are loaded
    if (Object.keys(translations).length === 0) {
        await loadTranslations();
    }
    
    // Save language preference and set a global variable
    localStorage.setItem('language', lang);
    window.currentLanguage = lang;
    
    // Get the correct translation dictionary
    const t = translations[lang] || translations.zh;
    
    // Update all elements that have a `data-translate` attribute
    document.querySelectorAll('[data-translate]').forEach(element => {
        const key = element.getAttribute('data-translate');
        if (t[key]) {
            // If the attribute is for a placeholder, update the placeholder
            if (element.hasAttribute('data-translate-placeholder')) {
                element.placeholder = t[key];
            } else {
                // Otherwise, update the text content of the element
                element.textContent = t[key];
            }
        }
    });

    // Update all elements that have a `data-translate-title` attribute
    document.querySelectorAll('[data-translate-title]').forEach(element => {
        const key = element.getAttribute('data-translate-title');
        if (t[key]) {
            element.title = t[key];
        }
    });

    // Update the page title separately
    const titleElement = document.querySelector('title');
    if (titleElement) {
        // Check if we are on the main page and not in the results view
        const resultContainer = document.getElementById('resultContainer');
        const isResultsView = resultContainer && resultContainer.style.display !== 'none' && resultContainer.innerHTML.trim() !== '';
        
        if (!isResultsView) {
             titleElement.textContent = t.mainHeading;
        }
    }

    // Update the document's language attribute
    document.documentElement.setAttribute('lang', lang === 'en' ? 'en-US' : 'zh-CN');
    
    // 更新进行中的下载进度条语言显示（仅针对进度条内的消息）
    if (typeof updateProgressLanguage === 'function') {
        updateProgressLanguage();
    }
    
    // --- NEW: Centralized logic to update dynamic result items ---
    document.querySelectorAll('.resolution-option').forEach(option => {
        // CRITICAL: If the option is currently downloading, DO NOTHING.
        if (option.classList.contains('is-downloading')) {
            return;
        }

        // Handle completed items separately
        const completedTitle = option.querySelector('.task-title[data-translate-type="completed-video"]');
        if (completedTitle) {
            const resolution = completedTitle.dataset.resolution;
            const formattedSize = completedTitle.dataset.formattedSize;
            const ext = completedTitle.dataset.ext;
            if (resolution && formattedSize && ext) {
                completedTitle.textContent = `${t.download} ${resolution} ${formattedSize} ${ext}`;
            }
            return; // Move to the next option
        }

        const span = option.querySelector('[data-translate-dynamic]');
        if (!span) return;

        const type = span.dataset.translateDynamic;
        let newText = '';

        if (type === 'video') {
            const resolution = option.dataset.resolution;
            const filesize = option.dataset.filesize;
            const filesizeIsApprox = option.dataset.filesizeIsApprox === 'true';
            const ext = option.dataset.ext;
            const isCompleteStream = option.dataset.isCompleteStream === 'true';
            const supportsBrowserDownload = option.dataset.supportsBrowserDownload === 'true';
            
            // 重新计算文件大小显示（会使用当前语言的翻译）
            const formattedSize = formatFileSize(filesize, filesizeIsApprox);
            const displayText = `${resolution} ${formattedSize}`;
            
            // 智能标识：检测完整流并添加⚡️标识
            const streamIndicator = (isCompleteStream && supportsBrowserDownload) ? ' ⚡️' : '';
            newText = `${t.download} ${displayText} ${ext}${streamIndicator}`;
        } else if (type === 'audio_lossless') {
            const audioFormat = option.dataset.audioFormat;
            const abr = option.dataset.abr;
            const supportsBrowserDownload = option.dataset.supportsBrowserDownload === 'true';
            // 智能标识：音频格式支持直接下载
            const streamIndicator = supportsBrowserDownload ? ' ⚡️' : '';
            if (abr && abr !== 'null' && abr !== 'undefined' && abr !== '') {
                newText = `${t.losslessAudio} ${audioFormat.toUpperCase()} ${abr}kbps${streamIndicator}`;
            } else {
                // Fallback to old logic if abr is not available
                const filesize = option.dataset.filesize;
                const isApprox = option.dataset.filesizeIsApprox === 'true';
                newText = `${t.losslessAudio} ${audioFormat.toUpperCase()} ${formatFileSize(filesize, isApprox)}${streamIndicator}`;
            }
        } else if (type === 'audio_compatible') {
            const originalFormat = option.dataset.audioFormatOriginal;
            newText = `${t.betterCompatibility} (${originalFormat.toUpperCase()} → MP3)`;
        } else if (type === 'download_complete') {
            newText = t.downloadComplete;
        } else if (type === 'download_failed') {
            newText = t.downloadFailed;
        } else if (type === 'download_timeout') {
            newText = t.downloadTimeout;
        } else if (type === 'downloading') {
            newText = t.downloading;
        }
        
        if (newText) {
            span.innerHTML = newText; // Use innerHTML to support potential HTML tags
        }
    });
}