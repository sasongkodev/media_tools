/* ═══════════════════════════════════════════
   Media Tools — JavaScript Application
   ═══════════════════════════════════════════ */

// ── State ──
let activeTasks = {};
let pollingInterval = null;

// ── Tab Switching ──
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));

    document.getElementById(tabName + '-tab').classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    if (tabName === 'library') loadFiles();
}

// ── Paste from Clipboard ──
async function pasteFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        document.getElementById('url-input').value = text;
        document.getElementById('url-input').focus();
    } catch (e) {
        showToast('Cannot access clipboard. Please paste manually.', 'error');
    }
}

// ── Handle Download ──
async function handleDownload(e) {
    e.preventDefault();
    const urlInput = document.getElementById('url-input');
    const qualitySelect = document.getElementById('quality-select');
    const btn = document.getElementById('btn-download');
    const url = urlInput.value.trim();
    const quality = qualitySelect.value;

    if (!url) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting...';

    try {
        const resp = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, quality })
        });
        const data = await resp.json();

        if (resp.ok) {
            activeTasks[data.task_id] = true;
            showToast('Download started!', 'success');
            urlInput.value = '';
            showTasksSection();
            startPolling();
        } else {
            showToast(data.error || 'Failed to start download', 'error');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'error');
    }

    btn.disabled = false;
    btn.innerHTML = '<span>⬇ Download</span>';
}

// ── Tasks Polling ──
function startPolling() {
    if (pollingInterval) return;
    pollingInterval = setInterval(pollTasks, 1500);
    pollTasks();
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

async function pollTasks() {
    try {
        const resp = await fetch('/api/tasks');
        const tasks = await resp.json();
        renderTasks(tasks);

        const hasActive = tasks.some(t =>
            ['pending', 'extracting', 'downloading'].includes(t.status)
        );
        if (!hasActive && Object.keys(activeTasks).length > 0) {
            stopPolling();
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
}

function showTasksSection() {
    document.getElementById('tasks-section').classList.remove('hidden');
}

function renderTasks(tasks) {
    const list = document.getElementById('tasks-list');
    const countEl = document.getElementById('task-count');

    if (!tasks.length) {
        document.getElementById('tasks-section').classList.add('hidden');
        return;
    }

    showTasksSection();
    countEl.textContent = tasks.length;

    list.innerHTML = tasks.map(t => `
        <div class="task-card" id="task-${t.task_id}">
            ${t.thumbnail
                ? `<img class="task-thumb" src="${t.thumbnail}" alt="">`
                : `<div class="task-thumb" style="display:flex;align-items:center;justify-content:center;font-size:1.4rem">🎬</div>`
            }
            <div class="task-info">
                <div class="task-title">${escapeHtml(t.title)}</div>
                <div class="task-meta">
                    <span>${t.quality.toUpperCase()}</span>
                    ${t.filesize ? `<span>${t.filesize}</span>` : ''}
                    ${t.speed ? `<span>${t.speed}</span>` : ''}
                    ${t.eta ? `<span>ETA: ${t.eta}</span>` : ''}
                    ${t.duration ? `<span>⏱ ${t.duration}</span>` : ''}
                </div>
                ${t.status === 'downloading' ? `
                    <div class="task-progress-bar">
                        <div class="task-progress-fill" style="width: ${t.progress}%"></div>
                    </div>
                ` : ''}
                ${t.error ? `<div style="color:var(--error);font-size:0.75rem;margin-top:6px">${escapeHtml(t.error).substring(0, 120)}</div>` : ''}
            </div>
            <div class="task-status ${t.status}">${t.status}</div>
        </div>
    `).join('');
}

// ── File Library ──
async function loadFiles() {
    const list = document.getElementById('files-list');
    try {
        const resp = await fetch('/api/files');
        const files = await resp.json();

        if (!files.length) {
            list.innerHTML = '<div class="empty-state"><p>No files yet. Download some videos first!</p></div>';
            return;
        }

        list.innerHTML = files.map(f => {
            const icon = getFileIcon(f.ext);
            return `
                <div class="file-card">
                    <div class="file-icon">${icon}</div>
                    <div class="file-info">
                        <div class="file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</div>
                        <div class="file-meta">${f.size} · ${f.modified}</div>
                    </div>
                    <div class="file-actions">
                        <a href="/downloads/${encodeURIComponent(f.name)}" class="file-btn" download>⬇ Save</a>
                        <button class="file-btn delete" onclick="deleteFile('${escapeHtml(f.name)}')">🗑</button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        list.innerHTML = '<div class="empty-state"><p>Error loading files.</p></div>';
    }
}

async function deleteFile(name) {
    if (!confirm(`Delete "${name}"?`)) return;
    try {
        const resp = await fetch(`/api/files/${encodeURIComponent(name)}/delete`, { method: 'DELETE' });
        if (resp.ok) {
            showToast('File deleted', 'success');
            loadFiles();
        } else {
            showToast('Delete failed', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

function getFileIcon(ext) {
    const icons = {
        '.mp4': '🎬', '.webm': '🎬', '.mkv': '🎬', '.avi': '🎬',
        '.mov': '🎬', '.flv': '🎬', '.m4v': '🎬', '.ts': '🎬',
        '.mp3': '🎵', '.m4a': '🎵', '.wav': '🎵', '.ogg': '🎵',
        '.jpg': '🖼', '.png': '🖼', '.gif': '🖼', '.webp': '🖼',
    };
    return icons[ext] || '📄';
}

// ── Toast Notifications ──
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Utilities ──
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Keyboard Shortcut ──
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
        const input = document.getElementById('url-input');
        if (document.activeElement !== input) {
            input.focus();
        }
    }
});
