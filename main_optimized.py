#!/usr/bin/env python3
"""
喵酱 Live2D Desktop Pet — PySide6 + QWebEngineView

Optimized focus:
- keep all Qt UI updates on the Qt thread
- make model switching safer and atomic
- avoid killing unrelated python.exe processes during backend restart
- reduce unused imports and repeated ad-hoc imports
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

# ── Configuration ───────────────────────────────────────────
BACKEND_URL = "http://localhost:12393"
OLLAMA_URL = "http://localhost:11434"
PET_WIDTH = 280
PET_HEIGHT = 420
ZOOM_FACTOR = 1.5
HTTP_TIMEOUT_SECONDS = 5
BACKEND_READY_MAX_ATTEMPTS = 30
BACKEND_READY_INTERVAL_MS = 2_000

BASE_DIR = Path(__file__).resolve().parent
OPEN_LLM_VTUBER_DIR = BASE_DIR.parent / "Open-LLM-VTuber"
CONF_PATH = OPEN_LLM_VTUBER_DIR / "conf.yaml"

AVAILABLE_MODELS = (
    {"id": "qwen2.5:3b", "name": "Qwen 2.5 3B", "emoji": "🐱"},
    {"id": "qwen2.5:1.5b", "name": "Qwen 2.5 1.5B", "emoji": "⚡"},
    {"id": "llama3.2:1b", "name": "Llama 3.2 1B", "emoji": "🦙"},
)

CHARACTERS_DIR = OPEN_LLM_VTUBER_DIR / "characters"
LIVE2D_MODELS_DIR = OPEN_LLM_VTUBER_DIR / "live2d-models"

LOG = logging.getLogger("pet")


# ═══════════════════════════════════════════════════════════════
# Small helpers
# ═══════════════════════════════════════════════════════════════
def request_json(url: str, timeout: int = HTTP_TIMEOUT_SECONDS) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "Pet/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def yaml_single_quote(value: str) -> str:
    """Return a YAML-safe single-quoted scalar."""
    return "'" + value.replace("'", "''") + "'"


def update_ollama_model_in_conf(conf_path: Path, model_id: str) -> bool:
    """
    Update the `model:` line inside the `ollama_llm:` YAML section.

    This is intentionally line-based instead of a full YAML rewrite so comments,
    ordering, and unrelated formatting are preserved.
    """
    if not conf_path.exists():
        LOG.warning("conf.yaml not found: %s", conf_path)
        return False

    lines = conf_path.read_text(encoding="utf-8").splitlines(keepends=True)
    section_indent: int | None = None
    section_found = False
    model_updated = False

    section_re = re.compile(r"^(?P<indent>\s*)ollama_llm:\s*(?:#.*)?$")
    model_re = re.compile(
        r"^(?P<prefix>\s*model\s*:\s*)"
        r"(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^#\r\n]*?))"
        r"(?P<suffix>\s*(?:#.*)?)(?P<newline>\r?\n?)$"
    )

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not section_found:
            match = section_re.match(line)
            if match:
                section_found = True
                section_indent = len(match.group("indent"))
            continue

        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" \t"))
        if section_indent is not None and indent <= section_indent:
            # Reached next sibling section before finding model.
            break

        match = model_re.match(line)
        if match:
            lines[idx] = (
                f"{match.group('prefix')}{yaml_single_quote(model_id)}"
                f"{match.group('suffix')}{match.group('newline')}"
            )
            model_updated = True
            break

    if not section_found:
        LOG.warning("ollama_llm section not found in %s", conf_path)
        return False
    if not model_updated:
        LOG.warning("model field not found under ollama_llm in %s", conf_path)
        return False

    tmp_path = conf_path.with_suffix(conf_path.suffix + ".tmp")
    tmp_path.write_text("".join(lines), encoding="utf-8")
    tmp_path.replace(conf_path)
    return True


# ═══════════════════════════════════════════════════════════════
# Speech Bubble Widget
# ═══════════════════════════════════════════════════════════════
class SpeechBubble(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setVisible(False)
        self.setFixedWidth(170)
        self.setMinimumHeight(28)
        self.setMaximumHeight(90)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setFont(QFont("Microsoft YaHei", 8))
        self._label.setStyleSheet("color: #f0e6ff;")
        layout.addWidget(self._label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.setStyleSheet(
            """
            SpeechBubble {
                background: rgba(30, 30, 45, 230);
                border: 1px solid rgba(255, 150, 180, 100);
                border-radius: 14px;
            }
            """
        )

    def show_text(self, text: str, expressions: list[int] | None = None):
        emoji = self._expression_emoji(expressions or [])
        self._label.setText(f"{text}{emoji}")
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(7_000)

    @staticmethod
    def _expression_emoji(expressions: list[int]) -> str:
        if 3 in expressions:
            return " 😸"
        if 2 in expressions:
            return " 😠"
        if 1 in expressions:
            return " 😢"
        if 0 in expressions:
            return " 😐"
        return ""


# ═══════════════════════════════════════════════════════════════
# Chat Bar Widget
# ═══════════════════════════════════════════════════════════════
class ChatBar(QFrame):
    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setVisible(False)
        self.setFixedSize(210, 30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 3, 3)
        layout.setSpacing(4)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("说点什么...")
        self._input.setFont(QFont("Microsoft YaHei", 8))
        self._input.setMaxLength(500)
        self._input.returnPressed.connect(self._send)
        self._input.setStyleSheet(
            """
            QLineEdit {
                background: transparent;
                border: none;
                color: #f0e6ff;
                padding: 1px;
            }
            """
        )
        layout.addWidget(self._input)

        send_btn = QPushButton("发送", self)
        send_btn.setFont(QFont("Microsoft YaHei", 8, QFont.Bold))
        send_btn.clicked.connect(self._send)
        send_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 150, 180, 60);
                color: #ffaacc;
                border: none;
                border-radius: 10px;
                padding: 2px 8px;
            }
            QPushButton:hover { background: rgba(255, 150, 180, 110); }
            """
        )
        layout.addWidget(send_btn)

        self.setStyleSheet(
            """
            ChatBar {
                background: rgba(30, 30, 40, 230);
                border: 1px solid rgba(255, 150, 180, 100);
                border-radius: 15px;
            }
            """
        )

    def show_bar(self):
        self.show()
        self.raise_()
        self._input.setFocus()

    def hide_bar(self):
        self.hide()

    def toggle(self):
        self.hide_bar() if self.isVisible() else self.show_bar()

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        self.message_submitted.emit(text)
        self._input.clear()
        self.hide_bar()


