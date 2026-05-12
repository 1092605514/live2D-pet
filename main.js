const { app, BrowserWindow, Tray, Menu, screen, nativeImage, ipcMain, globalShortcut, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const WebSocket = require('ws');

// ============ Configuration ============
const BACKEND_URL = 'http://localhost:12393';
const WS_URL = 'ws://localhost:12393/client-ws';
const OLLAMA_URL = 'http://localhost:11434';
const PET_WIDTH = 420;
const PET_HEIGHT = 620;

// Available models (synced with Ollama)
const AVAILABLE_MODELS = [
  { id: 'qwen2.5:3b', name: 'Qwen 2.5 3B (推荐)', emoji: '🐱' },
  { id: 'qwen2.5:1.5b', name: 'Qwen 2.5 1.5B (快速)', emoji: '⚡' },
  { id: 'llama3.2:1b', name: 'Llama 3.2 1B (英文)', emoji: '🦙' },
];
let currentModel = 'qwen2.5:3b';

let mainWindow = null;
let chatWindow = null;
let tray = null;
let isQuitting = false;
let isClickThrough = false;
let windowPosition = null;

// ============ WebSocket Interceptor ============
function injectWsInterceptor() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.executeJavaScript(`
    (function() {
      if (window.__petWsInjected) return;
      window.__petWsInjected = true;

      const OrigWebSocket = window.WebSocket;
      const wsInstances = [];

      window.WebSocket = function(url, protocols) {
        const ws = new OrigWebSocket(url, protocols);
        wsInstances.push(ws);
        ws.addEventListener('close', () => {
          const idx = wsInstances.indexOf(ws);
          if (idx >= 0) wsInstances.splice(idx, 1);
        });
        return ws;
      };
      window.WebSocket.prototype = OrigWebSocket.prototype;
      window.WebSocket.CONNECTING = OrigWebSocket.CONNECTING;
      window.WebSocket.OPEN = OrigWebSocket.OPEN;
      window.WebSocket.CLOSING = OrigWebSocket.CLOSING;
      window.WebSocket.CLOSED = OrigWebSocket.CLOSED;

      window.__petSendMessage = function(text) {
        for (const ws of wsInstances) {
          if (ws.readyState === OrigWebSocket.OPEN &&
              (ws.url || '').includes('/client-ws')) {
            ws.send(JSON.stringify({ type: 'text-input', text: text }));
            return true;
          }
        }
        for (const ws of wsInstances) {
          if (ws.readyState === OrigWebSocket.OPEN &&
              (ws.url || '').includes('localhost:12393')) {
            ws.send(JSON.stringify({ type: 'text-input', text: text }));
            return true;
          }
        }
        return false;
      };

      window.__petSendWsRaw = function(msg) {
        for (const ws of wsInstances) {
          if (ws.readyState === OrigWebSocket.OPEN &&
              (ws.url || '').includes('/client-ws')) {
            ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
            return true;
          }
        }
        return false;
      };

      console.log('[Pet] WebSocket interceptor active');
    })();
  `).catch(err => console.log('[Pet] Interceptor injection error:', err.message));
}

// ============ CSS Injection (Transparent Background) ============
function injectTransparentCSS() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.executeJavaScript(`
    (function() {
      if (document.getElementById('__pet_transparent_css')) return;
      const style = document.createElement('style');
      style.id = '__pet_transparent_css';
      style.textContent = [
        'html, body, #root, #__next, [id*="root"], [class*="root"]',
        '{ background: transparent !important; background-color: transparent !important; }',
        '[class*="chakra"], [class*="css-"], [class*="Chat"], [class*="chat"]',
        '{ background: transparent !important; background-color: transparent !important; }',
        'div[class*="sidebar"], aside, nav, header, footer, [class*="panel"], [class*="Panel"]',
        '{ display: none !important; }',
        '[class*="chat"] textarea, [class*="Chat"] textarea, [class*="message"] textarea',
        '{ display: none !important; }',
        'div[style*="background"], div[style*="backgroundColor"]',
        '{ background: transparent !important; background-color: transparent !important; }',
        'canvas',
        '{ display: block !important; -webkit-app-region: no-drag !important; }',
        'body',
        '{ -webkit-app-region: drag !important; }',
        '#pet-chat-bar-container, #pet-chat-bar-container *, .pet-speech-bubble',
        '{ -webkit-app-region: no-drag !important; }',
      ].join('\\n');
      document.head.appendChild(style);
      console.log('[Pet] Transparent CSS injected');
    })();
  `).catch(err => console.log('[Pet] CSS injection error:', err.message));
}

