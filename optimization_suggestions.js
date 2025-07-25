// 建议的格式验证优化
function validateDownloadRequest(formatId, downloadType, currentVideoData) {
    const errors = [];
    
    // 验证格式ID
    if (!formatId || formatId === 'undefined' || formatId === 'null') {
        errors.push('Invalid format ID');
    }
    
    // 验证下载类型
    if (!['video', 'audio'].includes(downloadType)) {
        errors.push('Invalid download type');
    }
    
    // 验证视频数据
    if (!currentVideoData || !currentVideoData.formats) {
        errors.push('No video data available');
    }
    
    // 验证格式存在性
    const formatExists = currentVideoData.formats.some(f => f.format_id === formatId);
    if (!formatExists) {
        errors.push(`Format ${formatId} not found in available formats`);
    }
    
    if (errors.length > 0) {
        throw new DownloadValidationError(errors.join(', '));
    }
    
    return true;
}

// 在下载前调用验证
function handleDownload(formatId) {
    try {
        validateDownloadRequest(formatId, currentVideoData.download_type, currentVideoData);
        // 继续下载逻辑...
    } catch (error) {
        showErrorMessage(error.message);
        return;
    }
}