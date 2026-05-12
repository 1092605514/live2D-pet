#!/usr/bin/env python3
"""
喵酱 Live2D Desktop Pet — PySide6 + QWebEngineView
QQ宠物-style virtual pet raising system with Live2D rendering.
"""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ── Qt imports ──────────────────────────────────────────────
from PySide6.QtCore import (
    Qt, QUrl, QTimer, QRect, QPoint, Signal, Slot,
    QPropertyAnimation, QEasingCurve, QEvent,
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QFont, QAction,
    QBrush, QPen, QPainterPath, QPalette, QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QLabel,
    QSystemTrayIcon, QMenu, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QSlider,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineScript

# ── pet-core ───────────────────────────────────────────────
from pet_core import (
    PetState,
    PetBehavior,
    tick_pet,
    feed,
    clean,
    pet_action,
    sleep_action,
    BEHAVIOR_MESSAGE,
    BehaviorPlanner,
    PetPersistence,
    MotionAdapter,
    prepare_tts_text,
    check_level_up,
    time_of_day_context,
    absence_greeting,
)

# ── TTS ────────────────────────────────────────────────────
from tts import MiMoTTS

# ── Configuration ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OPEN_LLM_VTUBER_DIR = BASE_DIR.parent / "Open-LLM-VTuber"
CHARACTERS_DIR = OPEN_LLM_VTUBER_DIR / "characters"

def _load_settings() -> dict:
    settings_path = BASE_DIR / "config" / "settings.json"
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_settings = _load_settings()

BACKEND_URL = _settings.get("backend_url", "http://localhost:12393")
WS_URL = BACKEND_URL.replace("http://", "ws://") + "/client-ws"
OLLAMA_URL = "http://localhost:11434"
PET_WIDTH = _settings.get("window_width", 280)
PET_HEIGHT = _settings.get("window_height", 420)
ZOOM_FACTOR = 1.5  # Scale up the web content to make character larger

AVAILABLE_MODELS = [
    {"id": "qwen2.5:3b", "name": "Qwen 2.5 3B", "emoji": "🐱"},
    {"id": "qwen2.5:1.5b", "name": "Qwen 2.5 1.5B", "emoji": "⚡"},
    {"id": "llama3.2:1b", "name": "Llama 3.2 1B", "emoji": "🦙"},
]

# ═══════════════════════════════════════════════════════════════
# Emoji / emotion tag patterns to strip from LLM text (e.g. [neutral], [:joy])
_CLS_EMOJI_TAGS = re.compile(r'\[:?\w+\]')

# Scale Bar Widget
# ═══════════════════════════════════════════════════════════════
class ScaleBar(QFrame):
    """Draggable slider + numeric input for precise model scale control."""

    SCALE_MIN = 30   # 30%
    SCALE_MAX = 300  # 300%

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)
        self.setVisible(False)
        self.setFixedSize(280, 60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Slider: 30-300 → 30%-300%
        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setRange(self.SCALE_MIN, self.SCALE_MAX)
        self._slider.setValue(100)
        self._slider.valueChanged.connect(self._on_slider_changed)

        # Editable numeric input
        self._spinbox = QLineEdit(self)
        self._spinbox.setFixedWidth(55)
        self._spinbox.setAlignment(Qt.AlignCenter)
        self._spinbox.setFont(QFont("Courier New", 12))
        self._spinbox.setStyleSheet("color: #ffffff; background: rgba(0,0,0,120); border: 1px solid #888; border-radius: 4px; padding: 2px;")
        self._spinbox.setToolTip("输入百分比后按回车确认")
        self._spinbox.returnPressed.connect(self._apply_from_input)

        # Apply button
        btn = QPushButton("✓", self)
        btn.setFixedSize(28, 28)
        btn.setStyleSheet("color: #fff; background: rgba(80,180,120,180); border-radius: 14px; font-weight: bold;")
        btn.setToolTip("应用缩放")
        btn.clicked.connect(self._apply_from_input)

        layout.addWidget(self._slider)
        layout.addWidget(self._spinbox)
        layout.addWidget(btn)

        self._callback = None
        self._current_pct = 100

        self.setStyleSheet("""
            ScaleBar {
                background: rgba(20, 20, 35, 220);
                border: 1px solid rgba(150, 200, 255, 80);
                border-radius: 10px;
            }
        """)

        # Sync spinbox with slider (live update while dragging)
        self._slider.valueChanged.connect(
            lambda v: self._spinbox.setText(f"{v}%")
        )
        self._slider.sliderReleased.connect(self._apply_from_slider)
        self._spinbox.setText("100%")

    def set_callback(self, cb):
        self._callback = cb

    def set_scale_pct(self, pct: int):
        """Set scale from external source (e.g. saved config)."""
        pct = max(self.SCALE_MIN, min(self.SCALE_MAX, pct))
        self._current_pct = pct
        self._slider.blockSignals(True)
        self._slider.setValue(pct)
        self._slider.blockSignals(False)
        self._spinbox.setText(f"{pct}%")

    def _on_slider_changed(self, value: int):
        self._spinbox.setText(f"{value}%")

    def _apply_from_slider(self):
        pct = self._slider.value()
        self._current_pct = pct
        if self._callback:
            self._callback(pct / 100.0)

    def _apply_from_input(self):
        txt = self._spinbox.text().replace("%", "").strip()
        try:
            pct = int(txt)
            pct = max(self.SCALE_MIN, min(self.SCALE_MAX, pct))
        except ValueError:
            pct = 100
        self._current_pct = pct
        self._slider.blockSignals(True)
        self._slider.setValue(pct)
        self._slider.blockSignals(False)
        self._spinbox.setText(f"{pct}%")
        if self._callback:
            self._callback(pct / 100.0)

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()


# Speech Bubble Widget
# ═══════════════════════════════════════════════════════════════
class SpeechBubble(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)  # Render above QWebEngineView
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Never block clicks
        self.setVisible(False)
        self.setMinimumSize(60, 28)
        self.setMaximumWidth(260)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setFont(QFont("Microsoft YaHei", 9))
        self._label.setStyleSheet("color: #f0e6ff; padding: 5px 7px;")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_bubble)

        # Sequential display: rapid-fire messages are queued & shown with delay
        self._seq_timer = QTimer(self)
        self._seq_timer.setSingleShot(True)
        self._seq_timer.timeout.connect(self._dequeue_and_show)
        self._display_queue: list[str] = []
        self._showing = False

        # Style
        self.setStyleSheet("""
            SpeechBubble {
                background: rgba(30, 30, 45, 230);
                border: 1px solid rgba(255, 150, 180, 100);
                border-radius: 14px;
            }
        """)

    def _format_text(self, text: str, expressions: list) -> str:
        """Clean text and append expression emoji."""
        emoji = (
            " 😸" if 3 in expressions else
            " 😠" if 2 in expressions else
            " 😢" if 1 in expressions else
            " 😐" if 0 in expressions else
            ""
        )
        return (_CLS_EMOJI_TAGS.sub('', text).strip() + emoji)

    def show_text(self, text: str, expressions: Optional[list] = None):
        """Queue text for display. Multiple rapid calls are shown sequentially."""
        display = self._format_text(text, expressions or [])
        if not display:
            return

        self._display_queue.append(display)

        if not self._showing:
            # Not in a sequence → start showing immediately
            self._dequeue_and_show()
        elif not self._seq_timer.isActive():
            # Already showing but next-item timer hasn't been armed yet → arm it
            self._seq_timer.start(3000)

    def _dequeue_and_show(self):
        """Show the next item from the queue."""
        if not self._display_queue:
            self._showing = False
            return

        self._showing = True
        display = self._display_queue.pop(0)
        self._render(display)

        if self._display_queue:
            # More items pending — show next after 3s, keep bubble open
            self._seq_timer.start(3000)
        else:
            # Last item — start auto-hide
            self._timer.start(7000)

    def _render(self, display: str):
        """Render text in the bubble with proper size for word-wrapped content."""
        self._label.setText(display)

        text_len = len(display)
        if text_len <= 8:
            bw = 120
        elif text_len <= 15:
            bw = 170
        elif text_len <= 30:
            bw = 220
        else:
            bw = 260
        self.setFixedWidth(bw)
        self._label.setFixedWidth(bw - 14)

        # Proper height via font metrics (word-wrap aware)
        metrics = self._label.fontMetrics()
        rect = metrics.boundingRect(0, 0, bw - 14, 0, Qt.AlignLeft | Qt.TextWordWrap, display)
        self.setFixedHeight(max(28, rect.height() + 20))

        self.setVisible(True)

    def hide_bubble(self):
        self.setVisible(False)
        self._seq_timer.stop()
        self._display_queue.clear()
        self._showing = False