// ============ Live2D Model Switching ============
function switchLive2DModel(modelId) {
  const configMap = { 'mao_pro': 'mao_pro.yaml', 'shizuku': 'shizuku.yaml' };
  const configFile = configMap[modelId];
  if (!configFile) {
    console.log('[Pet] Unknown Live2D model: ' + modelId);
    return;
  }
  console.log('[Pet] Switching Live2D model to: ' + modelId + ' (' + configFile + ')');
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.executeJavaScript(`
    (function() {
      if (window.__petSendWsRaw) {
        return window.__petSendWsRaw(${JSON.stringify({type: 'switch-config', file: configFile})}) ? 'ws-ok' : 'ws-closed';
      }
      return 'no-fn';
    })();
  `).then(result => {
    console.log('[Pet] Switch Live2D model result:', result);
  }).catch(err => {
    console.log('[Pet] Switch Live2D model error:', err.message);
  });
}

// ============ Main Window (Live2D Pet) ============
function createWindow() {
  const { width: screenWidth, height: screenHeight } = screen.getPrimaryDisplay().workAreaSize;

  const x = windowPosition?.x ?? (screenWidth - PET_WIDTH - 30);
  const y = windowPosition?.y ?? (screenHeight - PET_HEIGHT - 30);

  mainWindow = new BrowserWindow({
    width: PET_WIDTH,
    height: PET_HEIGHT,
    x, y,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    minWidth: 280,
    minHeight: 400,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadURL(BACKEND_URL);

  // Inject WebSocket interceptor & transparent CSS into the page context
  injectWsInterceptor();
  injectTransparentCSS();

  // Re-inject on every page load (new conversation, reload, etc.)
  mainWindow.webContents.on('did-finish-load', () => {
    injectWsInterceptor();
    injectTransparentCSS();
  });

  mainWindow.on('moved', () => {
    windowPosition = mainWindow.getPosition();
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.setAlwaysOnTop(true, 'screen-saver');
  mainWindow.setVisibleOnAllWorkspaces(true);

  console.log(`[Pet] Live2D window at ${x}, ${y}`);
}

// ============ Quick Chat Overlay ============
function createChatWindow() {
  if (chatWindow && !chatWindow.isDestroyed()) {
    chatWindow.focus();
    return;
  }

  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  chatWindow = new BrowserWindow({
    width: 380,
    height: 60,
    x: Math.round((sw - 380) / 2),
    y: sh - 100,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'chat_preload.js'),
    },
  });

  chatWindow.loadFile(path.join(__dirname, 'chat_overlay.html'));

  chatWindow.on('blur', () => {
    if (chatWindow && !chatWindow.isDestroyed()) {
      chatWindow.hide();
    }
  });

  console.log('[Pet] Quick chat overlay created');
}

function showChatOverlay() {
  createChatWindow();
  if (chatWindow) {
    chatWindow.show();
    chatWindow.focus();
    chatWindow.webContents.send('focus-input');
  }
}

// ============ Send chat message to backend ============
function sendChatMessage(text) {
  if (!mainWindow || mainWindow.isDestroyed()) return;

  const safeText = text.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n');

  // Method 1: Use the page-context WebSocket interceptor (preserves Live2D expressions)
  mainWindow.webContents.executeJavaScript(`
    (function() {
      try {
        if (window.__petSendMessage) {
          return window.__petSendMessage('${safeText}') ? 'ws-ok' : 'ws-closed';
        }
        return 'no-fn';
      } catch(e) {
        return 'ws-error:' + e.message;
      }
    })();
  `).then(result => {
    console.log('[Pet] WS send result:', result);
    if (result === 'ws-ok') return;
    console.log('[Pet] WS not available (' + result + '), trying DOM injection');
    sendViaDOMInjection(safeText, text);
  }).catch(err => {
    console.log('[Pet] WS send error:', err.message);
    sendViaDOMInjection(safeText, text);
  });
}

// Fallback: Try to find the chat input in the React web UI
function sendViaDOMInjection(safeText, originalText) {
  if (!mainWindow || mainWindow.isDestroyed()) return;

  mainWindow.webContents.executeJavaScript(`
    (function() {
      const text = '${safeText}';
      const selectors = [
        'textarea',
        'input[type="text"]',
        'input:not([type])',
        '[class*="chat"] input',
        '[class*="Chat"] textarea',
        '[class*="message"] input',
        '#message-input',
        '.chat-input input',
      ];

      let input = null;
      for (const sel of selectors) {
        try {
          const el = document.querySelector(sel);
          if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
              input = el;
              break;
            }
          }
        } catch(e) {}
      }

      if (input) {
        const isTextArea = input.tagName === 'TEXTAREA';
        const proto = isTextArea ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (nativeSetter) {
          nativeSetter.call(input, text);
        } else {
          input.value = text;
        }
        input.dispatchEvent(new Event('input', { bubbles: true }));

        const btnSelectors = ['button[type="submit"]', 'button[class*="send"]', 'button[class*="Send"]', '[class*="chat"] button'];
        for (const bsel of btnSelectors) {
          const btn = document.querySelector(bsel);
          if (btn && btn.getBoundingClientRect().width > 0) {
            setTimeout(() => btn.click(), 50);
            return 'clicked:' + input.tagName;
          }
        }

        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        input.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        return 'enter:' + input.tagName;
      }

      return 'no-input';
    })();
  `).then(result => {
    console.log('[Pet] DOM injection result:', result);
    if (result === 'no-input') {
      console.log('[Pet] All injection methods failed');
    }
  }).catch(err => {
    console.log('[Pet] DOM injection error:', err.message);
  });
}

// ============ Model Management ============
let cachedOllamaModels = [];

function getAvailableModels() {
  return new Promise((resolve) => {
    http.get(`http://localhost:11434/api/tags`, { timeout: 5000 }, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const data = JSON.parse(body);
          const models = (data.models || []).map(m => ({
            id: m.name,
            name: m.name,
            size: m.size,
          }));
          cachedOllamaModels = models;
          resolve(models);
        } catch (e) {
          resolve([]);
        }
      });
    }).on('error', () => resolve(cachedOllamaModels));
  });
}