# ═══════════════════════════════════════════════════════════════
# Main Pet Window
# ═══════════════════════════════════════════════════════════════
class PetWindow(QWidget):
    activate_chat_requested = Signal()
    ollama_models_loaded = Signal(list)

    def __init__(self):
        super().__init__()
        self._click_through = False
        self._drag_pos: QPoint | None = None
        self._current_model = "qwen2.5:3b"
        self._cached_ollama: list[dict[str, Any]] = []
        self._chatbar_discovery_shown = False
        self._last_chat_text = ""
        self._hotkey_handle: Any = None
        self._hotkey_listener: Any = None
        self._backend_process: subprocess.Popen[Any] | None = None

        self.activate_chat_requested.connect(self._activate_chat)
        self.ollama_models_loaded.connect(self._rebuild_tray_menu)

        self._setup_window()
        self._setup_webview()
        self._setup_overlays()
        self._setup_tray()
        self._position_window()

    # ── Window setup ─────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle("喵酱 Live2D Pet")
        self.setFixedSize(PET_WIDTH, PET_HEIGHT)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")

    # ── WebView ──────────────────────────────────────────
    def _setup_webview(self):
        self._webview = QWebEngineView(self)
        self._webview.setGeometry(0, 0, PET_WIDTH, PET_HEIGHT)
        self._webview.setAttribute(Qt.WA_TranslucentBackground)
        self._webview.setStyleSheet("background: transparent;")

        profile = self._webview.page().profile()
        profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)

        self._webview.page().setBackgroundColor(Qt.transparent)
        self._webview.setZoomFactor(ZOOM_FACTOR)
        self._webview.installEventFilter(self)
        self._webview.page().javaScriptConsoleMessage = self._on_js_console
        self._webview.loadFinished.connect(self._on_page_loaded)
        self._webview.load(QUrl(BACKEND_URL))

    def _on_page_loaded(self, ok: bool):
        if not ok:
            LOG.warning("Page failed to load: %s", BACKEND_URL)
            return
        self._inject_js()
        self._inject_transparent_css()

        if not self._chatbar_discovery_shown:
            self._chatbar_discovery_shown = True
            QTimer.singleShot(1_000, self._chatbar.show_bar)

    # ── JS injection ─────────────────────────────────────
    def _inject_js(self):
        """Inject WebSocket interceptor + bridge into the page context."""
        self._webview.page().runJavaScript(
            r"""
            (function() {
                if (window.__petInjected) return;
                window.__petInjected = true;

                const OrigWebSocket = window.WebSocket;
                const wsInstances = [];

                function _isSystemMessage(text) {
                    if (!text || text.length < 4) return true;
                    const sysPatterns = [
                        'Thinking...', 'Connection established',
                        'AI wants to speak',
                        '已连接', '连接成功', '会话开始', '会话已开始',
                        '对话已开始', '新对话已开始', '对话开始',
                        '正在思考', '思考中', '正在加载', '加载中',
                        'Connecting', 'Connected', 'Established',
                        '模型加载', '模型切换',
                        'WebSocket', '已断开', '连接断开',
                        'Loading', 'Idle', '空闲'
                    ];
                    const lower = text.toLowerCase();
                    for (const p of sysPatterns) {
                        if (text.includes(p) || lower.includes(p.toLowerCase())) return true;
                    }
                    return false;
                }

                function _bridgeResponse(event) {
                    try {
                        if (event && event.data) {
                            const data = JSON.parse(event.data);
                            if (data.type === 'audio' && data.display_text && data.display_text.text) {
                                const text = data.display_text.text;
                                if (_isSystemMessage(text)) return;
                                const expressions = (data.actions && data.actions.expressions) || [];
                                console.log('[PetBridge]' + JSON.stringify({
                                    type: 'response',
                                    text: text,
                                    expressions: expressions
                                }));
                            }
                            if (data.type === 'full-text' && data.text) {
                                if (_isSystemMessage(data.text)) return;
                                console.log('[PetBridge]' + JSON.stringify({
                                    type: 'response',
                                    text: data.text,
                                    expressions: []
                                }));
                            }
                        }
                    } catch(e) {}
                }

                window.WebSocket = function(url, protocols) {
                    const ws = new OrigWebSocket(url, protocols);
                    wsInstances.push(ws);

                    const origAddEventListener = ws.addEventListener.bind(ws);
                    ws.addEventListener = function(type, handler, options) {
                        if (type === 'message') {
                            const wrapped = function(event) {
                                _bridgeResponse(event);
                                if (typeof handler === 'function') handler.call(this, event);
                                else if (handler && handler.handleEvent) handler.handleEvent(event);
                            };
                            origAddEventListener(type, wrapped, options);
                        } else {
                            origAddEventListener(type, handler, options);
                        }
                    };

                    let _onmessage = null;
                    Object.defineProperty(ws, 'onmessage', {
                        get: function() { return _onmessage; },
                        set: function(handler) {
                            _onmessage = handler;
                            origAddEventListener('message', function(event) {
                                _bridgeResponse(event);
                                if (typeof _onmessage === 'function') _onmessage.call(ws, event);
                            });
                        },
                        configurable: true
                    });

                    ws.addEventListener('close', function() {
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

                function _openClientSocket() {
                    for (const ws of wsInstances) {
                        if (ws.readyState !== OrigWebSocket.OPEN) continue;
                        const url = ws.url || '';
                        if (url.includes('/client-ws') ||
                            url.includes('localhost:12393') ||
                            url.includes('127.0.0.1:12393')) {
                            return ws;
                        }
                    }
                    return null;
                }

                window.__petSendMessage = function(text) {
                    const ws = _openClientSocket();
                    if (ws) {
                        ws.send(JSON.stringify({type: 'text-input', text: text}));
                        return 'ws-ok';
                    }
                    const urls = wsInstances.map(function(ws) {
                        return (ws.url || 'unknown') + ' state=' + ws.readyState;
                    });
                    console.log('[Pet] Send failed. WS instances: ' +
                        (urls.length || 'none') + ' ' + urls.join(', '));
                    return 'ws-closed';
                };

                window.__petSendDomFallback = function(text) {
                    const selectors = ['textarea','input[type="text"]','input:not([type])',
                        '[class*="chat"] input','[class*="Chat"] textarea',
                        '#message-input','.chat-input input'];
                    let inp = null;
                    for (let i = 0; i < selectors.length; i++) {
                        const el = document.querySelector(selectors[i]);
                        if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) { inp = el; break; }
                        }
                    }
                    if (!inp) return;

                    const proto = inp.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    const d = Object.getOwnPropertyDescriptor(proto, 'value');
                    if (d && d.set) d.set.call(inp, text);
                    else inp.value = text;
                    inp.dispatchEvent(new Event('input', {bubbles: true}));

                    const btns = document.querySelectorAll('button');
                    for (let j = 0; j < btns.length; j++) {
                        if (btns[j].getBoundingClientRect().width > 0 &&
                            (btns[j].type === 'submit' || /send|Send|发送/i.test(btns[j].textContent || ''))) {
                            setTimeout(function(b) { b.click(); }, 50, btns[j]);
                            return;
                        }
                    }
                    inp.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                    }));
                };

                window.__petSendWsRaw = function(msg) {
                    const ws = _openClientSocket();
                    if (!ws) return 'ws-closed';
                    ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
                    return 'ws-ok';
                };

                console.log('[Pet] JS interceptor active');
            })();
            """
        )

    def _inject_transparent_css(self):
        """Hide all React UI — only the Live2D canvas and its ancestors survive."""
        self._webview.page().runJavaScript(
            r"""
            (function() {
                if (document.getElementById('__pet_css')) return;
                const s = document.createElement('style');
                s.id = '__pet_css';
                s.textContent = [
                    'html, body, #root, #__next, [id*="root"]',
                    '{ background: transparent !important; background-color: transparent !important; }',
                    'body',
                    '{ display: flex !important; justify-content: center !important;',
                    '  align-items: center !important; overflow: hidden !important; }',
                    '* { box-shadow: none !important; }',
                    'canvas',
                    '{ display: block !important; visibility: visible !important; opacity: 1 !important; }'
                ].join('\n');
                document.head.appendChild(s);

                setTimeout(function() {
                    const canvases = document.querySelectorAll('canvas');
                    const protectedNodes = new WeakSet();
                    for (let c = 0; c < canvases.length; c++) {
                        let node = canvases[c];
                        while (node) {
                            protectedNodes.add(node);
                            node = node.parentElement;
                        }
                    }
                    function walkAndHide(parent) {
                        const kids = parent.children;
                        for (let i = kids.length - 1; i >= 0; i--) {
                            const el = kids[i];
                            const tag = el.tagName;
                            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK') continue;
                            if (el.id === '__pet_css') continue;
                            if (protectedNodes.has(el)) walkAndHide(el);
                            else el.style.setProperty('display', 'none', 'important');
                        }
                    }
                    walkAndHide(document.body);
                    console.log('[Pet] UI cleanup done, protected ' + canvases.length + ' canvas(es)');
                }, 3000);

                console.log('[Pet] Transparent CSS injected');
            })();
            """
        )

    # ── JS Console Bridge ────────────────────────────────
    def _on_js_console(self, level: Any, message: str, line: int, source: str):
        if not message.startswith("[PetBridge]"):
            return
        try:
            data = json.loads(message[len("[PetBridge]") :])
        except json.JSONDecodeError:
            LOG.debug("Bad PetBridge payload at %s:%s: %s", source, line, message)
            return

        if data.get("type") == "response":
            text = data.get("text", "")
            expressions = data.get("expressions", [])
            self._bubble.show_text(text, expressions)

    # ── Overlay widgets ──────────────────────────────────
    def _setup_overlays(self):
        self._bubble = SpeechBubble(self)
        self._chatbar = ChatBar(self)
        self._chatbar.message_submitted.connect(self._on_chat_submit)
        self._reposition_overlays()

    def _reposition_overlays(self):
        w, h = self.width(), self.height()
        self._bubble.move((w - self._bubble.width()) // 2, 50)
        self._chatbar.move((w - self._chatbar.width()) // 2, h - 100)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._webview.setGeometry(0, 0, self.width(), self.height())
        self._reposition_overlays()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposition_overlays()

    # ── Chat ─────────────────────────────────────────────
    def _on_chat_submit(self, text: str):
        self.show()
        self.raise_()
        self._last_chat_text = text
        self._webview.page().runJavaScript(
            f"window.__petSendMessage({json.dumps(text)});",
            self._on_send_result,
        )

    def _on_send_result(self, result: Any):
        if result in ("ws-ok", None):
            return
        LOG.info("WS send result: %s, trying DOM fallback", result)
        self._webview.page().runJavaScript(
            f"window.__petSendDomFallback({json.dumps(self._last_chat_text)});"
        )

    # ── System tray ──────────────────────────────────────
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("喵酱 Live2D Desktop Pet")
        self._tray.setIcon(self._make_tray_icon())
        self._tray.activated.connect(self._on_tray_activated)
        self._rebuild_tray_menu()
        self._tray.show()
        self._refresh_ollama_models()

    def _make_tray_icon(self) -> QIcon:
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#ff99bb"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 4, 12, 10)

        left_ear = QPainterPath()
        left_ear.moveTo(3, 5)
        left_ear.lineTo(5, 0)
        left_ear.lineTo(7, 5)
        painter.drawPath(left_ear)

        right_ear = QPainterPath()
        right_ear.moveTo(13, 5)
        right_ear.lineTo(11, 0)
        right_ear.lineTo(9, 5)
        painter.drawPath(right_ear)

        painter.setBrush(QColor("#1a1a2e"))
        painter.drawEllipse(5, 6, 2, 2)
        painter.drawEllipse(10, 6, 2, 2)

        painter.setPen(QPen(QColor("#1a1a2e"), 0.5))
        painter.drawLine(7, 11, 8, 11)
        painter.end()
        return QIcon(pix)

    def _make_action(self, text: str, callback) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        return action

    def _rebuild_tray_menu(self, cached_models: list[dict[str, Any]] | None = None):
        models = cached_models if cached_models is not None else self._cached_ollama
        if cached_models is not None:
            self._cached_ollama = cached_models

        menu = QMenu(self)
        menu.addAction(self._make_action("💬 快捷聊天", self._chatbar.toggle))
        menu.addAction(self._make_action("👁 显示/隐藏 喵酱", self._toggle_visible))

        menu.addSeparator()
        menu.addAction(self._make_action("📝 新对话", self._reload_page))

        model_menu = menu.addMenu("🤖 切换模型")
        for action in self._model_actions(models):
            model_menu.addAction(action)

        l2d_menu = menu.addMenu("🎭 切换 Live2D 模型")
        for model_id in self._discover_l2d_models():
            l2d_menu.addAction(self._make_action(model_id, lambda _=False, mid=model_id: self._switch_l2d(mid)))

        menu.addSeparator()
        ct_label = f"🖱 点击穿透: {'开' if self._click_through else '关'}"
        menu.addAction(self._make_action(ct_label, self._toggle_click_through))

        menu.addSeparator()
        menu.addAction(self._make_action("🔄 重新加载", self._reload_page))
        menu.addAction(self._make_action("♻ 重启后端", self._restart_backend))
        menu.addAction(self._make_action("❌ 退出", self._quit))

        self._tray.setContextMenu(menu)

    def _model_actions(self, models: list[dict[str, Any]]) -> list[QAction]:
        actions: list[QAction] = []
        if models:
            for model in models:
                model_id = model.get("name") or model.get("id") or ""
                if not model_id:
                    continue
                mark = " ✓" if model_id == self._current_model else ""
                actions.append(self._make_action(f"{model_id}{mark}", lambda _=False, mid=model_id: self._switch_model(mid)))
            return actions

        for model in AVAILABLE_MODELS:
            mark = " ✓" if model["id"] == self._current_model else ""
            actions.append(
                self._make_action(
                    f"{model['emoji']} {model['name']}{mark}",
                    lambda _=False, mid=model["id"]: self._switch_model(mid),
                )
            )
        return actions

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visible()

    def _refresh_ollama_models(self):
        def fetch():
            try:
                data = request_json(f"{OLLAMA_URL}/api/tags")
                models = data.get("models", [])
                if not isinstance(models, list):
                    models = []
            except Exception as exc:
                LOG.info("Failed to refresh Ollama model list: %s", exc)
                models = self._cached_ollama
            self.ollama_models_loaded.emit(models)

        threading.Thread(target=fetch, name="ollama-model-refresh", daemon=True).start()

    # ── Actions ──────────────────────────────────────────
    def _reload_page(self):
        self._webview.reload()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
            return
        self.show()
        self.raise_()

    def _toggle_click_through(self):
        self._click_through = not self._click_through
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._click_through)
        self._rebuild_tray_menu()
        LOG.info("Click-through: %s", "ON" if self._click_through else "OFF")

    def _switch_model(self, model_id: str):
        LOG.info("Switching LLM model to: %s", model_id)
        self._current_model = model_id

        if update_ollama_model_in_conf(CONF_PATH, model_id):
            LOG.info("conf.yaml updated: model=%s", model_id)
            self._webview.reload()
        else:
            LOG.warning("Model state updated in UI, but conf.yaml was not changed")

        self._rebuild_tray_menu()

    def _discover_l2d_models(self) -> list[str]:
        """Scan live2d-models directory and return available model folder names."""
        l2d_dir = LIVE2D_MODELS_DIR
        if not l2d_dir.is_dir():
            return ["mao_pro"]
        models = []
        for d in sorted(l2d_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            # Must have a character config YAML
            if not (CHARACTERS_DIR / f"{d.name}.yaml").exists():
                continue
            has_model = any(d.rglob("*.model3.json")) or any(d.rglob("*.model.json"))
            if not has_model:
                continue
            has_texture = any(d.rglob("*.png"))
            if not has_texture:
                continue
            models.append(d.name)
        return models if models else ["mao_pro"]

    def _switch_l2d(self, model_id: str):
        config_file = f"{model_id}.yaml"
        char_path = CHARACTERS_DIR / config_file
        if not char_path.exists():
            LOG.warning("Character config not found for: %s", model_id)
            return

        LOG.info("Switching Live2D model to: %s", model_id)
        payload = {"type": "switch-config", "file": config_file}
        code = f"window.__petSendWsRaw({json.dumps(payload)});"
        self._webview.page().runJavaScript(code, lambda result: LOG.info("L2D switch: %s", result))

    def _restart_backend(self):
        LOG.info("Restarting backend...")
        self._stop_known_backend_processes()
        if not self._start_backend():
            return
        self._poll_backend()

    def _stop_known_backend_processes(self):
        if self._backend_process and self._backend_process.poll() is None:
            self._backend_process.terminate()
            try:
                self._backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._backend_process.kill()
            self._backend_process = None
            return

        # Optional best-effort cleanup: only kill processes whose command line
        # clearly points at this app's run_server.py. Never kill arbitrary python.exe.
        try:
            import psutil  # type: ignore
        except Exception:
            LOG.info("psutil not available; skipping external backend process cleanup")
            return

        target = str((OPEN_LLM_VTUBER_DIR / "run_server.py").resolve())
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(proc.info.get("cmdline") or [])
                if target in cmdline or ("run_server.py" in cmdline and str(OPEN_LLM_VTUBER_DIR) in cmdline):
                    proc.terminate()
            except Exception:
                continue

    def _start_backend(self) -> bool:
        if not OPEN_LLM_VTUBER_DIR.exists():
            LOG.error("Backend directory not found: %s", OPEN_LLM_VTUBER_DIR)
            return False

        env = os.environ.copy()
        env["NO_PROXY"] = "localhost,127.0.0.1,::1,.local"
        env["no_proxy"] = "localhost,127.0.0.1,::1,.local"

        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)

        try:
            self._backend_process = subprocess.Popen(
                ["uv", "run", "run_server.py"],
                cwd=str(OPEN_LLM_VTUBER_DIR),
                env=env,
                creationflags=creationflags,
            )
        except FileNotFoundError:
            LOG.error("Failed to start backend: `uv` is not in PATH")
            return False
        except Exception as exc:
            LOG.error("Failed to start backend: %s", exc)
            return False

        LOG.info("Backend starting...")
        return True

    def _poll_backend(self, attempts: int = 0):
        if attempts > BACKEND_READY_MAX_ATTEMPTS:
            LOG.warning("Backend startup timed out")
            return

        try:
            req = urllib.request.Request(BACKEND_URL, headers={"User-Agent": "Pet/1.0"})
            urllib.request.urlopen(req, timeout=2).close()
        except Exception:
            QTimer.singleShot(BACKEND_READY_INTERVAL_MS, lambda: self._poll_backend(attempts + 1))
            return

        LOG.info("Backend ready, reloading...")
        self._webview.reload()

    def _quit(self):
        self._cleanup_hotkeys()
        self._tray.hide()
        QApplication.quit()

    # ── Window dragging ──────────────────────────────────
    def eventFilter(self, obj: Any, event: QEvent) -> bool:
        if obj is self._webview:
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                elif event.button() == Qt.RightButton:
                    tray = getattr(self, "_tray", None)
                    if tray and tray.contextMenu():
                        tray.contextMenu().popup(event.globalPosition().toPoint())
                    return True
            elif event.type() == QEvent.MouseMove and self._drag_pos is not None:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._drag_pos = None
        return super().eventFilter(obj, event)

    # ── Global hotkeys ───────────────────────────────────
    def _setup_hotkeys(self):
        try:
            import keyboard  # type: ignore

            self._hotkey_handle = keyboard.add_hotkey(
                "ctrl+shift+space",
                lambda: self.activate_chat_requested.emit(),
            )
            self._keyboard_module = keyboard
            LOG.info("Global hotkeys active via keyboard (Ctrl+Shift+Space)")
        except ImportError:
            LOG.info("keyboard not installed; trying pynput")
            self._setup_hotkeys_pynput()
        except Exception as exc:
            LOG.warning("Hotkey setup via keyboard failed: %s", exc)
            self._setup_hotkeys_pynput()

    def _setup_hotkeys_pynput(self):
        try:
            from pynput import keyboard as pkb  # type: ignore

            state = {"ctrl": False, "shift": False}

            def on_press(key):
                if key in (pkb.Key.ctrl_l, pkb.Key.ctrl_r):
                    state["ctrl"] = True
                elif key in (pkb.Key.shift_l, pkb.Key.shift_r):
                    state["shift"] = True
                elif key == pkb.Key.space and state["ctrl"] and state["shift"]:
                    self.activate_chat_requested.emit()

            def on_release(key):
                if key in (pkb.Key.ctrl_l, pkb.Key.ctrl_r):
                    state["ctrl"] = False
                elif key in (pkb.Key.shift_l, pkb.Key.shift_r):
                    state["shift"] = False

            self._hotkey_listener = pkb.Listener(on_press=on_press, on_release=on_release)
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            LOG.info("Global hotkeys active via pynput (Ctrl+Shift+Space)")
        except Exception as exc:
            LOG.warning("All hotkey methods failed: %s", exc)

    def _cleanup_hotkeys(self):
        keyboard_module = getattr(self, "_keyboard_module", None)
        if keyboard_module and self._hotkey_handle is not None:
            try:
                keyboard_module.remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
        if self._hotkey_listener is not None:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass

    def _activate_chat(self):
        self.show()
        self.raise_()
        self._chatbar.show_bar()

    # ── Window positioning ───────────────────────────────
    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x = geo.right() - PET_WIDTH - 30
        y = geo.bottom() - PET_HEIGHT - 30
        self.move(x, y)
        LOG.info("Window at %s, %s", x, y)


# ═══════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════
def main():
    logging.basicConfig(level=logging.INFO, format="[Pet] %(message)s")

    if sys.platform == "win32":
        QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pet = PetWindow()
    pet.show()
    QTimer.singleShot(500, pet._setup_hotkeys)

    LOG.info("========================================")
    LOG.info(" 喵酱 Live2D Desktop Pet Ready!")
    LOG.info(" Ctrl+Shift+Space = Quick Chat")
    LOG.info(" Right-click tray  = Full menu")
    LOG.info("========================================")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
