/**
 * Hermes × Aizen — Mobile PWA Application Logic
 *
 * Vanilla JS, no framework dependency. Connects to the Hermes API server.
 * Features: chat, streak display, settings, offline support, auto-resize composer.
 */

// ============================================================
// Config
// ============================================================

function defaultServerUrl() {
  const saved = localStorage.getItem('hermes-server-url')
  if (saved !== null) return saved
  // Same-origin when Caddy serves this PWA in front of the gateway.
  if (typeof location !== 'undefined' && /^https?:$/.test(location.protocol)) {
    const port = location.port
    if (!port || port === '80' || port === '443') return ''
  }
  return 'http://127.0.0.1:8642'
}

const CONFIG = {
  serverUrl: defaultServerUrl(),
  apiKey: localStorage.getItem('hermes-api-key') || '',
  model: localStorage.getItem('hermes-model') || '',
  theme: localStorage.getItem('hermes-theme') || 'dark',
};

function apiUrl(path) {
  const base = String(CONFIG.serverUrl || '').replace(/\/$/, '')
  return `${base}${path}`
}

function apiHeaders(extra) {
  const headers = { ...(extra || {}) }
  if (CONFIG.apiKey) {
    headers.Authorization = `Bearer ${CONFIG.apiKey}`
  }
  return headers
}

// ============================================================
// DOM
// ============================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const elements = {
  app: $('#app'),
  input: $('#input'),
  sendBtn: $('#send-btn'),
  messages: $('#messages'),
  welcome: $('#welcome'),
  chatArea: $('#chat-area'),
  streakBar: $('#streak-bar'),
  streakText: $('#streak-text'),
  streakProgress: $('#streak-progress'),
  settingsModal: $('#settings-modal'),
  settingsBtn: $('#settings-btn'),
  settingsClose: $('#settings-close'),
  streakBtn: $('#streak-btn'),
  serverUrl: $('#server-url'),
  apiKey: $('#api-key'),
  modelSelect: $('#model-select'),
  themeSelect: $('#theme-select'),
  modelLabel: $('#model-label'),
};

// ============================================================
// Theme
// ============================================================

function applyTheme(theme) {
  if (theme === 'auto') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.body.dataset.theme = prefersDark ? 'dark' : 'light';
  } else {
    document.body.dataset.theme = theme;
  }
  localStorage.setItem('hermes-theme', theme);
}

applyTheme(CONFIG.theme);

// ============================================================
// Auto-resize textarea
// ============================================================

elements.input.addEventListener('input', () => {
  elements.input.style.height = 'auto';
  elements.input.style.height = Math.min(elements.input.scrollHeight, 120) + 'px';
  elements.sendBtn.disabled = !elements.input.value.trim();
});

// ============================================================
// Chat Logic
// ============================================================

let conversationId = crypto.randomUUID?.() || Date.now().toString(36);
let isStreaming = false;

async function sendMessage(text) {
  if (!text.trim() || isStreaming) return;

  // Hide welcome, show messages
  elements.welcome.style.display = 'none';
  elements.messages.style.display = 'flex';

  // Add user message
  appendMessage('user', text);

  // Clear input
  elements.input.value = '';
  elements.input.style.height = 'auto';
  elements.sendBtn.disabled = true;

  // Show typing indicator
  const typingEl = appendTyping();
  isStreaming = true;

  try {
    const response = await fetch(apiUrl('/api/chat'), {
      method: 'POST',
      headers: apiHeaders({
        'Content-Type': 'application/json',
        'X-Hermes-Session-Id': conversationId,
      }),
      body: JSON.stringify({
        message: text,
        conversation_id: conversationId,
        model: CONFIG.model || undefined,
      }),
    });

    typingEl.remove();

    if (!response.ok) {
      let detail = `Server returned ${response.status}`
      try {
        const errBody = await response.json()
        detail = errBody.error?.message || errBody.error || errBody.message || detail
      } catch {
        /* keep status text */
      }
      throw new Error(detail)
    }

    const rotated = response.headers.get('X-Hermes-Session-Id')
    if (rotated) conversationId = rotated

    // Check if streaming (SSE)
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/event-stream')) {
      await handleStream(response);
    } else {
      const data = await response.json();
      const reply = extractReply(data);
      appendMessage('assistant', reply);
    }

    // Record streak
    recordStreak();
  } catch (err) {
    typingEl.remove();
    appendMessage('assistant', `⚠️ Connection error: ${err.message}\n\nMake sure the Hermes server is running at ${CONFIG.serverUrl}`);
  }

  isStreaming = false;
  scrollToBottom();
}

async function handleStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let msgEl = null;
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // Keep incomplete line

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (data === '[DONE]') continue;

        try {
          const parsed = JSON.parse(data);
          const chunk = parsed.content || parsed.delta || parsed.text || '';
          if (chunk) {
            if (!msgEl) {
              msgEl = appendMessage('assistant', '');
            }
            msgEl.querySelector('.msg-text').textContent += chunk;
            scrollToBottom();
          }
        } catch {
          // Non-JSON SSE data
          if (!msgEl) {
            msgEl = appendMessage('assistant', '');
          }
          msgEl.querySelector('.msg-text').textContent += data;
        }
      }
    }
  }
}

