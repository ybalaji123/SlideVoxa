// Present page JS — synchronized slide + audio presentation player
const API_BASE = "https://slidevoxa-4.onrender.com";

// Auth guard
const uid = localStorage.getItem('sv_uid');
if (!uid) window.location.href = '/login';

// Get presentation ID from URL (support ?id=... or /present/...)
const params = new URLSearchParams(window.location.search);
let presentationId = params.get('id');

if (!presentationId) {
    const pathParts = window.location.pathname.split('/');
    // Check if the last part is a UUID-like string
    const lastPart = pathParts[pathParts.length - 1];
    if (lastPart && lastPart.length > 30) {
        presentationId = lastPart;
    }
}

if (!presentationId) window.location.href = '/dashboard';

// State
let slides = [];
let currentSlide = 0;
let currentAudio = null;
let isPaused = false;
let isComplete = false;
let questions = [];
let scriptVisible = false;
let hasStarted = false;
let presentationLanguage = 'en-IN'; // loaded from status endpoint
let isQAOpen = false;               // true while Q&A panel is visible
const slideDataCache = {}; // index -> { image_data_uri, audio_data_uri }
let browserSpeechToken = 0;

// Elements
const slideTitle = document.getElementById('slide-title');
const slideBullets = document.getElementById('slide-bullets');
const slideBody = document.getElementById('slide-body');
const slideContent = document.getElementById('slide-content');
const slideLoading = document.getElementById('slide-loading');
const narrationBar = document.getElementById('narration-bar');
const narrationText = document.getElementById('narration-text');
const narrationWaves = document.getElementById('narration-waves');
const scriptDisplay = document.getElementById('script-display');
const scriptText = document.getElementById('script-text');
const slideCounter = document.getElementById('slide-counter');
const progressFill = document.getElementById('progress-fill');
const slidesThumbsEl = document.getElementById('slides-thumbs');
const phPresentTitle = document.getElementById('ph-pres-title');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const pauseBtn = document.getElementById('pause-btn');
const pauseIcon = document.getElementById('pause-icon');
const volumeSlider = document.getElementById('volume-slider');
const showScriptBtn = document.getElementById('show-script-btn');
const completeOverlay = document.getElementById('complete-overlay');
const qaList = document.getElementById('qa-list');
const replayBtn = document.getElementById('replay-btn');
const returnPresBtn = document.getElementById('return-pres-btn');
const completeAskBtn = document.getElementById('complete-ask-btn');
const fullscreenBtn = document.getElementById('fullscreen-btn');

// Helper to dramatically improve performance by extracting massive base64 to memory Blobs
function dataURItoBlobUrl(dataURI) {
    if (!dataURI) return null;
    if (dataURI.startsWith('blob:')) return dataURI;
    try {
        const parts = dataURI.split(',');
        const mime = parts[0].split(':')[1].split(';')[0];
        const byteString = atob(parts[1]);
        const ab = new ArrayBuffer(byteString.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < byteString.length; i++) {
            ia[i] = byteString.charCodeAt(i);
        }
        return URL.createObjectURL(new Blob([ab], { type: mime }));
    } catch (e) {
        return dataURI; // fallback
    }
}

