// download.js - External script for download.html page

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

// Language selector functionality
function initializeLanguageSelector() {
    console.log('Initializing language selector...');
    const languageToggle = document.getElementById('languageToggle');
    const languageMenu = document.getElementById('languageMenu');
    const languageOptions = document.querySelectorAll('.language-option');
    
    console.log('languageToggle:', languageToggle);
    console.log('languageMenu:', languageMenu);
    console.log('languageOptions:', languageOptions.length);
    
    if (!languageToggle || !languageMenu) {
        console.error('Language selector elements not found!');
        return;
    }
    
    // Toggle language menu
    languageToggle.addEventListener('click', (e) => {
        console.log('Language toggle clicked');
        e.stopPropagation();
        languageMenu.classList.toggle('hidden');
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!languageToggle.contains(e.target) && !languageMenu.contains(e.target)) {
            languageMenu.classList.add('hidden');
        }
    });
    
    // Handle language selection
    languageOptions.forEach(option => {
        option.addEventListener('click', (e) => {
            console.log('Language option clicked:', e.target.dataset.lang);
            const selectedLang = e.target.dataset.lang;
            switchLanguage(selectedLang);
            languageMenu.classList.add('hidden');
        });
    });
    
    // Load saved language preference
    const savedLang = localStorage.getItem('language') || 'zh';
    switchLanguage(savedLang);
}



// Global variables
let selectedResolution = null;
let selectedFormatId = null;
let videoData = null;

// Safe filename sanitization function
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

// Generate safe filename
function generateSafeFilename(title, resolution, type) {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const extension = type === 'video' ? 'mp4' : 'mp3';
    const cleanTitle = sanitizeFilename(title);
    const cleanResolution = sanitizeFilename(resolution);
    
    return `${cleanTitle}_${cleanResolution}_${timestamp}.${extension}`;
}

document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM Content Loaded');
    
    // Test direct element access
    const toggle = document.getElementById('languageToggle');
    const menu = document.getElementById('languageMenu');
    console.log('Direct test - toggle:', toggle);
    console.log('Direct test - menu:', menu);
    
    // Initialize dark mode
    initializeDarkMode();
    
    // Initialize language selector
    initializeLanguageSelector();
    
    // Get URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const videoUrl = urlParams.get('url');
    const downloadType = urlParams.get('type') || 'video';
    
    if (!videoUrl) {
        showError('缺少视频URL参数');
        return;
    }
    
    // Display video URL
    document.getElementById('videoUrl').textContent = videoUrl;
    
    // Get real video information
    fetchVideoInfo(videoUrl, downloadType);
    
    // Download button event
    document.getElementById('downloadButton').addEventListener('click', () => {
        if (selectedFormatId) {
            startDownload();
        }
    });
});

async function fetchVideoInfo(url, type) {
    try {
        const response = await fetch('/video-info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ url: url, download_type: type }),
        });

        if (!response.ok) {
            // 检查响应是否是JSON格式
            const contentType = response.headers.get("content-type");
            let errorMessage;
            if (contentType && contentType.indexOf("application/json") !== -1) {
                const errorData = await response.json();
                errorMessage = errorData.detail || `API Error: ${response.status}`;
            } else {
                // 如果不是JSON，很可能是服务器超时返回的HTML页面
                errorMessage = `服务器错误: ${response.status} ${response.statusText}。服务器可能正忙或请求超时。`;
            }
            throw new Error(errorMessage);
        }

        const videoInfo = await response.json();
        
        // Store videoInfo and original URL in sessionStorage
        sessionStorage.setItem('video_info', JSON.stringify(videoInfo));
        sessionStorage.setItem('original_url', url);
        sessionStorage.setItem('download_type', type);

        // Redirect to the new page
        window.location.href = '/result_normal';
        
    } catch (error) {
        console.error('获取视频信息失败:', error);
        console.error('Error details:', error.message, error.name, error.stack); // Added detailed error logging
        showError('获取视频信息失败: ' + error.message);
    }
}

