// static/common.js



function formatFileSize(bytes, is_approx = false) {
    const t = getTranslations();

    // Explicitly check for non-truthy values or string representations of them
    // This handles null, undefined, "null", "undefined" from data attributes.
    if (!bytes || bytes === 'null' || bytes === 'undefined') {
        return t.unknownSize;
    }

    const numericBytes = Number(bytes);

    // Check if the result is not a number (NaN) or if it's negative.
    if (isNaN(numericBytes) || numericBytes < 0) {
        return t.unknownSize;
    }

    if (numericBytes === 0) return '0 Bytes';

    const k = 1000; // 使用1000作为基数来计算KB, MB, GB
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(numericBytes) / Math.log(k));

    const formattedString = `${parseFloat((numericBytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    
    return is_approx ? `≈ ${formattedString}` : formattedString;
}

function switchLanguage(lang) {
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

        const span = option.querySelector('[data-translate-dynamic]');
        if (!span) return;

        const type = span.dataset.translateDynamic;
        let newText = '';

        if (type === 'video') {
            const displayText = option.dataset.displayText;
            const ext = option.dataset.ext;
            const isCompleteStream = option.dataset.isCompleteStream === 'true';
            const supportsBrowserDownload = option.dataset.supportsBrowserDownload === 'true';
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