function extractReply(data) {
  if (data == null) return ''
  if (typeof data.response === 'string' && data.response) return data.response
  if (typeof data.message === 'string' && data.message) return data.message
  if (data.message && typeof data.message.content === 'string') return data.message.content
  if (typeof data.content === 'string' && data.content) return data.content
  if (data.choices && data.choices[0] && data.choices[0].message) {
    return data.choices[0].message.content || ''
  }
  return JSON.stringify(data)
}

function appendMessage(role, text) {
  const el = document.createElement('div');
  el.className = `message ${role}`;
  el.innerHTML = `<div class="msg-text">${escapeHtml(text)}</div>`;
  elements.messages.appendChild(el);
  scrollToBottom();
  return el;
}

function appendTyping() {
  const el = document.createElement('div');
  el.className = 'message assistant typing-indicator';
  el.innerHTML = '<span></span><span></span><span></span>';
  elements.messages.appendChild(el);
  scrollToBottom();
  return el;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    elements.chatArea.scrollTop = elements.chatArea.scrollHeight;
  });
}

// ============================================================
// Event Handlers
// ============================================================

// Send on Enter (Shift+Enter for newline)
elements.input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(elements.input.value);
  }
});

elements.sendBtn.addEventListener('click', () => {
  sendMessage(elements.input.value);
});

// Quick action buttons
$$('.quick-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const prompt = btn.dataset.prompt;
    if (prompt) sendMessage(prompt);
  });
});

// Settings
elements.settingsBtn.addEventListener('click', () => {
  elements.settingsModal.style.display = 'flex';
  elements.serverUrl.value = CONFIG.serverUrl;
  if (elements.apiKey) elements.apiKey.value = CONFIG.apiKey;
  elements.modelSelect.value = CONFIG.model;
  elements.themeSelect.value = CONFIG.theme;
});

elements.settingsClose.addEventListener('click', () => {
  elements.settingsModal.style.display = 'none';
});

elements.settingsModal.addEventListener('click', (e) => {
  if (e.target === elements.settingsModal) {
    elements.settingsModal.style.display = 'none';
  }
});

// Save settings on change
elements.serverUrl.addEventListener('change', () => {
  CONFIG.serverUrl = elements.serverUrl.value;
  localStorage.setItem('hermes-server-url', CONFIG.serverUrl);
});

if (elements.apiKey) {
  elements.apiKey.addEventListener('change', () => {
    CONFIG.apiKey = elements.apiKey.value.trim();
    localStorage.setItem('hermes-api-key', CONFIG.apiKey);
  });
}

elements.modelSelect.addEventListener('change', () => {
  CONFIG.model = elements.modelSelect.value;
  localStorage.setItem('hermes-model', CONFIG.model);
  elements.modelLabel.textContent = CONFIG.model || 'hermes × aizen';
});

elements.themeSelect.addEventListener('change', () => {
  CONFIG.theme = elements.themeSelect.value;
  applyTheme(CONFIG.theme);
});

// ============================================================
// Streak
// ============================================================

let streakVisible = false;

elements.streakBtn.addEventListener('click', () => {
  streakVisible = !streakVisible;
  elements.streakBar.style.display = streakVisible ? 'flex' : 'none';
  if (streakVisible) loadStreak();
});

async function loadStreak() {
  try {
    const res = await fetch(apiUrl('/api/panels/streaks'), { headers: apiHeaders() });
    if (res.ok) {
      const data = await res.json();
      const streak = data.streak || {};
      elements.streakText.textContent = streak.streak_display || 'Start your streak!';
      const progress = Math.min((streak.current_streak || 0) / 30 * 100, 100);
      elements.streakProgress.style.setProperty('--progress', progress + '%');
    }
  } catch {
    elements.streakText.textContent = '✨ Start your streak!';
  }
}

async function recordStreak() {
  try {
    await fetch(apiUrl('/api/panels/streaks/record'), { method: 'POST', headers: apiHeaders() });
  } catch {
    // Silently fail
  }
}

// ============================================================
// System theme listener
// ============================================================

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (CONFIG.theme === 'auto') applyTheme('auto');
});

// ============================================================
// Focus input on load
// ============================================================

elements.input.focus();

async function probeGateway() {
  try {
    const res = await fetch(apiUrl('/health'))
    if (res.ok) {
      elements.modelLabel.textContent = `${CONFIG.model || 'hermes × aizen'} · online`
      return
    }
  } catch {
    /* fall through */
  }
  elements.modelLabel.textContent = 'offline — set Server URL in settings'
}

probeGateway()

// Initial streak load (background)
setTimeout(loadStreak, 1000);
