// Preload for Live2D main window
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getConfig: () => ipcRenderer.invoke('get-pet-config'),
  setClickThrough: (enabled) => ipcRenderer.send('set-click-through', enabled),
  switchModel: (modelId) => ipcRenderer.send('switch-model', modelId),
  getModels: () => ipcRenderer.invoke('get-models'),
  onChatMessage: (callback) => ipcRenderer.on('chat-from-overlay', (_, text) => callback(text)),
  platform: process.platform,
});

// ============ Speech Bubble System ============
function showSpeechBubble(text, expressions) {
  const existing = document.querySelectorAll('.pet-speech-bubble');
  existing.forEach(el => el.remove());

  const bubble = document.createElement('div');
  bubble.className = 'pet-speech-bubble';

  const emotionEmoji = expressions?.includes(3) ? ' 😸'
    : expressions?.includes(2) ? ' 😠'
    : expressions?.includes(1) ? ' 😢'
    : expressions?.includes(0) ? ' 😐'
    : '';

  bubble.textContent = text + emotionEmoji;

  Object.assign(bubble.style, {
    position: 'fixed',
    top: '60px',
    left: '50%',
    transform: 'translateX(-50%) scale(0.85)',
    maxWidth: '340px',
    padding: '14px 20px',
    background: 'rgba(30, 30, 45, 0.92)',
    backdropFilter: 'blur(16px)',
    color: '#f0e6ff',
    fontSize: '14px',
    lineHeight: '1.6',
    borderRadius: '18px',
    border: '1px solid rgba(255, 150, 180, 0.4)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4), 0 0 20px rgba(255, 150, 180, 0.12)',
    zIndex: '99999',
    pointerEvents: 'none',
    fontFamily: "'Microsoft YaHei', 'PingFang SC', sans-serif",
    wordBreak: 'break-word',
    textAlign: 'center',
    transition: 'transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.35s ease-out',
  });

  // Arrow (downward triangle)
  const arrow = document.createElement('div');
  Object.assign(arrow.style, {
    position: 'absolute',
    bottom: '-8px',
    left: '50%',
    transform: 'translateX(-50%)',
    width: '0',
    height: '0',
    borderLeft: '10px solid transparent',
    borderRight: '10px solid transparent',
    borderTop: '10px solid rgba(30, 30, 45, 0.92)',
  });
  bubble.appendChild(arrow);

  if (!document.getElementById('pet-bubble-style')) {
    const style = document.createElement('style');
    style.id = 'pet-bubble-style';
    style.textContent = `
      @keyframes petBubbleOut {
        from { opacity: 1; transform: translateX(-50%) scale(1); }
        to   { opacity: 0; transform: translateX(-50%) scale(0.9); }
      }
    `;
    document.head.appendChild(style);
  }

  document.body.appendChild(bubble);

  // Trigger spring animation
  requestAnimationFrame(() => {
    bubble.style.transform = 'translateX(-50%) scale(1)';
    bubble.style.opacity = '1';
  });

  // Auto-dismiss after 7s
  setTimeout(() => {
    bubble.style.animation = 'petBubbleOut 0.4s ease-out forwards';
    setTimeout(() => bubble.remove(), 400);
  }, 7000);
}

// ============ Floating Chat Bar System ============
let chatBarContainer = null;
let chatBarInput = null;

