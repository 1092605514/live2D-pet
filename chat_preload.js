// Chat overlay preload - bridges IPC for the quick chat bar

const { contextBridge, ipcRenderer } = require('electron');

// When the overlay loads, set up the chat input
window.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');
  const qaHappy = document.getElementById('qaHappy');
  const qaSad = document.getElementById('qaSad');
  const qaWave = document.getElementById('qaWave');
  const qaSpin = document.getElementById('qaSpin');

  if (!input || !btn) return;

  // Submit handler
  function submitChat() {
    const text = input.value.trim();
    if (text) {
      ipcRenderer.send('send-chat-message', text);
      input.value = '';
    }
  }

  btn.addEventListener('click', submitChat);

  // Quick actions
  if (qaHappy) qaHappy.addEventListener('click', () => ipcRenderer.send('send-quick-action', 'expression', 'happy'));
  if (qaSad) qaSad.addEventListener('click', () => ipcRenderer.send('send-quick-action', 'expression', 'sad'));
  if (qaWave) qaWave.addEventListener('click', () => ipcRenderer.send('send-quick-action', 'action', 'wave'));
  if (qaSpin) qaSpin.addEventListener('click', () => ipcRenderer.send('send-quick-action', 'action', 'spin'));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitChat();
    if (e.key === 'Escape') window.close();
  });

  // Auto-focus when receiving signal
  ipcRenderer.on('focus-input', () => {
    input.focus();
    input.select();
  });

  input.focus();
});

contextBridge.exposeInMainWorld('chatAPI', {
  sendMessage: (text) => ipcRenderer.send('send-chat-message', text),
  close: () => window.close(),
});
