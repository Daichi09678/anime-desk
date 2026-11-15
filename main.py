#!/usr/bin/env python3
"""
Frieren 2D Interactive Desktop Companion & Codex Agent (macOS)
Ultra-lightweight transparent borderless window for MacBook Air 2015 (8GB RAM).

Features:
- Borderless, transparent, always-on-top window docked at bottom-right above macOS Dock.
- Dynamic click-through outside Frieren's sprite, speech bubble, and input bar.
- 4 2D expression states (`idle`, `thinking`, `talking`, `pleased`) with smooth 2D cross-fade.
- Custom lightweight 2D Loading Spinner with live Codex command status while thinking.
- Motion typing (typewriter) with toggleable soft anime sound effects (native ObjC NSSound).
- Scrollable Chat History (`📜`) AND Scrollable/Copyable Codex CLI Output Drawer (`💻`).
- Long-Term Memory (`long_term_memory.json` + `frieren_notes.md`) synced to selectable Google Drive.
- Toggleable Agent Execution Mode (`⚡` - open web/URLs, run shell/code via `gpt-6-luna`).
- Minimize Mode (`—` button: collapses to tiny floating orb or hides to Menu Bar without quitting).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import html
import math
import logging
from logging.handlers import RotatingFileHandler
import random
import re
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QRegion,
    QShortcut,
    QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QSizeGrip,
)

from codex_backend import CodexBackend, CodexResult
from ai_workers import CodexWorker, DiscoveryWorker
from chat_panel import ChatPanel
from chat_widgets import AttachmentList, ChatInputBox, local_path_candidates
from character_profiles import PROFILES, EXPRESSION_LABELS, EXPRESSION_STATES, get_profile
from character_theme import theme_styles
from character_voice import VoiceBank, VoiceController, VoiceDialog
from character_voice import VoiceClip
from speech_synthesis import NarrationWorker, narration_text
from clone_service import clone_service
from scene_theme import SceneSurface, SceneMenu
from character_widget import FrierenSpriteWidget
from needs_manager import NeedsManager
from sprite_helper import PLEASED_POSES, TALKING_POSES, THINKING_POSES, ensure_sprites


# ---------------------------------------------------------------------------
# Natural & Cozy Emotion / Feeling System (No negative/punitive mechanics)
# ---------------------------------------------------------------------------
EMOTION_CATALOG: Dict[str, tuple[str, str]] = {
    "tenang": ("🌿 Tenang", "Damai & rileks menemanimu di meja kerja"),
    "hangat": ("☕ Hangat", "Nyaman menemani harimu"),
    "senang": ("🌸 Senang", "Bahagia bisa mengobrol dan membantumu hari ini"),
    "ceria": ("🎶 Ceria", "Hati sedang riang sambil bersenandung kecil ♪"),
    "antusias": ("✨ Antusias", "Bersemangat mencari tahu & merapal sihir untukmu!"),
    "penasaran": ("🔍 Penasaran", "Tertarik mempelajari hal baru bersamamu"),
    "fokus": ("📖 Fokus", "Konsentrasi penuh membaca grimoire & catatan"),
    "tersentuh": ("🤍 Tersentuh", "Merasa disayangi & dihargai olehmu"),
    "nostalgia": ("💭 Nostalgia", "Terkenang petualangan indah di masa lalu"),
    "mengantuk": ("💤 Mengantuk Manja", "Mata agak berat karena suasananya terlalu nyaman~"),
}

STATE_DEFAULT_EMOTION: Dict[str, str] = {
    "idle": "tenang",
    "idle_cozy": "hangat",
    "idle_sleepy": "mengantuk",
    "idle_reading": "fokus",
    "idle_dancing": "ceria",
    "idle_tea": "hangat",
    "thinking": "fokus",
    "thinking_lookup": "nostalgia",
    "thinking_tilt": "penasaran",
    "thinking_hmmm": "penasaran",
    "action_laptop": "antusias",
    "action_magic": "antusias",
    "talking": "senang",
    "talking_explain": "antusias",
    "pleased": "tersentuh",
    "pleased_wave": "ceria",
    "needs_tea": "hangat",
    "needs_hungry": "penasaran",
    "needs_sleepy": "mengantuk",
    "needs_stretch": "antusias",
    "sleeping": "mengantuk",
    "sleepy_yawn": "mengantuk",
}


# ---------------------------------------------------------------------------
# Cute Thinking Statuses & 36 Varied Tap/Click Dialogues for Frieren
# ---------------------------------------------------------------------------
CUTE_THINKING_LINES = [
    "Hmm, tunggu sebentar ya, lagi kupikirkan... ✦",
    "Sedang membolak-balik halaman grimoire... ♪",
    "Emm... lagi merangkai kata-kata yang pas buatmu~",
    "Sebentar ya, Frieren lagi mikir keras nih... (・ω・)",
    "Lagi mengingat-ingat mantra yang cocok... ✦",
    "Hmm... menarik, coba kupikirkan dulu ya~",
    "Tunggu sebentar, telinga elfku lagi fokus... ♪",
    "Sedang merapikan catatan sihir sebentar... ✦",
    "Ehehe, sabar ya, lagi kucari jawabannya~",
    "Hmm... kira-kira gimana ya bagusnya... ♪",
]

PET_QUOTES = [
    "Hehe... terima kasih sudah menyapaku. Syal merah ini hangat sekali, semangat ya kerjanya hari ini!",
    "Hmm? Kamu memanggilku? Aku selalu di sini kok menemanimu.",
    "Jangan lupa minum air putih ya. Perjalanan panjang butuh tubuh yang sehat.",
    "Kepang rambutku rapi kan hari ini? Aku butuh waktu agak lama menyisirnya tadi pagi.",
    "Kalau lelah, istirahat sebentar tidak apa-apa. Bahkan petualang pun butuh duduk di dekat api unggun.",
    "Ada mantra sederhana untuk membuat teh terasa lebih hangat... mau kubuatkan?",
    "Telinga elfku bisa mendengar suara ketikan keyboardmu, ritmenya menenangkan sekali.",
    "Jangan begadang terlalu malam ya... nanti susah bangun pagi sepertiku, hehe.",
    "Himmel dulu pernah bilang, hal kecil yang dikerjakan hari ini akan jadi kenangan berharga nanti.",
    "Sweter rajut ini nyaman sekali... rasanya jadi agak mengantuk kalau udaranya sejuk begini.",
    "Kalau ada kode atau pekerjaan yang rumit, ceritakan saja padaku. Kita urai pelan-pelan bersama.",
    "Ehehe... geli tahu kalau diklik terus, tapi aku senang kamu memperhatikanku ♪",
    "Sedang sibuk ya? Aku duduk tenang di pojok sini sambil membaca grimoire kok.",
    "Kadang berhenti sejenak dan menarik napas dalam-dalam itu bagian dari sihir penenang terbaik.",
    "Aku suka suasana meja kerjamu hari ini. Rasanya damai dan fokus.",
    "Jangan lupa regangkan bahu dan punggungmu sebentar ya, sudah cukup lama kamu menatap layar.",
    "Waktu seribu tahun itu singkat bagi elf, tapi waktumu hari ini sangat berharga. Semangat ya!",
    "Kalau menemukan grimoire langka atau ide baru, jangan lupa catat di memoriku ya.",
    "Hmm... kira-kira camilan manis apa yang enak untuk menemani kerja sore ini ya?",
    "Fern pasti akan mengomeliku kalau tahu aku sempat mengantuk di pojok layarmu, hehe...",
    "Sihir favoritku? Sihir yang menumbuhkan padang bunga... dan sihir kecil untuk membantumu bekerja.",
    "Pelan-pelan saja mengerjakannya, satu langkah kecil tetap membawamu lebih dekat ke tujuan.",
    "Anting merah ini? Ini salah satu benda kesayanganku, cocok kan dengan syalku?",
    "Kamu sudah bekerja keras hari ini. Aku bangga melihat ketekunanmu dari sini ✦",
    "Kalau butuh membuka web atau mencari sesuatu, tinggal panggil aku dengan shortcut keyboard ya!",
    "Udara di sekitar sini terasa hangat... mungkin karena kamu sedang semangat bekerja.",
    "Hmm~ tadi aku hampir tertidur sambil memeluk syal, untung kamu menyapaku.",
    "Tidak semua hal harus selesai dalam satu kedipan mata. Nikmati prosesnya ya.",
    "Kalau kepalamu mulai penuh, coba tulis hal pentingnya agar aku yang menyimpannya untukmu.",
    "Lihat deh, aku bisa ganti-ganti gaya duduk kalau lagi santai... perhatikan ya ♪",
    "Semoga hari ini berjalan lancar tanpa bug yang menyebalkan untukmu!",
    "Hati-hati jangan sampai terhisap mimic ya... eh, maksudku jangan sampai terdistraksi hal aneh, hehe.",
    "Senang rasanya punya teman ngobrol di meja kerja seperti ini.",
    "Aku sudah siap kapan pun kamu butuh bantuan. Panggil saja namaku ya!",
    "Bintang-bintang di luar sana indah, tapi cahaya layarmu juga penuh dengan karya yang keren.",
    "Tarik napas pelan... hembuskan... nah, sekarang ayo kita lanjutkan dengan hati tenang ✦",
]


# ---------------------------------------------------------------------------
# macOS Carbon Global Hotkey (Cmd + Shift + Space) - Zero CPU Polling
# ---------------------------------------------------------------------------
kEventClassKeyboard = 0x6B657962  # 'keyb'
kEventHotKeyPressed = 5
cmdKey = 1 << 8
shiftKey = 1 << 9
kVK_Space = 0x31


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


EventHandlerProcPtr = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class MacGlobalHotKey:
    """Registers a native macOS Carbon global hotkey (Cmd+Shift+Space)."""

    def __init__(self, callback) -> None:
        self.callback = callback
        self._handler_ref = None
        self._hotkey_ref = ctypes.c_void_p()
        self._c_callback = None
        self._install()

    def _install(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            carbon_path = ctypes.util.find_library("Carbon")
            if not carbon_path:
                return
            self.carbon = ctypes.cdll.LoadLibrary(carbon_path)

            def _handler(next_handler, event, user_data):
                QTimer.singleShot(0, self.callback)
                return 0

            self._c_callback = EventHandlerProcPtr(_handler)
            spec = EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)

            self.carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            target = self.carbon.GetApplicationEventTarget()

            handler_ref = ctypes.c_void_p()
            self.carbon.InstallEventHandler(
                ctypes.c_void_p(target),
                self._c_callback,
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(handler_ref),
            )
            self._handler_ref = handler_ref

            hk_id = EventHotKeyID(0x46524E31, 1)  # 'FRN1'
            self.carbon.RegisterEventHotKey(
                ctypes.c_uint32(kVK_Space),
                ctypes.c_uint32(cmdKey | shiftKey),
                hk_id,
                ctypes.c_void_p(target),
                ctypes.c_uint32(0),
                ctypes.byref(self._hotkey_ref),
            )
        except Exception:
            pass


class WinGlobalHotKey(QAbstractNativeEventFilter):
    """Registers a native Windows global hotkey (Ctrl+Shift+Space) via Win32 RegisterHotKey."""

    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback
        self.registered = False
        self._hotkey_id = 9001
        self._install()

    def _install(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from ctypes import wintypes

            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                ]

            self._msg_cls = MSG
            self._wm_hotkey = 0x0312
            MOD_CONTROL = 0x0002
            MOD_SHIFT = 0x0004
            MOD_NOREPEAT = 0x4000
            VK_SPACE = 0x20

            self.user32 = ctypes.windll.user32
            res = self.user32.RegisterHotKey(
                None,
                self._hotkey_id,
                MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
                VK_SPACE,
            )
            if res:
                self.registered = True
                app = QCoreApplication.instance()
                if app:
                    app.installNativeEventFilter(self)
        except Exception:
            pass

    def nativeEventFilter(self, eventType, message):
        if self.registered and eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                msg = self._msg_cls.from_address(int(message))
                if msg.message == self._wm_hotkey and msg.wParam == self._hotkey_id:
                    QTimer.singleShot(0, self.callback)
                    return True, 0
            except Exception:
                pass
        return False, 0

    def unregister(self) -> None:
        if self.registered and sys.platform == "win32":
            try:
                self.user32.UnregisterHotKey(None, self._hotkey_id)
            except Exception:
                pass
            self.registered = False


# ---------------------------------------------------------------------------
# Ultra-lightweight Soft Anime Typing Sound Synthesizer & Player (Native ObjC)
# ---------------------------------------------------------------------------
class TypingSoundPlayer:
    """Generates tiny 3KB soft sine-chime WAVs and plays them via native ObjC NSSound."""

    def __init__(self, assets_dir: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self.sounds_dir = assets_dir / "sounds"
        self.sounds_dir.mkdir(parents=True, exist_ok=True)
        self.effects: list[int] = []
        self._idx = 0
        self._objc = None
        self._sel_is_playing = None
        self._sel_stop = None
        self._sel_play = None
        self._init_sounds()

    def _init_sounds(self) -> None:
        freqs = (587.33, 659.25, 783.99)
        for i, freq in enumerate(freqs):
            wav_path = self.sounds_dir / f"blip_{i}.wav"
            if not wav_path.exists():
                self._write_blip_wav(wav_path, freq)

        if sys.platform == "win32":
            # Native Windows winsound player support
            try:
                import winsound
                self._winsound = winsound
            except Exception:
                pass
            return

        if sys.platform != "darwin":
            return
        try:
            objc_path = ctypes.util.find_library("objc")
            appkit_path = ctypes.util.find_library("AppKit")
            if not objc_path or not appkit_path:
                return
            ctypes.cdll.LoadLibrary(appkit_path)
            objc = ctypes.cdll.LoadLibrary(objc_path)

            objc.objc_getClass.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]

            msg = objc.objc_msgSend
            self._objc = objc

            ns_string_cls = objc.objc_getClass(b"NSString")
            ns_sound_cls = objc.objc_getClass(b"NSSound")
            sel_str_utf8 = objc.sel_registerName(b"stringWithUTF8String:")
            sel_alloc = objc.sel_registerName(b"alloc")
            sel_init_file = objc.sel_registerName(b"initWithContentsOfFile:byReference:")
            sel_set_vol = objc.sel_registerName(b"setVolume:")
            self._sel_is_playing = objc.sel_registerName(b"isPlaying")
            self._sel_stop = objc.sel_registerName(b"stop")
            self._sel_play = objc.sel_registerName(b"play")

            for i in range(len(freqs)):
                wav_bytes = str(self.sounds_dir / f"blip_{i}.wav").encode("utf-8")
                msg.restype = ctypes.c_void_p
                msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
                ns_path = msg(ns_string_cls, sel_str_utf8, wav_bytes)

                msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                snd_alloc = msg(ns_sound_cls, sel_alloc)

                msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
                snd = msg(snd_alloc, sel_init_file, ns_path, True)
                if snd:
                    msg.restype = None
                    msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_float]
                    msg(snd, sel_set_vol, 0.28)
                    self.effects.append(snd)
        except Exception:
            pass

    @staticmethod
    def _write_blip_wav(path: Path, freq: float, duration_ms: int = 34, sample_rate: int = 22050) -> None:
        n_samples = int(sample_rate * (duration_ms / 1000.0))
        frames = bytearray()
        for s in range(n_samples):
            t = s / sample_rate
            progress = s / max(1, n_samples - 1)
            env = math.sin(math.pi * progress) * ((1.0 - progress) ** 0.7)
            val = math.sin(2.0 * math.pi * freq * t) * 0.45 * env
            sample_i16 = max(-32767, min(32767, int(val * 32767)))
            frames.extend(struct.pack("<h", sample_i16))

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))

    def play_tick(self) -> None:
        if not self.enabled:
            return
        if sys.platform == "win32" and hasattr(self, "_winsound"):
            try:
                wav_file = str(self.sounds_dir / f"blip_{self._idx % 3}.wav")
                self._idx += 1
                self._winsound.PlaySound(wav_file, self._winsound.SND_FILENAME | self._winsound.SND_ASYNC)
            except Exception:
                pass
            return

        if not self.effects or not self._objc:
            return
        try:
            snd = self.effects[self._idx % len(self.effects)]
            self._idx += 1
            msg = self._objc.objc_msgSend
            msg.restype = ctypes.c_bool
            msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            if msg(snd, self._sel_is_playing):
                msg(snd, self._sel_stop)
            msg(snd, self._sel_play)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Lightweight 2D Loading Spinner Widget (for `thinking` state)
# ---------------------------------------------------------------------------
class LoadingSpinnerWidget(QWidget):
    """Smooth 2D arc spinner drawn with QPainter (zero external assets)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._step)

    def start(self) -> None:
        self._angle = 0
        self.show()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _step(self) -> None:
        self._angle = (self._angle + 24) % 360
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(3.0, 3.0, self.width() - 6.0, self.height() - 6.0)

        bg_pen = QPen(QColor(255, 214, 220, 45), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        p.drawEllipse(rect)

        arc_pen = QPen(QColor("#FF758F"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        p.drawArc(rect, -self._angle * 16, 110 * 16)
        p.end()


# ---------------------------------------------------------------------------
# Background Worker Thread for Non-Interactive Codex CLI (`gpt-6-luna`)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Sprite animation is implemented in character_widget.py.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Speech Bubble Widget (Spinner + Motion Typing + History + Codex Output + Minimize)
# ---------------------------------------------------------------------------
class SpeechBubble(QFrame):
    panelRequested = Signal()
    soundToggled = Signal(bool)
    historyToggled = Signal(bool)
    outputToggled = Signal(bool)
    agentToggled = Signal(bool)
    needsToggled = Signal(bool)
    needReplenishRequested = Signal(str)
    careAllRequested = Signal()
    minimizeRequested = Signal()
    typingFinished = Signal()
    bubbleDragDeltaY = Signal(int)
    bubbleDragFinished = Signal()

    def __init__(
        self,
        sound_player: TypingSoundPlayer,
        typing_interval_ms: int = 26,
        history_enabled: bool = False,
        output_enabled: bool = False,
        agent_enabled: bool = True,
        needs_enabled: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("speechBubble")
        self.setMinimumWidth(280)

        self.sound_player = sound_player
        self.typing_interval_ms = max(12, typing_interval_ms)
        self.history_enabled = history_enabled
        self.output_enabled = output_enabled
        self.agent_enabled = agent_enabled
        self.needs_enabled = needs_enabled
        self._bubble_drag_last_y: Optional[int] = None

        self._full_text = ""
        self.character_name = "Frieren"
        self._typed_index = 0
        self._char_tick_counter = 0

        self.typing_timer = QTimer(self)
        self.typing_timer.setInterval(self.typing_interval_ms)
        self.typing_timer.timeout.connect(self._on_typing_step)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(6)

        # Header Row: Name + Emotion/State + Collapsible Quick Action Toolbar + Minimize
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self.name_label = QLabel("✦ Frieren")
        self.name_label.setObjectName("bubbleTitle")
        self.name_label.setCursor(Qt.CursorShape.SizeVerCursor)
        self.name_label.setToolTip("Geser (Drag) naik/turun untuk mengatur jarak Bubble dengan Frieren")
        self.name_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.current_emotion_key = "tenang"
        self.current_state_key = "idle"
        self.emotion_badge = QLabel("🌿 Tenang")
        self.emotion_badge.setObjectName("emotionBadge")
        self.emotion_badge.setCursor(Qt.CursorShape.SizeVerCursor)
        self.emotion_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.emotion_badge.setToolTip("Perasaan Frieren saat ini: Damai & rileks menemanimu di meja kerja")
        self.state_badge = QLabel("· santai")
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setMinimumWidth(0)
        self.state_badge.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        # Collapsible Tools Container (hidden/collapsed by default so emotion & status are clearly visible!)
        self.tools_expanded = False
        self.tools_panel = QWidget(self)
        tools_layout = QHBoxLayout(self.tools_panel)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(3)

        # 1. Agent Execution Toggle Button (⚡)
        self.agent_btn = QPushButton("⚡", self.tools_panel)
        self.agent_btn.setObjectName("iconToggleBtn")
        self.agent_btn.setCheckable(True)
        self.agent_btn.setChecked(self.agent_enabled)
        self.agent_btn.setFixedSize(22, 20)
        self.agent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.agent_btn.setToolTip("Mode Eksekusi Codex (Buka Web / Jalankan Perintah)")
        self.agent_btn.clicked.connect(self._on_agent_btn_clicked)

        # 2. Codex CLI Output Drawer Button (💻)
        self.output_btn = QPushButton("💻", self.tools_panel)
        self.output_btn.setObjectName("iconToggleBtn")
        self.output_btn.setCheckable(True)
        self.output_btn.setChecked(self.output_enabled)
        self.output_btn.setFixedSize(22, 20)
        self.output_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_btn.setToolTip("Panel Output / Log Eksekusi Codex CLI")
        self.output_btn.clicked.connect(self._on_output_btn_clicked)

        # 3. Scrollable Chat History Button (📜)
        self.history_btn = QPushButton("📜", self.tools_panel)
        self.history_btn.setObjectName("iconToggleBtn")
        self.history_btn.setCheckable(True)
        self.history_btn.setChecked(self.history_enabled)
        self.history_btn.setFixedSize(22, 20)
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setToolTip("Tampilkan / Sembunyikan Riwayat Chat (Scrollable)")
        self.history_btn.clicked.connect(self._on_history_btn_clicked)

        # 4. Sound Toggle Button (🔊 / 🔇)
        self.sound_btn = QPushButton("🔊" if self.sound_player.enabled else "🔇", self.tools_panel)
        self.sound_btn.setObjectName("iconToggleBtn")
        self.sound_btn.setCheckable(True)
        self.sound_btn.setChecked(self.sound_player.enabled)
        self.sound_btn.setFixedSize(22, 20)
        self.sound_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sound_btn.setToolTip("Aktifkan / Nonaktifkan Suara Ketikan Frieren")
        self.sound_btn.clicked.connect(self._on_sound_btn_clicked)

        # 5. Needs & Wellness Drawer Button (🍵)
        self.needs_btn = QPushButton("🍵", self.tools_panel)
        self.needs_btn.setObjectName("iconToggleBtn")
        self.needs_btn.setCheckable(True)
        self.needs_btn.setChecked(self.needs_enabled)
        self.needs_btn.setFixedSize(22, 20)
        self.needs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.needs_btn.setToolTip("Tampilkan / Sembunyikan Status Kebutuhan & Perhatian Frieren (🍵)")
        self.needs_btn.clicked.connect(self._on_needs_btn_clicked)

        tools_layout.addWidget(self.needs_btn)
        tools_layout.addWidget(self.agent_btn)
        tools_layout.addWidget(self.output_btn)
        tools_layout.addWidget(self.history_btn)
        tools_layout.addWidget(self.sound_btn)
        self.tools_panel.setVisible(False)

        # Toggle Button to Expand/Collapse Action Buttons (◂ / ▸)
        self.tools_toggle_btn = QPushButton("◂")
        self.tools_toggle_btn.setObjectName("iconToggleBtn")
        self.tools_toggle_btn.setCheckable(True)
        self.tools_toggle_btn.setChecked(False)
        self.tools_toggle_btn.setFixedSize(20, 20)
        self.tools_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tools_toggle_btn.setToolTip("Buka / Collapse Tombol Pengaturan Cepat (🍵 ⚡ 💻 📜 🔊)")
        self.tools_toggle_btn.clicked.connect(self._on_tools_toggle_clicked)

        # 5. Minimize Bubble Button (—)
        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("iconToggleBtn")
        self.min_btn.setFixedSize(20, 20)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tip_hk = "Cmd+Shift+Space" if sys.platform == "darwin" else "Ctrl+Shift+Space"
        self.min_btn.setToolTip(f"Sembunyikan Bubble Chat (Klik Frieren atau {tip_hk} untuk memunculkan lagi)")
        self.min_btn.clicked.connect(self.minimizeRequested.emit)

        header.addWidget(self.name_label)
        header.addWidget(self.emotion_badge)
        header.addWidget(self.state_badge, 1)
        header.addWidget(self.tools_panel)
        header.addWidget(self.tools_toggle_btn)
        header.addWidget(self.min_btn)
        layout.addLayout(header)

        context_row = QHBoxLayout()
        self.runtime_label = QLabel("AI · siap")
        self.runtime_label.setObjectName("runtimeLabel")
        self.runtime_label.setTextFormat(Qt.TextFormat.PlainText)
        self.runtime_label.setMinimumWidth(0)
        self.runtime_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.copy_btn = QPushButton("Salin")
        self.copy_btn.setObjectName("secondaryButton")
        self.copy_btn.setToolTip("Salin jawaban Frieren")
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._full_text))
        self.panel_btn = QPushButton("Chat ↗")
        self.panel_btn.setObjectName("secondaryButton")
        self.panel_btn.setToolTip("Buka panel chat besar, model AI, dan folder proyek")
        self.panel_btn.clicked.connect(self.panelRequested.emit)
        for button in (self.copy_btn, self.panel_btn):
            button.setMinimumHeight(26)
        context_row.addWidget(self.runtime_label, 1)
        context_row.addWidget(self.copy_btn)
        context_row.addWidget(self.panel_btn)
        layout.addLayout(context_row)

        self.output_available_btn = QPushButton("Hasil teknis tersedia · Buka Output")
        self.output_available_btn.setObjectName("secondaryButton")
        self.output_available_btn.clicked.connect(self._show_available_output)
        self.output_available_btn.hide()
        layout.addWidget(self.output_available_btn)

        # Scrollable Chat History Area
        self.history_scroll = QScrollArea(self)
        self.history_scroll.setObjectName("historyScroll")
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_scroll.setFixedHeight(105)

        self.history_content = QWidget()
        self.history_content.setObjectName("historyContent")
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(4, 4, 6, 4)
        self.history_layout.setSpacing(5)
        self.history_layout.addStretch(1)
        self.history_scroll.setWidget(self.history_content)
        self.history_scroll.setVisible(self.history_enabled)
        layout.addWidget(self.history_scroll)

        # Scrollable & Copyable Codex CLI Output Drawer (💻)
        self.output_box = QPlainTextEdit(self)
        self.output_box.setObjectName("codexOutputBox")
        self.output_box.setReadOnly(True)
        self.output_box.document().setMaximumBlockCount(1000)
        self.output_box.setPlaceholderText("Log perintah & output Codex CLI akan tampil di sini...")
        self.output_box.setFixedHeight(105)
        self.output_box.setVisible(self.output_enabled)
        layout.addWidget(self.output_box)

        # Interactive Needs & Wellness Panel (🍵)
        self.needs_panel = QFrame(self)
        self.needs_panel.setObjectName("needsPanel")
        needs_panel_layout = QVBoxLayout(self.needs_panel)
        needs_panel_layout.setContentsMargins(8, 8, 8, 8)
        needs_panel_layout.setSpacing(6)

        needs_header = QHBoxLayout()
        needs_title = QLabel("🍵 Kebutuhan Karakter", self.needs_panel)
        needs_title.setObjectName("needsTitle")
        care_all_btn = QPushButton("✨ Care All", self.needs_panel)
        care_all_btn.setObjectName("needsCareAllBtn")
        care_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        care_all_btn.setToolTip("Penuhi semua kebutuhan Frieren sekaligus")
        care_all_btn.clicked.connect(self.careAllRequested.emit)
        needs_header.addWidget(needs_title)
        needs_header.addStretch(1)
        needs_header.addWidget(care_all_btn)
        needs_panel_layout.addLayout(needs_header)

        self.needs_bars: Dict[str, QProgressBar] = {}
        items_def = [
            ("thirst", "☕ Haus", "#64B5F6", "+ Teh"),
            ("hunger", "🍰 Lapar", "#FFB74D", "+ Makan"),
            ("energy", "💤 Energi", "#BA68C8", "+ Tidur"),
            ("freshness", "🌿 Segar", "#81C784", "+ Regang"),
        ]
        for key, label_txt, color_hex, btn_txt in items_def:
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = QLabel(label_txt, self.needs_panel)
            lbl.setFixedWidth(56)
            lbl.setObjectName("needsRowLabel")

            bar = QProgressBar(self.needs_panel)
            bar.setRange(0, 100)
            bar.setValue(80)
            bar.setTextVisible(True)
            bar.setFormat("80%")
            bar.setFixedHeight(14)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(255, 255, 255, 20);
                    border: 1px solid rgba(255, 255, 255, 30);
                    border-radius: 6px;
                    text-align: center;
                    color: #FFFFFF;
                    font-size: 9.5px;
                    font-weight: 600;
                }}
                QProgressBar::chunk {{
                    background-color: {color_hex};
                    border-radius: 5px;
                }}
            """)
            self.needs_bars[key] = bar

            action_btn = QPushButton(btn_txt, self.needs_panel)
            action_btn.setObjectName("needsActionBtn")
            action_btn.setFixedSize(54, 18)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.clicked.connect(lambda checked=False, k=key: self.needReplenishRequested.emit(k))

            row.addWidget(lbl)
            row.addWidget(bar, 1)
            row.addWidget(action_btn)
            needs_panel_layout.addLayout(row)

        self.needs_panel.setVisible(self.needs_enabled)
        layout.addWidget(self.needs_panel)

        # Loading Spinner Row (shown only while `thinking`)
        self.loading_row = QWidget(self)
        loading_layout = QHBoxLayout(self.loading_row)
        loading_layout.setContentsMargins(2, 4, 2, 4)
        loading_layout.setSpacing(8)
        self.spinner = LoadingSpinnerWidget(self.loading_row)
        self.loading_label = QLabel("Sedang memproses permintaanmu...")
        self.loading_label.setObjectName("loadingLabel")
        self.loading_label.setWordWrap(True)
        loading_layout.addWidget(self.spinner)
        loading_layout.addWidget(self.loading_label, 1)
        self.loading_row.setVisible(False)
        layout.addWidget(self.loading_row)

        # Scrollable Current Active Message Area (prevents clipping & supports clickable links)
        self.msg_scroll = QScrollArea(self)
        self.msg_scroll.setObjectName("msgScroll")
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.msg_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.msg_scroll.setMinimumHeight(54)
        self.msg_scroll.setMaximumHeight(135)
        self.msg_scroll.setVisible(not self.history_enabled)

        self.text_label = QLabel(
            "Halo... Aku sudah duduk nyaman di pojok layarmu. "
            "Aku bisa mengingat hal penting, membuka web, dan membantu pekerjaanmu kapan saja!"
        )
        self.text_label.setObjectName("bubbleText")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextFormat(Qt.TextFormat.RichText)
        self.text_label.setOpenExternalLinks(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.msg_scroll.setWidget(self.text_label)
        layout.addWidget(self.msg_scroll)

    def _on_tools_toggle_clicked(self, checked: bool) -> None:
        self.tools_expanded = bool(checked)
        self.tools_panel.setVisible(self.tools_expanded)
        self.tools_toggle_btn.setText("▸" if self.tools_expanded else "◂")
        self._refresh_header_fit()

    def _refresh_header_fit(self) -> None:
        """Ensures `emotion_badge` is ALWAYS 100% readable even when resized down to 70%."""
        label, desc = EMOTION_CATALOG.get(self.current_emotion_key, ("🌸 Senang", ""))
        w = self.width()

        # When toolbar (🍵 ⚡ 💻 📜 🔊) is expanded on a compact bubble, shorten emotion to emoji or hide title
        if self.tools_expanded:
            self.state_badge.setVisible(False)
            if w < 430:
                # Show only emoji on compact width while tools are open
                emoji_only = label.split(" ")[0]
                self.emotion_badge.setText(emoji_only)
            else:
                self.emotion_badge.setText(label)
            return

        # Normal state (toolbar collapsed): ALWAYS show full emotion badge (`🔍 Penasaran`, etc.)!
        self.emotion_badge.setText(label)
        if w < 285:
            # On small/resized bubbles, hide secondary activity text so Emotion Badge has 100% room
            self.state_badge.setVisible(False)
        else:
            self.state_badge.setVisible(True)
            raw_state_txt = getattr(self, "_raw_state_text", "· santai")
            fm = self.state_badge.fontMetrics()
            avail = max(36, w - 215)
            self.state_badge.setText(fm.elidedText(raw_state_txt, Qt.TextElideMode.ElideRight, avail))

    def _on_sound_btn_clicked(self, checked: bool) -> None:
        self.set_sound_enabled(checked)
        self.soundToggled.emit(checked)

    def _on_history_btn_clicked(self, checked: bool) -> None:
        self.set_history_enabled(checked)
        self.historyToggled.emit(checked)

    def _on_output_btn_clicked(self, checked: bool) -> None:
        self.set_output_enabled(checked)
        self.outputToggled.emit(checked)

    def _on_agent_btn_clicked(self, checked: bool) -> None:
        self.set_agent_enabled(checked)
        self.agentToggled.emit(checked)

    def _on_needs_btn_clicked(self, checked: bool) -> None:
        self.set_needs_enabled(checked)
        self.needsToggled.emit(checked)

    def set_needs_enabled(self, enabled: bool) -> None:
        self.needs_enabled = enabled
        self.needs_btn.setChecked(enabled)
        self.needs_panel.setVisible(enabled)
        self.adjustSize()

    def update_needs_data(self, data: Dict[str, float]) -> None:
        """Update progress bars for all tracked needs in the drawer."""
        for key, bar in self.needs_bars.items():
            if key in data:
                val = int(round(data[key]))
                bar.setValue(val)
                bar.setFormat(f"{val}%")
        # Visual alert on the 🍵 button if any need is below 35%
        is_low = any(data.get(k, 100.0) < 35.0 for k in ("thirst", "hunger", "energy", "freshness"))
        if is_low and not self.needs_enabled:
            self.needs_btn.setStyleSheet("background-color: rgba(255, 152, 0, 160); border: 1px solid #FFD54F;")
        else:
            self.needs_btn.setStyleSheet("")

    def set_sound_enabled(self, enabled: bool) -> None:
        self.sound_player.enabled = enabled
        self.sound_btn.setChecked(enabled)
        self.sound_btn.setText("🔊" if enabled else "🔇")

    def set_history_enabled(self, enabled: bool) -> None:
        self.history_enabled = enabled
        self.history_btn.setChecked(enabled)
        self.history_scroll.setVisible(enabled)
        self.msg_scroll.setVisible(not enabled)
        self.adjustSize()
        if enabled:
            self.scroll_to_bottom()

    def set_output_enabled(self, enabled: bool) -> None:
        self.output_enabled = enabled
        self.output_btn.setChecked(enabled)
        self.output_box.setVisible(enabled)
        self.adjustSize()

    def set_agent_enabled(self, enabled: bool) -> None:
        self.agent_enabled = enabled
        self.agent_btn.setChecked(enabled)

    def set_cli_output(self, text: str) -> None:
        """Store CLI log in console box without forcing it open if user closed it."""
        self.output_box.setPlainText(text[-48000:])
        sb = self.output_box.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _show_available_output(self) -> None:
        self.set_output_enabled(True)
        self.outputToggled.emit(True)

    def show_stream(self, speech: str) -> None:
        self.typing_timer.stop()
        self._full_text = speech
        self.msg_scroll.setVisible(True)
        self.text_label.setText(self.format_rich_text(speech))
        self._update_msg_scroll_height()

    def format_rich_text(self, raw: str) -> str:
        """Convert Markdown (bold, italic, inline code, lists, links) into clean HTML."""
        escaped = html.escape(raw)

        # 1. Extract inline code `code` into placeholders first so markdown inside code isn't altered
        code_slots: List[str] = []

        def _code_repl(m: re.Match) -> str:
            idx = len(code_slots)
            code_slots.append(
                f'<code style="background-color:rgba(127,127,127,24); '
                f'padding:1px 4px; border-radius:4px; font-family:Menlo,monospace; font-size:11.5px;">{m.group(1)}</code>'
            )
            return f"@@CODE_{idx}@@"

        text = re.sub(r"`([^`\n]+)`", _code_repl, escaped)

        # 2. Convert [label](url) markdown links (supports https, http, file, and local paths) into placeholders
        link_slots: List[str] = []

        def _md_repl(m: re.Match) -> str:
            idx = len(link_slots)
            label, url = m.group(1), m.group(2)
            href = url
            # Convert local filesystem absolute paths to file:// URI for native desktop opening
            if url.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", url):
                href = f"file://{url}"
            colour = getattr(self,"link_colour","#82AAFF")
            link_slots.append(f'<a href="{href}" style="color:{colour}; text-decoration:underline;">{label}</a>')
            return f"@@LINK_{idx}@@"

        text = re.sub(
            r"\[([^\]]+)\]\(((?:https?://|file://|/|[a-zA-Z]:[\\/])[^\s\)]+)\)",
            _md_repl,
            text,
        )

        # 3. Convert standalone https://... URLs
        def _url_repl(m: re.Match) -> str:
            idx = len(link_slots)
            url = m.group(1)
            colour = getattr(self,"link_colour","#82AAFF")
            link_slots.append(f'<a href="{url}" style="color:{colour}; text-decoration:underline;">{url}</a>')
            return f"@@LINK_{idx}@@"

        text = re.sub(r"(https?://[^\s<>\")]+)", _url_repl, text)

        # 4. Bold (**text** or __text__)
        text = re.sub(
            r"\*\*(.+?)\*\*",
            r'<b>\1</b>',
            text,
            flags=re.S,
        )
        # Also gracefully close an unclosed ** at the end of a partial typing slice so `**` never flashes raw
        if text.count("**") % 2 == 1:
            text = re.sub(
                r"\*\*([^*]+)$",
                r'<b>\1</b>',
                text,
            )
        text = re.sub(
            r"__(.+?)__",
            r'<b>\1</b>',
            text,
            flags=re.S,
        )

        # 5. Italic (*text* or _text_) — avoid matching inside words or lone asterisks
        text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"<i>\1</i>", text)

        # 6. Strikethrough (~~text~~)
        text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

        # 7. Clean bullet lists & headings at start of lines
        formatted_lines: List[str] = []
        for line in text.split("\n"):
            s_line = line.strip()
            if re.match(r"^#{1,4}\s+", s_line):
                head_txt = re.sub(r"^#{1,4}\s+", "", s_line)
                formatted_lines.append(f'<b>{head_txt}</b>')
            elif re.match(r"^[-*]\s+", s_line):
                item_txt = re.sub(r"^[-*]\s+", "", s_line)
                formatted_lines.append(f"• {item_txt}")
            else:
                formatted_lines.append(line)

        result = "<br>".join(formatted_lines)

        # Restore links and inline code slots
        for idx, html_link in enumerate(link_slots):
            result = result.replace(f"@@LINK_{idx}@@", html_link)
        for idx, html_code in enumerate(code_slots):
            result = result.replace(f"@@CODE_{idx}@@", html_code)

        return result

    def set_emotion(self, emotion_key: str) -> None:
        key = emotion_key.lower().strip()
        if key not in EMOTION_CATALOG:
            key = "senang"
        self.current_emotion_key = key
        label, desc = EMOTION_CATALOG[key]
        self.emotion_badge.setText(label)
        self.emotion_badge.setToolTip(f"Perasaan {self.character_name}: {label} — {desc}")
        self._refresh_header_fit()

    def update_state_badge(self, state: str, emotion_override: Optional[str] = None) -> None:
        self.current_state_key = state
        badge_map = {
            "idle": "· santai",
            "idle_cozy": "· nyender ♪",
            "idle_sleepy": "· terkantuk~",
            "idle_reading": "· baca buku 📖",
            "idle_dancing": "· menari ♪",
            "idle_tea": "· minum teh ☕",
            "thinking": "· mikir...",
            "thinking_lookup": "· menerawang~",
            "thinking_tilt": "· memikir...",
            "thinking_hmmm": "· merenung...",
            "action_laptop": "· buka laptop 💻",
            "action_magic": "· merapal sihir ✦",
            "talking": "· berbicara",
            "talking_explain": "· menjelaskan ♪",
            "pleased": "· tersenyum ♪",
            "pleased_wave": "· menyapa 👋",
            "needs_tea": "· butuh teh ☕",
            "needs_hungry": "· lapar 🍰",
            "needs_sleepy": "· mengantuk 💤",
            "needs_stretch": "· peregangan 🌿",
            "sleeping": "· tidur lelap (Zzz...)",
            "sleepy_yawn": "· menguap 🥱",
        }
        self._raw_state_text = badge_map.get(state, f"· {state}")
        self.state_badge.setToolTip(f"Aktivitas saat ini: {self._raw_state_text.lstrip('· ')}")
        if emotion_override:
            self.set_emotion(emotion_override)
        elif state in STATE_DEFAULT_EMOTION:
            self.set_emotion(STATE_DEFAULT_EMOTION[state])
        else:
            self._refresh_header_fit()

    def show_loading(self, status_text: str = "Sedang memproses permintaanmu...") -> None:
        self.typing_timer.stop()
        self.update_state_badge("thinking")
        self.loading_label.setText(status_text)
        self.msg_scroll.setVisible(False)
        self.spinner.start()
        self.loading_row.setVisible(True)
        self.adjustSize()

    def update_loading_status(self, status_text: str) -> None:
        self.loading_label.setText(status_text)
        self.adjustSize()

    def show_message(
        self,
        text: str,
        state: str = "idle",
        animate: bool = False,
        emotion_override: Optional[str] = None,
    ) -> None:
        self.typing_timer.stop()
        self.spinner.stop()
        self.loading_row.setVisible(False)
        self.msg_scroll.setVisible(not self.history_enabled)
        self.update_state_badge(state, emotion_override=emotion_override)

        if not animate or not text:
            self._full_text = text
            self.text_label.setText(self.format_rich_text(text))
            self._update_msg_scroll_height()
            self.typingFinished.emit()
            return

        self._full_text = text
        self._typed_index = 0
        self._char_tick_counter = 0
        self.text_label.setText("")
        self._update_msg_scroll_height()
        self.typing_timer.start()

    def _update_msg_scroll_height(self) -> None:
        self.text_label.adjustSize()
        content_h = self.text_label.sizeHint().height() + 8
        target_h = max(48, min(135, content_h))
        self.msg_scroll.setFixedHeight(target_h)
        bar = self.msg_scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())
        self.adjustSize()

    def _on_typing_step(self) -> None:
        if self._typed_index >= len(self._full_text):
            self.typing_timer.stop()
            # Render final rich text with clickable links when typing finishes
            self.text_label.setText(self.format_rich_text(self._full_text))
            self._update_msg_scroll_height()
            self.typingFinished.emit()
            return

        self._typed_index += 1
        current_slice = self._full_text[: self._typed_index]
        last_char = self._full_text[self._typed_index - 1]
        self.text_label.setText(self.format_rich_text(current_slice))

        if not last_char.isspace():
            self._char_tick_counter += 1
            if self._char_tick_counter % 2 == 1:
                self.sound_player.play_tick()

        self._update_msg_scroll_height()

    def refresh_history(self, items: List[Dict[str, str]], ltm_count: int = 0) -> None:
        while self.history_layout.count() > 1:
            child = self.history_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if ltm_count > 0:
            ltm_badge = QLabel(f"✦ {ltm_count} catatan memori umum/proyek tersimpan")
            ltm_badge.setObjectName("ltmBadge")
            self.history_layout.insertWidget(0, ltm_badge)

        if not items:
            empty_lbl = QLabel("Belum ada riwayat percakapan.")
            empty_lbl.setObjectName("historyEmpty")
            self.history_layout.insertWidget(self.history_layout.count() - 1, empty_lbl)
        else:
            for entry in items[-20:]:
                role = entry.get("role", "user")
                text = entry.get("text", "")[:3000]
                row_frame = QFrame()
                row_frame.setObjectName("historyItemUser" if role == "user" else "historyItemBot")
                row_layout = QVBoxLayout(row_frame)
                row_layout.setContentsMargins(8, 4, 8, 4)
                row_layout.setSpacing(2)

                who = "Kamu" if role == "user" else "✦ " + entry.get("speaker", "Frieren")
                rich_body = self.format_rich_text(text)
                lbl = QLabel(f"<b>{who}:</b> {rich_body}")
                lbl.setObjectName("historyItemText")
                lbl.setWordWrap(True)
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setOpenExternalLinks(True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                row_layout.addWidget(lbl)
                self.history_layout.insertWidget(self.history_layout.count() - 1, row_frame)

        QTimer.singleShot(20, self.scroll_to_bottom)

    def scroll_to_bottom(self) -> None:
        bar = self.history_scroll.verticalScrollBar()
        if bar:
            bar.setValue(bar.maximum())

    def mousePressEvent(self, event) -> None:
        # Allow dragging the top header area of the bubble vertically to adjust gap from Frieren
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 34:
            self._bubble_drag_last_y = int(event.globalPosition().y())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._bubble_drag_last_y is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            curr_y = int(event.globalPosition().y())
            dy = curr_y - self._bubble_drag_last_y
            if dy != 0:
                self._bubble_drag_last_y = curr_y
                # Dragging up (dy < 0) increases gap; dragging down (dy > 0) brings bubble closer
                self.bubbleDragDeltaY.emit(-dy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._bubble_drag_last_y is not None:
            self._bubble_drag_last_y = None
            self.bubbleDragFinished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Main Transparent Desktop Companion Window
# ---------------------------------------------------------------------------
class FrierenDeskWindow(QWidget):
    def __init__(self, base_dir: Path, auto_discover: bool = True) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.backend = CodexBackend(base_dir)
        self.profile = self.backend.character
        if not self.profile.available(base_dir):
            self.backend.config.setdefault("ui", {})["character"] = "frieren"
            self.profile = get_profile("frieren")
        self._manual_expression = None
        self.voice = VoiceController(self)
        self._voice_active = False
        self.voice.speakingChanged.connect(self._on_voice_speaking)
        self._tts_workers = []
        self._tts_token = 0
        self._tts_pending = False
        self._tts_queue = []
        self._tts_generating = False
        self._synced_subtitle = None
        self._prefetched_narration = ""
        self._waiting_voice_result = False
        self._prefetch_error = ""
        self._voice_suppressed = False
        self._tts_started = 0.0
        self._tts_clock = QTimer(self)
        self._tts_clock.setInterval(1000)
        self._tts_clock.timeout.connect(self._tick_narration_clock)
        self.needs = NeedsManager(base_dir)
        self.config = self.backend.config

        win_cfg = self.config.get("window", {})
        self.base_win_w = int(win_cfg.get("width", 360))
        self.base_win_h = int(win_cfg.get("height", 620))
        self.margin_right = int(win_cfg.get("margin_right", 18))
        self.margin_bottom = int(win_cfg.get("margin_bottom", 12))

        anim_cfg = self.config.get("animation", {})
        self.fade_ms = int(anim_cfg.get("fade_duration_ms", 220))
        self.typing_interval_ms = int(anim_cfg.get("typing_interval_ms", 26))
        self.talking_hold_ms = int(anim_cfg.get("talking_hold_ms", 2200))
        self.pleased_hold_ms = int(anim_cfg.get("pleased_hold_ms", 4000))
        self.bubble_autohide_ms = int(anim_cfg.get("bubble_autohide_ms", 9000))

        ui_cfg = self.config.get("ui", {})
        sound_enabled = bool(ui_cfg.get("sound_enabled", True))
        history_enabled = bool(ui_cfg.get("history_enabled", False))
        output_enabled = bool(ui_cfg.get("output_enabled", False))
        needs_enabled = bool(ui_cfg.get("needs_enabled", False))
        self.is_minimized = bool(ui_cfg.get("minimized", False))
        self.auto_hide_bubble = bool(ui_cfg.get("auto_hide_bubble", True))
        self.scale_factor: float = float(ui_cfg.get("scale", 1.0))
        self.opacity_level: float = float(ui_cfg.get("opacity", 1.0))
        self.bubble_gap: int = int(ui_cfg.get("bubble_gap", 4))
        self._last_pet_idx: int = -1
        self._idle_pose_idx: int = 0

        self.sound_player = TypingSoundPlayer(self.base_dir / "assets", enabled=sound_enabled)

        self._drag_offset: Optional[QPoint] = None
        self._worker: Optional[CodexWorker] = None
        self._discovery_worker = None
        self._closing = False
        self._streamed = False
        self._explanation_voiced = False
        self.chat_panel = None
        self.pending_attachments: List[str] = []
        self.clipboard_dir = self.base_dir / "assets" / "clipboard"
        self.clipboard_dir.mkdir(parents=True, exist_ok=True)
        self.setAcceptDrops(True)

        # Auto-hide timer for bubble & input bar when idle / not chatting
        self.bubble_hide_timer = QTimer(self)
        self.bubble_hide_timer.setSingleShot(True)
        self.bubble_hide_timer.timeout.connect(self._on_bubble_autohide_timeout)

        self._init_window_flags()
        self._init_ui(history_enabled=history_enabled, output_enabled=output_enabled, needs_enabled=needs_enabled)
        self._init_shortcuts_and_tray()
        self.apply_scale(self.scale_factor, save=False, redock=False)
        self.apply_opacity(self.opacity_level, save=False)
        self.apply_bubble_gap(self.bubble_gap, save=False)
        if self.is_minimized:
            self.set_minimized(True)
        else:
            self._schedule_bubble_autohide()
        self.dock_bottom_right()

        # Perform initial quiet Google Drive sync check
        self.backend.sync_to_gdrive()

        self.state_timer = QTimer(self)
        self.state_timer.setSingleShot(True)
        self.state_timer.timeout.connect(self._on_state_timer)
        self._next_scheduled_state = "idle"

        # Long, varied holds keep Frieren calm instead of cycling mechanically.
        self.idle_cycle_timer = QTimer(self)
        self.idle_cycle_timer.setInterval(random.randint(24000, 48000))
        self.idle_cycle_timer.timeout.connect(self._cycle_idle_pose)
        self.idle_cycle_timer.start()

        # Needs & Wellness Tracker Timer (ticks every 60s)
        self.needs_timer = QTimer(self)
        self.needs_timer.setInterval(60000)
        self.needs_timer.timeout.connect(self._on_needs_tick)
        self.needs_timer.start()

        self.clickthrough_timer = QTimer(self)
        self.clickthrough_timer.setInterval(60)
        self.clickthrough_timer.timeout.connect(self._update_mask_and_clickthrough)
        self.clickthrough_timer.start()
        self.request_clock = QTimer(self)
        self.request_clock.setInterval(500)
        self.request_clock.timeout.connect(self._tick_request_clock)
        self._window_resize_timer = QTimer(self)
        self._window_resize_timer.setSingleShot(True)
        self._window_resize_timer.timeout.connect(self._save_main_size)
        self._request_started = 0.0
        self._request_stage = ""
        self._init_chat_panel()
        self._apply_character_theme()
        self._update_ai_context("Siap")
        if auto_discover:
            QTimer.singleShot(350, self.refresh_models)

    def _init_chat_panel(self) -> None:
        self.chat_panel = ChatPanel(self)
        self.chat_panel.characterSelected.connect(self._set_character)
        self.chat_panel.timeoutSelected.connect(self._set_timeout)
        self.chat_panel.voiceRequested.connect(self.open_voice_settings)
        self.chat_panel.stopVoiceRequested.connect(self._stop_voice_requested)
        self.chat_panel.expressionSelected.connect(self._preview_expression)
        self.chat_panel.panelResized.connect(self._save_panel_size)
        self.chat_panel.sendRequested.connect(self.send_message)
        self.chat_panel.cancelRequested.connect(self.cancel_request)
        self.chat_panel.refreshRequested.connect(self.refresh_models)
        self.chat_panel.modelSelected.connect(self._select_model)
        self.chat_panel.chooseProjectRequested.connect(self.choose_project)
        self.chat_panel.projectSelected.connect(self._select_project)
        self.chat_panel.revealProjectRequested.connect(self.reveal_project)
        self.chat_panel.attachRequested.connect(self._pick_attachments_dialog)
        self.chat_panel.removeAttachmentRequested.connect(self.remove_attachment)
        self.chat_panel.imagePasted.connect(self._on_image_pasted)
        self.chat_panel.filesDropped.connect(self._on_files_dropped)
        self.chat_panel.update_context(self.backend)
        self.chat_panel.set_history(self.backend.load_memory())
        size = self.config.get("ui", {}).get("chat_panel_size", [800,720])
        if isinstance(size, list) and len(size) == 2:
            screen = QGuiApplication.primaryScreen()
            available = screen.availableGeometry() if screen else QRect(0,0,1600,1000)
            self.chat_panel.resize(max(420, min(int(size[0]), available.width())), max(420, min(int(size[1]), available.height())))

    def _save_panel_size(self, width, height) -> None:
        if not self._closing:
            self.config.setdefault("ui", {})["chat_panel_size"] = [width,height]
            self.backend.save_config()

    def _save_main_size(self) -> None:
        if not self._closing:
            self.base_win_w = round(self.width()/self.scale_factor)
            self.base_win_h = round(self.height()/self.scale_factor)
            self.config.setdefault("window",{}).update(width=self.base_win_w,height=self.base_win_h)
            self.backend.save_config()

    def _set_timeout(self, seconds) -> None:
        if not self._worker or not self._worker.isRunning():
            self.backend.set_timeout(seconds)
            self._update_ai_context(f"Batas waktu {seconds} detik")

    def _tick_request_clock(self) -> None:
        if self._closing or not self._worker or not self._worker.isRunning():
            self.request_clock.stop()
            return
        elapsed = max(0,round(time.monotonic()-self._request_started))
        limit = self.backend.agy_timeout_seconds if self.backend.active_engine == "antigravity" else self.backend.timeout_seconds
        text = f"{self._request_stage or 'Memproses'} · {elapsed}/{limit} dtk"
        self.bubble.update_loading_status(text)
        self._update_ai_context(text)

    def _set_character(self, identifier) -> None:
        if self._worker and self._worker.isRunning():
            return
        profile = get_profile(identifier)
        if not profile.available(self.base_dir):
            self.chat_panel.status.setText(f"Aset {profile.name} belum lengkap.")
            return
        sprites, blink = profile.assets(self.base_dir)
        self.stop_all_voice()
        self.backend.set_character(profile.id)
        self.profile = profile
        self._manual_expression = None
        self.state_timer.stop()
        self.sprite.set_sprites(sprites,blink,profile.mouth_frames(self.base_dir))
        self._apply_character_theme()
        self._sync_expression_controls(None)
        self.chat_panel.update_context(self.backend)
        self._refresh_bubble_history()
        self.set_character_state("idle", profile.taps[0], animate_typing=False)
        self._update_ai_context("Karakter dipilih")
        self._play_voice_event("greeting")

    def open_voice_settings(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        bank = VoiceBank(self.base_dir, self.profile.id)
        prefs = self.config.get("ui",{})
        dialog = VoiceDialog(bank,self.voice,self.profile,prefs.get("voice_enabled",True),self.chat_panel,
                             mode=prefs.get("voice_mode","narration"),engine=prefs.get("tts_engine","qwen-local"))
        dialog.narrationPreview.connect(lambda:self._start_narration(self.profile.voice_preview,"hangat",True,dialog.engine.currentData()))
        dialog.stopRequested.connect(self._stop_voice_requested)
        dialog.finished.connect(self.stop_all_voice)
        dialog.exec()
        self.config.setdefault("ui",{})["voice_enabled"] = dialog.enabled.isChecked()
        self.config["ui"]["voice_mode"] = dialog.mode.currentData()
        self.config["ui"]["tts_engine"] = dialog.engine.currentData()
        self.backend.save_config()
        dialog.deleteLater()

    def _play_voice_event(self, event) -> None:
        if not self.config.get("ui",{}).get("voice_enabled",True) or self._closing:
            return
        if self.config.get("ui",{}).get("voice_mode","narration") != "clips":
            return
        clip = VoiceBank(self.base_dir,self.profile.id).clip_for(event)
        if clip:
            self.voice.play(clip)

    def _stop_voice_requested(self):
        self._voice_suppressed = True
        self.stop_all_voice()

    def stop_all_voice(self) -> None:
        self._release_synced_subtitle()
        self._prefetched_narration = ""
        self._waiting_voice_result = False
        self._prefetch_error = ""
        self._tts_queue.clear()
        self._tts_generating = False
        self._tts_clock.stop()
        self._tts_token += 1
        self._tts_pending = False
        for worker in self._tts_workers:
            worker.cancel()
        self.voice.stop()
        if self.chat_panel:
            self.chat_panel.stop_voice_btn.hide()

    def _start_narration(self, text, emotion=None, force=False, engine=None) -> None:
        if self._closing or (not force and not self.config.get("ui",{}).get("voice_enabled",True)):
            return
        self.stop_all_voice()
        token = self._tts_token
        self._tts_pending = True
        self._tts_generating = True
        self._tts_started = time.monotonic()
        self._tts_clock.start()
        self.chat_panel.stop_voice_btn.show()
        self._tick_narration_clock()
        logging.info("Narration started: character=%s engine=%s chars=%s token=%s", self.profile.id,
                     engine or self.config.get("ui",{}).get("tts_engine","qwen-local"), len(text), token)
        worker = NarrationWorker(self.base_dir,self.profile.id,text,emotion,
                                 engine or self.config.get("ui",{}).get("tts_engine","qwen-local"),self)
        self._tts_workers.append(worker)
        worker.ready.connect(lambda audio,t=token:self._on_narration_ready(t,audio))
        worker.failed.connect(lambda message,t=token:self._on_narration_failed(t,message))
        worker.finished.connect(self._on_narration_finished)
        worker.finished.connect(lambda t=token:self._on_narration_generated(t))
        worker.start()

    def _sync_voice_enabled(self):
        prefs = self.config.get("ui", {})
        return (not self._voice_suppressed and prefs.get("voice_enabled", True)
                and prefs.get("voice_mode", "narration") == "narration")

    def _start_synced_narration(self, text, japanese, emotion, pose="talking", result=None):
        prefetched = bool(self._prefetched_narration) and self._prefetched_narration == narration_text(japanese)
        error = self._prefetch_error if prefetched else ""
        if not prefetched:
            self._start_narration(japanese, emotion)
        self._prefetched_narration = ""
        self._waiting_voice_result = False
        self._synced_subtitle = (text, emotion, pose, result)
        self.state_timer.stop()
        self.set_character_state("thinking", "Menyiapkan suara karakter…", animate_typing=False)
        if error:
            self._on_narration_failed(self._tts_token, error)
        elif self._tts_queue:
            self._play_next_narration()

    def _release_synced_subtitle(self):
        pending = self._synced_subtitle
        self._synced_subtitle = None
        if pending:
            text, emotion, pose, result = pending
            if result is not None:
                self._refresh_bubble_history()
            self.set_character_state(pose, text, animate_typing=False, emotion_override=emotion)

    def _tick_narration_clock(self) -> None:
        if self._tts_pending:
            elapsed = int(time.monotonic() - self._tts_started)
            self._update_ai_context(f"Menyiapkan dub Jepang · {elapsed} detik (cloning CPU bisa lambat)")

    def _on_narration_ready(self, token, audio) -> None:
        if self._closing or token != self._tts_token:
            return
        self._tts_queue.append(audio)
        if not self._voice_active:
            self._play_next_narration()

    def _play_next_narration(self) -> None:
        if self._closing or self._voice_active or self._waiting_voice_result or not self._tts_queue:
            return
        audio = self._tts_queue.pop(0)
        self._tts_pending = False
        self._tts_clock.stop()
        logging.info("Narration ready: engine=%s duration_ms=%s elapsed=%.1fs", audio.engine,
                     audio.duration_ms, time.monotonic()-self._tts_started)
        if self.voice.play(VoiceClip(audio.file,0,audio.duration_ms+100)):
            logging.info("Narration playback started")
            label = {"edge":"Jepang sintetis", "windows":"Jepang Windows offline",
                     "qwen-local":"Jepang · cloning sample lokal"}.get(audio.engine,audio.engine)
            self._update_ai_context(f"Narasi · {label}")
        else:
            logging.warning("Narration playback could not start")
            self._release_synced_subtitle()
            self.chat_panel.stop_voice_btn.hide()
            self._update_ai_context("Audio tidak dapat diputar; jawaban tetap tersedia")

    def _on_narration_generated(self, token) -> None:
        if token != self._tts_token:
            return
        self._tts_generating = False
        if not self._voice_active and not self._tts_queue:
            self._tts_pending = False
            self._tts_clock.stop()
            self.chat_panel.stop_voice_btn.hide()

    def _on_narration_failed(self, token, message) -> None:
        if self._closing or token != self._tts_token:
            return
        if self._waiting_voice_result:
            self._prefetch_error = message
        self._release_synced_subtitle()
        self._tts_pending = False
        self._tts_clock.stop()
        self.chat_panel.stop_voice_btn.hide()
        self._update_ai_context("Dub Jepang gagal: " + message[-220:])
        self.chat_panel.status.setToolTip(message)
        logging.warning("Narration failed: %s",message)

    def _on_narration_finished(self) -> None:
        worker = self.sender()
        if worker in self._tts_workers:
            self._tts_workers.remove(worker)
        if worker:
            worker.deleteLater()

    def _on_voice_speaking(self, active) -> None:
        if self._closing or active == self._voice_active:
            return
        self._voice_active = active
        if self.chat_panel:
            self.chat_panel.stop_voice_btn.setVisible(active or self._tts_pending)
        if active:
            self._release_synced_subtitle()
            if not self._worker or not self._worker.isRunning():
                self.sprite.set_state("talking")
                self.bubble.update_state_badge("talking")
            self.sprite.set_speaking(True)
        else:
            self.sprite.set_speaking(False)
            if self._tts_queue:
                QTimer.singleShot(0, self._play_next_narration)
            elif self._tts_generating:
                self._tts_pending = True
                self._tts_clock.start()
                self.chat_panel.stop_voice_btn.show()
            if not self._worker or not self._worker.isRunning():
                state = EXPRESSION_STATES.get(self._manual_expression,"idle")
                self.sprite.set_state(state)
                self.bubble.update_state_badge(state)
                self.sprite.set_speaking(self._manual_expression == "talking")

    def _apply_character_theme(self) -> None:
        name = self.profile.name
        self.setStyleSheet(self._base_style + theme_styles(self.profile))
        self.surface = SceneSurface(self.profile,"companion")
        self.update()
        self.chat_panel.apply_theme(self.profile)
        self.bubble.character_name = name
        self.bubble.link_colour = "#395e9e" if self.profile.id == "frieren" else self.profile.colours["accent"]
        self.bubble.name_label.setText("✦ " + name)
        self.bubble.name_label.setToolTip(f"Geser untuk mengatur jarak bubble dengan {name}")
        self.bubble.copy_btn.setToolTip(f"Salin jawaban {name}")
        self.bubble.sound_btn.setToolTip(f"Suara ketikan {name}")
        self.bubble.needs_btn.setToolTip(f"Kebutuhan dan istirahat {name}")
        self.input_box.setPlaceholderText(f"Ngobrol dengan {name}…")
        self.chat_panel.input.setPlaceholderText(f"Tulis pesan untuk {name}… Enter kirim, Shift+Enter baris baru")
        if hasattr(self, "context_menu"):
            self.context_menu.setStyleSheet(theme_styles(self.profile))
            self.context_menu.apply_profile(self.profile)
            self.menu_character_name.setText(name)
            self.menu_character_desc.setText(self.profile.description)
            pix = self.sprite.pixmaps.get("idle")
            if pix:
                self.menu_character_avatar.setPixmap(pix.scaled(42,48,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
                self.tray.setIcon(QIcon(pix))
            for identifier, action in self.character_actions.items():
                action.setChecked(identifier == self.profile.id)

    def _preview_expression(self, expression) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.voice.stop()
        self._manual_expression = expression
        self.bubble.typing_timer.stop()
        self.state_timer.stop()
        state = EXPRESSION_STATES.get(expression, "idle")
        self.sprite.set_speaking(expression == "talking")
        self.set_character_state(state)
        self.bubble.update_state_badge(state)
        self.show_bubble()

        self._sync_expression_controls(expression)

    def _sync_expression_controls(self, expression) -> None:
        index = self.chat_panel.expression_combo.findData(expression)
        self.chat_panel.expression_combo.setCurrentIndex(max(0,index))
        if hasattr(self, "expression_actions"):
            for key, action in self.expression_actions.items():
                action.setChecked(key == expression)

    def _refresh_model_menus(self) -> None:
        if not hasattr(self, "model_menus"):
            return
        if hasattr(self, "model_action_group"):
            self.model_action_group.deleteLater()
        self.model_action_group = QActionGroup(self)
        self.model_action_group.setExclusive(True)
        for engine, menu in self.model_menus.items():
            menu.clear()
            state = self.backend.providers[engine]
            if not state.connected:
                placeholder = menu.addAction("Belum terhubung · Refresh Model")
                placeholder.setEnabled(False)
            else:
                for model in state.models:
                    action = menu.addAction(model["name"])
                    action.setToolTip(model["id"])
                    action.setCheckable(True)
                    action.setChecked(engine == self.backend.active_engine and model["id"] == self.backend.active_model)
                    action.triggered.connect(lambda checked=False, provider=engine, identifier=model["id"]: self._select_model(provider, identifier))
                    self.model_action_group.addAction(action)
        if self._worker and self._worker.isRunning():
            self.model_action_group.setEnabled(False)


    def open_chat_panel(self) -> None:
        self.chat_panel.update_context(self.backend)
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.chat_panel.activateWindow()
        self.chat_panel.input.setFocus()
        logging.info("Chat panel opened")

    def _update_ai_context(self, status: str = "Siap") -> None:
        engine = "AGY" if self.backend.active_engine == "antigravity" else "Codex"
        project = self.backend.project_dir.name if self.backend.project_dir else "Umum"
        full = f"{self.profile.name} · {engine} · {self.backend.active_model} · {project} · {status}"
        label = self.bubble.runtime_label
        label.setToolTip(full)
        label.setText(label.fontMetrics().elidedText(full, Qt.TextElideMode.ElideMiddle, max(90, self.bubble.width() - 150)))
        if self.chat_panel:
            self.chat_panel.status.setText(full)

    def refresh_models(self) -> None:
        if self._closing or (self._discovery_worker and self._discovery_worker.isRunning()):
            return
        self.chat_panel.refresh_btn.setEnabled(False)
        self.chat_panel.connections.setText("Memeriksa login dan mengambil model dari Codex serta AGY…")
        self._discovery_worker = DiscoveryWorker(self.backend, self)
        self._discovery_worker.ready.connect(self._on_models_ready)
        self._discovery_worker.failed.connect(self.chat_panel.connections.setText)
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()

    def _on_models_ready(self, states) -> None:
        if self._closing:
            return
        self.backend.providers = states
        logging.info("Model discovery completed: %s", {name: len(state.models) if state.connected else "disconnected" for name, state in states.items()})
        self.chat_panel.update_context(self.backend)
        self._refresh_model_menus()
        self._update_ai_context("Siap" if not self._worker else "Memproses")

    def _on_discovery_finished(self) -> None:
        worker = self.sender()
        if worker is self._discovery_worker:
            self._discovery_worker = None
        if worker:
            worker.deleteLater()
        if not self._closing:
            self.chat_panel.refresh_btn.setEnabled(True)

    def _select_model(self, engine: str, model: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        try:
            self.backend.set_model(engine, model)
            if hasattr(self, "engine_group"):
                self.engine_group.actions()[0].setChecked(engine == "codex")
                self.engine_group.actions()[1].setChecked(engine == "antigravity")
            self.chat_panel.update_context(self.backend)
            self._refresh_model_menus()
            self._update_ai_context("Model dipilih")
        except (ValueError, OSError) as exc:
            self.chat_panel.status.setText(str(exc))

    def choose_project(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        folder = QFileDialog.getExistingDirectory(self.chat_panel, "Pilih folder proyek", str(self.backend.working_directory))
        if folder:
            self._select_project(folder)

    def _select_project(self, folder) -> None:
        if self._worker and self._worker.isRunning():
            return
        if self._discovery_worker and self._discovery_worker.isRunning():
            self.chat_panel.status.setText("Tunggu pemeriksaan model selesai sebelum berpindah proyek.")
            self.chat_panel.update_context(self.backend)
            return
        try:
            self.stop_all_voice()
            self.backend.set_project(folder)
            self.clear_attachments()
            self.bubble.typing_timer.stop()
            self.state_timer.stop()
            self.bubble.set_cli_output("")
            self.bubble.output_available_btn.hide()
            self.chat_panel.output.clear()
            self.chat_panel.update_context(self.backend)
            self._refresh_bubble_history()
            self.chat_panel.set_history(self.backend.load_memory())
            self.set_character_state("idle", "Proyek aktif sudah diganti. Percakapan dan catatan mengikuti folder ini.")
            self._update_ai_context("Proyek dipilih")
        except (ValueError, OSError) as exc:
            self.chat_panel.status.setText(str(exc))
            self.chat_panel.update_context(self.backend)

    def reveal_project(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.backend.working_directory)))

    def _set_request_busy(self, busy: bool) -> None:
        self.input_box.setEnabled(not busy)
        self.send_btn.setVisible(not busy)
        self.send_btn.setEnabled(not busy)
        self.attach_btn.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)
        self.attachment_bar.setEnabled(not busy)
        self.chat_panel.attachments.setEnabled(not busy)
        self.chat_panel.set_busy(busy)
        for name in ("engine_group", "character_group", "expression_group", "model_action_group"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(not busy)
        for name in ("act_agent", "act_clear", "act_clear_all"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(not busy)
        self.bubble.agent_btn.setEnabled(not busy)

    def cancel_request(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.stop_all_voice()
            self.cancel_btn.setEnabled(False)
            self.chat_panel.cancel_btn.setEnabled(False)
            self._update_ai_context("Menghentikan proses…")

    def _on_stream_text(self, text: str) -> None:
        if self._closing:
            return
        # The work panel stays responsive while the character subtitle waits
        # for audio. Always strip the private Japanese dubbing block.
        self.chat_panel.set_partial(self.backend.subtitle_text(text))
        if self._sync_voice_enabled():
            voice = re.search(r"\[VOICE_JA\](.*?)\[/VOICE_JA\]", text, re.S | re.I)
            if (voice and voice.group(1).strip() and not self._prefetched_narration
                    and self.config.get("ui", {}).get("tts_engine", "qwen-local") == "qwen-local"):
                self._start_narration(voice.group(1))
                self._prefetched_narration = narration_text(voice.group(1))
                self._waiting_voice_result = True
            # Keep only the character bubble/mouth synchronized with audio.
            self._update_ai_context("Menyiapkan jawaban dan dubbing karakter…")
            return
        self._streamed = True
        speech = self.backend.preview_speech(text)
        if speech:
            if not self._explanation_voiced:
                self._play_voice_event("explaining")
                self._explanation_voiced = True
            self.sprite.set_state("talking")
            self.sprite.set_speaking(True)
            self.bubble.show_stream(speech)
        self._update_ai_context("Sedang menjawab")

    def _on_request_finished(self) -> None:
        self.request_clock.stop()
        worker = self.sender()
        if worker is self._worker:
            self._worker = None
        if worker:
            worker.deleteLater()
        if not self._closing:
            self._set_request_busy(False)
            if self.chat_panel.isVisible():
                self.chat_panel.input.setFocus()

    def request_shutdown(self) -> None:
        self._closing = True
        self.request_clock.stop()
        self.stop_all_voice()
        self.bubble_hide_timer.stop()
        self.idle_cycle_timer.stop()
        self.needs_timer.stop()
        self.clickthrough_timer.stop()
        for worker in (self._worker, self._discovery_worker, *self._tts_workers):
            if worker and worker.isRunning():
                worker.cancel()
        self._finish_shutdown()

    def _finish_shutdown(self) -> None:
        if any(w and w.isRunning() for w in (self._worker, self._discovery_worker, *self._tts_workers)):
            QTimer.singleShot(100, self._finish_shutdown)
            return
        if hasattr(self, "global_hotkey") and hasattr(self.global_hotkey, "unregister"):
            self.global_hotkey.unregister()
        if hasattr(self, "tray"):
            self.tray.hide()
        self.chat_panel.hide()
        self.hide()
        QApplication.instance().quit()

    def _cleanup_workers(self) -> None:
        self.stop_all_voice()
        for worker in (self._worker, self._discovery_worker, *self._tts_workers):
            if worker and worker.isRunning():
                worker.cancel()
        for worker in (self._worker, self._discovery_worker, *self._tts_workers):
            if worker and worker.isRunning():
                worker.wait(7000)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.request_shutdown()

    def _init_window_flags(self) -> None:
        self.setWindowTitle("Frieren Desk Companion")
        self.setMinimumSize(340,560)
        self.setMouseTracking(True)
        self.resize(self.base_win_w,self.base_win_h)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if hasattr(Qt.WidgetAttribute, "WA_MacAlwaysShowToolWindow") and sys.platform == "darwin":
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

    def _init_ui(self, history_enabled: bool, output_enabled: bool, needs_enabled: bool = False) -> None:
        if self.profile.id == "frieren":
            sprites = ensure_sprites(self.base_dir / "assets" / "sprites")
            folder = self.base_dir / "assets/characters/frieren/blink"
            blink_sprites = {state: folder / f"{state}.png" for state in sprites if (folder / f"{state}.png").is_file()}
        else:
            sprites, blink_sprites = self.profile.assets(self.base_dir)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 24)
        root.setSpacing(4)

        # Top stretch pushes the speech bubble down so it sits right above Frieren's head!
        root.addSpacing(4)

        self.bubble = SpeechBubble(
            sound_player=self.sound_player,
            typing_interval_ms=self.typing_interval_ms,
            history_enabled=history_enabled,
            output_enabled=output_enabled,
            agent_enabled=self.backend.agent_execution_enabled,
            needs_enabled=needs_enabled,
            parent=self,
        )
        self.bubble.soundToggled.connect(self._on_sound_toggled)
        self.bubble.historyToggled.connect(self._on_history_toggled)
        self.bubble.outputToggled.connect(self._on_output_toggled)
        self.bubble.agentToggled.connect(self._on_agent_toggled)
        self.bubble.needsToggled.connect(self._on_needs_toggled)
        self.bubble.needReplenishRequested.connect(self._fulfill_need)
        self.bubble.careAllRequested.connect(self._fulfill_all_needs)
        self.bubble.minimizeRequested.connect(self.minimize_bubble_only)
        self.bubble.panelRequested.connect(self.open_chat_panel)
        self.bubble.typingFinished.connect(self._on_typing_finished)
        self.bubble.bubbleDragDeltaY.connect(self._on_bubble_drag_delta)
        self.bubble.bubbleDragFinished.connect(self._on_bubble_drag_finished)
        self._refresh_bubble_history()
        self.bubble.update_needs_data(self.needs.data)
        root.addWidget(self.bubble)

        # Controlled gap widget between Bubble and Frieren (clamped 0..70px so it never goes too far)
        self.bubble_spacer = QWidget(self)
        self.bubble_spacer.setFixedHeight(max(0, min(70, self.bubble_gap)))
        self.bubble_spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        root.addWidget(self.bubble_spacer)
        root.addStretch(1)

        self.sprite = FrierenSpriteWidget(
            sprites, fade_ms=self.fade_ms, parent=self,
            motion_mode=self.config.get("ui", {}).get("motion_mode", "natural"),
        )
        self.sprite.set_sprites(sprites,blink_sprites,self.profile.mouth_frames(self.base_dir))
        root.addWidget(self.sprite, alignment=Qt.AlignmentFlag.AlignRight)

        # Attachment Preview Bar (shown above input bar when user pastes/drops images or files)
        self.attachment_bar = AttachmentList(self)
        self.attachment_bar.removeRequested.connect(self.remove_attachment)
        self.attachment_bar.setVisible(False)
        root.addWidget(self.attachment_bar)

        self.input_container = QFrame(self)
        self.input_container.setObjectName("inputContainer")
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(5)

        self.attach_btn = QPushButton("📎", self.input_container)
        self.attach_btn.setObjectName("attachButton")
        self.attach_btn.setFixedSize(30, 32)
        self.attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_btn.setToolTip("Lampirkan Gambar / File (Atau langsung Cmd+V / Drag & Drop ke Frieren)")
        self.attach_btn.clicked.connect(self._pick_attachments_dialog)

        self.input_box = ChatInputBox(self.input_container)
        self.input_box.setFixedHeight(64)
        self.input_box.setObjectName("chatInput")
        self.input_box.setPlaceholderText("Ngobrol sama Frieren...")
        self.input_box.returnPressed.connect(self.send_message)
        self.input_box.imagePasted.connect(self._on_image_pasted)
        self.input_box.filesDropped.connect(self._on_files_dropped)

        self.send_btn = QPushButton("Kirim", self.input_container)
        self.send_btn.setObjectName("sendButton")
        self.send_btn.setFixedSize(48, 32)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)
        self.cancel_btn = QPushButton("Batal", self.input_container)
        self.cancel_btn.setObjectName("cancelButton")
        self.cancel_btn.setToolTip("Hentikan permintaan AI yang sedang berjalan")
        self.cancel_btn.setFixedSize(48, 32)
        self.cancel_btn.clicked.connect(self.cancel_request)
        self.cancel_btn.hide()

        input_layout.addWidget(self.attach_btn)
        input_layout.addWidget(self.input_box, 1)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.cancel_btn)
        root.addWidget(self.input_container)

        self._base_style = (
            """
            #speechBubble {
                background-color: rgba(25, 27, 38, 238);
                border: 1.5px solid rgba(216, 67, 82, 195);
                border-radius: 14px;
            }
            #bubbleTitle {
                color: #FFD6DC;
                font-size: 12px;
                font-weight: 700;
            }
            #emotionBadge {
                background-color: rgba(216, 67, 82, 55);
                border: 1px solid rgba(255, 182, 193, 95);
                border-radius: 7px;
                color: #FFEBF0;
                font-size: 10.5px;
                font-weight: 600;
                padding: 1px 6px;
            }
            #stateBadge {
                color: #AEB8D0;
                font-size: 10.5px;
                font-style: italic;
            }
            #iconToggleBtn {
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 35);
                border-radius: 6px;
                color: #F5F7FA;
                font-size: 11px;
                padding: 0px;
            }
            #iconToggleBtn:checked {
                background-color: rgba(209, 59, 73, 155);
                border: 1px solid rgba(255, 190, 200, 175);
            }
            #iconToggleBtn:hover {
                background-color: rgba(255, 255, 255, 45);
            }
            #secondaryButton {
                background-color: #382535;
                color: #FFE5ED;
                border: 1px solid #815066;
                border-radius: 6px;
                padding: 3px 7px;
                font-size: 11px;
            }
            #secondaryButton:hover { background-color: #603048; }
            #cancelButton {
                background-color: #883C4B;
                color: #FFFFFF;
                border: 1px solid #D97D8D;
                border-radius: 7px;
                font-size: 11px;
            }
            #historyScroll {
                background-color: rgba(16, 18, 26, 175);
                border: 1px solid rgba(255, 255, 255, 28);
                border-radius: 9px;
            }
            #msgScroll {
                background-color: transparent;
                border: none;
            }
            #bubbleText {
                background-color: rgba(25, 27, 38, 245);
                color: #F5F7FA;
                font-size: 12.5px;
                line-height: 1.35;
                padding-right: 4px;
            }
            #historyContent {
                background: transparent;
            }
            #codexOutputBox {
                background-color: rgba(12, 14, 20, 215);
                border: 1px solid rgba(130, 170, 255, 75);
                border-radius: 9px;
                color: #B9F27C;
                font-family: "SF Mono", Menlo, Monaco, monospace;
                font-size: 11px;
                padding: 5px;
                selection-background-color: #3D59A1;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 2px 1px 2px 1px;
            }
            QScrollBar::handle:vertical {
                background: rgba(216, 67, 82, 160);
                min-height: 18px;
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            #ltmBadge {
                color: #FFE082;
                font-size: 10.5px;
                font-weight: 600;
                padding: 2px 4px;
            }
            #historyItemUser {
                background-color: rgba(58, 66, 92, 145);
                border-radius: 7px;
            }
            #historyItemBot {
                background-color: rgba(120, 38, 52, 130);
                border-radius: 7px;
            }
            #historyItemText {
                color: #ECEFF6;
                font-size: 11.5px;
            }
            #historyEmpty {
                color: #8E96AA;
                font-size: 11px;
                font-style: italic;
                padding: 6px;
            }
            #loadingLabel {
                color: #FFD6DC;
                font-size: 11.5px;
                font-style: italic;
            }
            #needsPanel {
                background-color: rgba(16, 18, 26, 195);
                border: 1px solid rgba(255, 182, 193, 45);
                border-radius: 9px;
            }
            #needsTitle {
                color: #FFEBF0;
                font-size: 11.5px;
                font-weight: 700;
            }
            #needsCareAllBtn {
                background-color: rgba(216, 67, 82, 140);
                border: 1px solid rgba(255, 190, 200, 160);
                border-radius: 5px;
                color: #FFFFFF;
                font-size: 9.5px;
                font-weight: bold;
                padding: 1px 6px;
            }
            #needsCareAllBtn:hover {
                background-color: rgba(228, 84, 98, 210);
            }
            #needsRowLabel {
                color: #ECEFF6;
                font-size: 11px;
                font-weight: 500;
            }
            #needsActionBtn {
                background-color: rgba(255, 255, 255, 22);
                border: 1px solid rgba(255, 255, 255, 45);
                border-radius: 5px;
                color: #ECEFF6;
                font-size: 9.5px;
                font-weight: 600;
            }
            #needsActionBtn:hover {
                background-color: rgba(216, 67, 82, 155);
                border-color: rgba(255, 190, 200, 180);
            }
            #bubbleText {
                color: #F5F7FA;
                font-size: 12.5px;
                line-height: 1.35;
            }
            #inputContainer {
                background-color: rgba(24, 26, 36, 240);
                border: 1.5px solid rgba(236, 239, 246, 150);
                border-radius: 16px;
            }
            #attachmentBar {
                background-color: rgba(34, 38, 54, 238);
                border: 1px solid rgba(130, 170, 255, 145);
                border-radius: 11px;
            }
            #attachmentLabel {
                color: #D8E6FF;
                font-size: 11px;
                font-weight: 600;
            }
            #attachmentClearBtn {
                background-color: rgba(216, 67, 82, 140);
                border: none;
                border-radius: 9px;
                color: #FFFFFF;
                font-size: 10px;
                font-weight: bold;
            }
            #attachmentClearBtn:hover {
                background-color: rgba(228, 84, 98, 210);
            }
            #attachButton {
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 38);
                border-radius: 13px;
                color: #ECEFF6;
                font-size: 12px;
            }
            #attachButton:hover {
                background-color: rgba(255, 255, 255, 45);
            }
            #chatInput {
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-size: 12.5px;
                selection-background-color: #D13B49;
            }
            #sendButton {
                background-color: #D13B49;
                color: #FFFFFF;
                border: none;
                border-radius: 14px;
                font-weight: bold;
                font-size: 13px;
            }
            #sendButton:hover {
                background-color: #E45462;
            }
            #sendButton:disabled {
                background-color: #5A5F72;
            }
            """
        )
        self.setStyleSheet(self._base_style)
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(22,22)
        self.resize_grip.setStyleSheet("QSizeGrip { background: rgba(190, 155, 90, 100); border-radius: 5px; }")
        self.resize_grip.setToolTip("Tarik sudut atau tepi jendela untuk memperlebar / memperkecil chat")

    def _init_shortcuts_and_tray(self) -> None:
        hotkey_label = "Cmd+Shift+Space" if sys.platform == "darwin" else "Ctrl+Shift+Space"
        self.local_shortcut = QShortcut(QKeySequence("Meta+Shift+Space" if sys.platform == "darwin" else "Ctrl+Shift+Space"), self)
        self.local_shortcut.activated.connect(self.toggle_input_bar)

        meta_mod = "Meta" if sys.platform == "darwin" else "Ctrl"
        self.min_shortcut = QShortcut(QKeySequence(f"{meta_mod}+M"), self)
        self.min_shortcut.activated.connect(lambda: self.set_minimized(not self.is_minimized))

        self.zoom_in_shortcut = QShortcut(QKeySequence(f"{meta_mod}+="), self)
        self.zoom_in_shortcut.activated.connect(lambda: self.apply_scale(self.scale_factor + 0.12))
        self.zoom_in_shortcut2 = QShortcut(QKeySequence(f"{meta_mod}++"), self)
        self.zoom_in_shortcut2.activated.connect(lambda: self.apply_scale(self.scale_factor + 0.12))

        self.zoom_out_shortcut = QShortcut(QKeySequence(f"{meta_mod}+-"), self)
        self.zoom_out_shortcut.activated.connect(lambda: self.apply_scale(self.scale_factor - 0.12))

        self.zoom_reset_shortcut = QShortcut(QKeySequence(f"{meta_mod}+0"), self)
        self.zoom_reset_shortcut.activated.connect(lambda: self.apply_scale(1.0))

        self.esc_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.esc_shortcut.activated.connect(self.hide_input_bar)

        if sys.platform == "darwin":
            self.global_hotkey = MacGlobalHotKey(self.toggle_input_bar)
        elif sys.platform == "win32":
            self.global_hotkey = WinGlobalHotKey(self.toggle_input_bar)
        else:
            self.global_hotkey = None

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            tray_pix = self.sprite.pixmaps.get("idle")
            if tray_pix:
                self.tray.setIcon(QIcon(tray_pix))
            self.tray.setToolTip(f"Frieren Desk Companion ({hotkey_label})")

            menu = SceneMenu(self.profile,self)
            self.context_menu = menu
            header_action = QWidgetAction(menu)
            header = QFrame(menu)
            header.setObjectName("characterMenuHeader")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(10,8,12,8)
            self.menu_character_avatar = QLabel(header)
            self.menu_character_avatar.setFixedSize(48,52)
            header_layout.addWidget(self.menu_character_avatar)
            header_text = QVBoxLayout()
            self.menu_character_name = QLabel(self.profile.name)
            self.menu_character_name.setStyleSheet("font-size: 15px; font-weight: 700;")
            self.menu_character_desc = QLabel(self.profile.description)
            self.menu_character_desc.setObjectName("menuCharacterDescription")
            header_text.addWidget(self.menu_character_name)
            header_text.addWidget(self.menu_character_desc)
            header_layout.addLayout(header_text)
            header_action.setDefaultWidget(header)
            menu.addAction(header_action)
            menu.addSeparator()
            act_toggle = QAction(f"Munculkan / Fokus Input ({hotkey_label})", self)
            act_toggle.triggered.connect(self.toggle_input_bar)
            menu.addAction(act_toggle)

            act_chat = QAction("Buka Chat & Proyek", self)
            act_chat.triggered.connect(self.open_chat_panel)
            menu.addAction(act_chat)
            act_project = QAction("Pilih Folder Proyek…", self)
            act_project.triggered.connect(self.choose_project)
            menu.addAction(act_project)

            character_menu = menu.addMenu("Karakter")
            self.character_group = QActionGroup(self)
            self.character_group.setExclusive(True)
            self.character_actions = {}
            for identifier, profile in PROFILES.items():
                action = character_menu.addAction(profile.name)
                action.setCheckable(True)
                action.setChecked(identifier == self.profile.id)
                action.setEnabled(profile.available(self.base_dir))
                action.triggered.connect(lambda checked=False, value=identifier: self._set_character(value))
                self.character_group.addAction(action)
                self.character_actions[identifier] = action
            expression_menu = menu.addMenu("Ekspresi")
            self.expression_group = QActionGroup(self)
            self.expression_group.setExclusive(True)
            self.expression_actions = {}
            for key, label in [(None,"Otomatis"), *EXPRESSION_LABELS.items()]:
                action = expression_menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(key is None)
                action.triggered.connect(lambda checked=False, value=key: self._preview_expression(value))
                self.expression_group.addAction(action)
                self.expression_actions[key] = action
            view_menu = menu.addMenu("Tampilan & Posisi")
            voice_action = menu.addAction("Voice · Sample & Konteks…")
            voice_action.triggered.connect(self.open_voice_settings)

            act_min_bubble = QAction("Sembunyikan Bubble Chat Saja", self)
            act_min_bubble.triggered.connect(self.minimize_bubble_only)
            view_menu.addAction(act_min_bubble)

            self.act_autohide_bubble = QAction("Otomatis Minimize Bubble Saat Diam (Idle)", self)
            self.act_autohide_bubble.setCheckable(True)
            self.act_autohide_bubble.setChecked(self.auto_hide_bubble)
            self.act_autohide_bubble.triggered.connect(self._toggle_autohide_bubble)
            view_menu.addAction(self.act_autohide_bubble)

            self.act_minimize = QAction("Minimize Karakter ke Mode Mini (Cmd+M)", self)
            self.act_minimize.setCheckable(True)
            self.act_minimize.setChecked(self.is_minimized)
            self.act_minimize.triggered.connect(self.set_minimized)
            view_menu.addAction(self.act_minimize)

            self.act_hide_window = QAction("Sembunyikan ke Menu Bar Saja", self)
            self.act_hide_window.setCheckable(True)
            self.act_hide_window.setChecked(False)
            self.act_hide_window.triggered.connect(self._toggle_hide_to_tray)
            view_menu.addAction(self.act_hide_window)

            motion_menu = view_menu.addMenu("Gerakan Karakter")
            self.motion_group = QActionGroup(self)
            self.motion_group.setExclusive(True)
            for mode, label in (("natural", "Natural (25 FPS)"), ("reduced", "Hemat (10 FPS)"), ("off", "Nonaktif")):
                action = QAction(label, self)
                action.setCheckable(True)
                action.setChecked(self.sprite.motion_mode == mode)
                action.triggered.connect(lambda checked=False, value=mode: self._set_motion_mode(value))
                self.motion_group.addAction(action)
                motion_menu.addAction(action)

            menu.addSeparator()

            # Submenu: AI Engine Selection (Codex vs Antigravity)
            engine_menu = menu.addMenu("🤖 Mesin AI (Codex vs Antigravity)")
            self.engine_group = QActionGroup(self)
            self.engine_group.setExclusive(True)

            act_eng_codex = QAction("OpenAI Codex CLI", self)
            act_eng_codex.setCheckable(True)
            act_eng_codex.setChecked(self.backend.active_engine == "codex")
            act_eng_codex.triggered.connect(lambda: self._switch_engine("codex"))
            self.engine_group.addAction(act_eng_codex)
            engine_menu.addAction(act_eng_codex)

            act_eng_agy = QAction("Google Antigravity CLI", self)
            act_eng_agy.setCheckable(True)
            act_eng_agy.setChecked(self.backend.active_engine == "antigravity")
            act_eng_agy.triggered.connect(lambda: self._switch_engine("antigravity"))
            self.engine_group.addAction(act_eng_agy)
            engine_menu.addAction(act_eng_agy)

            self.model_menus = {"codex": engine_menu.addMenu("Model Codex"), "antigravity": engine_menu.addMenu("Model AGY")}
            self._refresh_model_menus()
            refresh_action = engine_menu.addAction("Refresh Model")
            refresh_action.triggered.connect(self.refresh_models)

            engine_menu.addSeparator()
            act_check_pre = QAction("Periksa Kesiapan Mesin (Login & Binary)", self)
            act_check_pre.triggered.connect(self._check_engine_status_dialog)
            engine_menu.addAction(act_check_pre)

            menu.addSeparator()

            self.act_agent = QAction("⚡ Izinkan Eksekusi Aksi / Buka Web (Agent Mode)", self)
            self.act_agent.setCheckable(True)
            self.act_agent.setChecked(self.backend.agent_execution_enabled)
            self.act_agent.triggered.connect(self._toggle_agent_from_menu)
            menu.addAction(self.act_agent)

            self.act_output = QAction("💻 Tampilkan Panel Output / Log Codex", self)
            self.act_output.setCheckable(True)
            self.act_output.setChecked(self.bubble.output_enabled)
            self.act_output.triggered.connect(self._toggle_output_from_menu)
            view_menu.addAction(self.act_output)

            self.act_history = QAction("📜 Tampilkan Riwayat Chat (Scrollable)", self)
            self.act_history.setCheckable(True)
            self.act_history.setChecked(self.bubble.history_enabled)
            self.act_history.triggered.connect(self._toggle_history_from_menu)
            view_menu.addAction(self.act_history)

            self.act_sound = QAction("🔊 Suara Ketikan (Motion Typing Sound)", self)
            self.act_sound.setCheckable(True)
            self.act_sound.setChecked(self.sound_player.enabled)
            self.act_sound.triggered.connect(self._toggle_sound_from_menu)
            view_menu.addAction(self.act_sound)

            # Submenu: Kebutuhan & Perhatian (Needs & Wellness System)
            needs_menu = menu.addMenu("🍵 Kebutuhan & Istirahat (Needs System)")

            self.act_status_needs = QAction("Tampilkan Panel Indikator Kebutuhan (🍵)", self)
            self.act_status_needs.setCheckable(True)
            self.act_status_needs.setChecked(self.bubble.needs_enabled)
            self.act_status_needs.triggered.connect(self._toggle_needs_from_menu)
            needs_menu.addAction(self.act_status_needs)
            needs_menu.addSeparator()

            act_feed_tea = QAction("🍵 Beri Teh Hangat (Thirst +40)", self)
            act_feed_tea.triggered.connect(lambda: self._fulfill_need("thirst"))
            needs_menu.addAction(act_feed_tea)

            act_feed_cake = QAction("🍰 Beri Camilan Manis (Hunger +40)", self)
            act_feed_cake.triggered.connect(lambda: self._fulfill_need("hunger"))
            needs_menu.addAction(act_feed_cake)

            act_rest = QAction("💤 Temani Istirahat Sejenak (Energy +40)", self)
            act_rest.triggered.connect(lambda: self._fulfill_need("energy"))
            needs_menu.addAction(act_rest)

            act_stretch = QAction("🌿 Peregangan Bersama (Freshness +40)", self)
            act_stretch.triggered.connect(lambda: self._fulfill_need("freshness"))
            needs_menu.addAction(act_stretch)

            needs_menu.addSeparator()
            act_care_all = QAction("✨ Penuhi Semua Kebutuhan (Care All)", self)
            act_care_all.triggered.connect(self._fulfill_all_needs)
            needs_menu.addAction(act_care_all)

            menu.addSeparator()

            # Submenu: Perasaan / Suasana Hati Frieren (Natural & Cozy)
            emotion_menu = expression_menu.addMenu("Suasana Hati")
            lbl_emo = QAction("Pilih suasana hati karakter:", self)
            lbl_emo.setEnabled(False)
            emotion_menu.addAction(lbl_emo)
            emotion_menu.addSeparator()
            for emo_key, (emo_label, emo_desc) in EMOTION_CATALOG.items():
                act_emo = QAction(f"{emo_label} — {emo_desc}", self)
                act_emo.triggered.connect(lambda checked=False, k=emo_key: self._set_manual_emotion(k))
                emotion_menu.addAction(act_emo)

            # Submenu: Resize / Ukuran Karakter & Window
            size_menu = view_menu.addMenu("📐 Ukuran Karakter")
            self.size_group = QActionGroup(self)
            self.size_group.setExclusive(True)
            size_presets = [
                ("Kecil (80%)", 0.80),
                ("Normal (100% - Cmd+0)", 1.00),
                ("Besar (120%)", 1.20),
                ("Ekstra Besar (140%)", 1.40),
            ]
            self.size_actions: Dict[float, QAction] = {}
            for label, sc in size_presets:
                act_sz = QAction(label, self)
                act_sz.setCheckable(True)
                act_sz.setChecked(abs(self.scale_factor - sc) < 0.06)
                act_sz.triggered.connect(lambda checked, s=sc: self.apply_scale(s))
                self.size_group.addAction(act_sz)
                size_menu.addAction(act_sz)
                self.size_actions[sc] = act_sz

            size_menu.addSeparator()
            act_zin = QAction("Perbesar Sedikit (Cmd + =)", self)
            act_zin.triggered.connect(lambda: self.apply_scale(self.scale_factor + 0.10))
            size_menu.addAction(act_zin)

            act_zout = QAction("Perkecil Sedikit (Cmd + -)", self)
            act_zout.triggered.connect(lambda: self.apply_scale(self.scale_factor - 0.10))
            size_menu.addAction(act_zout)

            # Submenu: Opacity / Transparansi (Option + Scroll)
            opacity_menu = view_menu.addMenu("💧 Transparansi / Opacity")
            self.opacity_group = QActionGroup(self)
            self.opacity_group.setExclusive(True)
            opacity_presets = [
                ("Solid (100%)", 1.00),
                ("Sedikit Transparan (85%)", 0.85),
                ("Lembut (70%)", 0.70),
                ("Samar (55%)", 0.55),
                ("Bayangan Tipis (40%)", 0.40),
            ]
            self.opacity_actions: Dict[float, QAction] = {}
            for label, op in opacity_presets:
                act_op = QAction(label, self)
                act_op.setCheckable(True)
                act_op.setChecked(abs(self.opacity_level - op) < 0.06)
                act_op.triggered.connect(lambda checked, o=op: self.apply_opacity(o))
                self.opacity_group.addAction(act_op)
                opacity_menu.addAction(act_op)
                self.opacity_actions[op] = act_op

            opacity_menu.addSeparator()
            act_opin = QAction("Lebih Jelas (+10%)", self)
            act_opin.triggered.connect(lambda: self.apply_opacity(self.opacity_level + 0.10))
            opacity_menu.addAction(act_opin)

            act_opout = QAction("Lebih Transparan (-10%)", self)
            act_opout.triggered.connect(lambda: self.apply_opacity(self.opacity_level - 0.10))
            opacity_menu.addAction(act_opout)

            # Submenu: Bubble Distance / Jarak Bubble ke Frieren (Drag Header / Shift + Scroll)
            gap_menu = view_menu.addMenu("💬 Jarak Bubble ke Karakter")
            self.gap_group = QActionGroup(self)
            self.gap_group.setExclusive(True)
            gap_presets = [
                ("Menempel Dekat (0 px)", 0),
                ("Dekat & Pas (4 px - Default)", 4),
                ("Sedang (16 px)", 16),
                ("Agak Atas (32 px)", 32),
                ("Batas Atas Maksimal (55 px)", 55),
            ]
            self.gap_actions: Dict[int, QAction] = {}
            for label, gp in gap_presets:
                act_gp = QAction(label, self)
                act_gp.setCheckable(True)
                act_gp.setChecked(abs(self.bubble_gap - gp) <= 3)
                act_gp.triggered.connect(lambda checked, g=gp: self.apply_bubble_gap(g))
                self.gap_group.addAction(act_gp)
                gap_menu.addAction(act_gp)
                self.gap_actions[gp] = act_gp

            gap_menu.addSeparator()
            act_gdown = QAction("Lebih Dekat ke Karakter (-6 px)", self)
            act_gdown.triggered.connect(lambda: self.apply_bubble_gap(self.bubble_gap - 6))
            gap_menu.addAction(act_gdown)

            act_gup = QAction("Agak Naik Sedikit (+6 px)", self)
            act_gup.triggered.connect(lambda: self.apply_bubble_gap(self.bubble_gap + 6))
            gap_menu.addAction(act_gup)

            menu.addSeparator()

            # Submenu: Memory & Google Drive Selection
            gdrive_menu = menu.addMenu("☁️ Memori & Sinkronisasi Google Drive")

            self.act_gdrive_sync = QAction("Aktifkan Auto-Sync ke Google Drive", self)
            self.act_gdrive_sync.setCheckable(True)
            self.act_gdrive_sync.setChecked(self.backend.gdrive_sync_enabled)
            self.act_gdrive_sync.triggered.connect(self.backend.set_gdrive_sync_enabled)
            gdrive_menu.addAction(self.act_gdrive_sync)

            gdrive_menu.addSeparator()
            lbl_acc = QAction("Pilih Akun Google Drive:", self)
            lbl_acc.setEnabled(False)
            gdrive_menu.addAction(lbl_acc)

            self.gdrive_group = QActionGroup(self)
            self.gdrive_group.setExclusive(True)
            for acc_name in self.backend.get_gdrive_accounts().keys():
                act_acc = QAction(f"• {acc_name}", self)
                act_acc.setCheckable(True)
                act_acc.setChecked(acc_name == self.backend.gdrive_account)
                act_acc.triggered.connect(lambda checked, a=acc_name: self._select_gdrive_account(a))
                self.gdrive_group.addAction(act_acc)
                gdrive_menu.addAction(act_acc)

            gdrive_menu.addSeparator()

            self.act_gdrive_plugin = QAction("Aktifkan Plugin Google Drive Codex (Cloud Search)", self)
            self.act_gdrive_plugin.setCheckable(True)
            self.act_gdrive_plugin.setChecked(self.backend.enable_gdrive_plugin)
            self.act_gdrive_plugin.triggered.connect(self.backend.set_enable_gdrive_plugin)
            gdrive_menu.addAction(self.act_gdrive_plugin)

            act_open_notes = QAction("Buka Catatan Grimoire (frieren_notes.md)", self)
            act_open_notes.triggered.connect(self._open_notes_file)
            gdrive_menu.addAction(act_open_notes)

            act_restore_gdrive = QAction("Muat Ulang Memori dari Google Drive", self)
            act_restore_gdrive.triggered.connect(self._restore_from_gdrive)
            gdrive_menu.addAction(act_restore_gdrive)

            menu.addSeparator()

            act_pleased = QAction("Sapa Karakter ♪", self)
            act_pleased.triggered.connect(self._pet_frieren)
            menu.addAction(act_pleased)

            act_reset = QAction("Bersihkan Riwayat Chat Sementara", self)
            act_reset.triggered.connect(lambda: self._clear_history(include_ltm=False))
            gdrive_menu.addAction(act_reset)

            act_reset_all = QAction("Bersihkan Semua Memori (Termasuk LTM)", self)
            act_reset_all.triggered.connect(lambda: self._clear_history(include_ltm=True))
            gdrive_menu.addAction(act_reset_all)

            act_dock = QAction("Kembalikan ke Pojok Kanan Bawah", self)
            act_dock.triggered.connect(self.dock_bottom_right)
            view_menu.addAction(act_dock)

            menu.addSeparator()
            act_quit = QAction("Keluar", self)
            act_quit.triggered.connect(self.request_shutdown)
            menu.addAction(act_quit)

            self.tray.setContextMenu(menu)
            self.tray.show()

    def _refresh_bubble_history(self) -> None:
        ltm_count = len(self.backend.load_ltm()) + len(self.backend.load_ltm("project"))
        self.bubble.refresh_history(self.backend.load_memory(), ltm_count=ltm_count)
        if self.chat_panel:
            self.chat_panel.set_history(self.backend.load_memory())

    # ------------------------------------------------------------------
    # Resize / Scale & Idle Multi-Pose Controls
    # ------------------------------------------------------------------
    def apply_scale(self, new_scale: float, save: bool = True, redock: bool = True) -> None:
        self.scale_factor = max(0.70, min(1.50, round(float(new_scale), 2)))

        # Keep bottom-right corner anchored when resizing
        old_geo = self.geometry()
        new_w = int(self.base_win_w * self.scale_factor)
        new_h = int(self.base_win_h * self.scale_factor)
        self.resize(new_w,new_h)

        bubble_w = max(240, new_w - 22)
        self.bubble.setMinimumWidth(max(240,int(280*self.scale_factor)))
        self.bubble.setMaximumWidth(bubble_w)
        self.bubble._refresh_header_fit()
        self.bubble._update_msg_scroll_height()
        self.sprite.set_scale_factor(self.scale_factor)

        if hasattr(self, "size_actions"):
            for sc, act in self.size_actions.items():
                act.setChecked(abs(self.scale_factor - sc) < 0.06)

        if redock and old_geo.width() > 0:
            new_x = old_geo.right() - new_w + 1
            new_y = old_geo.bottom() - new_h + 1
            self.move(new_x, new_y)

        if save:
            self.backend.save_ui_prefs(
                self.sound_player.enabled,
                self.bubble.history_enabled,
                output_enabled=self.bubble.output_enabled,
                minimized=self.is_minimized,
                scale=self.scale_factor,
                opacity=self.opacity_level,
            )

    def apply_opacity(self, new_opacity: float, save: bool = True) -> None:
        self.opacity_level = max(0.25, min(1.00, round(float(new_opacity), 2)))
        self.setWindowOpacity(self.opacity_level)
        if hasattr(self, "opacity_actions"):
            for op, act in self.opacity_actions.items():
                act.setChecked(abs(self.opacity_level - op) < 0.06)
        if save:
            self.backend.save_ui_prefs(
                self.sound_player.enabled,
                self.bubble.history_enabled,
                output_enabled=self.bubble.output_enabled,
                minimized=self.is_minimized,
                scale=self.scale_factor,
                opacity=self.opacity_level,
                bubble_gap=self.bubble_gap,
            )

    def apply_bubble_gap(self, new_gap: int, save: bool = True) -> None:
        # Clamp strictly within 0..65px so the bubble always stays close to Frieren!
        self.bubble_gap = max(0, min(65, int(new_gap)))
        if hasattr(self, "bubble_spacer"):
            self.bubble_spacer.setFixedHeight(self.bubble_gap)
        if hasattr(self, "gap_actions"):
            for gp, act in self.gap_actions.items():
                act.setChecked(abs(self.bubble_gap - gp) <= 3)
        if save:
            self.backend.save_ui_prefs(
                self.sound_player.enabled,
                self.bubble.history_enabled,
                output_enabled=self.bubble.output_enabled,
                minimized=self.is_minimized,
                scale=self.scale_factor,
                opacity=self.opacity_level,
                bubble_gap=self.bubble_gap,
            )

    def _on_bubble_drag_delta(self, dy: int) -> None:
        self.apply_bubble_gap(self.bubble_gap + dy, save=False)

    def _on_bubble_drag_finished(self) -> None:
        self.apply_bubble_gap(self.bubble_gap, save=True)

    def _cycle_idle_pose(self) -> None:
        """Gently cycles Frieren's idle pose between various cute expressions."""
        self.idle_cycle_timer.setInterval(random.randint(24000, 48000))
        if self._manual_expression is not None or self._voice_active:
            return
        if not self.isVisible() or self.is_minimized or self.bubble.typing_timer.isActive():
            return
        if self.sprite.motion_mode == "off":
            return
        if self._worker and self._worker.isRunning():
            return
        # If Frieren is sleeping, do not interrupt her sleep with active idle poses
        if getattr(self, "needs", None) and self.needs.is_sleeping:
            return
        if not self.sprite.current_state.startswith("idle"):
            return
        # Prefer quiet, related poses; tea/reading return through the neutral pose
        # rather than switching directly between very different hand positions.
        current = self.sprite.current_state
        if current not in ("idle", "idle_cozy"):
            next_pose = "idle"
        else:
            choices = ["idle", "idle_cozy", "idle_reading", "idle_tea"]
            if self.needs.data["energy"] < 45:
                choices.append("idle_sleepy")
            next_pose = random.choice([pose for pose in choices if pose != current])
        self.sprite.set_state(next_pose)
        self.bubble.update_state_badge(next_pose)

    # ------------------------------------------------------------------
    # Minimize & Auto-Hide Bubble Controls
    # ------------------------------------------------------------------
    def minimize_bubble_only(self) -> None:
        """Hides the speech bubble and input bar while keeping Frieren at normal size."""
        self.bubble_hide_timer.stop()
        self.input_box.clearFocus()
        self.bubble.setVisible(False)
        self.input_container.setVisible(False)

    def show_bubble(self) -> None:
        if not self.is_minimized and not self.bubble.isVisible():
            self.bubble.setVisible(True)

    def _toggle_autohide_bubble(self, checked: bool) -> None:
        self.auto_hide_bubble = bool(checked)
        self.config.setdefault("ui", {})["auto_hide_bubble"] = self.auto_hide_bubble
        self.backend.save_config()
        if self.auto_hide_bubble:
            self._schedule_bubble_autohide()
        else:
            self.bubble_hide_timer.stop()
            self.show_bubble()

    def _schedule_bubble_autohide(self) -> None:
        if not self.auto_hide_bubble:
            return
        self.bubble_hide_timer.start(self.bubble_autohide_ms)

    def _on_bubble_autohide_timeout(self) -> None:
        if self._voice_active or self._tts_pending:
            self._schedule_bubble_autohide()
            return
        if not self.auto_hide_bubble or self.is_minimized or self._is_context_menu_open():
            if self._is_context_menu_open():
                self._schedule_bubble_autohide()
            return
        # Do not auto-hide if Codex is running, typing is active, input has focus/text, or cursor is inside bubble/input
        if self._worker and self._worker.isRunning():
            self._schedule_bubble_autohide()
            return
        if self.bubble.typing_timer.isActive():
            self._schedule_bubble_autohide()
            return
        if self.input_box.hasFocus() or self.input_box.text().strip() or self.pending_attachments:
            self._schedule_bubble_autohide()
            return
        if self.bubble.history_enabled or self.bubble.output_enabled or self.bubble.needs_enabled:
            self._schedule_bubble_autohide()
            return
        local_cursor = self.mapFromGlobal(QCursor.pos())
        if self.bubble.geometry().contains(local_cursor) or self.input_container.geometry().contains(local_cursor):
            self._schedule_bubble_autohide()
            return
        self.minimize_bubble_only()

    def set_minimized(self, minimized: bool) -> None:
        self.is_minimized = bool(minimized)
        self.resize_grip.setVisible(not self.is_minimized)
        self.update()
        if hasattr(self, "act_minimize"):
            self.act_minimize.setChecked(self.is_minimized)

        if self.is_minimized:
            self.bubble.setVisible(False)
            self.input_container.setVisible(False)
            self.sprite.set_minimized_mode(True)
        else:
            if not self.isVisible():
                self.show()
                if hasattr(self, "act_hide_window"):
                    self.act_hide_window.setChecked(False)
            self.sprite.set_minimized_mode(False)
            self.bubble.setVisible(True)
            self.input_container.setVisible(True)

        self.backend.save_ui_prefs(
            self.sound_player.enabled,
            self.bubble.history_enabled,
            output_enabled=self.bubble.output_enabled,
            minimized=self.is_minimized,
        )

    def _toggle_hide_to_tray(self, hidden: bool) -> None:
        if hidden:
            self.hide()
        else:
            self.show()
            self.raise_()

    # ------------------------------------------------------------------
    # Settings & Menu Callbacks
    # ------------------------------------------------------------------
    def _show_needs_status(self) -> None:
        d = self.needs.data
        status_msg = (
            f"Status Kebutuhan & Kesejahteraan:\n"
            f"• ☕ Kehausan (Thirst): {int(d['thirst'])}%\n"
            f"• 🍰 Kelaparan (Hunger): {int(d['hunger'])}%\n"
            f"• 💤 Energi (Energy): {int(d['energy'])}%\n"
            f"• 🌿 Kesegaran (Freshness): {int(d['freshness'])}%\n\n"
            f"{self.profile.name} siap menemanimu bekerja ✦"
        )
        self.set_character_state("pleased", status_msg, animate_typing=True, emotion_override="hangat")

    def _fulfill_need(self, need_key: str) -> None:
        reply = self.needs.replenish(need_key)
        self.bubble.update_needs_data(self.needs.data)
        pose_map = {
            "thirst": "needs_tea",
            "hunger": "needs_hungry",
            "energy": "needs_sleepy",
            "freshness": "needs_stretch",
        }
        pose = pose_map.get(need_key, "pleased")
        self.set_character_state(pose, reply, animate_typing=True, emotion_override="senang")

    def _fulfill_all_needs(self) -> None:
        reply = self.needs.replenish_all().replace("Frieren",self.profile.name)
        self.bubble.update_needs_data(self.needs.data)
        self.set_character_state("pleased_wave", reply, animate_typing=True, emotion_override="antusias")

    def _on_needs_tick(self) -> None:
        reminder = self.needs.tick(elapsed_seconds=60.0)
        self.bubble.update_needs_data(self.needs.data)
        if self._manual_expression is not None or self._voice_active or self._tts_pending:
            return

        # If Frieren is sleeping, keep her in sleeping state quietly without spamming bubble
        if self.needs.is_sleeping and not self.bubble.typing_timer.isActive():
            if not self._worker or not self._worker.isRunning():
                if self.sprite.current_state != "sleeping":
                    self.sprite.set_state("sleeping")
                    self.bubble.update_state_badge("sleeping", emotion_override="mengantuk")

        # Only notify if Frieren is idle and not typing or chatting
        if reminder and not self.bubble.typing_timer.isActive():
            if not self._worker or not self._worker.isRunning():
                need_key, text, pose = reminder
                # Soft friendly reminder or auto-sleep notification
                emotion = "mengantuk" if need_key in ("auto_sleep", "energy") else ("ceria" if need_key == "wake_up" else "penasaran")
                self.set_character_state(pose, text, animate_typing=True, emotion_override=emotion)

    def _switch_engine(self, engine_name: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.backend.set_engine(engine_name)
        ok, reason = self.backend.check_engine_prerequisites()
        engine_label = f"{engine_name} ({self.backend.active_model})"
        if ok:
            msg = f"Mesin AI dialihkan ke {engine_label} ✦"
            emo = "antusias"
        else:
            msg = f"Beralih ke {engine_label}, namun ada catatan:\n{reason}"
            emo = "tenang"
        self.set_character_state("pleased", msg, animate_typing=True, emotion_override=emo)
        self.chat_panel.update_context(self.backend)
        self._update_ai_context("Engine dipilih")

    def _check_engine_status_dialog(self) -> None:
        ok, reason = self.backend.check_engine_prerequisites()
        engine_label = "Antigravity CLI" if self.backend.active_engine == "antigravity" else "OpenAI Codex CLI"
        status_txt = f"[{engine_label}]\n{reason}"
        self.set_character_state("pleased", status_txt, animate_typing=True, emotion_override="fokus" if ok else "penasaran")

    def _on_sound_toggled(self, enabled: bool) -> None:
        if hasattr(self, "act_sound"):
            self.act_sound.setChecked(enabled)
        self.backend.save_ui_prefs(enabled, self.bubble.history_enabled, self.bubble.output_enabled, self.is_minimized)

    def _set_motion_mode(self, mode: str) -> None:
        self.sprite.set_motion_mode(mode)
        self.config.setdefault("ui", {})["motion_mode"] = self.sprite.motion_mode
        self.backend.save_config()

    def _on_history_toggled(self, enabled: bool) -> None:
        if hasattr(self, "act_history"):
            self.act_history.setChecked(enabled)
        if enabled:
            self._refresh_bubble_history()
        self.backend.save_ui_prefs(self.sound_player.enabled, enabled, self.bubble.output_enabled, self.is_minimized)

    def _on_output_toggled(self, enabled: bool) -> None:
        if hasattr(self, "act_output"):
            self.act_output.setChecked(enabled)
        self.backend.save_ui_prefs(self.sound_player.enabled, self.bubble.history_enabled, enabled, self.is_minimized)

    def _on_needs_toggled(self, enabled: bool) -> None:
        if hasattr(self, "act_status_needs"):
            self.act_status_needs.setChecked(enabled)
        if enabled:
            self.bubble.update_needs_data(self.needs.data)
        self.config.setdefault("ui", {})["needs_enabled"] = bool(enabled)
        self.backend.save_config()

    def _on_agent_toggled(self, enabled: bool) -> None:
        if self._worker and self._worker.isRunning():
            self.bubble.set_agent_enabled(self.backend.agent_execution_enabled)
            return
        if hasattr(self, "act_agent"):
            self.act_agent.setChecked(enabled)
        self.backend.set_agent_execution_enabled(enabled)
        mode_msg = (
            "Mode Eksekusi Codex (⚡) diaktifkan. Aku sekarang bisa membuka web dan menjalankan perintah untukmu."
            if enabled
            else "Mode Eksekusi Codex (⚡) dimatikan (Read-Only). Aku hanya akan mengobrol dan menganalisis dengan aman."
        )
        self.set_character_state("pleased", mode_msg, animate_typing=True)

    def _toggle_sound_from_menu(self, checked: bool) -> None:
        self.bubble.set_sound_enabled(checked)
        self._on_sound_toggled(checked)

    def _toggle_history_from_menu(self, checked: bool) -> None:
        if checked:
            self._refresh_bubble_history()
        self.bubble.set_history_enabled(checked)
        self._on_history_toggled(checked)

    def _toggle_output_from_menu(self, checked: bool) -> None:
        self.bubble.set_output_enabled(checked)
        self._on_output_toggled(checked)

    def _toggle_agent_from_menu(self, checked: bool) -> None:
        self.bubble.set_agent_enabled(checked)
        self._on_agent_toggled(checked)

    def _toggle_needs_from_menu(self, checked: bool) -> None:
        self.bubble.set_needs_enabled(checked)
        self._on_needs_toggled(checked)

    def _select_gdrive_account(self, account: str) -> None:
        status = self.backend.set_gdrive_account(account)
        if self.is_minimized:
            self.set_minimized(False)
        self.set_character_state("pleased", f"Akun Google Drive diatur ke {account}. ({status})", animate_typing=True)

    def _open_notes_file(self) -> None:
        if not self.backend.notes_path.exists():
            self.backend._write_markdown_notes(self.backend.load_ltm())
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.backend.notes_path)))

    def _restore_from_gdrive(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        status = self.backend.restore_from_gdrive()
        self._refresh_bubble_history()
        if self.is_minimized:
            self.set_minimized(False)
        self.set_character_state("pleased", status, animate_typing=True)

    # ------------------------------------------------------------------
    # Window Positioning & Dynamic Click-Through
    # ------------------------------------------------------------------
    def dock_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        avail: QRect = screen.availableGeometry()
        x = avail.right() - self.width() - self.margin_right
        y = avail.bottom() - self.height() - self.margin_bottom
        self.move(x, y)

    def _interactive_region(self) -> QRegion:
        if hasattr(self,"surface") and not self.is_minimized:
            return QRegion(self.rect())
        region = QRegion()
        if self.bubble.isVisible():
            region = region.united(QRegion(self.bubble.geometry()))
        if self.attachment_bar.isVisible():
            region = region.united(QRegion(self.attachment_bar.geometry()))
        if self.input_container.isVisible():
            region = region.united(QRegion(self.input_container.geometry()))

        sprite_reg = self.sprite.opaque_region().translated(self.sprite.pos())
        region = region.united(sprite_reg)
        return region

    def _is_context_menu_open(self) -> bool:
        if QApplication.activePopupWidget() is not None:
            return True
        if hasattr(self, "tray") and self.tray.contextMenu() and self.tray.contextMenu().isVisible():
            return True
        return False

    def _update_mask_and_clickthrough(self) -> None:
        if not self.isVisible():
            return
        # Never toggle window flags while a right-click popup menu is open (otherwise self.show() closes the menu!)
        if self._is_context_menu_open():
            return
        region = self._interactive_region()
        local_cursor = self.mapFromGlobal(QCursor.pos())
        inside_interactive = region.contains(local_cursor)

        should_clickthrough = not inside_interactive and not self.input_box.hasFocus()

        if sys.platform == "win32":
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            is_transparent = bool(style & WS_EX_TRANSPARENT)
            if should_clickthrough and not is_transparent:
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT)
            elif not should_clickthrough and is_transparent:
                user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
        else:
            transparent_for_input = bool(self.windowFlags() & Qt.WindowType.WindowTransparentForInput)
            if should_clickthrough:
                if not transparent_for_input:
                    self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
                    self.show()
            else:
                if transparent_for_input:
                    self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
                    self.show()

    def _set_manual_emotion(self, emotion_key: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        expression = {"senang":"happy", "ceria":"happy", "antusias":"happy",
                      "tersentuh":"happy", "penasaran":"thinking", "fokus":"thinking",
                      "nostalgia":"thinking", "mengantuk":"sleepy"}.get(emotion_key,"neutral")
        self._preview_expression(expression)
        self.bubble.set_emotion(emotion_key)
        pose_for_emotion = {
            "tenang": "idle",
            "hangat": "idle_cozy",
            "senang": "pleased",
            "ceria": "idle_dancing",
            "antusias": "pleased_wave",
            "penasaran": "thinking_tilt",
            "fokus": "idle_reading",
            "tersentuh": "pleased",
            "nostalgia": "thinking_lookup",
            "mengantuk": "idle_sleepy",
        }.get(emotion_key, "idle")
        self.sprite.set_state(pose_for_emotion)
        self.bubble.update_state_badge(pose_for_emotion, emotion_override=emotion_key)
        self.show_bubble()
        self._schedule_bubble_autohide()

    def set_character_state(
        self,
        state: str,
        message: Optional[str] = None,
        animate_typing: bool = False,
        emotion_override: Optional[str] = None,
    ) -> None:
        self.sprite.set_state(state)
        if message is not None:
            self.sprite.set_speaking(bool(animate_typing and state.startswith("talking")))
        elif not state.startswith("talking"):
            self.sprite.set_speaking(False)
        if state == "thinking" and message is None:
            self.show_bubble()
            self.bubble_hide_timer.stop()
            self.bubble.show_loading()
        elif message is not None:
            self.show_bubble()
            self.bubble_hide_timer.stop()
            self.bubble.show_message(
                message,
                state=state,
                animate=animate_typing,
                emotion_override=emotion_override,
            )
        else:
            self.bubble.update_state_badge(state, emotion_override=emotion_override)

    def _on_typing_finished(self) -> None:
        self.sprite.set_speaking(self._voice_active)
        if (
            self.sprite.current_state in TALKING_POSES
            or self.sprite.current_state.startswith("talking")
            or self.sprite.current_state.startswith("needs_")
        ):
            self._next_scheduled_state = "pleased"
            self.state_timer.start(self.talking_hold_ms)
        else:
            self._schedule_bubble_autohide()

    def _on_state_timer(self) -> None:
        if self._manual_expression is not None:
            return
        if self._voice_active or self._tts_pending:
            self.state_timer.start(200)
            return
        if self._worker and self._worker.isRunning():
            return
        if self._next_scheduled_state == "pleased":
            pleased_pose = random.choice(("pleased", "idle_cozy"))
            # Keep the current conversation emotion while holding the pleased smile after talking
            self.set_character_state(pleased_pose, emotion_override=self.bubble.current_emotion_key)
            self._next_scheduled_state = "idle"
            self.state_timer.start(self.pleased_hold_ms)
        else:
            idle_pose = random.choice(("idle", "idle_cozy"))
            self.set_character_state(idle_pose)
            self._schedule_bubble_autohide()

    def toggle_input_bar(self) -> None:
        if not self.isVisible():
            self._toggle_hide_to_tray(False)
        if self.is_minimized:
            self.set_minimized(False)
            self.show_input_bar()
            return
        if self.input_container.isVisible() and self.input_box.hasFocus():
            self.hide_input_bar()
        else:
            self.show_bubble()
            self.show_input_bar()

    def show_input_bar(self) -> None:
        if bool(self.windowFlags() & Qt.WindowType.WindowTransparentForInput):
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
            self.show()
        self.show_bubble()
        self.bubble_hide_timer.stop()
        self.input_container.setVisible(True)
        self.raise_()
        self.activateWindow()
        self.input_box.setFocus()

    def hide_input_bar(self) -> None:
        self.input_box.clearFocus()
        self.input_container.setVisible(False)
        self._schedule_bubble_autohide()

    def _pet_frieren(self) -> None:
        if self._worker and self._worker.isRunning():
            self.show_input_bar()
            return
        self._voice_suppressed = False
        if self.is_minimized:
            self.set_minimized(False)
            return
        if self._tts_pending or self._voice_active:
            # Repeated taps must not restart an expensive clone or interrupt a reply.
            self.show_bubble()
            return
        self.state_timer.stop()
        self._manual_expression = None
        self._sync_expression_controls(None)
        self.sprite.react_to_click()
        self._play_voice_event("greeting")

        # If Frieren was sleeping, waking her up gently by petting
        if getattr(self, "needs", None) and self.needs.is_sleeping:
            self.needs.wake_up()
            self.bubble.update_needs_data(self.needs.data)
            quote = "Hooam... eh, kamu menyapaku ya? Aku bangun kok... Ada yang bisa kubantu? ✦"
            if self._sync_voice_enabled():
                self._start_synced_narration(quote, "ふああ……あ、声をかけてくれたんだね。起きてるよ。何か手伝おうか？", "hangat", "pleased")
                return
            self.set_character_state("pleased", quote, animate_typing=True, emotion_override="hangat")
            self._next_scheduled_state = "idle"
            self.state_timer.start(self.pleased_hold_ms)
            return

        # Keep the visible Indonesian line and its Japanese dub paired.
        candidates = [i for i in range(len(self.profile.taps)) if i != self._last_pet_idx]
        idx = random.choice(candidates)
        self._last_pet_idx = idx
        quote = self.profile.taps[idx]

        # Pick a varied happy/cozy pose & warm emotion when clicked
        pose = random.choice(PLEASED_POSES)
        pet_emotion = random.choice(("senang", "tersentuh", "hangat", "ceria"))
        if self._sync_voice_enabled():
            self._start_synced_narration(quote, self.profile.voice_taps[idx], pet_emotion, pose)
            return
        self.set_character_state(
            pose,
            quote,
            animate_typing=True,
            emotion_override=pet_emotion,
        )
        self._next_scheduled_state = "idle"
        self.state_timer.start(self.pleased_hold_ms)

    def _clear_history(self, include_ltm: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            return
        self.stop_all_voice()
        self.backend.clear_memory(include_ltm=include_ltm)
        self._refresh_bubble_history()
        msg = (
            "Riwayat dan catatan untuk konteks aktif sudah kubersihkan."
            if include_ltm
            else "Riwayat chat sementara sudah kubersihkan, tapi catatan pentingmu tetap tersimpan aman."
        )
        self.set_character_state("pleased", msg, animate_typing=True)
        self._next_scheduled_state = "idle"
        self.state_timer.start(self.pleased_hold_ms)

    # ------------------------------------------------------------------
    # Image Clipboard Paste (Cmd+V) & File/Image Drag-and-Drop Support
    # ------------------------------------------------------------------
    def _refresh_attachment_bar(self) -> None:
        self.attachment_bar.set_paths(self.pending_attachments, max_rows=2)
        if self.chat_panel:
            self.chat_panel.set_attachment_paths(self.pending_attachments)

    def remove_attachment(self, path: str) -> None:
        if path in self.pending_attachments:
            self.pending_attachments.remove(path)
            self._refresh_attachment_bar()

    def clear_attachments(self) -> None:
        self.pending_attachments.clear()
        self._refresh_attachment_bar()

    def _add_attachment_path(self, path_str: str) -> None:
        if self._worker and self._worker.isRunning():
            return
        clean = str(Path(path_str.strip()).resolve())
        if not clean or not Path(clean).exists():
            return
        if clean not in self.pending_attachments:
            if len(self.pending_attachments) >= 8:
                self.chat_panel.status.setText("Maksimal 8 lampiran per pesan agar penggunaan memori terkendali.")
                return
            self.pending_attachments.append(clean)
        if not self.chat_panel.isVisible():
            self.show_input_bar()
        self._refresh_attachment_bar()

    def _on_image_pasted(self, img_obj) -> None:
        """Saves a pasted QImage/QPixmap from macOS clipboard into a PNG file and attaches it quietly."""
        try:
            if self._worker and self._worker.isRunning():
                return
            from datetime import datetime as _dt

            ts = _dt.now().strftime("%Y%m%d_%H%M%S_%f")
            out_file = self.clipboard_dir / f"gambar_{ts}.png"
            saved = img_obj.save(str(out_file), "PNG")
            if saved and out_file.exists():
                self._add_attachment_path(str(out_file))
        except Exception:
            pass

    def _on_files_dropped(self, paths: list) -> None:
        for raw_p in paths:
            p_str = str(raw_p).strip()
            if p_str and Path(p_str).exists():
                self._add_attachment_path(p_str)

    def _pick_attachments_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih Gambar atau File untuk Frieren",
            str(Path.home()),
            "Semua File (*.*);;Gambar (*.png *.jpg *.jpeg *.webp *.gif)",
        )
        if files:
            self._on_files_dropped(files)

    def dragEnterEvent(self, event) -> None:
        md = event.mimeData()
        if md and (md.hasUrls() or md.hasImage()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        if md:
            if md.hasImage():
                img = md.imageData()
                if img is not None:
                    self._on_image_pasted(img)
                    event.acceptProposedAction()
                    return
            if md.hasUrls():
                local_paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
                if local_paths:
                    self._on_files_dropped(local_paths)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def send_message(self, message=None) -> None:
        text = message if isinstance(message, str) else self.input_box.text().strip()
        attachments = list(self.pending_attachments)

        # Also support raw pasted file paths inside the text box (e.g. `/Users/user/file.png`)
        for token in local_path_candidates(text):
            if Path(token).exists() and token not in attachments and len(attachments) < 8:
                attachments.append(token)

        if not text and not attachments:
            return
        if self._worker and self._worker.isRunning():
            return
        self._manual_expression = None
        self._sync_expression_controls(None)
        self.sprite.set_speaking(False)
        self.stop_all_voice()

        self._voice_suppressed = False

        # If Frieren was sleeping, she wakes up immediately to help
        if getattr(self, "needs", None) and self.needs.is_sleeping:
            self.needs.wake_up()
            self.bubble.update_needs_data(self.needs.data)

        self.chat_panel.begin_message(text)
        self._streamed = False
        self._explanation_voiced = False
        self.input_box.clear()
        self.clear_attachments()
        self._set_request_busy(True)
        self.bubble.agent_btn.setEnabled(False)
        self.bubble.output_available_btn.hide()
        self.bubble.set_cli_output("Permintaan baru · log akan diisi oleh proses saat ini.")
        self.chat_panel.output.clear()
        self.bubble_hide_timer.stop()
        self.state_timer.stop()

        # Determine initial activity status & sprite pose:
        # Normal questions/greetings ONLY use soft thinking poses (`thinking`, `thinking_lookup`, `thinking_tilt`, `thinking_hmmm`).
        # `action_laptop` and `action_magic` are strictly reserved for explicit web/search or CLI/file/attachment execution!
        low = text.lower()
        has_image_att = any(self.backend._is_image_path(a) for a in attachments)
        has_file_att = bool(attachments) and not has_image_att
        is_web_request = bool(
            re.search(r"\b(https?://|www\.|buka\s+web|bukakan|cari\s+di\s+web|search|browsing|situs|website)\b", low)
        )
        is_agent_cli_request = bool(
            re.search(r"\b(cek\s+file|cek\s+folder|baca\s+file|git\s+|jalankan|eksekusi|terminal|script|coding|buatkan\s+file)\b", low)
        )

        if has_image_att:
            init_status = "Sedang mengamati gambar yang kamu kirimkan... 🖼️✦"
            init_pose = "thinking_tilt"
        elif has_file_att:
            init_status = "Sedang membuka grimoire untuk memeriksa filemu... 📄✦"
            init_pose = "action_magic"
        elif is_web_request:
            init_status = "Sedang membuka laptop & menelusuri web untukmu... 💻"
            init_pose = "action_laptop"
        elif is_agent_cli_request:
            init_status = "Sedang membuka buku grimoire & tongkat sihir... ✦"
            init_pose = "action_magic"
        else:
            init_status = random.choice(CUTE_THINKING_LINES) if self.profile.id == "frieren" else f"{self.profile.name} sedang memikirkan permintaanmu…"
            init_pose = random.choice(THINKING_POSES)

        self.sprite.set_state(init_pose)
        self.show_bubble()
        self.bubble.show_loading(init_status)
        self.bubble.update_state_badge(init_pose)

        self._worker = CodexWorker(self.backend, text, attachments=attachments, parent=self)
        self._worker.status_update.connect(self._on_worker_status_update)
        self._worker.text_update.connect(self._on_stream_text)
        self._worker.finished_result.connect(self._on_codex_result)
        self._worker.finished.connect(self._on_request_finished)
        self._request_started = time.monotonic()
        self._request_stage = "Menghubungkan AI…"
        self.request_clock.start()
        self._update_ai_context("Memproses")
        self._worker.start()
        self._play_voice_event("thinking")

    def _on_worker_status_update(self, status_text: str) -> None:
        if self._closing:
            return
        self.bubble.update_loading_status(status_text)
        self._request_stage = status_text
        self.sprite.set_speaking(False)
        self._update_ai_context(status_text)
        s_low = status_text.lower()
        if any(k in s_low for k in ("membuka web", "membaca halaman", "mengintip halaman web", "mengambil data dari web", "menelusuri web")):
            self.sprite.set_state("action_laptop")
            self.bubble.update_state_badge("action_laptop")
        elif any(k in s_low for k in ("melihat isi folder", "membaca isi file", "memeriksa repositori", "menjalankan proses", "mencari file", "memproses:", "menjalankan perintah", "memperbarui file")):
            self.sprite.set_state("action_magic")
            self.bubble.update_state_badge("action_magic")
        else:
            # Normal reasoning/thinking step -> rotate among soft thinking poses only
            if (
                not self.sprite.current_state.startswith("action_")
                and time.monotonic() - self.sprite.state_started_at >= 6.0
            ):
                pose = random.choice(THINKING_POSES)
                self.sprite.set_state(pose)
                self.bubble.update_state_badge(pose)

    @staticmethod
    def _infer_emotion_from_text(speech: str) -> str:
        low = speech.lower()
        if any(w in low for w in ("ulang tahun", "terima kasih", "makasih", "sayang", "bangga", "🤍", "senang bisa")):
            return "tersentuh"
        if any(w in low for w in ("hehe", "♪", "asyik", "hore", "selamat")):
            return "ceria"
        if any(w in low for w in ("himmel", "dulu", "ribuan tahun", "kenangan", "masa lalu")):
            return "nostalgia"
        if any(w in low for w in ("teh", "hangat", "syal", "istirahat", "nyaman", "santai")):
            return "hangat"
        if any(w in low for w in ("kantuk", "tidur", "malas", "lelah")):
            return "mengantuk"
        if any(w in low for w in ("sudah kubukakan", "berhasil", "selesai", "siap", "ayo")):
            return "antusias"
        if any(w in low for w in ("menarik", "kira-kira", "coba kita", "penasaran")):
            return "penasaran"
        return "senang"

    def _on_codex_result(self, result: CodexResult) -> None:
        if self._closing:
            return
        self.request_clock.stop()
        self.bubble.spinner.stop()
        self.bubble.loading_row.hide()
        self.bubble.agent_btn.setEnabled(True)
        if self.input_container.isVisible():
            self.input_box.setFocus()

        # Update console output in background; ONLY visible if user toggled 💻 open
        self.bubble.set_cli_output(result.cli_output)
        self.bubble.output_available_btn.setVisible(bool(result.technical_output))
        self.chat_panel.output.setPlainText(result.cli_output[-48000:])
        self.chat_panel.set_history(self.backend.load_memory())
        labels = {"completed": "Selesai", "failed": "Gagal", "timeout": "Batas waktu tercapai", "cancelled": "Dibatalkan"}
        self._update_ai_context(labels.get(result.status, result.status))

        emotion = result.emotion or self._infer_emotion_from_text(result.speech)
        talk_pose = random.choice(("talking", "talking_explain"))
        if self._sync_voice_enabled() and result.narration_ja and result.status == "completed":
            self._start_synced_narration(result.speech, result.narration_ja, emotion, talk_pose, result)
            return
        self._refresh_bubble_history()
        self.set_character_state(
            talk_pose,
            result.speech,
            animate_typing=not self._streamed and result.status == "completed",
            emotion_override=emotion,
        )
        if self.config.get("ui",{}).get("voice_mode","narration") == "narration":
            if self._voice_suppressed:
                return
            if result.narration_ja:
                self._start_narration(result.narration_ja,result.emotion)
            else:
                self.stop_all_voice()
                if self.config.get("ui",{}).get("voice_enabled",True):
                    self._on_narration_failed(self._tts_token, "Terjemahan dubbing Jepang belum tersedia untuk jawaban ini.")
        else:
            self._play_voice_event({"completed":"success", "cancelled":"cancelled"}.get(result.status,"error"))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if hasattr(self,"surface") and not self.is_minimized:
            self.surface.paint(painter,self.rect())
        painter.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self,"resize_grip"):
            self.resize_grip.move(self.width()-26,self.height()-26)
            self.resize_grip.raise_()
        if hasattr(self,"bubble"):
            self.bubble.setMaximumWidth(max(280,self.width()-20))
            self.bubble._refresh_header_fit()
        if hasattr(self,"_window_resize_timer"):
            self._window_resize_timer.start(350)

    def _resize_edges(self, pos):
        edges = Qt.Edge(0)
        if self.is_minimized:
            return edges
        if pos.x() < 10:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width()-10:
            edges |= Qt.Edge.RightEdge
        if pos.y() < 10:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height()-10:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._resize_edges(event.position().toPoint())
            if edges and self.windowHandle() and self.windowHandle().startSystemResize(edges):
                self._drag_offset = None
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_pos = event.globalPosition().toPoint()
        elif event.button() == Qt.MouseButton.RightButton:
            if hasattr(self, "tray") and self.tray.contextMenu():
                self.tray.contextMenu().popup(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        edges = self._resize_edges(event.position().toPoint())
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            diagonal = edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if diagonal else Qt.CursorShape.SizeBDiagCursor)
        elif horizontal or vertical:
            self.setCursor(Qt.CursorShape.SizeHorCursor if horizontal else Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            dist = (event.globalPosition().toPoint() - self._press_pos).manhattanLength()
            self._drag_offset = None
            if dist < 6 and self.sprite.geometry().contains(event.position().toPoint()):
                self._pet_frieren()

    def wheelEvent(self, event) -> None:
        """Hold Cmd + Scroll to resize, or Option (Alt) + Scroll to adjust Opacity."""
        mods = event.modifiers()
        delta = event.angleDelta().y()
        if mods & Qt.KeyboardModifier.ControlModifier:  # Command key on macOS Qt
            if delta > 0:
                self.apply_scale(self.scale_factor + 0.06)
            elif delta < 0:
                self.apply_scale(self.scale_factor - 0.06)
            event.accept()
            return
        if mods & Qt.KeyboardModifier.AltModifier:  # Option key on macOS Qt
            if delta > 0:
                self.apply_opacity(self.opacity_level + 0.06)
            elif delta < 0:
                self.apply_opacity(self.opacity_level - 0.06)
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:  # Shift + Scroll adjusts Bubble Gap
            if delta > 0:
                self.apply_bubble_gap(self.bubble_gap + 4)
            elif delta < 0:
                self.apply_bubble_gap(self.bubble_gap - 4)
            event.accept()
            return
        super().wheelEvent(event)


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    logging.basicConfig(
        level=logging.INFO,
        handlers=[RotatingFileHandler(base_dir / "frieren_runtime.log", maxBytes=1024 * 1024, backupCount=1, encoding="utf-8")],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    def report_exception(kind, value, traceback):
        logging.error("Unhandled application error", exc_info=(kind, value, traceback))
        sys.__excepthook__(kind, value, traceback)
    sys.excepthook = report_exception
    show_panel = "--panel" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("Frieren Desk")
    app.setQuitOnLastWindowClosed(False)

    window = FrierenDeskWindow(base_dir)
    app.aboutToQuit.connect(window._cleanup_workers)
    app.aboutToQuit.connect(clone_service.stop)
    prefs = window.config.get("ui", {})
    if prefs.get("voice_enabled", True) and prefs.get("tts_engine", "qwen-local") == "qwen-local":
        clone_service.start(base_dir)
    window.show()
    logging.info("Application started (panel=%s)", show_panel)
    if show_panel:
        window.open_chat_panel()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