// Fetch slide-specific heavy assets on demand
async function getSlideData(idx) {
    if (slideDataCache[idx]) return await slideDataCache[idx];

    const fetchPromise = fetch(`${API_BASE}/api/presentations/${presentationId}/slide/${idx + 1}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
            if (data) {
                // Convert to Blob URLs so the browser main thread doesn't lag parsing huge base64 strings
                if (data.image_data_uri && data.image_data_uri.startsWith('data:')) {
                    data.image_data_uri = dataURItoBlobUrl(data.image_data_uri);
                }
                if (data.audio_data_uri && data.audio_data_uri.startsWith('data:')) {
                    data.audio_data_uri = dataURItoBlobUrl(data.audio_data_uri);
                }
            }
            return data;
        })
        .catch(e => { console.error("Fetch error:", e); return null; });

    slideDataCache[idx] = fetchPromise;
    return await fetchPromise;
}

// Load presentation metadata first
async function loadPresentation() {
    try {
        const res = await fetch(`${API_BASE}/api/presentations/${presentationId}/status`);
        if (!res.ok) throw new Error('Presentation not found');
        const data = await res.json();

        slides = data.slides || [];
        questions = data.questions || [];
        presentationLanguage = data.language || 'en-IN';
        phPresentTitle.textContent = data.title || 'Presentation';

        if (slides.length === 0) {
            slideLoading.textContent = 'No slides found.';
            return;
        }

        buildThumbnails();
        slideLoading.style.display = 'none';
        slideContent.style.display = 'flex';

        // Preload first two slides aggressively
        let firstSlidePromise = null;
        if (slides.length > 0) firstSlidePromise = getSlideData(0);
        if (slides.length > 1) getSlideData(1); // look-ahead preload

        const btn = document.getElementById('start-pres-btn');
        btn.disabled = true;
        btn.innerHTML = `<div style="width:16px;height:16px;border:2.5px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;animation:spin 0.8s linear infinite;display:inline-block;vertical-align:middle;margin-right:8px;"></div> Preparing Assets...`;
        btn.style.opacity = '0.7';

        // Wait for the first slide to be fully loaded and converted to Blobs
        if (firstSlidePromise) await firstSlidePromise;

        // Ready to start!
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>Start Presentation`;

        // Initial setup
        showSlide(0);
    } catch (err) {
        slideLoading.innerHTML = `<p style="color:#FF2D55">Error: ${err.message}</p>`;
    }
}

function buildThumbnails() {
    slidesThumbsEl.innerHTML = '';
    slides.forEach((slide, i) => {
        const thumb = document.createElement('div');
        thumb.className = `slide-thumb ${i === 0 ? 'active' : ''}`;
        thumb.id = `thumb-${i}`;
        thumb.innerHTML = `
            <div class="thumb-number">${i + 1}</div>
            <div class="thumb-preview">
                <div class="thumb-preview-fallback">${escapeHtml(slide.title || `Slide ${i + 1}`)}</div>
                <img class="thumb-image" alt="Slide ${i + 1}" loading="lazy" />
            </div>
            <div class="thumb-title">${escapeHtml(slide.title || `Slide ${i + 1}`)}</div>
        `;
        const thumbnailImage = thumb.querySelector('.thumb-image');
        thumbnailImage.addEventListener('error', () => thumbnailImage.remove(), { once: true });
        thumbnailImage.src = `${API_BASE}/api/presentations/${encodeURIComponent(presentationId)}/thumbnail/${i + 1}`;
        thumb.addEventListener('click', () => navigateTo(i));
        slidesThumbsEl.appendChild(thumb);
    });
}

function stopAudio() {
    browserSpeechToken++;
    if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
    }
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    narrationBar.style.display = 'none';
    if (narrationWaves) narrationWaves.style.display = 'none';
}

function finishNarration() {
    narrationBar.style.display = 'none';
    if (narrationWaves) narrationWaves.style.display = 'none';
    if (currentSlide < slides.length - 1 && !isPaused) {
        setTimeout(() => navigateTo(currentSlide + 1), 800);
    } else if (currentSlide === slides.length - 1 && !isPaused) {
        showCompletionOverlay();
    }
}

