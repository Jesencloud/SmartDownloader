// static/common.js

const translations = {
    zh: {
        // From script.js
        homeButton: 'Home',
        mainTitle: '智能下载器',
        mainHeading: '智能下载器',
        urlPlaceholder: '粘贴视频或播放列表URL...',
        pasteButton: '粘贴',
        clearButton: '清除',
        videoButton: '提取视频',
        audioButton: '提取音频',
        introTitle: '智能下载器介绍',
        introDesc1: '智能下载器 – 免费高质量下载视频和音频。只需在下方输入框中粘贴视频URL，点击"提取"按钮，即可立即保存您所需分辨率的视频或音频。',
        introDesc2: '如何轻松下载视频和音频？视频和音频是内容呈现的关键部分，通过引人注目的视觉和听觉吸引注意力。如果您想保存视频或音频，使用智能下载器可以轻松完成。许多工具允许您通过几次点击即可从各种平台下载内容。',
        introDesc3: '使用智能下载器非常简单。您只需粘贴视频链接，工���将立即获取并允许您在几秒钟内下载高质量的视频或音频。这非常适合内容创作者、研究��员或任何想要保存媒体内容以供个人使用的人。',
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
        download: '下载'
    },
    en: {
        // From script.js
        homeButton: 'Home',
        mainTitle: 'Smart Downloader',
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
        download: 'Download'
    }
};

function switchLanguage(lang) {
    // Save language preference
    localStorage.setItem('language', lang);
    
    const t = translations[lang] || translations.zh;
    
    // Update text content based on elements that exist on the page
    const updateIfExists = (selector, text) => {
        const element = document.querySelector(selector);
        if (element) element.textContent = text;
    };

    // This function is generic and can be used by both pages
    const updateTextContent = () => {
        // Header
        updateIfExists('.header-right a[href="/"]', t.homeButton);
        
        // Page title and meta
        const titleElement = document.querySelector('title');
        if (titleElement) {
            if (window.location.pathname.includes('download.html')) {
                titleElement.textContent = t.title;
            } else {
                titleElement.textContent = lang === 'en' ? 'Smart Downloader: Intelligent Video Downloader' : 'Smart Downloader: 智能下载器';
            }
        }
        
        // Main hero section (index.html)
        updateIfExists('.hero-section h1', t.mainHeading);
        const urlInput = document.querySelector('#videoUrl');
        if (urlInput) urlInput.placeholder = t.urlPlaceholder;
        
        // Buttons (index.html)
        const pasteButtonSpan = document.querySelector('#pasteButton span');
        if (pasteButtonSpan) pasteButtonSpan.textContent = t.pasteButton;
        
        const clearButtonSpan = document.querySelector('#clearButton span');
        if (clearButtonSpan) clearButtonSpan.textContent = t.clearButton;
        
        const videoButton = document.querySelector('#downloadVideoButton');
        if (videoButton) {
            const textNode = Array.from(videoButton.childNodes).find(node => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim());
            if (textNode) textNode.nodeValue = t.videoButton;
        }
        
        const audioButton = document.querySelector('#downloadAudioButton');
        if (audioButton) {
            const textNode = Array.from(audioButton.childNodes).find(node => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim());
            if (textNode) textNode.nodeValue = t.audioButton;
        }
        
        // Introduction section (index.html)
        const introSectionH2 = document.querySelector('.dcontainer h2');
        if (introSectionH2) introSectionH2.textContent = t.introTitle;
        
        const dcontainer = document.querySelector('.dcontainer');
        if (dcontainer) {
            const introPs = dcontainer.querySelectorAll('p');
            if (introPs.length >= 4) {
                introPs[0].textContent = t.introDesc1;
                introPs[1].textContent = t.introDesc2;
                introPs[2].textContent = t.introDesc3;
                introPs[3].textContent = t.introDesc4;
            }
        }
        
        // How to use section (index.html)
        const howToSection = Array.from(document.querySelectorAll('section')).find(s => s.querySelector('h2')?.textContent.includes('如何使用') || s.querySelector('h2')?.textContent.includes('How to Use'));
        if (howToSection) {
            howToSection.querySelector('h2').textContent = t.howToTitle;
            const howToContainer = howToSection.querySelector('.dcontainer');
            if (howToContainer) {
                howToContainer.querySelector('p').textContent = t.howToDesc;
                const steps = howToContainer.querySelectorAll('.step p');
                if (steps.length >= 4) {
                    steps[0].textContent = t.step1;
                    steps[1].textContent = t.step2;
                    steps[2].textContent = t.step3;
                    steps[3].textContent = t.step4;
                }
            }
        }
        
        // About section (index.html)
        const aboutSection = document.querySelector('.about-us');
        if (aboutSection) {
            aboutSection.querySelector('h2').textContent = t.aboutTitle;
            const aboutPs = aboutSection.querySelectorAll('p');
            if (aboutPs.length >= 3) {
                aboutPs[0].textContent = t.aboutDesc1;
                aboutPs[1].textContent = t.aboutDesc2;
                aboutPs[2].textContent = t.aboutDesc3;
            }
        }
        
        // FAQ section (index.html)
        const faqH3 = document.querySelector('.faq-container h3');
        if (faqH3) faqH3.textContent = t.faqTitle;
        
        const faqItems = document.querySelectorAll('.faq-item');
        const faqTranslations = [
            { q: t.faq1Q, a: t.faq1A }, { q: t.faq2Q, a: t.faq2A }, { q: t.faq3Q, a: t.faq3A },
            { q: t.faq4Q, a: t.faq4A }, { q: t.faq5Q, a: t.faq5A }, { q: t.faq6Q, a: t.faq6A }
        ];
        faqItems.forEach((item, index) => {
            if (faqTranslations[index]) {
                const question = item.querySelector('.faq-question');
                const answer = item.querySelector('.faq-answer p');
                if (question) question.textContent = faqTranslations[index].q;
                if (answer) answer.textContent = faqTranslations[index].a;
            }
        });
        
        // Footer (shared)
        const footerLinks = document.querySelectorAll('.footer-right a');
        if (footerLinks.length >= 4) {
            footerLinks[0].textContent = t.footerPrivacy;
            footerLinks[1].textContent = t.footerDisclaimer;
            footerLinks[2].textContent = t.footerAbout;
            footerLinks[3].textContent = t.footerContact;
        }

        // Download page elements (download.html)
        updateIfExists('#loadingState p', t.loading);
        updateIfExists('#errorMessage', t.errorTitle);
        updateIfExists('.section-title', t.selectResolution);
        updateIfExists('#downloadButton .text', t.downloadSelected);
        
        const returnHomeLinks = document.querySelectorAll('a[href="/"]');
        returnHomeLinks.forEach(link => {
            if (link.textContent.includes('返回主页') || link.textContent.includes('Back to Home')) {
                link.textContent = t.returnHome;
            }
        });

        // Update HTML lang attribute
        document.documentElement.setAttribute('lang', lang === 'en' ? 'en-US' : 'zh-CN');
        
        // Store current language for use in other functions
        window.currentLanguage = lang;
    };

    updateTextContent();
}