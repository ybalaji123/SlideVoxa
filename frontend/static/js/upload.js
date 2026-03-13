// Upload page JS — handles PPT upload, voice sample, and generation flow

const API_BASE = "https://slidevoxa-4.onrender.com";

// Auth guard
const uid = localStorage.getItem('sv_uid');
const userName = localStorage.getItem('sv_name') || 'User';
const userEmail = localStorage.getItem('sv_email') || '';
const userPhoto = localStorage.getItem('sv_photo') || '';

if (!uid) window.location.href = '/login';

// Populate user info
document.querySelectorAll('#user-name').forEach(el => el.textContent = userName);
document.querySelectorAll('#user-email').forEach(el => el.textContent = userEmail);
document.querySelectorAll('#user-avatar-img').forEach(el => {
    if (userPhoto) {
        el.innerHTML = `<img src="${userPhoto}" alt="${userName}" style="width:100%;height:100%;border-radius:50%;object-fit:cover" />`;
    } else {
        el.textContent = userName.charAt(0).toUpperCase();
    }
});

document.querySelectorAll('#logout-btn').forEach(btn => {
    btn.addEventListener('click', () => { localStorage.clear(); window.location.href = '/login'; });
});

// Toast helper
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// File state
let pptFile = null;
let voiceFile = null;

// ---- DROPZONE ----
const dropzone = document.getElementById('dropzone');
const pptInput = document.getElementById('ppt-file-input');
const browseBtn = document.getElementById('browse-btn');
const fileSelected = document.getElementById('file-selected');
const fileName = document.getElementById('file-name');
const fileSize = document.getElementById('file-size');
const removeFileBtn = document.getElementById('remove-file-btn');

browseBtn.addEventListener('click', () => pptInput.click());
dropzone.addEventListener('click', (e) => {
    if (e.target !== browseBtn) pptInput.click();
});

pptInput.addEventListener('change', (e) => {
    if (e.target.files[0]) setPptFile(e.target.files[0]);
});

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragging');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragging');
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith('.pptx') || file.name.endsWith('.ppt'))) {
        setPptFile(file);
    } else {
        showToast('Please drop a .ppt or .pptx file.', 'error');
    }
});

function setPptFile(file) {
    pptFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    dropzone.style.display = 'none';
    fileSelected.style.display = 'flex';
    updateGenerateBtn();
}

removeFileBtn.addEventListener('click', () => {
    pptFile = null;
    pptInput.value = '';
    dropzone.style.display = 'flex';
    fileSelected.style.display = 'none';
    updateGenerateBtn();
});

// ---- VOICE SELECTION ----
const voiceSelect = document.getElementById('voice-select');

// ---- GENERATE BUTTON ----
const generateBtn = document.getElementById('generate-btn');
const generateHint = document.getElementById('generate-hint');

function updateGenerateBtn() {
    if (pptFile) {
        generateBtn.disabled = false;
        generateHint.textContent = 'Ready! Click to generate your AI presentation.';
    } else {
        generateBtn.disabled = true;
        generateHint.textContent = 'Please upload a PowerPoint file to continue.';
    }
}

generateBtn.addEventListener('click', async () => {
    if (!pptFile) return;

    generateBtn.disabled = true;
    generateBtn.innerHTML = `<div class="spinner"></div> Uploading...`;

    // Show progress panel
    document.getElementById('progress-panel').style.display = 'block';
    setProgress('extract', 'active');

    // Upload the file
    const formData = new FormData();
    formData.append('file', pptFile);
    formData.append('user_id', uid);
    formData.append('user_email', userEmail);
    formData.append('voice_id', voiceSelect.value || '21m00Tcm4TlvDq8ikWAM');

    try {
        const uploadRes = await fetch(`${API_BASE}/api/presentations/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!uploadRes.ok) {
            const err = await uploadRes.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const data = await uploadRes.json();
        const presentationId = data.presentation_id;
        setProgress('extract', 'done');
        setProgress('script', 'active');

        generateBtn.innerHTML = `<div class="spinner"></div> Generating AI scripts...`;

        // Trigger generation
        const genRes = await fetch(`${API_BASE}/api/presentations/${presentationId}/generate`, {
            method: 'POST',
        });
        if (!genRes.ok) throw new Error('Generation failed');

        setProgress('script', 'done');
        setProgress('audio', 'active');

        generateBtn.innerHTML = `<div class="spinner"></div> Creating audio narration...`;

        // Poll status
        let attempts = 0;
        const maxAttempts = 60; // 2 minutes
        const poll = setInterval(async () => {
            attempts++;
            try {
                const statusRes = await fetch(`${API_BASE}/api/presentations/${presentationId}/status`);
                const status = await statusRes.json();

                if (status.status === 'ready') {
                    clearInterval(poll);
                    setProgress('audio', 'done');
                    setProgress('questions', 'done');
                    generateBtn.innerHTML = `✅ Presentation Ready!`;
                    generateHint.textContent = 'Your presentation is ready. Redirecting to player...';
                    showToast('Presentation generated successfully!', 'success');
                    setTimeout(() => {
                        window.location.href = `/present?id=${presentationId}`;
                    }, 1500);
                } else if (attempts >= maxAttempts) {
                    clearInterval(poll);
                    showToast('Generation timed out. Audio may still be processing.', 'error');
                    generateBtn.disabled = false;
                    generateBtn.innerHTML = `Generate Presentation`;
                }
            } catch {
                // ignore polling errors
            }
        }, 2000);

    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
        generateBtn.disabled = false;
        generateBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>Generate Presentation`;
        document.getElementById('progress-panel').style.display = 'none';
    }
});

function setProgress(step, state) {
    const mapping = {
        extract: 'ps-extract',
        script: 'ps-script',
        audio: 'ps-audio',
        questions: 'ps-questions',
    };
    const el = document.getElementById(mapping[step]);
    if (!el) return;
    el.className = `prog-step ${state}`;
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}