# ═══════════════════════════════════════════════════════════════
# Chat Bar Widget
# ═══════════════════════════════════════════════════════════════
class ChatBar(QFrame):
    message_submitted = Signal(str)
    quick_action = Signal(str, str)  # action_type, action_value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow)  # Render above QWebEngineView
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Transparent when hidden
        self.setVisible(False)
        self.setFixedSize(400, 36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(3)

        # ── Quick-action buttons ──
        quick_btns = [
            ("😊", "expression", "happy", "开心"),
            ("😢", "expression", "sad", "难过"),
            ("👋", "action", "wave", "挥手"),
            ("🔄", "action", "spin", "转圈"),
        ]
        btn_style = """
            QPushButton {
                background: rgba(255, 150, 180, 40); color: #ffaacc;
                border: none; border-radius: 12px; padding: 2px 6px;
                font-size: 13px; min-width: 32px;
            }
            QPushButton:hover { background: rgba(255, 150, 180, 100); }
        """
        for emoji, atype, aval, tip in quick_btns:
            btn = QPushButton(emoji, self)
            btn.setToolTip(tip)
            btn.setFont(QFont("Segoe UI Emoji", 10))
            btn.setStyleSheet(btn_style)
            btn.setFixedSize(30, 26)
            btn.clicked.connect(lambda checked, t=atype, v=aval: self.quick_action.emit(t, v))
            layout.addWidget(btn)

        self._input = QLineEdit(self)
        self._input.setPlaceholderText("说点什么...")
        self._input.setFont(QFont("Microsoft YaHei", 8))
        self._input.setStyleSheet("""
            QLineEdit {
                background: transparent; border: none; color: #f0e6ff;
                padding: 1px;
            }
        """)
        self._input.setMaxLength(500)
        self._input.returnPressed.connect(self._send)
        layout.addWidget(self._input)

        send_btn = QPushButton("发送", self)
        send_btn.setFont(QFont("Microsoft YaHei", 8, QFont.Bold))
        send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 150, 180, 60); color: #ffaacc;
                border: none; border-radius: 10px; padding: 2px 8px;
            }
            QPushButton:hover { background: rgba(255, 150, 180, 110); }
        """)
        send_btn.clicked.connect(self._send)
        layout.addWidget(send_btn)

        self.setStyleSheet("""
            ChatBar {
                background: rgba(30, 30, 40, 230);
                border: 1px solid rgba(255, 150, 180, 100);
                border-radius: 15px;
            }
        """)

    def show_bar(self):
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # Allow typing
        self.setVisible(True)
        self._input.setFocus()

    def hide_bar(self):
        self.setVisible(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # Pass clicks through

    def toggle(self):
        if self.isVisible():
            self.hide_bar()
        else:
            self.show_bar()

    def _send(self):
        text = self._input.text().strip()
        if text:
            self.message_submitted.emit(text)
            self._input.clear()
            self.hide_bar()


# ═══════════════════════════════════════════════════════════════
# Command Log Panel — popup dialog showing last 20 AI commands
# ═══════════════════════════════════════════════════════════════
class CommandLogPanel(QFrame):
    """Floating popup showing the last N AI commands received."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 指令日志")
        self.setFixedSize(380, 320)
        self.setStyleSheet("""
            CommandLogPanel {
                background: rgba(30, 30, 45, 240);
                border: 1px solid rgba(255, 150, 180, 100);
                border-radius: 12px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self._log_area = QLabel(self)
        self._log_area.setWordWrap(True)
        self._log_area.setFont(QFont("Consolas", 8))
        self._log_area.setStyleSheet("color: #e0d0f0;")
        self._log_area.setAlignment(Qt.AlignTop)
        layout.addWidget(self._log_area)

        # Close button (top-right corner)
        self._close_btn = QPushButton("×", self)
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ff99bb;
                border: none; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { color: #ffb3cc; }
        """)
        self._close_btn.clicked.connect(self.hide)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._close_btn.move(self.width() - 28, 2)

    def update_log(self, entries: list[str]):
        text = "\n".join(entries) if entries else "(暂无指令)"
        self._log_area.setText(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

# ═══════════════════════════════════════════════════════════════
# Custom WebEngine Page — proper javaScriptConsoleMessage override
# ═══════════════════════════════════════════════════════════════
class PetWebEnginePage(QWebEnginePage):
    """Properly overrides javaScriptConsoleMessage for reliable JS→Python bridge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge_callback = None

    def set_bridge_callback(self, callback):
        self._bridge_callback = callback

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        if self._bridge_callback:
            self._bridge_callback(level, message, lineNumber, sourceID)


# ═══════════════════════════════════════════════════════════════
# Main Pet Window
# ═══════════════════════════════════════════════════════════════
class PetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._click_through = False
        self._drag_pos = None  # Optional[QPoint]
        self._current_model = "qwen2.5:3b"
        self._current_l2d = "mao_pro"

        # ── Live2D model switch state ──
        self._pending_l2d_switch: str | None = None
        self._pending_model_info: dict | None = None
        self._l2d_needs_manual_apply = False
        self._l2d_switch_timer = QTimer(self)
        self._l2d_switch_timer.setSingleShot(True)
        self._l2d_switch_timer.timeout.connect(self._on_l2d_switch_timeout)

        # ── pet-core: state machine + behavior ──
        self._persistence = PetPersistence()
        self._pet_state = self._persistence.load()
        print(f"[Pet] State loaded: hunger={self._pet_state.hunger:.0f} "
              f"clean={self._pet_state.cleanliness:.0f} "
              f"mood={self._pet_state.mood:.0f} "
              f"level={self._pet_state.level}")

        self._planner = BehaviorPlanner()
        self._motion_adapter = MotionAdapter()
        from pet_core.expression_catalog import ExpressionCatalog
        from pet_core.motion_catalog import MotionCatalog
        _actions_path = BASE_DIR / "config" / "pet_actions.json"
        self._expr_catalog = ExpressionCatalog.from_config(_actions_path)
        self._motion_catalog = MotionCatalog.from_config(_actions_path)
        self._allowed_actions = frozenset(self._motion_catalog.all_actions)
        self._allowed_expressions = frozenset(self._expr_catalog.all_names)
        self._tts = MiMoTTS(
            voice=_settings.get("tts_voice", "冰糖"),
            speed=_settings.get("tts_speed", 1.0),
        )
        self._audio_buffer: list[dict] = []
        self._audio_flush_timer: QTimer | None = None
        self._audio_flush_timeout = _settings.get("audio_flush_timeout_ms", 3000)
        self._full_text_received: str | None = None
        self._conversation_active = False
        self._llm_active_until: float = 0.0
        self._last_behavior_time: float = 0.0
        self._cmd_cooldowns: dict[str, float] = {}
        self._cmd_cooldown_sec = _settings.get("command_cooldown_sec", 3.0)
        self._cmd_queue: list = []
        self._cmd_log: list[str] = []  # last 20 AI commands for F2 log panel
        self._cmd_log_panel = None
        self._hotkey_actions: dict[int, object] = {}

        # ── Proactive AI chat ──
        self._proactive_enabled = _settings.get("proactive_enabled", True)
        self._last_interaction_time = time.time()
        self._proactive_interval = _settings.get("proactive_interval_sec", 90)
        self._last_proactive_time = 0.0
        self._tod_greeting_shown = False

        # ── Model scale per Live2D model ──
        self._model_scales: dict[str, float] = _settings.get("model_scales", {})
        self._model_scale_step = 0.1
        self._model_scale_min = 0.3
        self._model_scale_max = 3.0

        # ── Model position offsets per Live2D model ──
        self._model_offsets: dict[str, list[float]] = _settings.get("model_offsets", {})
        # Each entry: [offset_x, offset_y]

        # ── Heartbeat timer ──
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)
        self._heartbeat_timer.setInterval(_settings.get("heartbeat_interval_sec", 30) * 1000)
        self._heartbeat_timer.start()
        self._queue_timer = QTimer(self)
        self._queue_timer.timeout.connect(self._process_cmd_queue)
        self._queue_timer.setInterval(_settings.get("command_queue_interval_ms", 2500))

        # ── Pet tick timer: decay stats + re-evaluate behavior ──
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_pet_tick)
        self._tick_timer.setInterval(_settings.get("tick_interval_ms", 15000))
        self._tick_timer.start()

        # ── Auto-save timer ──
        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self._save_state)
        self._save_timer.setInterval(_settings.get("save_interval_ms", 60000))
        self._save_timer.start()

        # ── JS message poll timer (reliable bridge, no console.log needed) ──
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_js_messages)
        self._poll_timer.setInterval(_settings.get("poll_interval_ms", 300))
        self._poll_timer.start()

        # ── Delayed first tick to let the page load ──
        QTimer.singleShot(5000, self._on_pet_tick)

        self._setup_window()
        self._setup_webview()
        self._setup_overlays()
        self._setup_tray()
        self._position_window()
        # _setup_hotkeys() deferred until Qt event loop runs (see main())

    # ── Window setup ─────────────────────────────────────
    def _setup_window(self):
        self.setWindowTitle("喵酱 Live2D Pet")
        self.setFixedSize(PET_WIDTH, PET_HEIGHT)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")
        # Install event filter on self for dragging from anywhere
        self.installEventFilter(self)

    # ── WebView ──────────────────────────────────────────
    def _setup_webview(self):
        # Use custom page class for reliable console.log interception
        self._page = PetWebEnginePage(self)
        self._page.set_bridge_callback(self._on_js_console)
        self._page.setBackgroundColor(Qt.transparent)
        self._page.profile().setHttpCacheType(QWebEngineProfile.MemoryHttpCache)

        self._webview = QWebEngineView(self)
        self._webview.setPage(self._page)
        self._webview.setGeometry(0, 0, PET_WIDTH, PET_HEIGHT)
        self._webview.setAttribute(Qt.WA_TranslucentBackground)
        self._webview.setStyleSheet("background: transparent;")
        self._webview.setZoomFactor(ZOOM_FACTOR)
        # Register persistent scripts BEFORE loading the page.
        # QWebEngineScript.DocumentCreation runs before any page scripts,
        # so the WebSocket override is in place when React creates its WS.
        self._inject_js()
        self._inject_transparent_css()

        self._webview.load(QUrl(BACKEND_URL))

        # Install event filter so the frameless window is draggable through the WebView
        self._webview.installEventFilter(self)

        # Inject UI cleanup + transparent CSS after each page load
        self._webview.loadFinished.connect(self._on_page_loaded)

    def _on_page_loaded(self, ok: bool):
        if not ok:
            print("[Pet] Page failed to load")
            return
        print(f"[Pet] Page loaded: {self._webview.url().toString()[:80]}")
        # Apply saved scale — the JS side polls until the model is ready,
        # so we can call it immediately without waiting for React render.
        # This works even if Live2D model hasn't loaded yet.
        QTimer.singleShot(500, self._apply_saved_scale)

    # ── JS injection ─────────────────────────────────────
    def _inject_js(self):
        """Inject WebSocket interceptor + bridge into the page context.

        Uses QWebEngineScript at DocumentCreation to ensure the WebSocket
        monkey-patch runs BEFORE the React app creates its WS connection.
        """
        code = r"""
        (function() {
            if (window.__petInjected) return;
            window.__petInjected = true;

            const OrigWebSocket = window.WebSocket;
            const wsInstances = [];

            // ── Reliable message bridge: Python polls this array ──
            window.__petPendingMessages = [];
            window.__petDrainMessages = function() {
                if (window.__petPendingMessages.length === 0) return '[]';
                var msgs = window.__petPendingMessages.splice(0);
                try { return JSON.stringify(msgs); } catch(e) { return '[]'; }
            };

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
                    'Loading', 'Idle', '空闲',
                    'conversation-chain-start', 'conversation-chain-end',
                    'Conversation chain',
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
                        const msgType = data.type || 'unknown';
                        // Debug: log non-heartbeat messages
                        if (msgType !== 'heartbeat-ack' && msgType !== 'backend-synth-complete') {
                            console.log('[PetBridge]' + JSON.stringify({
                                type: 'debug',
                                wsType: msgType,
                                keys: Object.keys(data)
                            }));
                        }
                        // Capture audio display_text (LLM response with TTS)
                        if (msgType === 'audio' && data.display_text && data.display_text.text) {
                            const text = data.display_text.text;
                            if (_isSystemMessage(text)) return;
                            const expressions = (data.actions && data.actions.expressions) || [];
                            const msg = JSON.stringify({type: 'response', text: text, expressions: expressions});
                            console.log('[PetBridge]' + msg);
                            window.__petPendingMessages.push(JSON.parse(msg));
                        }
                        // Also catch full-text for non-TTS responses
                        if (msgType === 'full-text' && data.text) {
                            if (_isSystemMessage(data.text)) return;
                            const msg = JSON.stringify({type: 'response', text: data.text, expressions: []});
                            console.log('[PetBridge]' + msg);
                            window.__petPendingMessages.push(JSON.parse(msg));
                        }
                        // Catch-all: untagged response text (not audio/full-text)
                        if (msgType !== 'audio' && msgType !== 'full-text'
                            && msgType !== 'control' && msgType !== 'error'
                            && msgType !== 'config-switched' && msgType !== 'set-model-and-conf'
                            && msgType !== 'heartbeat-ack' && msgType !== 'backend-synth-complete') {
                            var _text = '';
                            if (data.text) _text = data.text;
                            else if (data.content) _text = data.content;
                            if (_text && !_isSystemMessage(_text)) {
                                const msg = JSON.stringify({type: 'response', text: _text, expressions: []});
                                console.log('[PetBridge]' + msg);
                                window.__petPendingMessages.push(JSON.parse(msg));
                            }
                        }

                        // Catch config-switched (Live2D model change done)
                        if (msgType === 'config-switched') {
                            console.log('[PetBridge]' + JSON.stringify({
                                type: 'config-switched',
                                message: data.message || ''
                            }));
                            window.__petPendingMessages.push({type: 'config-switched', message: data.message || ''});
                        }
                        // Capture set-model-and-conf (model switch info from backend)
                        if (msgType === 'set-model-and-conf') {
                            console.log('[PetBridge]' + JSON.stringify({
                                type: 'set-model-and-conf',
                                model_info: data.model_info || null,
                                conf_name: data.conf_name || ''
                            }));
                            window.__petPendingMessages.push({
                                type: 'set-model-and-conf',
                                model_info: data.model_info || null,
                                conf_name: data.conf_name || ''
                            });
                        }
                        // Capture backend-synth-complete for playback feedback loop
                        if (msgType === 'backend-synth-complete') {
                            window.__petPendingMessages.push({type: 'backend-synth-complete'});
                        }
                        // Capture control signals (conversation-chain-start/end)
                        if (msgType === 'control') {
                            window.__petPendingMessages.push({
                                type: 'control',
                                text: data.text || ''
                            });
                        }
                        // Capture error messages for user-visible feedback
                        if (msgType === 'error') {
                            console.log('[PetBridge]' + JSON.stringify({
                                type: 'error',
                                error: data.message || data.text || '(no message)'
                            }));
                            window.__petPendingMessages.push({
                                type: 'error',
                                error: data.message || data.text || '(unknown error)'
                            });
                        }
                    }
                } catch(e) {
                    console.log('[PetBridge]' + JSON.stringify({type: 'error', error: e.message}));
                }
            }

            window.WebSocket = function(url, protocols) {
                const ws = new OrigWebSocket(url, protocols);
                wsInstances.push(ws);

                // Intercept addEventListener('message', ...)
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

                // Intercept onmessage property assignment
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

            // ── Dedicated pet WebSocket (reliable: always captures messages) ──
            var _petSocket = null;
            var _petSocketReconnectTimer = null;

            function _connectPetSocket() {
                if (_petSocket && (_petSocket.readyState === OrigWebSocket.OPEN || _petSocket.readyState === OrigWebSocket.CONNECTING))
                    return;
                var host = window.location.hostname || 'localhost';
                var url = 'ws://' + host + ':12393/client-ws';
                try {
                    _petSocket = new OrigWebSocket(url);
                    _petSocket.onmessage = function(event) {
                        _bridgeResponse(event);
                    };
                    _petSocket.onopen = function() {
                        console.log('[Pet] Pet socket connected');
                        if (_petSocketReconnectTimer) {
                            clearTimeout(_petSocketReconnectTimer);
                            _petSocketReconnectTimer = null;
                        }
                    };
                    _petSocket.onclose = function() {
                        console.log('[Pet] Pet socket disconnected, reconnecting in 3s');
                        _petSocket = null;
                        _petSocketReconnectTimer = setTimeout(_connectPetSocket, 3000);
                    };
                    _petSocket.onerror = function() {
                        // Will trigger onclose
                    };
                } catch(e) {
                    console.log('[Pet] Pet socket error: ' + e.message);
                    _petSocketReconnectTimer = setTimeout(_connectPetSocket, 3000);
                }
            }

            // Connect pet socket after a short delay (let page initialize first)
            setTimeout(_connectPetSocket, 1000);

            // Send a chat message through the pet socket
            window.__petSendMessage = function(text) {
                console.log('[PetBridge]' + JSON.stringify({
                    type: 'send',
                    text: text.substring(0, 100)
                }));
                // Try dedicated pet socket first
                if (_petSocket && _petSocket.readyState === OrigWebSocket.OPEN) {
                    _petSocket.send(JSON.stringify({type: 'text-input', text: text}));
                    return 'ws-ok';
                }
                // Fallback: try captured WS instances
                for (const ws of wsInstances) {
                    if (ws.readyState === OrigWebSocket.OPEN &&
                        (ws.url || '').includes('/client-ws')) {
                        ws.send(JSON.stringify({type: 'text-input', text: text}));
                        return 'ws-ok';
                    }
                }
                for (const ws of wsInstances) {
                    if (ws.readyState === OrigWebSocket.OPEN &&
                        ((ws.url || '').includes('localhost:12393') ||
                         (ws.url || '').includes('127.0.0.1:12393'))) {
                        ws.send(JSON.stringify({type: 'text-input', text: text}));
                        return 'ws-ok';
                    }
                }
                // Fallback: try to reconnect and retry once
                _connectPetSocket();
                var urls = [];
                for (var k = 0; k < wsInstances.length; k++) {
                    urls.push((wsInstances[k].url || 'unknown') + ' state=' + wsInstances[k].readyState);
                }
                console.log('[Pet] Send failed. WS instances: ' + (urls.length || 'none') +
                    ' ' + urls.join(', '));
                return 'ws-closed';
            };

            // Send raw WS message (for config switching, etc.)
            window.__petSendWsRaw = function(msg) {
                // Try dedicated pet socket first
                if (_petSocket && _petSocket.readyState === OrigWebSocket.OPEN) {
                    _petSocket.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
                    return 'ws-ok';
                }
                // Fallback through wsInstances
                for (const ws of wsInstances) {
                    if (ws.readyState === OrigWebSocket.OPEN &&
                        ((ws.url || '').includes('/client-ws') ||
                         (ws.url || '').includes('localhost:12393') ||
                         (ws.url || '').includes('127.0.0.1:12393'))) {
                        ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
                        return 'ws-ok';
                    }
                }
                return 'ws-closed';
            };

            // Send switch-config through the frontend's own WS ONLY.
            // Using _petSocket would switch config for a different backend session,
            // so on page reload the frontend reverts to the old config.
            window.__petSwitchConfig = function(msg) {
                var urls = [];
                for (var i = 0; i < wsInstances.length; i++) {
                    var ws = wsInstances[i];
                    urls.push((ws.url || 'unknown') + ' state=' + ws.readyState);
                    if (ws.readyState === OrigWebSocket.OPEN &&
                        ((ws.url || '').includes('/client-ws') ||
                         (ws.url || '').includes('localhost:12393') ||
                         (ws.url || '').includes('127.0.0.1:12393'))) {
                        ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
                        return 'ws-ok';
                    }
                }
                console.log('[Pet] __petSwitchConfig: no frontend WS found. wsInstances=' + urls.join(', '));
                // No fallback to _petSocket — it's a different session
                return 'no-frontend-ws';
            };

            // DOM fallback: try to find and use the page's own input
            window.__petSendDomFallback = function(text) {
                var selectors = ['textarea','input[type="text"]','input:not([type])',
                    '[class*="chat"] input','[class*="Chat"] textarea',
                    '#message-input','.chat-input input'];
                var inp = null;
                for (var i = 0; i < selectors.length; i++) {
                    var el = document.querySelector(selectors[i]);
                    if (el && (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) { inp = el; break; }
                    }
                }
                if (inp) {
                    var proto = inp.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                    var d = Object.getOwnPropertyDescriptor(proto, 'value');
                    if (d && d.set) d.set.call(inp, text);
                    else inp.value = text;
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                    var btns = document.querySelectorAll('button');
                    for (var j = 0; j < btns.length; j++) {
                        if (btns[j].getBoundingClientRect().width > 0 &&
                            (btns[j].type === 'submit' || /send|Send|发送/i.test(btns[j].textContent || ''))) {
                            setTimeout(function(b) { b.click(); }, 50, btns[j]);
                            return;
                        }
                    }
                    inp.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                    }));
                }
            };

            // Expose wsInstances for Python-side access
            window.__petWsInstances = wsInstances;

            // ── Live2D Expression Control ──
            // Set expression by index (0-7 for mao_pro)
            window.__petSetExpression = function(exprIndex) {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var name = adapter.getExpressionName(exprIndex);
                    if (name) {
                        adapter.setExpression(name);
                        return 'ok:' + name;
                    }
                    return 'no-name';
                } catch(e) { return 'err:' + e.message; }
            };

            // Reset expression to default (neutral)
            window.__petResetExpression = function() {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    adapter.setExpression(adapter.getExpressionName(0) || 'neutral');
                    return 'ok';
                } catch(e) { return 'err:' + e.message; }
            };

            // ── Live2D Motion Control ──
            // Play a random motion from a group (e.g. "Idle", "Talk")
            window.__petPlayRandomMotion = function(group, priority) {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var model = adapter.getModel();
                    if (!model) return 'no-model';
                    priority = priority || 3; // PriorityForce
                    return model.startRandomMotion(group || '', priority) ? 'ok' : 'no-motion';
                } catch(e) { return 'err:' + e.message; }
            };

            // Play a specific motion by group + index
            window.__petPlayMotion = function(group, index, priority) {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var model = adapter.getModel();
                    if (!model) return 'no-model';
                    priority = priority || 3;
                    return model.startMotion(group || '', index || 0, priority) ? 'ok' : 'no-motion';
                } catch(e) { return 'err:' + e.message; }
            };

            // Play a motion by group name (wraps __petPlayRandomMotion for _send_l2d_motion)
            window.__petSendMotion = function(motionName) {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var model = adapter.getModel();
                    if (!model) return 'no-model';
                    return model.startRandomMotion(motionName || '', 3) ? 'ok' : 'no-motion';
                } catch(e) { return 'err:' + e.message; }
            };

            // Set expression by name (maps via ExpressionCatalog)
            window.__petExpressionMap = EXPR_MAP_JSON;
            window.__petSetExpressionByName = function(name) {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var map = window.__petExpressionMap || {};
                    var idx = map[name.toLowerCase()];
                    if (idx === undefined) return 'unknown-name:' + name;
                    var ename = adapter.getExpressionName(idx);
                    if (ename) { adapter.setExpression(ename); return 'ok:' + ename; }
                    return 'no-name';
                } catch(e) { return 'err:' + e.message; }
            };

            // ── Model Position & Scale Control ──
            window.__petScaleFactor = 1.0;
            window.__petOffsetX = 0.0;
            window.__petOffsetY = 0.0;
            window.__petScalePollTimer = null;

            window.__petApplyCanvasTransform = function(canvas, factor, dx, dy) {
                if (!canvas) return false;
                // Prevent clipping
                var p = canvas.parentElement;
                if (p) p.style.overflow = 'visible';
                if (p && p.parentElement) p.parentElement.style.overflow = 'visible';

                // Center + offset + scale
                canvas.style.position = 'absolute';
                canvas.style.left = '50%';
                canvas.style.top = '50%';
                canvas.style.transformOrigin = '0 0';
                canvas.style.transform =
                    'translate(calc(-50% + ' + dx + 'px), calc(-50% + ' + dy + 'px)) scale(' + factor + ')';
                // Preserve draw size (don't confuse canvas.width with CSS width)
                canvas.style.width = canvas.width + 'px';
                canvas.style.height = canvas.height + 'px';
                return true;
            };

            window.__petSetModelScale = function(factor, dx, dy) {
                try {
                    var canvas = document.querySelector('canvas');
                    if (!canvas) return {status: 'wait', reason: 'no-canvas'};
                    window.__petScaleFactor = factor;
                    if (dx !== undefined) window.__petOffsetX = dx;
                    if (dy !== undefined) window.__petOffsetY = dy;
                    window.__petApplyCanvasTransform(canvas, factor, window.__petOffsetX, window.__petOffsetY);
                    return {status: 'ok', factor: factor, dx: window.__petOffsetX, dy: window.__petOffsetY};
                } catch(e) { return {status: 'error', reason: e.message}; }
            };

            // Set position offset only (preserve current scale)
            window.__petSetModelPosition = function(dx, dy) {
                window.__petOffsetX = dx;
                window.__petOffsetY = dy;
                var canvas = document.querySelector('canvas');
                if (!canvas) return {status: 'wait', reason: 'no-canvas'};
                window.__petApplyCanvasTransform(canvas, window.__petScaleFactor, dx, dy);
                return {status: 'ok', dx: dx, dy: dy};
            };

            // Auto-retry: poll until canvas appears
            window.__petStartScalePolling = function(factor, dx, dy, maxRetries) {
                maxRetries = maxRetries || 30;
                var retries = 0;
                if (window.__petScalePollTimer) {
                    clearInterval(window.__petScalePollTimer);
                }
                window.__petScalePollTimer = setInterval(function() {
                    var result = window.__petSetModelScale(factor, dx, dy);
                    if (result && result.status === 'ok') {
                        clearInterval(window.__petScalePollTimer);
                        window.__petScalePollTimer = null;
                        console.log('[Pet] Transform applied after ' + retries + ' retries: ' + factor);
                    } else if (++retries >= maxRetries) {
                        clearInterval(window.__petScalePollTimer);
                        window.__petScalePollTimer = null;
                        console.log('[Pet] Transform polling exhausted');
                    }
                }, 500);
            };

            // Watch for canvas re-creation
            var __petCanvasWatchInterval = setInterval(function() {
                var canvas = document.querySelector('canvas');
                if (!canvas) return;
                var hasScale = canvas.style.transform
                    && canvas.style.transform.indexOf('scale(' + window.__petScaleFactor) >= 0;
                if (!hasScale && (window.__petScaleFactor !== 1.0 || window.__petOffsetX !== 0 || window.__petOffsetY !== 0)) {
                    window.__petApplyCanvasTransform(canvas, window.__petScaleFactor, window.__petOffsetX, window.__petOffsetY);
                }
            }, 1000);

            window.__petGetModelScale = function() {
                return '' + (window.__petScaleFactor || 1.0);
            };

            console.log('[Pet] JS interceptor active');
        })();
        """
        # Inject expression map from Python catalog
        from pet_core.expression_catalog import ExpressionCatalog
        expr_map = ExpressionCatalog().as_mapping()
        code = code.replace("EXPR_MAP_JSON", json.dumps(expr_map))

        # Use QWebEngineScript at DocumentCreation to ensure the WS monkey-patch
        # runs BEFORE the React app creates its WebSocket connection.
        script = QWebEngineScript()
        script.setName("__pet_interceptor")
        script.setSourceCode(code)
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        # Remove old script if re-injecting
        for old in self._page.scripts().find("__pet_interceptor"):
            self._page.scripts().remove(old)
        self._page.scripts().insert(script)

    def _inject_transparent_css(self):
        """Register persistent UI cleanup script (survives page reloads).

        Hides all React UI — only the Live2D canvas and its ancestors survive.
        Uses QWebEngineScript at DocumentReady so it runs after DOM is available
        on every page load, without needing re-injection from loadFinished.
        """
        # Remove old script if re-registering
        for old in self._page.scripts().find("__pet_ui_cleanup"):
            self._page.scripts().remove(old)

        css = r"""
        (function() {
            // Add persistent style tag (only once)
            if (!document.getElementById('__pet_css')) {
                var s = document.createElement('style');
                s.id = '__pet_css';
                s.textContent = [
                    'html, body, #root, #__next, [id*="root"], div, section, main, article',
                    '{ background: transparent !important; background-color: transparent !important;',
                    '  border: none !important; border-radius: 0 !important; outline: none !important; }',
                    '* { box-shadow: none !important; }',
                    'body',
                    '{ display: flex !important; justify-content: center !important;',
                    '  align-items: center !important; overflow: hidden !important; }',
                    'canvas',
                    '{ display: block !important; visibility: visible !important; opacity: 1 !important; }'
                ].join('\n');
                document.head.appendChild(s);
            }

            // No guard — cleanUI must run on every interval tick because the
            // canvas is rendered by React AFTER DocumentReady.  If we skip
            // later runs, the canvas ancestors stay hidden.
            function cleanUI() {
                var canvases = document.querySelectorAll('canvas');
                if (canvases.length === 0) return 0;  // canvas not rendered yet
                var protectedNodes = new WeakSet();
                for (var c = 0; c < canvases.length; c++) {
                    var node = canvases[c];
                    while (node) {
                        protectedNodes.add(node);
                        node = node.parentElement;
                    }
                }
                function walkAndHide(parent) {
                    var kids = parent.children;
                    for (var i = kids.length - 1; i >= 0; i--) {
                        var el = kids[i];
                        var tag = el.tagName;
                        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK') continue;
                        if (el.id === '__pet_css') continue;
                        if (protectedNodes.has(el)) {
                            // CRITICAL: reset display so previously-hidden ancestors
                            // become visible again when a new canvas appears inside them
                            el.style.setProperty('display', '', 'important');
                            el.style.setProperty('visibility', 'visible', 'important');
                            el.style.setProperty('opacity', '1', 'important');
                            el.style.setProperty('background', 'transparent', 'important');
                            el.style.setProperty('background-color', 'transparent', 'important');
                            el.style.setProperty('border', 'none', 'important');
                            el.style.setProperty('border-radius', '0', 'important');
                            el.style.setProperty('outline', 'none', 'important');
                            el.style.setProperty('box-shadow', 'none', 'important');
                            walkAndHide(el);
                        } else {
                            el.style.setProperty('display', 'none', 'important');
                        }
                    }
                }
                walkAndHide(document.body);
                return canvases.length;
            }

            window.__petCleanUI = cleanUI;

            // Canvas click → Python bridge + keep native tapMotions
            window.__petClickHandler = function(e) {
                var el = e.target;
                while (el) {
                    if (el.tagName === 'CANVAS') {
                        console.log('[PetBridge]' + JSON.stringify({type: 'click', x: e.clientX, y: e.clientY}));
                        // Do NOT preventDefault/stopPropagation — let React tapMotions fire too
                        return;
                    }
                    el = el.parentElement;
                }
            };
            document.addEventListener('pointerdown', window.__petClickHandler, true);
            // Also re-attach on canvas appearance (survives React rerenders)
            window.__petReattachClick = function() {
                document.removeEventListener('pointerdown', window.__petClickHandler, true);
                document.addEventListener('pointerdown', window.__petClickHandler, true);
            };

            // Keep running: React renders the canvas after DocumentReady,
            // so we must keep checking until it appears, then keep guarding.
            var _cleanupInterval = setInterval(function() {
                var n = cleanUI();
                if (n > 0 && !window.__petCleanupLogged) {
                    console.log('[Pet] UI cleanup: found ' + n + ' canvas(es)');
                    window.__petCleanupLogged = true;
                }
                // Re-attach click handler via helper (survives page re-renders)
                window.__petReattachClick && window.__petReattachClick();
            }, 1000);
        })();
        """
        script = QWebEngineScript()
        script.setName("__pet_ui_cleanup")
        script.setSourceCode(css)
        script.setInjectionPoint(QWebEngineScript.DocumentReady)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        self._page.scripts().insert(script)

    # ── JS Console Bridge (diagnostic only — response handling via polling) ──
    def _on_js_console(self, level, message: str, line, source):
        if not message.startswith("[PetBridge]"):
            return
        try:
            data = json.loads(message[len("[PetBridge]"):])
            msg_type = data.get("type", "")
            # Response / send are handled by _on_poll_result
            if msg_type in ("response", "send"):
                return
            if msg_type == "config-switched":
                print(f"[Pet] Config switched: {data.get('message', '')}")
                return
            if msg_type == "debug":
                print(f"[Pet] WS msg: type={data.get('wsType')}, keys={data.get('keys')}")
            elif msg_type == "error":
                print(f"[Pet] Bridge error: {data.get('error', '')}")
            elif msg_type == "click":
                if not self._click_through:
                    QTimer.singleShot(0, self._on_click_pet)
        except Exception:
            pass

    # ── JS Message Polling (reliable bridge, no console.log dependency) ──
    def _poll_js_messages(self):
        """Poll window.__petDrainMessages() via runJavaScript callback."""
        self._webview.page().runJavaScript(
            "window.__petDrainMessages && window.__petDrainMessages()",
            self._on_poll_result
        )

    def _on_poll_result(self, result):
        if not result or result == '[]':
            return
        try:
            messages = json.loads(result)
            for data in messages:
                msg_type = data.get("type", "")
                if msg_type == "response":
                    text = data.get("text", "")
                    exps = data.get("expressions", [])
                    # Parse and apply any JSON command embedded in the LLM text
                    from pet_core.command_parser import parse, strip_command_block
                    cmd = parse(text, allowed_actions=self._allowed_actions, allowed_expressions=self._allowed_expressions)
                    if cmd and not cmd.is_empty():
                        self._enqueue_command(cmd)
                    # Always strip JSON command blocks from display text
                    text = strip_command_block(text)
                    print(f"[Pet] Poll: {text[:80]} exps={exps}" if len(text) > 80 else f"[Pet] Poll: {text} exps={exps}")
                    self._bubble.show_text(text, exps)
                    self._log_llm_response(text)
                    tts_segments = prepare_tts_text(text, max_segment_chars=100, add_ending=True)
                    if tts_segments:
                        self._tts.speak_segments(tts_segments)
                    self._llm_active_until = time.time() + 10.0
                elif msg_type == "audio":
                    # Buffer audio slices — process after all slices arrive
                    self._audio_buffer.append(data)
                    # display_text may be a dict {"text":..., "name":..., "avatar":...} or a string
                    _dt = data.get("display_text", "")
                    if isinstance(_dt, dict):
                        _dt = _dt.get("text", "")
                    if _dt:
                        print(f"[Pet] Poll: {_dt[:80]} exps=[]")
                    # Reset flush timer: wait 3s after last slice
                    if self._audio_flush_timer:
                        self._audio_flush_timer.stop()
                    self._audio_flush_timer = QTimer()
                    self._audio_flush_timer.setSingleShot(True)
                    self._audio_flush_timer.timeout.connect(self._flush_audio_buffer)
                    self._audio_flush_timer.start(self._audio_flush_timeout)
                elif msg_type == "full-text":
                    self._full_text_received = data.get("text", "")
                elif msg_type == "set-model-and-conf":
                    model_info = data.get("model_info")
                    conf_name = data.get("conf_name", "")
                    mi_url = model_info.get("url", "?") if model_info else "None"
                    mi_scale = model_info.get("kScale", "?") if model_info else "?"
                    print(f"[Pet] Poll: set-model-and-conf conf={conf_name} url={mi_url} kScale={mi_scale}")
                    if model_info:
                        self._pending_model_info = model_info
                elif msg_type == "config-switched":
                    print(f"[Pet] Poll: config switched, verifying model...")
                    self._l2d_switch_timer.stop()
                    QTimer.singleShot(1500, self._verify_l2d_switch)
                elif msg_type == "backend-synth-complete":
                    self._signal_playback_complete_when_ready()
                elif msg_type == "control":
                    ctrl_text = data.get("text", "")
                    if ctrl_text == "conversation-chain-start":
                        self._conversation_active = True
                        self._webview.page().runJavaScript(
                            "window.__petSetExpressionByName('surprised');"
                        )
                    elif ctrl_text == "conversation-chain-end":
                        self._conversation_active = False
                        QTimer.singleShot(2000, lambda: self._webview.page().runJavaScript(
                            "window.__petResetExpression();"
                        ))
                elif msg_type == "error":
                    error_text = data.get("error", "Unknown error")
                    print(f"[Pet] Backend error: {error_text}")
                    self._bubble.show_text(f"出错了: {error_text[:60]}", [])
        except Exception:
            pass

    def _flush_audio_buffer(self):
        """Process buffered audio slices as a single response."""
        if not self._audio_buffer:
            return
        slices = self._audio_buffer[:]
        self._audio_buffer.clear()

        # Collect all display_text fragments
        # display_text may be a dict {"text":..., "name":..., "avatar":...} or a string
        from pet_core.command_parser import strip_command_block, parse
        text_parts = []
        for s in slices:
            dt = s.get("display_text", "")
            if isinstance(dt, dict):
                dt = dt.get("text", "")
            if dt:
                text_parts.append(dt)
        raw_text = "".join(text_parts).strip()

        # Prefer full-text if available (more complete)
        if self._full_text_received:
            raw_text = self._full_text_received
            self._full_text_received = None

        # Parse and apply JSON command from the COMPLETE collected text
        cmd = parse(raw_text, allowed_actions=self._allowed_actions, allowed_expressions=self._allowed_expressions)
        if cmd and not cmd.is_empty():
            self._enqueue_command(cmd)

        # Clean text for display and TTS
        clean = strip_command_block(raw_text)
        if not clean:
            return

        # Extract expressions from actions (top-level or nested in display_text)
        exps = []
        for s in slices:
            # Top-level actions
            actions = s.get("actions")
            if isinstance(actions, dict):
                for expr in (actions.get("expressions") or []):
                    exps.append(expr)
            elif isinstance(actions, list):
                for action in actions:
                    if "expression" in action:
                        exps.append(action["expression"])
            # Also check display_text.actions (some backend versions nest here)
            dt = s.get("display_text", "")
            if isinstance(dt, dict):
                dt_actions = dt.get("actions")
                if isinstance(dt_actions, dict):
                    for expr in (dt_actions.get("expressions") or []):
                        exps.append(expr)
                elif isinstance(dt_actions, list):
                    for action in dt_actions:
                        if "expression" in action:
                            exps.append(action["expression"])

        self._bubble.show_text(clean, exps)
        self._log_llm_response(clean)

        # TTS: preprocess and segment for natural speech
        tts_segments = prepare_tts_text(clean, max_segment_chars=100, add_ending=True)
        if tts_segments:
            self._tts.speak_segments(tts_segments)
        self._llm_active_until = time.time() + 10.0

    def _send_heartbeat(self):
        self._webview.page().runJavaScript(
            "window.__petSendWsRaw({type: 'heartbeat'});"
        )

    def _signal_playback_complete_when_ready(self):
        """Wait for local TTS to finish, then notify backend playback is complete."""
        if self._tts.is_speaking:
            QTimer.singleShot(500, self._signal_playback_complete_when_ready)
            return
        self._webview.page().runJavaScript(
            "window.__petSendWsRaw({type: 'frontend-playback-complete'});"
        )

    # ── Overlay widgets ──────────────────────────────────
    def _setup_overlays(self):
        self._bubble = SpeechBubble(self)
        self._chatbar = ChatBar(self)
        self._chatbar.message_submitted.connect(self._on_chat_submit)
        self._chatbar.quick_action.connect(self._on_quick_action)
        self._scale_bar = ScaleBar(self)
        self._scale_bar.set_callback(self._set_model_scale)
        self._reposition_overlays()

    def _reposition_overlays(self):
        w, h = self.width(), self.height()
        # Speech bubble — top center
        self._bubble.move((w - self._bubble.width()) // 2, 50)
        # Chat bar — bottom center
        self._chatbar.move((w - self._chatbar.width()) // 2, h - 100)
        # Scale bar — right side, vertically centered
        sb_w = self._scale_bar.width()
        sb_h = self._scale_bar.height()
        self._scale_bar.move(w - sb_w - 5, (h - sb_h) // 2 + 20)

    def showEvent(self, event):
        super().showEvent(event)
        # Initialize Win32 click-through state when window is first shown
        if sys.platform == "win32" and hasattr(self, "_set_click_through_win32"):
            QTimer.singleShot(50, lambda: self._set_click_through_win32(False))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._webview.setGeometry(0, 0, self.width(), self.height())
        self._reposition_overlays()

    def moveEvent(self, event):
        super().moveEvent(event)
        # Reposition native-window overlays when window moves
        self._reposition_overlays()

    # ── Chat ─────────────────────────────────────────────

    # Keyword → quick-action mapping for D2 (bypass LLM)
    _QUICK_KEYWORDS: dict[str, tuple[str, str]] = {
        "挥个手": ("action", "wave"),
        "挥手": ("action", "wave"),
        "打个招呼": ("action", "wave"),
        "转个圈": ("action", "spin"),
        "转圈": ("action", "spin"),
        "跳个舞": ("action", "dance"),
        "跳舞": ("action", "dance"),
        "点点头": ("action", "nod"),
        "点头": ("action", "nod"),
        "摇摇头": ("action", "shake_head"),
        "摇头": ("action", "shake_head"),
        "做个鬼脸": ("expression", "happy"),
        "开心点": ("expression", "happy"),
        "笑一个": ("expression", "happy"),
        "卖个萌": ("expression", "shy"),
        "装可爱": ("expression", "shy"),
        "睡觉吧": ("expression", "sleepy"),
    }

    def _on_chat_submit(self, text: str):
        self._last_interaction_time = time.time()
        self._pet_state.last_interaction_at = time.time()
        self.show()
        self.raise_()
        # Voice switching command: "音色 冰糖" or "切换音色 星火"
        if text.startswith(("音色 ", "切换音色 ")):
            voice = text.split(None, 1)[-1].strip()
            if voice in MiMoTTS.available_voices() or voice in MiMoTTS.voice_design_presets():
                self._switch_voice(voice)
            else:
                names = ", ".join(MiMoTTS.available_voices().keys())
                self._bubble.show_text(f"未知音色: {voice}\n可用: {names}", [])
            return
        # TTS model switching: "tts模型 voicedesign" or "切换tts voiceclone"
        if text.startswith(("tts模型 ", "切换tts ", "tts ")):
            model = text.split(None, 1)[-1].strip()
            if model in MiMoTTS.available_models():
                self._switch_tts_model(model)
            else:
                names = ", ".join(MiMoTTS.available_models().keys())
                self._bubble.show_text(f"未知模型: {model}\n可用: {names}", [])
            return
        # D2: check keywords — bypass LLM if matched
        for keyword, (atype, aval) in self._QUICK_KEYWORDS.items():
            if keyword in text:
                print(f"[Pet] Keyword match '{keyword}' → {atype}:{aval}")
                self._on_quick_action(atype, aval)
                return
        self._last_chat_text = text  # Store for fallback
        self._webview.page().runJavaScript(
            f"window.__petSendMessage({json.dumps(text)});",
            self._on_send_result
        )
        # Clean UI elements that might have appeared
        QTimer.singleShot(500, lambda: self._webview.page().runJavaScript(
            "window.__petCleanUI && window.__petCleanUI()"))

    def _on_send_result(self, result):
        if result in ("ws-ok", None):
            return
        print(f"[Pet] WS send result: {result}, trying DOM fallback")
        text = getattr(self, "_last_chat_text", "")
        safe = json.dumps(text)
        self._webview.page().runJavaScript(
            f"window.__petSendDomFallback({safe});"
        )
        QTimer.singleShot(500, lambda: self._webview.page().runJavaScript(
            "window.__petCleanUI && window.__petCleanUI()"))

    def _on_quick_action(self, action_type: str, action_value: str):
        """Handle quick-action button clicks from ChatBar."""
        self._last_interaction_time = time.time()
        self._pet_state.last_interaction_at = time.time()
        if action_type == "expression":
            if action_value == "reset":
                self._webview.page().runJavaScript("window.__petResetExpression()")
            else:
                js = f"window.__petSetExpressionByName({json.dumps(action_value)});"
                self._webview.page().runJavaScript(js)
            print(f"[Pet] Quick expression: {action_value}")
        elif action_type == "action":
            self._apply_command(dict(action=action_value))
            print(f"[Pet] Quick action: {action_value}")

    # ── System tray ──────────────────────────────────────
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip("喵酱 Live2D Desktop Pet")

        # Build a simple cat-face icon programmatically
        icon = self._make_tray_icon()
        self._tray.setIcon(icon)

        self._tray.activated.connect(self._on_tray_activated)
        self._rebuild_tray_menu()
        self._tray.show()

        # Async refresh model list from Ollama
        self._refresh_ollama_models()

    def _make_tray_icon(self) -> QIcon:
        """Draw a simple 16x16 cat icon."""
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        # Pink circle body
        painter.setBrush(QColor("#ff99bb"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 4, 12, 10)

        # Ears (triangles)
        path = QPainterPath()
        path.moveTo(3, 5)
        path.lineTo(5, 0)
        path.lineTo(7, 5)
        painter.drawPath(path)
        path = QPainterPath()
        path.moveTo(13, 5)
        path.lineTo(11, 0)
        path.lineTo(9, 5)
        painter.drawPath(path)

        # Eyes
        painter.setBrush(QColor("#1a1a2e"))
        painter.drawEllipse(5, 6, 2, 2)
        painter.drawEllipse(10, 6, 2, 2)

        # Mouth
        painter.setPen(QPen(QColor("#1a1a2e"), 0.5))
        painter.drawLine(7, 11, 8, 11)

        painter.end()
        return QIcon(pix)

    def _rebuild_tray_menu(self, cached_models=None):
        models = cached_models or []
        model_items = []
        if models:
            for m in models:
                mid = m.get("name", m.get("id", ""))
                mark = " ✓" if mid == self._current_model else ""
                model_items.append(QAction(f"{mid}{mark}", self))
                model_items[-1].triggered.connect(
                    lambda checked, mid=mid: self._switch_model(mid)
                )
        else:
            for m in AVAILABLE_MODELS:
                mark = " ✓" if m["id"] == self._current_model else ""
                model_items.append(QAction(f"{m['emoji']} {m['name']}{mark}", self))
                model_items[-1].triggered.connect(
                    lambda checked, mid=m["id"]: self._switch_model(mid)
                )

        menu = QMenu()

        # ── Pet care ──
        care_menu = menu.addMenu("🥩 照顾喵酱")
        care_menu.addAction("🍖 喂食", self._pet_feed)
        care_menu.addAction("🛁 洗澡", self._pet_clean)
        care_menu.addAction("🤚 摸头", self._pet_pet)
        care_menu.addAction("💤 睡觉", self._pet_sleep)

        # ── Status ──
        s = self._pet_state
        status_text = (
            f"🍖{s.hunger:.0f} 🛁{s.cleanliness:.0f} "
            f"😊{s.mood:.0f} ❤{s.health:.0f} 😴{s.fatigue:.0f} "
            f"Lv{s.level}"
        )
        menu.addAction(status_text, None).setEnabled(False)

        menu.addSeparator()
        menu.addAction("💬 快捷聊天", self._chatbar.toggle)

        pro_label = f"🤖 AI 主动聊天: {'开' if self._proactive_enabled else '关'}"
        menu.addAction(pro_label, self._toggle_proactive)

        show_action = menu.addAction("👁 显示/隐藏 喵酱")
        show_action.triggered.connect(self._toggle_visible)

        menu.addSeparator()
        menu.addAction("📝 新对话", self._reload_page)

        model_menu = menu.addMenu("🤖 切换模型")
        for item in model_items:
            model_menu.addAction(item)

        l2d_menu = menu.addMenu("🎭 切换 Live2D 模型")
        l2d_models = self._discover_l2d_models()
        category_models = self._get_categorized_models(l2d_models)

        # Category display order and labels
        cat_order = [
            ("official", "📦 官方示例"),
            ("azurlane", "🎮 碧蓝航线"),
            ("gfl", "🔫 少女前线"),
            ("honkai", "🏫 崩坏学园2"),
            ("warship", "🚢 战舰少女"),
            ("other", "📁 其他"),
        ]

        uncategorized = set(l2d_models)
        for label_zh, cat_id in [(l, c) for c, l in cat_order]:
            models_in_cat = category_models.get(cat_id, [])
            if not models_in_cat:
                continue
            cat_menu = l2d_menu.addMenu(label_zh)
            for _m in models_in_cat:
                uncategorized.discard(_m)
                mark = " ✓" if _m == self._current_l2d else ""
                act = QAction(f"{_m}{mark}", self)
                act.triggered.connect(lambda checked, m=_m: self._switch_l2d(m))
                cat_menu.addAction(act)

        # Any remaining uncategorized models
        if uncategorized:
            other_menu = l2d_menu.addMenu("📁 其他")
            for _m in sorted(uncategorized):
                mark = " ✓" if _m == self._current_l2d else ""
                act = QAction(f"{_m}{mark}", self)
                act.triggered.connect(lambda checked, m=_m: self._switch_l2d(m))
                other_menu.addAction(act)

        l2d_menu.addSeparator()
        l2d_menu.addAction("📥 下载更多模型...", self._download_more_models)

        # ── Model scale toggle ──
        current_scale = self._model_scales.get(self._current_l2d, 1.0)
        scale_label = "📐 调整模型大小" if self._scale_bar.isVisible() else f"📐 调整模型大小 ({int(current_scale * 100)}%)"
        menu.addAction(scale_label, self._scale_bar.toggle)

        # ── Model position adjustment ──
        pos = self._model_offsets.get(self._current_l2d, [0, 0])
        pos_menu = menu.addMenu(f"📌 调整位置 ({pos[0]},{pos[1]})")
        step = 10  # pixels per nudge
        pos_menu.addAction("⬆ 上移 10px", lambda: self._nudge_model(0, -step))
        pos_menu.addAction("⬇ 下移 10px", lambda: self._nudge_model(0, step))
        pos_menu.addAction("⬅ 左移 10px", lambda: self._nudge_model(-step, 0))
        pos_menu.addAction("➡ 右移 10px", lambda: self._nudge_model(step, 0))
        pos_menu.addSeparator()
        pos_menu.addAction("🏠 重置居中", lambda: self._nudge_model(reset=True))

        voice_menu = menu.addMenu("🎙 切换音色")
        for vname, vdesc in MiMoTTS.available_voices().items():
            mark = " ✓" if vname == self._tts.current_voice else ""
            act = QAction(f"{vname} — {vdesc}{mark}", self)
            act.triggered.connect(lambda checked, vn=vname: self._switch_voice(vn))
            voice_menu.addAction(act)

        model_menu = menu.addMenu("🔊 TTS 模型")
        for mname, mdesc in MiMoTTS.available_models().items():
            mark = " ✓" if mname == self._tts.current_model else ""
            act = QAction(f"{mname}{mark} — {mdesc}", self)
            act.triggered.connect(lambda checked, mn=mname: self._switch_tts_model(mn))
            model_menu.addAction(act)
        # Voice design presets submenu (only when using voicedesign model)
        if self._tts.current_model == "mimo-v2.5-tts-voicedesign":
            vd_menu = model_menu.addMenu("🎨 音色设计预设")
            for vname, vdesc in MiMoTTS.voice_design_presets().items():
                act = QAction(f"{vname} — {vdesc}", self)
                act.triggered.connect(lambda checked, vn=vname: self._switch_voice(vn))
                vd_menu.addAction(act)

        menu.addSeparator()
        ct_label = f"🔍 半透明查看: {'开' if self._click_through else '关'}"
        menu.addAction(ct_label, self._toggle_click_through)

        menu.addSeparator()
        log_visible = self._cmd_log_panel is not None and self._cmd_log_panel.isVisible()
        menu.addAction("🔇 关闭 AI 指令日志" if log_visible else "📋 AI 指令日志", self._show_cmd_log)
        menu.addAction("🔄 重新加载", self._reload_page)
        menu.addAction("♻ 重启后端", self._restart_backend)
        menu.addAction("❌ 退出", self._quit)

        self._tray.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_visible()

    def _show_cmd_log(self):
        """Toggle the AI command log panel."""
        if self._cmd_log_panel is not None and self._cmd_log_panel.isVisible():
            self._cmd_log_panel.hide()
            self._rebuild_tray_menu()
            return
        if self._cmd_log_panel is None:
            self._cmd_log_panel = CommandLogPanel()
            self._cmd_log_panel.setWindowFlags(
                Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self._cmd_log_panel.setAttribute(Qt.WA_TranslucentBackground)
        self._cmd_log_panel.update_log(self._cmd_log)
        # Position to the left of the pet window
        pos = self.mapToGlobal(self.rect().topLeft())
        pw = self._cmd_log_panel.width()
        self._cmd_log_panel.move(pos.x() - pw - 10, pos.y())
        self._cmd_log_panel.show()
        self._rebuild_tray_menu()

    def _refresh_ollama_models(self):
        """Fetch Ollama models in background thread, then update menu."""
        import urllib.request

        def fetch():
            try:
                req = urllib.request.Request(
                    f"{OLLAMA_URL}/api/tags",
                    headers={"User-Agent": "Pet/1.0"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    models = data.get("models", [])
                    self._cached_ollama = models
            except Exception:
                models = getattr(self, "_cached_ollama", [])
            # Back on main thread
            QTimer.singleShot(0, lambda: self._rebuild_tray_menu(models))

        threading.Thread(target=fetch, daemon=True).start()

    # ── Actions ──────────────────────────────────────────
    def _reload_page(self):
        self._webview.reload()

    def _toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            # Absence greeting
            greeting = absence_greeting(self._pet_state.last_interaction_at)
            if greeting:
                self._bubble.show_text(greeting, [])
                self._tts.speak(greeting)
            self._pet_state.last_interaction_at = time.time()
            self._save_state()

    def _toggle_click_through(self):
        """Toggle click-through mode.

        Instead of blocking ALL mouse events (which prevents character interaction),
        uses window opacity for visual transparency while keeping mouse events alive.
        In this mode, only window dragging is disabled; canvas clicks (pet interaction)
        and tray menu still work. Hold Ctrl to drag in click-through mode.
        """
        self._click_through = not self._click_through
        # Always keep overlays click-transparent
        self._bubble.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._chatbar.setAttribute(Qt.WA_TransparentForMouseEvents,
                                    self._click_through or not self._chatbar.isVisible())
        if self._click_through:
            # Use window opacity so the pet is semi-transparent visually
            # BUT mouse events still reach the webview (character interaction works!)
            self.setWindowOpacity(0.35)
            # Don't set WA_TransparentForMouseEvents — let canvas receive clicks
            # Only prevent dragging (handled in eventFilter)
            print("[Pet] Click-through ON — pet is semi-transparent, character clicks still work")
        else:
            self.setWindowOpacity(1.0)
            print("[Pet] Click-through OFF")
        self._rebuild_tray_menu()

    def _switch_voice(self, voice: str):
        self._tts.set_voice(voice)
        self._rebuild_tray_menu()
        self._bubble.show_text(f"音色已切换: {voice}", [])
        print(f"[Pet] Voice switched to: {voice}")

    def _switch_tts_model(self, model: str):
        self._tts.set_model(model)
        self._rebuild_tray_menu()
        self._bubble.show_text(f"TTS模型已切换: {model}", [])
        print(f"[Pet] TTS model switched to: {model}")

    def _set_click_through_win32(self, enabled: bool):
        """Use Win32 API to toggle WS_EX_TRANSPARENT for reliable click-through."""
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            # Also add WS_EX_LAYERED when transparent to ensure proper hit testing
            WS_EX_LAYERED = 0x00080000
            current = ctypes.windll.user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
            if enabled:
                new = current | WS_EX_TRANSPARENT
            else:
                new = current & ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, new)
            # Force style refresh — required on some Windows versions
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_FRAMECHANGED = 0x0020
            ctypes.windll.user32.SetWindowPos(
                wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED
            )
        except Exception as e:
            print(f"[Pet] Win32 click-through failed: {e}")

    def _toggle_proactive(self):
        self._proactive_enabled = not self._proactive_enabled
        self._last_interaction_time = time.time()
        self._rebuild_tray_menu()
        print(f"[Pet] Proactive AI chat: {'ON' if self._proactive_enabled else 'OFF'}")

    # ── pet-core: tick, care actions, motion ──────────────

    def _on_pet_tick(self):
        """Periodic tick: decay stats, choose behavior, drive motion."""
        import time
        now = time.time()
        # Skip behavior planning when LLM is actively sending commands
        if now < self._llm_active_until:
            return
        state = self._pet_state

        # ── Time-of-day greeting (once per session) ──
        if not self._tod_greeting_shown:
            self._tod_greeting_shown = True
            ctx = time_of_day_context(now)
            greeting = ctx["greeting"]
            self._bubble.show_text(greeting, [])
            self._tts.speak(greeting)

        # Decay stats
        self._pet_state = tick_pet(state)

        # Choose behavior
        behavior = self._planner.choose(self._pet_state)

        # Only act if behavior changed to something with a message
        if behavior != PetBehavior.IDLE:
            msg = self._motion_adapter.get_message(behavior)
            if msg and behavior != state.current_behavior:
                self._bubble.show_text(msg, [])
                self._tts.speak(msg)

            # Send motion to Live2D
            motion = self._motion_adapter.get_motion(behavior)
            self._send_l2d_motion(motion)

        self._pet_state = PetState(
            **{**self._pet_state.__dict__,
               "current_behavior": behavior}
        )

        # ── Proactive AI chat: trigger when idle for a while ──
        if self._proactive_enabled:
            idle_time = now - self._last_interaction_time
            if (idle_time > self._proactive_interval
                    and now - self._last_proactive_time > self._proactive_interval * 2):
                self._last_proactive_time = now
                print(f"[Pet] Proactive ai-speak-signal (idle {idle_time:.0f}s)")
                self._webview.page().runJavaScript(
                    "window.__petSendWsRaw({type: 'ai-speak-signal'});"
                )

    def _save_state(self):
        self._persistence.save(self._pet_state)

    def _do_action(self, action_fn, behavior: PetBehavior):
        """Execute a care action and show feedback."""
        self._pet_state = action_fn(self._pet_state)
        self._pet_state.last_interaction_at = time.time()

        # Show speech bubble
        msg = self._motion_adapter.get_message(behavior)
        if msg:
            self._bubble.show_text(msg, [])
            self._tts.speak(msg)

        # Send motion
        motion = self._motion_adapter.get_motion(behavior)
        self._send_l2d_motion(motion)

        # Check for level-up
        self._pet_state, leveled = check_level_up(self._pet_state)
        if leveled:
            lvl = self._pet_state.level
            lvl_msg = f"升级啦！现在是 Lv.{lvl} 了~ 🎉"
            self._bubble.show_text(lvl_msg, [])
            self._tts.speak(lvl_msg)
            self._send_l2d_motion(self._motion_adapter.get_motion(PetBehavior.HAPPY))

        # Save
        self._save_state()

    def _pet_feed(self):
        self._do_action(feed, PetBehavior.EAT)

    def _pet_clean(self):
        self._do_action(clean, PetBehavior.BATH)

    def _pet_sleep(self):
        self._do_action(sleep_action, PetBehavior.SLEEP)

    def _pet_pet(self):
        self._do_action(pet_action, PetBehavior.PETTED)

    def _send_l2d_motion(self, motion: str):
        """Send a motion command to the Live2D model via injected JS."""
        code = f"window.__petSendMotion({json.dumps(motion)});"
        self._webview.page().runJavaScript(code, self._log_js_result)

    def _apply_command(self, cmd):
        """Apply a PetCommand from LLM to the Live2D model.

        Dispatches to JS bridges for action/expression, and shows text in
        the speech bubble. Handles both PetCommand objects and raw dicts.
        Cooldown: same action/expression won't replay within _cmd_cooldown_sec.
        """
        import time
        from pet_core.command_parser import strip_command_block

        # Normalise to PetCommand if needed
        if isinstance(cmd, dict):
            from pet_core.commands import validate
            cmd = validate(cmd)

        now = time.time()

        # ── Action → motion (via MotionCatalog) ──
        if cmd.action:
            last = self._cmd_cooldowns.get(f"act:{cmd.action}", 0.0)
            if now - last < self._cmd_cooldown_sec:
                print(f"[Pet] Skip action={cmd.action} (cooldown)")
            else:
                from pet_core.motion_catalog import MotionCatalog
                resolved = MotionCatalog().resolve(cmd.action)
                if resolved is not None:
                    group, idx = resolved
                    js = f"window.__petPlayMotion({json.dumps(group)}, {idx})"
                    self._webview.page().runJavaScript(js, self._log_js_result)
                elif cmd.action == "idle":
                    self._send_l2d_motion("Idle")
                else:
                    self._send_l2d_motion("")  # random unnamed motion
                self._cmd_cooldowns[f"act:{cmd.action}"] = now
                print(f"[Pet] Command: action={cmd.action}")

        # ── Expression → set expression ──
        if cmd.expression:
            last = self._cmd_cooldowns.get(f"exp:{cmd.expression}", 0.0)
            if now - last < self._cmd_cooldown_sec:
                print(f"[Pet] Skip expression={cmd.expression} (cooldown)")
            else:
                code = f"window.__petSetExpressionByName({json.dumps(cmd.expression)});"
                self._webview.page().runJavaScript(code, self._log_js_result)
                self._cmd_cooldowns[f"exp:{cmd.expression}"] = now
                print(f"[Pet] Command: expression={cmd.expression}")

        # ── Text → speech bubble ──
        if cmd.text:
            clean = strip_command_block(cmd.text)
            if clean:
                self._bubble.show_text(clean, [])
                print(f"[Pet] Command: text={clean[:60]}")
                tts_segments = prepare_tts_text(clean, max_segment_chars=100, add_ending=True)
                if tts_segments:
                    self._tts.speak_segments(tts_segments)

        # ── Log ──
        parts = []
        if cmd.action:
            parts.append(f"act:{cmd.action}")
        if cmd.expression:
            parts.append(f"exp:{cmd.expression}")
        if cmd.text:
            parts.append(f"text:{cmd.text[:30]}")
        if parts:
            self._cmd_log.append(f"[{now:.0f}] {' '.join(parts)}")
            if len(self._cmd_log) > 20:
                self._cmd_log.pop(0)

    def _log_js_result(self, result):
        """Log JS bridge errors from runJavaScript callbacks."""
        if result and isinstance(result, str) and result.startswith(("err:", "no-", "unknown-")):
            print(f"[Pet] JS bridge warning: {result}")

    def _log_llm_response(self, text: str):
        """Log raw LLM response text to the command log panel."""
        import time
        clean = _CLS_EMOJI_TAGS.sub('', text).strip()
        if not clean:
            return
        now = time.time()
        display = clean[:60]
        self._cmd_log.append(f"[{now:.0f}] {display}")
        if len(self._cmd_log) > 20:
            self._cmd_log.pop(0)

    def _enqueue_command(self, cmd):
        """Add a command to the playback queue (sequential processing)."""
        from pet_core.commands import PetCommand
        if isinstance(cmd, dict):
            from pet_core.commands import validate
            cmd = validate(cmd)
        if not isinstance(cmd, PetCommand) or cmd.is_empty():
            return
        self._cmd_queue.append(cmd)
        if not self._queue_timer.isActive():
            self._queue_timer.start()
            # Process first item immediately
            QTimer.singleShot(0, self._process_cmd_queue)

    def _process_cmd_queue(self):
        """Pop and play the next queued command."""
        try:
            if not self._cmd_queue:
                self._queue_timer.stop()
                return
            cmd = self._cmd_queue.pop(0)
            self._apply_command(cmd)
        except Exception as e:
            print(f"[Pet] Queue error: {e}")

    def _switch_model(self, model_id: str):
        """Switch the LLM model and update conf.yaml."""
        print(f"[Pet] Switching LLM model to: {model_id}")
        self._current_model = model_id
        # Update conf.yaml
        conf_path = OPEN_LLM_VTUBER_DIR / "conf.yaml"
        try:
            content = conf_path.read_text(encoding="utf-8")
            idx = content.find("ollama_llm:")
            if idx > 0:
                after = content[idx:]
                import re
                match = re.search(r"(model:\s*)'[^']*'", after)
                if match:
                    start = idx + match.start() + len(match.group(1))
                    before = content[:start]
                    after_end = content[start + len(match.group(0)) - len(match.group(1)):]
                    content = f"{before}'{model_id}'{after_end}"
                    conf_path.write_text(content, encoding="utf-8")
                    print(f"[Pet] conf.yaml updated: model='{model_id}'")
        except Exception as e:
            print(f"[Pet] Failed to update conf.yaml: {e}")

        self._rebuild_tray_menu()
        self._webview.reload()

    # ── Model Scale ──────────────────────────────────────
    def _set_model_scale(self, factor: float):
        """Set absolute scale for current Live2D model (keeps current offset)."""
        factor = max(self._model_scale_min, min(self._model_scale_max, factor))
        factor = round(factor, 2)
        self._scale_bar.set_scale_pct(int(factor * 100))
        # Save immediately so the value persists
        offset = self._model_offsets.get(self._current_l2d, [0, 0])
        self._model_scales[self._current_l2d] = factor
        self._save_model_scales()
        # Try immediate apply, fall back to polling if canvas not ready
        js_check = f"""
        (function() {{
            var r = window.__petSetModelScale && window.__petSetModelScale({factor}, {offset[0]}, {offset[1]});
            if (r && r.status === 'ok') {{
                return 'ok';
            }}
            window.__petStartScalePolling && window.__petStartScalePolling({factor}, {offset[0]}, {offset[1]}, 30);
            return r ? r.status + ':' + r.reason : 'no-fn';
        }})()
        """
        def _on_result(r):
            status = str(r)[:30] if r else 'None'
            print(f"[Pet] Scale set: {factor} → {status}")
            if r == 'ok':
                self._bubble.show_text(f"模型大小: {int(factor * 100)}%", [])
            elif r and isinstance(r, str) and 'wait' in r:
                self._bubble.show_text(f"缩放已排入队列: {int(factor * 100)}%", [])
        self._webview.page().runJavaScript(js_check, _on_result)

    def _scale_model_up(self):
        current = self._model_scales.get(self._current_l2d, 1.0)
        self._set_model_scale(current + self._model_scale_step)

    def _scale_model_down(self):
        current = self._model_scales.get(self._current_l2d, 1.0)
        self._set_model_scale(current - self._model_scale_step)

    def _apply_saved_scale(self):
        """Apply saved scale + position offset for current Live2D model."""
        factor = self._model_scales.get(self._current_l2d)
        if factor is None:
            self._scale_bar.set_scale_pct(100)
            factor = 1.0
        else:
            self._scale_bar.set_scale_pct(int(factor * 100))
        offset = self._model_offsets.get(self._current_l2d, [0, 0])
        # Use JS polling — retries every 500ms up to 30 times (15s)
        js = f"window.__petStartScalePolling && window.__petStartScalePolling({factor}, {offset[0]}, {offset[1]}, 30);"
        self._webview.page().runJavaScript(js)
        print(f"[Pet] Applying saved transform: scale={factor} offset=({offset[0]},{offset[1]}) for {self._current_l2d}")
        self._webview.page().runJavaScript(js, _on_result)

    def _save_model_scales(self):
        """Persist model_scales to config/settings.json."""
        settings_path = BASE_DIR / "config" / "settings.json"
        try:
            data = {}
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["model_scales"] = self._model_scales
            data["model_offsets"] = self._model_offsets
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Pet] Failed to save model scales: {e}")

    def _nudge_model(self, dx=0, dy=0, reset=False):
        """Adjust the Live2D model position within the window."""
        key = self._current_l2d
        current = self._model_offsets.get(key, [0, 0])
        if reset:
            new_pos = [0, 0]
            label = "已重置居中"
        else:
            new_pos = [current[0] + dx, current[1] + dy]
            label = f"位置: ({new_pos[0]}, {new_pos[1]})"
        self._model_offsets[key] = new_pos
        self._save_model_scales()
        self._rebuild_tray_menu()
        js = f"window.__petSetModelPosition({new_pos[0]}, {new_pos[1]});"
        self._webview.page().runJavaScript(js, lambda r: print(f"[Pet] Position set: {new_pos} → {r}"))
        self._bubble.show_text(label, [])

    def _get_categorized_models(self, l2d_models: list[str]) -> dict[str, list[str]]:
        """Group Live2D models by category from model_dict.json."""
        cat_map: dict[str, list[str]] = {}
        # Read model_dict.json for category metadata
        import json
        model_dict_path = OPEN_LLM_VTUBER_DIR / "model_dict.json"
        if model_dict_path.exists():
            try:
                model_dict = json.loads(model_dict_path.read_text(encoding="utf-8"))
                for entry in model_dict:
                    name = entry.get("name", "")
                    if name in l2d_models:
                        cat = entry.get("category", "other")
                        cat_map.setdefault(cat, []).append(name)
            except Exception:
                pass
        return cat_map

    def _download_more_models(self):
        """Open the model downloader in a background process."""
        self._bubble.show_text("正在后台下载模型...\n请稍后刷新菜单查看新模型", [])
        import subprocess, sys
        script = BASE_DIR / "scripts" / "download_models.py"
        if script.exists():
            subprocess.Popen(
                [sys.executable, str(script), "--force"],
                cwd=str(BASE_DIR),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        else:
            self._bubble.show_text("下载脚本不存在", [])

    def _discover_l2d_models(self) -> list[str]:
        """Scan live2d-models directory and return available model folder names.

        Only returns models that have:
        - A character config YAML in the characters directory
        - At least one .model3.json / .model.json file
        - At least one .png texture file (otherwise model can't render)
        """
        l2d_dir = OPEN_LLM_VTUBER_DIR / "live2d-models"
        if not l2d_dir.is_dir():
            return ["mao_pro"]
        models = []
        for d in sorted(l2d_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            # Must have a character config YAML
            if not (CHARACTERS_DIR / f"{d.name}.yaml").exists():
                continue
            # Must contain at least one Live2D model file
            has_model = any(d.rglob("*.model3.json")) or any(d.rglob("*.model.json"))
            if not has_model:
                continue
            # Must have at least one texture file (PNG)
            has_texture = any(d.rglob("*.png"))
            if not has_texture:
                print(f"[Pet] Skipping {d.name}: no texture files")
                continue
            models.append(d.name)
        return models if models else ["mao_pro"]

    def _switch_l2d(self, model_id: str, _retry: int = 0):
        config_file = f"{model_id}.yaml"
        char_path = CHARACTERS_DIR / config_file
        if not char_path.exists():
            print(f"[Pet] Character config not found for: {model_id}")
            self._bubble.show_text(f"模型配置不存在: {model_id}", [])
            return
        self._current_l2d = model_id
        self._rebuild_tray_menu()
        print(f"[Pet] Switching Live2D model to: {model_id}")

        self._bubble.show_text(f"正在切换模型: {model_id}...", [])
        self._pending_l2d_switch = model_id
        self._l2d_needs_manual_apply = False

        # First diagnose: is the WS monkey-patch active?
        diag_js = r"""
        (function() {
            return JSON.stringify({
                injected: !!window.__petInjected,
                wsCount: (window.__petWsInstances || []).length,
                hasSwitch: !!window.__petSwitchConfig,
                urls: (window.__petWsInstances || []).map(function(w) {
                    return (w.url||'?') + ' state=' + w.readyState;
                })
            });
        })()
        """
        def _on_diag(diag_str):
            try:
                diag = json.loads(diag_str) if diag_str else {}
            except Exception:
                diag = {"raw": str(diag_str)}
            print(f"[Pet] WS diag: {diag}")

            msg = json.dumps({'type': 'switch-config', 'file': config_file})
            code = f"window.__petSwitchConfig && window.__petSwitchConfig({msg});"
            def _on_switch_result(r):
                print(f"[Pet] L2D switch result: {r}")
                if r in ('ws-closed', 'no-fn'):
                    self._bubble.show_text("后端未连接，无法切换模型", [])
                    self._pending_l2d_switch = None
                    return
                if r == 'no-frontend-ws':
                    if _retry < 3:
                        delay = 2000 * (_retry + 1)
                        print(f"[Pet] Frontend WS not ready, retry { _retry + 1}/3 in {delay}ms")
                        QTimer.singleShot(delay, lambda: self._switch_l2d(model_id, _retry + 1))
                    else:
                        self._bubble.show_text("前端连接超时，请刷新页面后重试", [])
                        self._pending_l2d_switch = None
                    return
                self._l2d_switch_timer.start(10000)
            self._webview.page().runJavaScript(code, _on_switch_result)

        self._webview.page().runJavaScript(diag_js, _on_diag)

    def _apply_l2d_switch(self, model_info=None):
        """Apply Live2D model switch when frontend WS wasn't available.

        Since parseModelUrl/updateModelConfig are internal React module functions
        (not window globals), we re-dispatch the set-model-and-conf message
        through any captured frontend WS so the React app handles it natively.
        Falls back to page reload if no frontend WS is available.
        """
        try:
            if not model_info:
                print("[Pet] _apply_l2d_switch: no model_info")
                self._pending_l2d_switch = None
                return

            # Ensure URL is absolute
            if model_info.get("url") and not model_info["url"].startswith("http"):
                model_info["url"] = BACKEND_URL + model_info["url"]

            raw_msg = json.dumps({"type": "set-model-and-conf", "model_info": model_info})

            # Try to dispatch through a captured frontend WS instance
            fwd_js = f"""
                (function() {{
                    var msg = {json.dumps(raw_msg)};
                    var instances = window.__petWsInstances || [];
                    for (var i = 0; i < instances.length; i++) {{
                        var ws = instances[i];
                        if (ws.readyState === 1) {{
                            try {{
                                var evt = new MessageEvent('message', {{data: msg}});
                                ws.dispatchEvent(evt);
                                console.log('[Pet] Dispatched set-model-and-conf to frontend WS');
                                return 'dispatched';
                            }} catch(e) {{
                                console.warn('[Pet] dispatchEvent failed: ' + e.message);
                            }}
                        }}
                    }}
                    return 'no-ws';
                }})()
            """
            def _on_fwd(r):
                if r == 'dispatched':
                    print(f"[Pet] Model switch forwarded to React frontend")
                else:
                    # No frontend WS available — reload so backend re-sends on connect
                    print("[Pet] No frontend WS, reloading page for model switch...")
                    self._bubble.show_text("正在重新加载模型...", [])
                    QTimer.singleShot(500, self._webview.reload)
            self._webview.page().runJavaScript(fwd_js, _on_fwd)

        except Exception as e:
            print(f"[Pet] Failed to apply L2D switch: {e}")
            self._bubble.show_text(f"模型切换异常: {e}", [])
            self._pending_l2d_switch = None

    def _on_l2d_switch_timeout(self):
        """Handle model switch timeout (10s)."""
        model_id = self._pending_l2d_switch
        if not model_id:
            return
        print(f"[Pet] L2D switch timeout for: {model_id}")
        self._bubble.show_text(f"模型切换超时: {model_id}", [])
        self._pending_l2d_switch = None
        self._l2d_needs_manual_apply = False

    def _verify_l2d_switch(self):
        """Verify the Live2D model actually loaded."""
        model_id = self._pending_l2d_switch
        if not model_id:
            return
        js = """
            (function() {
                try {
                    var adapter = window.getLAppAdapter && window.getLAppAdapter();
                    if (!adapter) return 'no-adapter';
                    var model = adapter.getModel();
                    if (!model) return 'no-model';
                    var canvas = document.querySelector('canvas');
                    if (!canvas || canvas.width === 0) return 'no-canvas';
                    // Check if WebGL context is valid
                    var gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                    var glOk = gl && !gl.isContextLost();
                    // Check React app's stored model info
                    var stored = null;
                    try { stored = JSON.parse(localStorage.getItem('modelInfo')); } catch(e) {}
                    var storedUrl = stored ? (stored.url || '').split('/').pop() : 'unknown';
                    // Check model name from adapter
                    var modelName = adapter.live2d_model_name || adapter._modelName || 'unknown';
                    return JSON.stringify({
                        status: 'ok',
                        glOk: glOk,
                        canvasW: canvas.width,
                        canvasH: canvas.height,
                        storedUrl: storedUrl,
                        modelName: modelName
                    });
                } catch(e) {
                    return 'error:' + e.message;
                }
            })();
        """
        def _on_verify(result):
            print(f"[Pet] L2D verify raw: {result}")
            if result and result.startswith('{'):
                try:
                    info = json.loads(result)
                    print(f"[Pet] L2D verify: glOk={info.get('glOk')} canvas={info.get('canvasW')}x{info.get('canvasH')} stored={info.get('storedUrl')} model={info.get('modelName')}")
                except Exception:
                    pass
            if result and ('ok' in result):
                print(f"[Pet] L2D model verified: {model_id}")
                self._bubble.show_text(f"模型已切换: {model_id}", [])
                # Apply saved scale after model loads
                QTimer.singleShot(500, self._apply_saved_scale)
            else:
                print(f"[Pet] L2D model verification failed: {result}")
                self._bubble.show_text(f"模型切换可能失败: {model_id}", [])
            self._pending_l2d_switch = None
            self._pending_model_info = None
        self._webview.page().runJavaScript(js, _on_verify)

    def _cycle_l2d_model(self):
        """Cycle between available Live2D models."""
        models = self._discover_l2d_models()
        try:
            idx = models.index(self._current_l2d)
            nxt = models[(idx + 1) % len(models)]
        except ValueError:
            nxt = models[0]
        self._current_l2d = nxt
        self._switch_l2d(nxt)

    def _restart_backend(self):
        print("[Pet] Restarting backend...")
        try:
            import subprocess
            subprocess.run(
                ['taskkill', '/f', '/fi', 'IMAGENAME eq python.exe', '/fi', 'MEMUSAGE gt 200000'],
                capture_output=True, timeout=10
            )
        except Exception:
            pass

        import subprocess
        env = os.environ.copy()
        env["NO_PROXY"] = "localhost,127.0.0.1,::1,.local"
        env["no_proxy"] = "localhost,127.0.0.1,::1,.local"
        subprocess.Popen(
            ["uv", "run", "run_server.py"],
            cwd=str(OPEN_LLM_VTUBER_DIR),
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            if sys.platform == "win32" else 0,
        )
        print("[Pet] Backend starting...")

        # Poll until ready then reload
        self._poll_backend()

    def _poll_backend(self, attempts=0):
        import urllib.request
        if attempts > 30:
            print("[Pet] Backend startup timed out")
            return
        try:
            req = urllib.request.Request(BACKEND_URL, headers={"User-Agent": "Pet/1.0"})
            urllib.request.urlopen(req, timeout=2)
            print("[Pet] Backend ready, reloading...")
            self._webview.reload()
        except Exception:
            QTimer.singleShot(2000, lambda: self._poll_backend(attempts + 1))

    def _quit(self):
        self._unregister_hotkeys()
        self._save_state()
        print(f"[Pet] State saved: hunger={self._pet_state.hunger:.0f} "
              f"level={self._pet_state.level}")
        self._tray.hide()
        QApplication.quit()

    # ── Window dragging (frameless, works through WebView + overlays) ─
    _CLICK_EXPRESSIONS = ["happy", "shy", "surprised", "love", "wink"]

    def _on_click_pet(self):
        """Trigger a random interactive reaction when clicking the pet."""
        import random
        expr = random.choice(self._CLICK_EXPRESSIONS)
        js = f"window.__petSetExpressionByName({json.dumps(expr)});"
        self._webview.page().runJavaScript(js, self._log_js_result)
        self._send_l2d_motion("")

    def eventFilter(self, obj, event):
        # Handle dragging from self (PetWindow) or self._webview
        if obj is self or obj is self._webview:
            # In click-through mode, only respond when Ctrl is held
            ctrl_held = False
            try:
                app = QApplication.instance()
                if app:
                    mods = app.keyboardModifiers()
                    ctrl_held = bool(mods & Qt.ControlModifier)
            except Exception:
                pass

            allow = not self._click_through or ctrl_held

            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    if allow:
                        self._on_click_pet()
                        self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return allow
                elif event.button() == Qt.RightButton:
                    if allow and self._tray and self._tray.contextMenu():
                        self._tray.contextMenu().popup(event.globalPosition().toPoint())
                    return allow
            elif event.type() == QEvent.MouseMove:
                if self._drag_pos is not None:
                    self.move(event.globalPosition().toPoint() - self._drag_pos)
                    return True
                return False
            elif event.type() == QEvent.MouseButtonRelease:
                if self._drag_pos is not None:
                    self._drag_pos = None
                    return True
                return False
        return super().eventFilter(obj, event)

    # ── Mouse event overrides for extra drag reliability ──
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._click_through:
                self._on_click_pet()
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        elif event.button() == Qt.RightButton and not self._click_through:
            if self._tray and self._tray.contextMenu():
                self._tray.contextMenu().popup(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and not self._click_through:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ── Global hotkeys (Win32 RegisterHotKey) ─────────────
    def _toggle_chat_safe(self):
        QTimer.singleShot(0, self._activate_chat)

    def _toggle_visible_safe(self):
        QTimer.singleShot(0, self._toggle_visible)

    def _cycle_l2d_safe(self):
        QTimer.singleShot(0, self._cycle_l2d_model)

    def _setup_hotkeys(self):
        if sys.platform == "win32":
            self._setup_hotkeys_win32()
        else:
            self._setup_hotkeys_pynput()

    def _setup_hotkeys_win32(self):
        """Register global hotkeys via Win32 RegisterHotKey API (most reliable)."""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            MOD_CONTROL = 0x0002
            MOD_SHIFT = 0x0004
            MOD_NOREPEAT = 0x4000
            mods = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT

            # Virtual key codes
            VK_SPACE = 0x20
            VK_H = 0x48
            VK_L = 0x4C
            VK_OEM_PLUS = 0xBB   # =/+ key
            VK_OEM_MINUS = 0xBD  # -/_ key
            VK_UP = 0x26
            VK_DOWN = 0x28
            VK_LEFT = 0x25
            VK_RIGHT = 0x27
            VK_R = 0x52  # Reset position
            NUDGE = 10

            bindings = [
                (1, mods, VK_SPACE,      self._toggle_chat_safe,     "Chat"),
                (2, mods, VK_H,           self._toggle_visible_safe, "Show/Hide"),
                (3, mods, VK_L,           self._cycle_l2d_safe,      "Switch L2D"),
                (4, mods, VK_OEM_PLUS,    self._scale_bar.toggle,    "Scale Bar"),
                (5, mods, VK_OEM_MINUS,   self._scale_bar.toggle,    "Scale Bar"),
                # Position nudge: Ctrl+Shift+Arrow
                (6, mods, VK_UP,     lambda: self._nudge_model(0, -NUDGE), "Nudge Up"),
                (7, mods, VK_DOWN,   lambda: self._nudge_model(0, NUDGE),  "Nudge Down"),
                (8, mods, VK_LEFT,   lambda: self._nudge_model(-NUDGE, 0), "Nudge Left"),
                (9, mods, VK_RIGHT,  lambda: self._nudge_model(NUDGE, 0),  "Nudge Right"),
                (10, mods, VK_R,     lambda: self._nudge_model(reset=True), "Reset Position"),
            ]

            # Unregister first in case they were registered previously
            for hk_id, mod, vk, action, _name in bindings:
                ctypes.windll.user32.UnregisterHotKey(
                    wintypes.HWND(hwnd), hk_id
                )

            self._hotkey_actions = {}
            for hk_id, mod, vk, action, _name in bindings:
                ok = ctypes.windll.user32.RegisterHotKey(
                    wintypes.HWND(hwnd), hk_id, mod, vk
                )
                if ok:
                    self._hotkey_actions[hk_id] = action
                else:
                    err = ctypes.GetLastError()
                    print(f"[Pet] Win32 hotkey registration failed: {_name} (err={err})")

            if self._hotkey_actions:
                print("[Pet] Global hotkeys active (Win32): Ctrl+Shift+Space=Chat, Ctrl+Shift+H=Show/Hide, Ctrl+Shift+L=Switch L2D, Ctrl+Shift+=/-=Scale")
            else:
                print("[Pet] No Win32 hotkeys registered, trying pynput...")
                self._setup_hotkeys_pynput()
        except Exception as e:
            print(f"[Pet] Win32 hotkey init failed: {e}, trying pynput...")
            self._setup_hotkeys_pynput()

    def nativeEvent(self, eventType, message):
        """Catch WM_HOTKEY (0x0312) from Win32 RegisterHotKey."""
        if sys.platform == "win32" and self._hotkey_actions:
            try:
                import ctypes
                # PySide6 passes message as a shiboken pointer; convert to int
                ptr = int(message)
                msg = ctypes.wintypes.MSG.from_address(ptr)
                if msg.message == 0x0312:  # WM_HOTKEY
                    action = self._hotkey_actions.get(msg.wParam)
                    if action:
                        action()
                        return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _setup_hotkeys_pynput(self):
        """Fallback: pynput listener for non-Windows or if Win32 fails."""
        try:
            from pynput import keyboard as pkb

            _ctrl = [False]
            _shift = [False]

            def on_press(key):
                try:
                    if key in (pkb.Key.ctrl_l, pkb.Key.ctrl_r):
                        _ctrl[0] = True
                    if key in (pkb.Key.shift_l, pkb.Key.shift_r):
                        _shift[0] = True
                    if not (_ctrl[0] and _shift[0]):
                        return
                    if key == pkb.Key.space:
                        self._toggle_chat_safe()
                    elif hasattr(key, 'char') and key.char == 'h':
                        self._toggle_visible_safe()
                    elif hasattr(key, 'char') and key.char == 'l':
                        self._cycle_l2d_safe()
                    elif hasattr(key, 'char') and key.char == '=':
                        self._scale_bar.toggle()
                    elif hasattr(key, 'char') and key.char == '-':
                        self._scale_bar.toggle()
                except Exception:
                    pass

            def on_release(key):
                try:
                    if key in (pkb.Key.ctrl_l, pkb.Key.ctrl_r):
                        _ctrl[0] = False
                    if key in (pkb.Key.shift_l, pkb.Key.shift_r):
                        _shift[0] = False
                except Exception:
                    pass

            listener = pkb.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
            print("[Pet] Global hotkeys active via pynput (Ctrl+Shift+Space=Chat, Ctrl+Shift+H=Show/Hide, Ctrl+Shift+L=Switch L2D, Ctrl+Shift+=/-=Scale)")
        except Exception as e:
            print(f"[Pet] All hotkey methods failed: {e}")

    def _unregister_hotkeys(self):
        """Unregister Win32 hotkeys on exit to avoid stale registrations."""
        if sys.platform != "win32" or not self._hotkey_actions:
            return
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self.winId())
            for hk_id in self._hotkey_actions:
                ctypes.windll.user32.UnregisterHotKey(wintypes.HWND(hwnd), hk_id)
            self._hotkey_actions.clear()
        except Exception:
            pass

    def _activate_chat(self):
        self.show()
        self.raise_()
        self._chatbar.toggle()

    # ── Window positioning ───────────────────────────────
    def _position_window(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - PET_WIDTH - 30
            y = geo.bottom() - PET_HEIGHT - 30
            self.move(x, y)
            print(f"[Pet] Window at {x}, {y}")


# ═══════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════
def main():
    # Qt WebEngine needs this on Windows before QApplication
    if sys.platform == "win32":
        try:
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    pet = PetWindow()
    pet.show()

    # Defer hotkey registration until Qt event loop is running
    QTimer.singleShot(500, pet._setup_hotkeys)

    print("[Pet] ========================================")
    print("[Pet]  喵酱 Live2D Desktop Pet Ready!")
    print("[Pet]  Ctrl+Shift+Space = Quick Chat")
    print("[Pet]  Ctrl+Shift+H     = Show / Hide")
    print("[Pet]  Ctrl+Shift+L     = Switch Live2D Model")
    print("[Pet]  Ctrl+Shift+=/-   = Adjust Model Scale")
    print("[Pet]  Ctrl+Shift+↑↓←→ = Nudge Model Position")
    print("[Pet]  Ctrl+Shift+R     = Reset Position")
    print("[Pet]  Right-click tray = Full menu")
    print("[Pet] ========================================")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