function generateResolutionOptions(formats, type) {
    const resolutionGrid = document.getElementById('resolutionGrid');
    resolutionGrid.innerHTML = '';
    
    if (formats.length === 0) {
        resolutionGrid.innerHTML = `
            <div class="col-span-full text-center p-6">
                <p class="text-gray-500 text-lg mb-2">未找到符合条件的${type === 'video' ? '视频' : '音频'}格式</p>
                <p class="text-gray-400 text-sm">我们只支持MP4格式的视频</p>
            </div>
        `;
        return;
    }
    
    formats.forEach(format => {
        const optionElement = document.createElement('div');
        optionElement.className = 'resolution-option';
        optionElement.dataset.formatId = format.format_id;
        optionElement.dataset.resolution = format.resolution;
        
        // Format file size
        const sizeText = formatFileSize(format.filesize);
        
        // Build format description
        const codecInfo = format.vcodec ? ` (${format.vcodec})` : '';
        const fpsInfo = format.fps ? ` ${format.fps}fps` : '';
        
        // Display format label (now only MP4 format)
        const formatLabel = format.ext.toUpperCase();
        
        optionElement.innerHTML = `
            <div class="resolution-label">${format.resolution}</div>
            <div class="resolution-details">${formatLabel}${codecInfo}${fpsInfo}</div>
            <div class="resolution-details">${sizeText}</div>
        `;
        
        optionElement.addEventListener('click', () => selectResolution(format.format_id, format.resolution));
        resolutionGrid.appendChild(optionElement);
    });
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '未知大小';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function selectResolution(formatId, resolution) {
    // Remove previous selection
    document.querySelectorAll('.resolution-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    // Select current option
    const selectedOption = document.querySelector(`[data-format-id="${formatId}"]`);
    if (selectedOption) {
        selectedOption.classList.add('selected');
        selectedFormatId = formatId;
        selectedResolution = resolution;
        document.getElementById('downloadButton').disabled = false;
    }
}

function startDownload() {
    const downloadButton = document.getElementById('downloadButton');
    downloadButton.disabled = true;
    downloadButton.innerHTML = `
        <div class="spinner" style="width: 20px; height: 20px; margin-right: 0.5rem;"></div>
        正在准备下载...
    `;
    
    // Get URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    const videoUrl = urlParams.get('url');
    const downloadType = urlParams.get('type') || 'video';
    
    // Trigger file save dialog
    setTimeout(() => {
        triggerFileDownload(videoUrl, downloadType, selectedFormatId, selectedResolution);
    }, 1000);
}

function triggerFileDownload(url, type, formatId, resolution) {
    // Check if showSaveFilePicker API is supported (modern browsers)
    if ('showSaveFilePicker' in window) {
        triggerModernFileSave(url, type, formatId, resolution);
    } else {
        // Fallback to traditional download method
        triggerTraditionalDownload(url, type, formatId, resolution);
    }
}

async function triggerModernFileSave(url, type, formatId, resolution) {
    try {
        const filename = generateSafeFilename(videoData.title, resolution, type);
        
        // Use modern file system access API to show save dialog
        const fileHandle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [{
                description: type === 'video' ? 'Video files' : 'Audio files',
                accept: type === 'video' ? { 'video/mp4': ['.mp4'] } : { 'audio/mp3': ['.mp3'] }
            }]
        });

        // This should call the actual download API
        // Simulate file data (in real applications this would be actual file content)
        const blob = new Blob([`模拟下载内容 - Format ID: ${formatId}`], { 
            type: type === 'video' ? 'video/mp4' : 'audio/mp3' 
        });
        
        const writable = await fileHandle.createWritable();
        await writable.write(blob);
        await writable.close();
        
        alert('文件保存成功！');
    } catch (error) {
        if (error.name !== 'AbortError') {
            console.error('保存文件时出错:', error);
            alert('保存文件失败: ' + error.message);
        }
        // If user cancelled the dialog, fallback to traditional download
        triggerTraditionalDownload(url, type, formatId, resolution);
    } finally {
        resetDownloadButton();
    }
}

function triggerTraditionalDownload(url, type, formatId, resolution) {
    // Create a temporary a tag to trigger file download
    const link = document.createElement('a');
    
    const filename = generateSafeFilename(videoData.title, resolution, type);
    
    // This should call the actual download API
    // Simulate file data (in real applications this would be actual file content)
    const blob = new Blob([`模拟下载内容 - Format ID: ${formatId}`], { 
        type: type === 'video' ? 'video/mp4' : 'audio/mp3' 
    });
    const objectUrl = URL.createObjectURL(blob);
    
    link.href = objectUrl;
    link.download = filename;
    link.style.display = 'none';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Clean up URL object
    URL.revokeObjectURL(objectUrl);
    
    resetDownloadButton();
    alert('文件下载已开始！请检查您的下载文件夹。');
}

function resetDownloadButton() {
    const downloadButton = document.getElementById('downloadButton');
    downloadButton.disabled = false;
    downloadButton.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4m4-5l5 5 5-5m-5 5V3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        下载选中格式
    `;
}

function showError(message) {
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('errorState').style.display = 'block';
}