async function switchModel(modelId) {
  console.log(`[Pet] Switching to model: ${modelId}`);

  // Update conf.yaml
  const confPath = path.join(__dirname, '..', 'Open-LLM-VTuber', 'conf.yaml');
  try {
    const content = fs.readFileSync(confPath, 'utf8');
    // Find ollama_llm block and replace the model line after it
    const ollamaIndex = content.indexOf('ollama_llm:');
    if (ollamaIndex > 0) {
      const afterSection = content.substring(ollamaIndex);
      const modelMatch = afterSection.match(/(model:\s*)'[^']*'/);
      if (modelMatch) {
        const start = ollamaIndex + modelMatch.index + modelMatch[1].length;
        const before = content.substring(0, start);
        const after = content.substring(start + modelMatch[0].length - modelMatch[1].length);
        const updated = before + "'" + modelId + "'" + after;
        fs.writeFileSync(confPath, updated, 'utf8');
        console.log(`[Pet] conf.yaml updated with model: ${modelId}`);
      }
    }
  } catch (e) {
    console.log('[Pet] Failed to update conf.yaml:', e.message);
  }

  currentModel = modelId;
  createTray();

  // Reload main window to reconnect with new model
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.reload();
  }

  // Non-blocking notification - no dialog popup
  console.log(`[Pet] Model updated in conf.yaml: ${modelId}. Restart backend to apply.`);
}

async function restartBackend() {
  console.log('[Pet] Restarting backend...');

  // Kill existing python process running run_server.py
  try {
    const { execSync } = require('child_process');
    execSync('taskkill /f /fi "WINDOWTITLE eq *run_server*" 2>nul', { stdio: 'ignore' });
    execSync('taskkill /f /fi "IMAGENAME eq python.exe" /fi "MEMUSAGE gt 200000" 2>nul', { stdio: 'ignore' });
  } catch(e) {}

  // Start new backend
  const backendDir = path.join(__dirname, '..', 'Open-LLM-VTuber');
  const backendProcess = require('child_process').spawn('cmd', ['/c', 'start', '"喵酱Backend"', '/min', 'cmd', '/c',
    'set NO_PROXY=localhost,127.0.0.1,::1,.local && set no_proxy=localhost,127.0.0.1,::1,.local && uv run run_server.py'
  ], {
    cwd: backendDir,
    detached: true,
    stdio: 'ignore',
  });
  backendProcess.unref();

  console.log('[Pet] Backend starting, waiting for it to be ready...');

  // Poll until backend is ready, then reload
  let attempts = 0;
  const checkBackend = setInterval(() => {
    attempts++;
    http.get('http://localhost:12393', (res) => {
      clearInterval(checkBackend);
      console.log('[Pet] Backend ready after ' + (attempts * 2) + 's');
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reload();
      }
    }).on('error', () => {
      if (attempts > 30) {
        clearInterval(checkBackend);
        console.log('[Pet] Backend startup timed out');
      }
    });
  }, 2000);
}