function getOrCreateChatBar() {
  if (chatBarContainer && chatBarContainer.parentNode) return;

  chatBarContainer = document.createElement('div');
  chatBarContainer.id = 'pet-chat-bar-container';

  const bar = document.createElement('div');
  Object.assign(bar.style, {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 14px',
    background: 'rgba(30, 30, 40, 0.92)',
    backdropFilter: 'blur(14px)',
    borderRadius: '24px',
    border: '1px solid rgba(255, 150, 180, 0.4)',
    boxShadow: '0 6px 24px rgba(0,0,0,0.35), 0 0 14px rgba(255, 150, 180, 0.1)',
  });

  chatBarInput = document.createElement('input');
  Object.assign(chatBarInput.style, {
    flex: '1',
    border: 'none',
    outline: 'none',
    background: 'transparent',
    color: '#f0e6ff',
    fontSize: '14px',
    fontFamily: "'Microsoft YaHei', 'PingFang SC', sans-serif",
    padding: '6px 4px',
    minWidth: '200px',
  });
  chatBarInput.placeholder = '和喵酱说点什么...';
  chatBarInput.maxLength = 500;
  bar.appendChild(chatBarInput);

  // Send button
  const sendBtn = document.createElement('button');
  sendBtn.textContent = '发送';
  Object.assign(sendBtn.style, {
    border: 'none',
    outline: 'none',
    background: 'rgba(255, 150, 180, 0.25)',
    color: '#ffaacc',
    fontSize: '13px',
    padding: '6px 14px',
    borderRadius: '16px',
    cursor: 'pointer',
    fontFamily: "'Microsoft YaHei', 'PingFang SC', sans-serif",
    fontWeight: '600',
    transition: 'background 0.2s',
  });
  sendBtn.addEventListener('mouseenter', () => {
    sendBtn.style.background = 'rgba(255, 150, 180, 0.45)';
  });
  sendBtn.addEventListener('mouseleave', () => {
    sendBtn.style.background = 'rgba(255, 150, 180, 0.25)';
  });
  bar.appendChild(sendBtn);

  chatBarContainer.appendChild(bar);

  Object.assign(chatBarContainer.style, {
    position: 'fixed',
    bottom: '40px',
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: '99998',
    display: 'none',
    transition: 'opacity 0.2s ease-out, transform 0.2s ease-out',
    WebkitAppRegion: 'no-drag',
  });

  document.body.appendChild(chatBarContainer);

  // Event handlers
  function sendMessage() {
    const text = chatBarInput.value.trim();
    if (!text) return;
    chatBarInput.value = '';
    ipcRenderer.send('send-chat-message', text);
  }

  sendBtn.addEventListener('click', sendMessage);

  chatBarInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
    if (e.key === 'Escape') {
      hideChatBar();
    }
  });
}

function showChatBar() {
  getOrCreateChatBar();
  if (!chatBarContainer) return;
  chatBarContainer.style.display = 'block';
  chatBarContainer.style.opacity = '1';
  chatBarContainer.style.transform = 'translateX(-50%)';
  chatBarInput.focus();
  ipcRenderer.send('chat-bar-active', true);
}

function hideChatBar() {
  if (!chatBarContainer) return;
  chatBarContainer.style.opacity = '0';
  chatBarContainer.style.transform = 'translateX(-50%) translateY(8px)';
  setTimeout(() => {
    if (chatBarContainer) chatBarContainer.style.display = 'none';
  }, 200);
  ipcRenderer.send('chat-bar-active', false);
}

function toggleChatBar() {
  if (!chatBarContainer || chatBarContainer.style.display === 'none') {
    showChatBar();
  } else {
    hideChatBar();
  }
}

// ============ IPC Listeners ============
window.addEventListener('DOMContentLoaded', () => {
  // Response bubble
  window.addEventListener('pet-chat-response', (e) => {
    const { text: msg, expressions } = e.detail || {};
    if (!msg) return;
    showSpeechBubble(msg, expressions);
  });

  window.addEventListener('pet-chat-error', (e) => {
    const { text } = e.detail || {};
    showSpeechBubble(text || '发送失败', []);
  });

  ipcRenderer.on('show-response', (_, data) => {
    if (data.text) showSpeechBubble(data.text, data.expressions || []);
  });

  // Chat bar toggle/hide from main process
  ipcRenderer.on('toggle-chat-bar', () => toggleChatBar());
  ipcRenderer.on('hide-chat-bar', () => hideChatBar());
});
