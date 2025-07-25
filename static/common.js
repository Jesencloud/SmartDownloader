// static/common.js

const translations = {
    zh: {
        // From script.js
        homeButton: '主页',
        mainHeading: '智能下载器',
        urlPlaceholder: '粘贴视频或播放列表URL...',
        pasteButton: '粘贴',
        clearButton: '清除',
        videoButton: '提取视频',
        audioButton: '提取音频',
        introTitle: '智能下载器介绍',
        introDesc1: '智能下载器 – 免费高质量下载视频和音频。只需在下方输入框中粘贴视频URL，点击"提取"按钮，即可立即保存您所需分辨率的视频或音频。',
        introDesc2: '如何轻松下载视频和音频？视频和音频是内容呈现的关键部分，通过引人注目的视觉和听觉吸引注意力。如果您想保存视频或音频，使用智能下载器可以轻松完成。许多工具允许您通过几次点击即可从各种平台下载内容。',
        introDesc3: '使用智能下载器非常简单。您只需粘贴视频链接，将立即获取并允许您在几秒钟内下载高质量的视频或音频。这非常适合内容创作者、研究员或任何想要保存媒体内容以供个人使用的人。',
        introDesc4: '为了快速可靠地下载视频和音频，请尝试使用这款易于使用的工具。',
        howToTitle: '如何使用智能下载器',
        howToDesc: '按照以下简单步骤使用我们的工具下载视频和音频：',
        step1: '复制您想要下载视频或音频的URL。',
        step2: '将URL粘贴到我们工具的输入框中。',
        step3: '点击"提取视频"或"提取音频"按钮。',
        step4: '下载将开始，您可以在状态区域查看进度。',
        aboutTitle: '关于我们',
        aboutDesc1: '欢迎使用我们的智能下载器！我们提供一种简单快捷的方式来下载高质量的视频和音频。我们的目标是通过用户友好的界面和可靠的服务，让您的体验尽可能无缝。',
        aboutDesc2: '我们的团队热衷于帮助您充分利用您的媒体体验。无论您是内容创作者、营销人员还是仅仅是爱好者，我们都会协助您获取所需的视觉和听觉内容。',
        aboutDesc3: '感谢您的选择！',
        faqTitle: '常见问题',
        faq1Q: '什么是智能下载器？',
        faq1A: '智能下载器允许您通过简单地输入视频URL来下载视频和音频。',
        faq2Q: '如何使用智能下载器？',
        faq2A: '只需将视频URL复制并粘贴到我们主页的输入框中，然后点击下载按钮。视频或音频将下载到您的设备。',
        faq3Q: '使用此服务免费吗？',
        faq3A: '是的，我们的智能下载器完全免费使用。',
        faq4Q: '我可以下载不同大小的视频或音频吗？',
        faq4A: '这取决于原始视频的可用格式。我们的工具会尝试获取最高质量的可用选项。',
        faq5Q: '下载视频或音频合法吗？',
        faq5A: '下载视频或音频供个人使用通常是允许的，但请确保您没有侵犯任何版权或知识产权。',
        faq6Q: '支持哪些设备？',
        faq6A: '我们的智能下载器兼容所有设备，包括智能手机、平板电脑和电脑。',
        footerPrivacy: '隐私政策',
        footerDisclaimer: '免责声明',
        footerAbout: '关于我们',
        footerContact: '联系我们',

        // From download.js & dynamic content
        title: 'Download Video',
        loading: '正在获取视频信息...',
        videoLoading: '你的视频正在加载中',
        audioLoading: '你的音频正在提取中',
        parsingVideoPleaseWait: '正在解析视频，请稍候...',
        errorTitle: '获取视频信息失败',
        returnHome: '返回主页',
        selectResolution: '选择分辨率',
        selectAudioQuality: '选择音频质量',
        downloadSelected: '下载选中格式',
        preparing: '正在准备下载...',
        noFormats: '未找到符合条件的',
        supportInfo: '我们只支持MP4格式的视频',
        unknownSize: '未知大小',
        downloadStarted: '文件下载已开始！请检查您的下载文件夹。',
        saveSuccess: '文件保存成功！',
        saveFailed: '保存文件失败: ',
        videoFormats: '视频',
        audioFormats: '音频',
        analysisFailed: '解析失败',
        errorBackButton: '返回主页',
        download: '下载',
        losslessAudio: '高比特率',
        betterCompatibility: '兼容性佳',
        downloadComplete: '下载完成',
        downloadFailed: '下载失败',
        downloadTimeout: '检查超时',
        downloadTimeoutMessage: '下载状态检查超时。',
        cleaningUp: '正在取消下载并清理文件...',
        cleanupComplete: '清理完成！删除了 {fileCount} 个临时文件{sizeInfo}',
        domainNotAllowed: '抱歉，不允许从',
        notAllowedSuffix: '下载。只允许从以下网站下载：',
        directDownloading: '直接下载中...',
        directDownloadComplete: '直接下载完成',
        smartDownloadTitle: '智能下载',
        completeStreamInfo: '⚡ 完整流',
        directAudioDownloading: '音频流传输中...',
        directAudioDownloadComplete: '音频下载开始',
        smartDownloadInfoText: '⚡️ 支持直接下载',
        downloading: '正在下载中',
        downloadComplete: '下载完成'
    },
    en: {
        // From script.js
        homeButton: 'Home',
        mainHeading: 'Smart Downloader',
        urlPlaceholder: 'Paste video or playlist URL...',
        pasteButton: 'Paste',
        clearButton: 'Clear',
        videoButton: 'Extract Video',
        audioButton: 'Extract Audio',
        introTitle: 'Smart Downloader Introduction',
        introDesc1: 'Smart Downloader – Download high-quality videos and audio for free. Simply paste a video URL in the input box below, click the "Extract" button, and you can immediately save videos or audio in your desired resolution.',
        introDesc2: 'How to easily download videos and audio? Videos and audio are key components of content presentation, attracting attention through compelling visuals and sound. If you want to save videos or audio, using Smart Downloader makes it easy. Many tools allow you to download content from various platforms with just a few clicks.',
        introDesc3: 'Using Smart Downloader is very simple. You just need to paste a video link, and the tool will immediately fetch and allow you to download high-quality videos or audio in seconds. This is perfect for content creators, researchers, or anyone who wants to save media content for personal use.',
        introDesc4: 'For fast and reliable video and audio downloads, try using this easy-to-use tool.',
        howToTitle: 'How to Use Smart Downloader',
        howToDesc: 'Follow these simple steps to download videos and audio using our tool:',
        step1: 'Copy the URL of the video or audio you want to download.',
        step2: 'Paste the URL into the input box of our tool.',
        step3: 'Click the "Extract Video" or "Extract Audio" button.',
        step4: 'The download will start, and you can check the progress in the status area.',
        aboutTitle: 'About Us',
        aboutDesc1: 'Welcome to our Smart Downloader! We provide a simple and fast way to download high-quality videos and audio. Our goal is to make your experience as seamless as possible through a user-friendly interface and reliable service.',
        aboutDesc2: 'Our team is passionate about helping you make the most of your media experience. Whether you are a content creator, marketer, or just an enthusiast, we will help you get the visual and audio content you need.',
        aboutDesc3: 'Thank you for choosing us!',
        faqTitle: 'Frequently Asked Questions',
        faq1Q: 'What is Smart Downloader?',
        faq1A: 'Smart Downloader allows you to download videos and audio by simply entering a video URL.',
        faq2Q: 'How to use Smart Downloader?',
        faq2A: 'Simply copy and paste the video URL into the input box on our homepage, then click the download button. The video or audio will be downloaded to your device.',
        faq3Q: 'Is this service free?',
        faq3A: 'Yes, our Smart Downloader is completely free to use.',
        faq4Q: 'Can I download videos or audio in different sizes?',
        faq4A: 'This depends on the available formats of the original video. Our tool will try to get the highest quality options available.',
        faq5Q: 'Is it legal to download videos or audio?',
        faq5A: 'Downloading videos or audio for personal use is generally allowed, but please make sure you are not infringing any copyright or intellectual property rights.',
        faq6Q: 'Which devices are supported?',
        faq6A: 'Our Smart Downloader is compatible with all devices, including smartphones, tablets, and computers.',
        footerPrivacy: 'Privacy Policy',
        footerDisclaimer: 'Disclaimer',
        footerAbout: 'About Us',
        footerContact: 'Contact Us',

        // From download.js & dynamic content
        title: 'Download Video',
        loading: 'Getting video information...',
        videoLoading: 'Your video is loading',
        audioLoading: 'Your audio is being extracted',
        parsingVideoPleaseWait: 'Parsing video, please wait...',
        errorTitle: 'Failed to get video information',
        returnHome: 'Back to Home',
        selectResolution: 'Select Video Resolution',
        selectAudioQuality: 'Select Audio Quality',
        downloadSelected: 'Download Selected Format',
        preparing: 'Preparing download...',
        noFormats: 'No suitable formats found',
        supportInfo: 'We only support MP4 format videos',
        unknownSize: 'Unknown size',
        downloadStarted: 'File download started! Please check your downloads folder.',
        saveSuccess: 'File saved successfully!',
        saveFailed: 'Failed to save file: ',
        videoFormats: 'video',
        audioFormats: 'audio',
        analysisFailed: 'Analysis Failed',
        errorBackButton: 'Back to Home',
        download: 'Download',
        losslessAudio: 'High Bitrate',
        betterCompatibility: 'Better Compatibility',
        downloadComplete: 'Download Complete',
        downloadFailed: 'Download Failed',
        downloadTimeout: 'Check Timed Out',
        downloadTimeoutMessage: 'Download status check timed out.',
        cleaningUp: 'Cancelling downloads and cleaning up files...',
        cleanupComplete: 'Cleanup complete! Deleted {fileCount} temporary files{sizeInfo}',
        domainNotAllowed: 'Sorry, downloads from',
        notAllowedSuffix: 'are not allowed. Only downloads from the following sites are permitted:',
        directDownloading: 'Direct downloading...',
        directDownloadComplete: 'Direct download complete',
        smartDownloadTitle: 'Smart Download',
        completeStreamInfo: '⚡ Complete Stream',
        directAudioDownloading: 'Audio streaming...',
        directAudioDownloadComplete: 'Audio download started',
        smartDownloadInfoText: '⚡️ Direct download supported',
        downloading: 'Downloading',
        downloadComplete: 'Download Complete'
    },
};

function getTranslations() {
    const lang = localStorage.getItem('language') || 'zh';
    return translations[lang] || translations.zh;
}

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