// ============ System Tray ============
function createTray() {
  if (tray) tray.destroy();

  try {
    tray = new Tray(nativeImage.createFromBuffer(Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAbwAAAG8B8aLcQwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAEoSURBVDiNpVMxTsNAEJy7xI4dxx8gHX+goaCg4AMkfIAHQEMaJH4AHX9Io+SBPAAKOhRISTZN6NBBg0Ry9q3kGCdYAtmnd7c7M7s7Kw5YV3jHh36uX6/1f3mCBXrHlTq9hvt8B1e8Xq5V0GJnpXn6GP12XqGDs8K7EIm0a0BNk7vJ9BFnweAQMoR/lYJ6sm37d4Q5WWhQ1F2rxKliAWoW8UXn0HT5JpEVCc3I1cmQssM+LX2YLIIE29XyQWuOcp6fZil4NMs0NmfJQiMMnYkyN9dxdnMB9uZKE0gxE0ysoTbUInhMppSX2iHDDHnHmCGEKrjHfaB/hlrtBpETiG3wib2TYscMgI7qu6YMZnkY4p+n+h0y/SF2O8Czpm3BXqh4w2MHNEPm/RHHm3ATc1/vH+ETv2M6h5IAAAAASUVORK5CYII=',
      'base64'
    )));
  } catch (e) {
    console.error('[Pet] Failed to create tray icon:', e.message);
    return;
  }

  const modelItems = cachedOllamaModels.length > 0
    ? cachedOllamaModels.map(m => ({
        label: `${m.id}${currentModel === m.id ? ' ✓' : ''}`,
        click: () => switchModel(m.id),
      }))
    : AVAILABLE_MODELS.map(m => ({
        label: `${m.emoji} ${m.name}${currentModel === m.id ? ' ✓' : ''}`,
        click: () => switchModel(m.id),
      }));

  const contextMenu = Menu.buildFromTemplate([
    { label: '💬 快捷聊天', click: () => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('toggle-chat-bar');
      }
    }},
    { label: '👁 显示/隐藏 喵酱', click: toggleWindow },
    { type: 'separator' },
    { label: '📝 新对话', click: () => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.reload();
        console.log('[Pet] New conversation started');
      }
    }},
    { label: '🤖 切换模型', submenu: modelItems },
    { label: '🎭 切换 Live2D 模型', submenu: [
      { label: 'mao_pro', click: () => switchLive2DModel('mao_pro') },
      { label: 'shizuku', click: () => switchLive2DModel('shizuku') },
    ]},
    { type: 'separator' },
    { label: `🖱 点击穿透: ${isClickThrough ? '开' : '关'}`, click: toggleClickThrough },
    { type: 'separator' },
    { label: '🔄 重新加载', click: () => mainWindow?.reload() },
    { label: '♻ 重启后端', click: restartBackend },
    { label: '❌ 退出', click: quitApp },
  ]);

  tray.setToolTip('喵酱 Live2D Desktop Pet');
  tray.setContextMenu(contextMenu);
  tray.on('double-click', toggleWindow);

  // Async refresh model list - updates context menu when Ollama responds
  getAvailableModels().then(ollamaModels => {
    if (ollamaModels.length > 0) {
      const freshItems = ollamaModels.map(m => ({
        label: `${m.id}${currentModel === m.id ? ' ✓' : ''}`,
        click: () => switchModel(m.id),
      }));
      const freshMenu = Menu.buildFromTemplate([
        { label: '💬 快捷聊天', click: () => {
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('toggle-chat-bar');
          }
        }},
        { label: '👁 显示/隐藏 喵酱', click: toggleWindow },
        { type: 'separator' },
        { label: '📝 新对话', click: () => {
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.reload();
            console.log('[Pet] New conversation started');
          }
        }},
        { label: '🤖 切换模型', submenu: freshItems },
        { label: '🎭 切换 Live2D 模型', submenu: [
          { label: 'mao_pro', click: () => switchLive2DModel('mao_pro') },
          { label: 'shizuku', click: () => switchLive2DModel('shizuku') },
        ]},
        { type: 'separator' },
        { label: `🖱 点击穿透: ${isClickThrough ? '开' : '关'}`, click: toggleClickThrough },
        { type: 'separator' },
        { label: '🔄 重新加载', click: () => mainWindow?.reload() },
        { label: '♻ 重启后端', click: restartBackend },
        { label: '❌ 退出', click: quitApp },
      ]);
      tray.setContextMenu(freshMenu);
      console.log('[Pet] Tray menu updated with Ollama models');
    }
  });
}

