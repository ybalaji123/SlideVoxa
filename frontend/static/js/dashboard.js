// Dashboard JS — load user info, fetch presentations, display cards

const API_BASE = window.location.origin;

// Auth guard
const uid = localStorage.getItem('sv_uid');
const userName = localStorage.getItem('sv_name') || 'User';
const userEmail = localStorage.getItem('sv_email') || '';
const userPhoto = localStorage.getItem('sv_photo') || '';

if (!uid) {
    window.location.href = '/login';
}

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

// Logout
document.querySelectorAll('#logout-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        localStorage.clear();
        window.location.href = '/login';
    });
});

// Toast helper
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
}

// Format date
function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Load presentations
async function loadPresentations() {
    const grid = document.getElementById('pres-grid');
    grid.innerHTML = `<div class="pres-loading"><div class="spinner spinner-lg"></div><p>Loading presentations...</p></div>`;

    try {
        const res = await fetch(`${API_BASE}/api/presentations/user/${uid}`);
        if (!res.ok) throw new Error('Failed to load');
        const data = await res.json();

        // Update stats
        document.getElementById('total-count').textContent = data.length;
        document.getElementById('ready-count').textContent = data.filter(p => p.status === 'ready').length;
        document.getElementById('processing-count').textContent = data.filter(p => p.status === 'processing').length;

        if (data.length === 0) {
            grid.innerHTML = `
        <div class="pres-empty">
          <div class="pres-empty-icon">📊</div>
          <h3>No Presentations Yet</h3>
          <p>Upload your first PowerPoint to get started.</p>
          <a href="/upload" class="btn btn-primary" style="margin-top:16px">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Presentation
          </a>
        </div>`;
            return;
        }

        grid.innerHTML = '';
        data.reverse().forEach(p => {
            const card = document.createElement('div');
            card.className = 'pres-card';
            const statusClass = p.status === 'ready' ? 'status-ready' : p.status === 'processing' ? 'status-processing' : 'status-error';
            const statusLabel = p.status === 'ready' ? '● Ready' : p.status === 'processing' ? '◌ Processing' : '✕ Error';

            card.innerHTML = `
        <div class="pres-card-icon">📊</div>
        <div class="pres-card-title" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</div>
        <div class="pres-card-meta">
          <span>${p.slide_count} slides</span>
          <span>${formatDate(p.created_at)}</span>
        </div>
        <span class="status-pill ${statusClass}">${statusLabel}</span>
        <div class="pres-card-actions">
          ${p.status === 'ready'
                    ? `<button class="btn btn-primary btn-sm" onclick="startPresentation('${p.id}')">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Present
              </button>`
                    : p.status === 'processing'
                        ? `<button class="btn btn-ghost btn-sm" disabled>Processing...</button>`
                        : ''
                }
          <button class="btn btn-ghost btn-sm" onclick="deletePresentation('${p.id}')">Delete</button>
        </div>
      `;
            grid.appendChild(card);
        });
    } catch (err) {
        grid.innerHTML = `<div class="pres-empty"><div class="pres-empty-icon">⚠️</div><h3>Failed to Load</h3><p>${err.message}</p></div>`;
        showToast('Failed to load presentations', 'error');
    }
}

function startPresentation(id) {
    window.location.href = `/present?id=${id}`;
}

async function deletePresentation(id) {
    if (!confirm('Delete this presentation? This cannot be undone.')) return;
    try {
        const res = await fetch(`${API_BASE}/api/presentations/${id}?user_id=${uid}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Presentation deleted.', 'success');
            loadPresentations();
        } else {
            showToast('Failed to delete.', 'error');
        }
    } catch {
        showToast('Network error.', 'error');
    }
}

function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.getElementById('refresh-btn').addEventListener('click', loadPresentations);

loadPresentations();