function playBrowserSpeech(script, statusMessage) {
    if (!script || !('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
        narrationBar.style.display = 'flex';
        narrationText.textContent = 'Narration is unavailable on this device.';
        if (narrationWaves) narrationWaves.style.display = 'none';
        return;
    }

    stopAudio();
    const token = browserSpeechToken;
    const utterance = new SpeechSynthesisUtterance(script);
    utterance.lang = presentationLanguage || 'en-IN';
    utterance.volume = parseFloat(volumeSlider.value);

    const availableVoices = window.speechSynthesis.getVoices();
    const languagePrefix = utterance.lang.split('-')[0].toLowerCase();
    utterance.voice = availableVoices.find(voice => voice.lang.toLowerCase() === utterance.lang.toLowerCase())
        || availableVoices.find(voice => voice.lang.toLowerCase().startsWith(`${languagePrefix}-`))
        || null;

    let started = false;
    currentAudio = {
        pause: () => window.speechSynthesis.pause(),
        play: () => {
            if (window.speechSynthesis.paused) window.speechSynthesis.resume();
            else if (!started) {
                started = true;
                window.speechSynthesis.speak(utterance);
            }
        },
    };

    narrationBar.style.display = 'flex';
    narrationText.textContent = statusMessage || 'Using your device voice for narration.';
    if (narrationWaves) narrationWaves.style.display = 'flex';

    utterance.onend = () => {
        if (token === browserSpeechToken) finishNarration();
    };
    utterance.onerror = event => {
        if (token !== browserSpeechToken || event.error === 'canceled' || event.error === 'interrupted') return;
        narrationText.textContent = 'Device voice could not speak this slide.';
        if (narrationWaves) narrationWaves.style.display = 'none';
    };

    started = true;
    window.speechSynthesis.speak(utterance);
}

function playSlideAudioDirect(dataUri, fallbackScript) {
    stopAudio();
    currentAudio = new Audio(dataUri);
    currentAudio.volume = parseFloat(volumeSlider.value);
    let fallbackStarted = false;
    const useFallbackVoice = () => {
        if (fallbackStarted) return;
        fallbackStarted = true;
        playBrowserSpeech(fallbackScript, 'Generated audio could not play. Using your device voice.');
    };

    narrationBar.style.display = 'flex';
    narrationText.textContent = 'AI Presenter Speaking...';
    if (narrationWaves) narrationWaves.style.display = 'flex';

    currentAudio.addEventListener('ended', finishNarration);

    currentAudio.addEventListener('error', event => {
        console.error('Audio error:', event);
        useFallbackVoice();
    });

    if (!isPaused) {
        currentAudio.play().catch(err => {
            console.warn("Autoplay blocked:", err);
            useFallbackVoice();
        });
    }
}

async function showSlide(index) {
    stopAudio();
    currentSlide = index;
    const slide = slides[index];
    if (!slide) return;

    // 1. Instant Text Update
    slideCounter.textContent = `Slide ${index + 1} of ${slides.length}`;
    progressFill.style.width = `${((index + 1) / slides.length) * 100}%`;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === slides.length - 1;

    scriptText.textContent = slide.script || 'No script available.';
    slideTitle.textContent = slide.title || `Slide ${index + 1}`;
    slideBullets.innerHTML = (slide.points || []).map(p => `<li>${escapeHtml(p)}</li>`).join('');
    slideBody.textContent = slide.body || '';

    document.querySelectorAll('.slide-thumb').forEach((t, i) => {
        t.classList.toggle('active', i === index);
    });
    const activeThumb = document.getElementById(`thumb-${index}`);
    if (activeThumb) activeThumb.scrollIntoView({ block: 'nearest', behavior: 'smooth' });

    // Transition Animation
    slideContent.style.animation = 'none';
    slideContent.offsetHeight; // reflow
    slideContent.style.animation = 'fadeInUp 0.4s ease';

    const slideImage = document.getElementById('slide-image');
    const slideTextFallback = document.getElementById('slide-text-fallback');

    // 2. Fetch Heavy Assets (On-Demand)
    const data = await getSlideData(index);
    if (!data) {
        // Fallback simple view — no image available
        slideImage.style.display = 'none';
        slideTextFallback.style.display = 'flex';
        slideContent.style.backgroundColor = '#FFFFFF';
        return;
    }

    if (data.image_data_uri) {
        // Show the exact PPT slide image
        slideImage.src = data.image_data_uri;
        slideImage.style.display = 'block';
        slideTextFallback.style.display = 'none';
        slideContent.style.backgroundColor = '#000';
    } else {
        // No image — show text fallback
        slideImage.style.display = 'none';
        slideTextFallback.style.display = 'flex';
        slideContent.style.backgroundColor = '#FFFFFF';
    }

    // Auto-play audio if started
    const narrationScript = slide.script || [slide.title, ...(slide.points || [])].filter(Boolean).join('. ');
    if (data.audio_data_uri && !isPaused && hasStarted) {
        playSlideAudioDirect(data.audio_data_uri, narrationScript);
    } else if (!isPaused && hasStarted) {
        playBrowserSpeech(narrationScript, 'No generated audio for this slide. Using your device voice.');
    }

    // 3. Low-priority look-ahead prefetch
    if (index + 1 < slides.length) getSlideData(index + 1);
}

function navigateTo(index) {
    if (index < 0 || index >= slides.length) return;
    isPaused = false;
    updatePauseButton();
    showSlide(index);
}

// Event Listeners
prevBtn.addEventListener('click', () => navigateTo(currentSlide - 1));
nextBtn.addEventListener('click', () => {
    if (currentSlide >= slides.length - 1) {
        showCompletionOverlay();
    } else {
        navigateTo(currentSlide + 1);
    }
});

pauseBtn.addEventListener('click', () => {
    if (!hasStarted) return;
    isPaused = !isPaused;
    updatePauseButton();
    if (currentAudio) {
        if (isPaused) {
            currentAudio.pause();
            narrationText.textContent = 'Paused';
        } else {
            currentAudio.play().catch(() => { });
            narrationText.textContent = 'AI Presenter Speaking...';
        }
    }
});

function updatePauseButton() {
    if (isPaused) {
        pauseIcon.innerHTML = `<polygon points="5 3 19 12 5 21 5 3"/>`;
        pauseBtn.childNodes[2].textContent = ' Resume';
    } else {
        pauseIcon.innerHTML = `<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>`;
        pauseBtn.childNodes[2].textContent = ' Pause';
    }
}

volumeSlider.addEventListener('input', () => {
    if (currentAudio) currentAudio.volume = parseFloat(volumeSlider.value);
});

showScriptBtn.addEventListener('click', () => {
    scriptVisible = !scriptVisible;
    scriptDisplay.style.display = scriptVisible ? 'block' : 'none';
});

fullscreenBtn.addEventListener('click', () => {
    if (!document.fullscreenElement) {
        document.getElementById('slide-display').requestFullscreen?.();
    } else {
        document.exitFullscreen?.();
    }
});

document.addEventListener('fullscreenchange', () => {
    if (document.fullscreenElement) {
        fullscreenBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 0 2-2h3M3 16h3a2 2 0 0 0 2 2v3"/></svg> Exit Fullscreen`;
    } else {
        fullscreenBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg> Fullscreen`;
    }
});

function showCompletionOverlay() {
    stopAudio();
    isComplete = true;
    completeOverlay.style.display = 'none';
    qaList.innerHTML = '';
    if (questions.length > 0) {
        questions.forEach((q, i) => {
            const item = document.createElement('div');
            item.className = 'qa-item';
            item.innerHTML = `<span class="qa-num">${i + 1}.</span> <span>${escapeHtml(q)}</span>`;
            qaList.appendChild(item);
        });
    } else {
        qaList.innerHTML = '<p style="color:var(--text-muted);font-size:14px;">No questions generated.</p>';
    }
    clearTimeout(window.__completionQATimer);
    window.__completionQATimer = setTimeout(() => {
        if (isComplete && !isQAOpen) openQAPanel();
    }, 1000);
}

replayBtn.addEventListener('click', () => {
    isComplete = false;
    isPaused = false;
    hasStarted = true;
    completeOverlay.style.display = 'none';
    updatePauseButton();
    navigateTo(0);
});

if (returnPresBtn) {
    returnPresBtn.addEventListener('click', () => {
        isComplete = false;
        completeOverlay.style.display = 'none';
        // User stays on the last slide, but can navigate back. Use navigateTo to ensure correct state.
        navigateTo(slides.length - 1);
    });
}

if (completeAskBtn) {
    completeAskBtn.addEventListener('click', () => {
        completeOverlay.style.display = 'none';
        openQAPanel();
    });
}

document.getElementById('start-pres-btn').addEventListener('click', () => {
    hasStarted = true;
    document.getElementById('start-overlay').style.display = 'none';

    // Show the floating Ask button
    const askFloatBtn = document.getElementById('ask-float-btn');
    if (askFloatBtn) askFloatBtn.style.display = 'flex';

    // Trigger local ppt opening
    fetch(`${API_BASE}/api/presentations/${presentationId}/open_ppt`, { method: 'POST' })
        .catch(e => console.error("Failed to open local PPT:", e));

    showSlide(0);
});

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    switch (e.key) {
        case 'ArrowRight': case 'ArrowDown': case ' ':
            e.preventDefault();
            if (currentSlide < slides.length - 1) navigateTo(currentSlide + 1);
            else showCompletionOverlay();
            break;
        case 'ArrowLeft': case 'ArrowUp':
            e.preventDefault();
            navigateTo(currentSlide - 1);
            break;
        case 'p': case 'P':
            pauseBtn.click();
            break;
        case 'q': case 'Q':
            // Open Q&A panel shortcut
            if (hasStarted && !isComplete) openQAPanel();
            break;
    }
});

// ═══════════════════════════════════════════════════
// LIVE Q&A CHAT
const askFloatBtn = document.getElementById('ask-float-btn');
const qaPanel = document.getElementById('qa-panel');
const qaCloseBtn = document.getElementById('qa-close-btn');
const qaInput = document.getElementById('qa-question-input');
const qaSubmitBtn = document.getElementById('qa-submit-btn');
const qaChatHistory = document.getElementById('qa-chat-history');
const qaChatAudio = document.getElementById('qa-chat-audio');
const qaAnswerWaves = document.getElementById('qa-answer-waves');
const qaVoiceBtn = document.getElementById('qa-voice-btn');
const qaVoiceStatus = document.getElementById('qa-voice-status');
const qaResumeBtn = document.getElementById('qa-resume-btn');
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
let qaAudio = null;
let qaRecognition = null;

if (!SpeechRecognitionAPI && qaVoiceBtn) {
    qaVoiceBtn.disabled = true;
    qaVoiceBtn.title = 'Voice input is not supported in this browser';
    qaVoiceBtn.setAttribute('aria-label', 'Voice input is not supported in this browser');
}

function appendQAMessage(role, message, extraClass = '') {
    const item = document.createElement('div');
    item.className = `qa-message qa-message-${role}${extraClass ? ` ${extraClass}` : ''}`;
    item.textContent = message;
    qaChatHistory.appendChild(item);
    qaChatHistory.scrollTop = qaChatHistory.scrollHeight;
    return item;
}

function openQAPanel() {
    if (isQAOpen || !hasStarted) return;
    isQAOpen = true;

    if (currentAudio && typeof currentAudio.pause === 'function') {
        currentAudio.pause();
        narrationText.textContent = 'Paused for Q&A';
    }
    if (window.__autoAdvanceTimeout) clearTimeout(window.__autoAdvanceTimeout);

    if (isComplete && qaChatHistory.dataset.completionPromptShown !== 'true') {
        appendQAMessage('assistant', "The presentation is complete. Do you have any questions? Type or say your question, and I'll answer using the uploaded slides.");
        qaChatHistory.dataset.completionPromptShown = 'true';
    } else if (!qaChatHistory.childElementCount) {
        appendQAMessage(
            'assistant',
            "Ask me anything about the slides. I'll answer using the uploaded presentation."
        );
    }
    qaResumeBtn.style.display = 'none';
    qaSubmitBtn.disabled = false;
    qaSubmitBtn.textContent = 'Send';
    qaPanel.style.display = 'flex';
    setTimeout(() => qaInput.focus(), 120);
}

function closeQAPanel() {
    if (qaRecognition) {
        try { qaRecognition.stop(); } catch (_) { }
        qaRecognition = null;
    }
    if (qaAudio) { qaAudio.pause(); qaAudio = null; }
    qaChatAudio.style.display = 'none';
    qaPanel.style.display = 'none';
    isQAOpen = false;
    if (isComplete) completeOverlay.style.display = 'flex';
}

async function submitQuestion() {
    const question = qaInput.value.trim();
    if (!question) { qaInput.focus(); return; }

    appendQAMessage('user', question);
    qaInput.value = '';
    const answerMessage = appendQAMessage('assistant', 'Thinking...', 'qa-message-pending');
    qaSubmitBtn.disabled = true;
    qaSubmitBtn.textContent = 'Thinking...';
    qaVoiceBtn.disabled = true;
    if (qaAudio) { qaAudio.pause(); qaAudio = null; }
    qaChatAudio.style.display = 'none';

    try {
        const res = await fetch(`${API_BASE}/api/presentations/${presentationId}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, language: presentationLanguage }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        answerMessage.classList.remove('qa-message-pending');
        answerMessage.textContent = data.answer || 'Sorry, I could not generate an answer.';
        qaResumeBtn.style.display = isComplete ? 'none' : 'inline-flex';

        if (data.audio_data_uri) {
            let audioSrc = data.audio_data_uri;
            if (audioSrc.startsWith('data:')) audioSrc = dataURItoBlobUrl(audioSrc);
            qaAudio = new Audio(audioSrc);
            qaAudio.volume = parseFloat(volumeSlider.value);
            qaChatAudio.style.display = 'flex';
            qaAudio.addEventListener('ended', () => { qaChatAudio.style.display = 'none'; });
            qaAudio.addEventListener('error', () => { qaChatAudio.style.display = 'none'; });
            qaAudio.play().catch(() => { qaChatAudio.style.display = 'none'; });
        }
    } catch (err) {
        answerMessage.classList.remove('qa-message-pending');
        answerMessage.textContent = `I couldn't get an answer just now (${err.message}). Please try again.`;
    } finally {
        qaSubmitBtn.disabled = false;
        qaSubmitBtn.textContent = 'Send';
        qaVoiceBtn.disabled = !SpeechRecognitionAPI;
        qaInput.focus();
    }
}

function startVoiceQuestion() {
    if (!SpeechRecognitionAPI || !qaVoiceBtn) return;
    if (qaRecognition) {
        qaRecognition.stop();
        return;
    }

    const recognition = new SpeechRecognitionAPI();
    qaRecognition = recognition;
    recognition.lang = presentationLanguage || 'en-IN';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
        qaVoiceBtn.classList.add('is-listening');
        qaVoiceStatus.textContent = 'Listening... speak your question.';
        qaVoiceStatus.style.display = 'block';
    };
    recognition.onresult = event => {
        const transcript = event.results?.[0]?.[0]?.transcript?.trim();
        if (transcript) {
            qaInput.value = [qaInput.value.trim(), transcript].filter(Boolean).join(' ');
            qaVoiceStatus.textContent = "Voice question captured. Select Send when you're ready.";
            qaInput.focus();
        }
    };
    recognition.onerror = event => {
        qaVoiceStatus.textContent = event.error === 'not-allowed'
            ? 'Allow microphone access to ask by voice.'
            : 'Voice input stopped. You can type your question instead.';
        qaVoiceStatus.style.display = 'block';
    };
    recognition.onend = () => {
        qaVoiceBtn.classList.remove('is-listening');
        qaRecognition = null;
        setTimeout(() => {
            if (!qaVoiceBtn.classList.contains('is-listening')) qaVoiceStatus.style.display = 'none';
        }, 3500);
    };
    try {
        recognition.start();
    } catch (_) {
        qaRecognition = null;
        qaVoiceStatus.textContent = 'Voice input could not start. You can type your question instead.';
        qaVoiceStatus.style.display = 'block';
    }
}

function resumeFromQA() {
    closeQAPanel();
    if (isComplete) return;

    if (currentAudio && typeof currentAudio.play === 'function' && !isPaused) {
        currentAudio.play().catch(() => {});
        narrationBar.style.display = 'flex';
        narrationText.textContent = 'AI Presenter Speaking...';
        if (narrationWaves) narrationWaves.style.display = 'flex';
    } else if (!isPaused) {
        showSlide(currentSlide);
    }
}

if (askFloatBtn) askFloatBtn.addEventListener('click', openQAPanel);
if (qaCloseBtn) qaCloseBtn.addEventListener('click', closeQAPanel);
if (qaSubmitBtn) qaSubmitBtn.addEventListener('click', submitQuestion);
if (qaVoiceBtn) qaVoiceBtn.addEventListener('click', startVoiceQuestion);
if (qaResumeBtn) qaResumeBtn.addEventListener('click', resumeFromQA);
if (qaInput) {
    qaInput.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); submitQuestion(); }
        if (event.key === 'Escape') closeQAPanel();
    });
}

// Boot
loadPresentation();