function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible()) {
    mainWindow.hide();
  } else {
    mainWindow.show();
    mainWindow.focus();
  }
}

function toggleClickThrough() {
  isClickThrough = !isClickThrough;
  if (mainWindow) {
    mainWindow.setIgnoreMouseEvents(isClickThrough, { forward: true });
  }
  createTray();
  console.log(`[Pet] Click-through: ${isClickThrough ? 'ON' : 'OFF'}`);
}

function quitApp() {
  isQuitting = true;
  globalShortcut.unregisterAll();
  if (tray) tray.destroy();
  if (chatWindow && !chatWindow.isDestroyed()) chatWindow.destroy();
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy();
  // Note: Python backend (run_server.py) stays alive — it's an independent process.
  // This lets the user relaunch the pet without waiting for backend cold-start.
  app.quit();
}

// ============ IPC Handlers ============
function setupIPC() {
  ipcMain.handle('get-pet-config', () => ({
    backendUrl: BACKEND_URL,
    clickThrough: isClickThrough,
    currentModel: currentModel,
  }));

  ipcMain.on('set-click-through', (_, enabled) => {
    isClickThrough = enabled;
    if (mainWindow) {
      mainWindow.setIgnoreMouseEvents(enabled, { forward: true });
    }
  });

  // Chat bar → main window message relay
  ipcMain.on('send-chat-message', (_, text) => {
    sendChatMessage(text);
    // Hide chat bar after sending
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('hide-chat-bar');
    }
  });

  // Chat bar active state → temporarily disable click-through while typing
  ipcMain.on('chat-bar-active', (_, active) => {
    if (mainWindow && isClickThrough) {
      mainWindow.setIgnoreMouseEvents(!active, { forward: true });
    }
  });

  // Get models list
  ipcMain.handle('get-models', async () => {
    const ollamaModels = await getAvailableModels();
    return ollamaModels.length > 0 ? ollamaModels.map(m => m.name) : AVAILABLE_MODELS.map(m => m.id);
  });

  // Switch model
  ipcMain.on('switch-model', (_, modelId) => switchModel(modelId));
}

// ============ App Lifecycle ============
app.whenReady().then(() => {
  setupIPC();
  createWindow();
  createTray();

  // Global shortcuts (work even when window is unfocused / click-through)
  globalShortcut.register('Ctrl+Shift+Space', () => {
    console.log('[Pet] Shortcut: Quick chat');
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
      mainWindow.webContents.send('toggle-chat-bar');
    }
  });
  globalShortcut.register('Ctrl+Shift+H', () => {
    console.log('[Pet] Shortcut: Toggle window');
    toggleWindow();
  });
  globalShortcut.register('Ctrl+Shift+T', () => {
    console.log('[Pet] Shortcut: Toggle click-through');
    toggleClickThrough();
  });

  console.log('[Pet] ========================================');
  console.log('[Pet]  喵酱 Live2D Desktop Pet Ready!');
  console.log('[Pet]  Ctrl+Shift+Space = Quick Chat');
  console.log('[Pet]  Ctrl+Shift+H     = Show/Hide');
  console.log('[Pet]  Ctrl+Shift+T     = Click-through ON/OFF');
  console.log('[Pet]  Right-click tray = Full menu');
  console.log('[Pet] ========================================');
});

app.on('window-all-closed', () => {});  // Don't quit - keep in tray
app.on('before-quit', () => { isQuitting = true; if (tray) tray.destroy(); });
app.on('activate', () => { if (mainWindow) mainWindow.show(); });
