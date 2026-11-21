"""Lazy sample playback with explicit event/range assignments; no voice cloning."""

from dataclasses import dataclass
import ctypes
import json
from pathlib import Path
import re
import sys

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                              QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from character_theme import theme_styles


EVENTS = {"greeting":"Sapaan", "thinking":"Berpikir", "explaining":"Menjelaskan",
          "success":"Berhasil", "error":"Gagal / timeout", "cancelled":"Dibatalkan"}
FORMATS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


class _WindowsAudio:
    """MCI playback avoids Qt/FFmpeg hardware-device probing on Windows."""

    def __init__(self):
        self.dll = ctypes.WinDLL("winmm")
        self.dll.mciSendStringW.argtypes = [ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint,ctypes.c_void_p]
        self.dll.mciGetErrorStringW.argtypes = [ctypes.c_uint,ctypes.c_wchar_p,ctypes.c_uint]
        self.alias = f"frieren_voice_{id(self):x}"
        self.opened = False
        self.muted = False
        self.volume = 650

    def command(self, text):
        result = ctypes.create_unicode_buffer(512)
        error = self.dll.mciSendStringW(text,result,len(result),None)
        if error:
            message = ctypes.create_unicode_buffer(512)
            self.dll.mciGetErrorStringW(error,message,len(message))
            raise RuntimeError(message.value or f"Windows audio error {error}")
        return result.value

    def setVolume(self, volume):
        self.volume = round(max(0,min(1,volume))*1000)

    def setMuted(self, muted):
        self.muted = bool(muted)

    def play_clip(self, clip):
        self.close()
        self.command(f'open "{clip.file.resolve()}" type mpegvideo alias {self.alias}')
        self.opened = True
        self.command(f"set {self.alias} time format milliseconds")
        duration = int(self.command(f"status {self.alias} length"))
        if clip.start_ms >= duration:
            raise ValueError("Waktu mulai melewati durasi file.")
        self.command(f"setaudio {self.alias} volume to {0 if self.muted else self.volume}")
        self.command(f"play {self.alias} from {clip.start_ms} to {min(clip.end_ms,duration)}")
        return duration

    def playing(self):
        return self.opened and self.command(f"status {self.alias} mode").lower() == "playing"

    def close(self):
        if self.opened:
            try:
                self.command(f"stop {self.alias}")
                self.command(f"close {self.alias}")
            finally:
                self.opened = False


@dataclass(frozen=True)
class VoiceClip:
    file: Path
    start_ms: int = 0
    end_ms: int = 8000


class VoiceBank:
    def __init__(self, base_dir, character):
        self.folder = Path(base_dir) / "assets/voices" / character

    def files(self):
        return sorted((p for p in self.folder.glob("*") if p.is_file() and p.suffix.lower() in FORMATS), key=lambda p:p.name.casefold())

    def assignments(self):
        try:
            data = json.loads((self.folder / "manifest.json").read_text(encoding="utf-8"))
            events = data.get("events", {}) if isinstance(data, dict) else {}
            return events if isinstance(events,dict) else {}
        except (OSError, ValueError):
            return {}

    def clip_for(self, event):
        data = self.assignments().get(event)
        if isinstance(data, dict):
            filename = data.get("file", "")
            if not isinstance(filename,str):
                return None
            file = (self.folder / filename).resolve()
            try:
                start, end = int(data.get("start_ms",0)), int(data.get("end_ms",8000))
            except (ValueError, TypeError):
                return None
            if file.parent == self.folder.resolve() and file.is_file() and 0 <= start < end <= start+20000:
                return VoiceClip(file, start, end)
        for file in self.files():
            if re.fullmatch(re.escape(event)+r"(?:_\d+)?", file.stem, re.I):
                return VoiceClip(file)
        return None

    def assign(self, event, clip):
        if event not in EVENTS or not 0 <= clip.start_ms < clip.end_ms <= clip.start_ms+20000:
            raise ValueError("Pilih kategori dan rentang audio 0–20 detik yang valid.")
        if clip.file.resolve().parent != self.folder.resolve() or not clip.file.is_file():
            raise ValueError("File harus berada dalam folder voice karakter aktif.")
        events = self.assignments()
        events[event] = {"file":clip.file.name, "start_ms":clip.start_ms, "end_ms":clip.end_ms}
        temporary = self.folder / "manifest.json.tmp"
        temporary.write_text(json.dumps({"events":events}, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
        temporary.replace(self.folder / "manifest.json")


class VoiceController(QObject):
    speakingChanged = Signal(bool)
    statusChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = None
        self.output = None
        self.clip = None
        self._started = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.stop)
        self.poll = QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self._poll_native)

    def _init_player(self):
        if self.player is not None:
            return
        if sys.platform == "win32":
            self.player = self.output = _WindowsAudio()
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self.output = QAudioOutput(self)
        self.output.setVolume(0.65)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.player.mediaStatusChanged.connect(lambda status:QTimer.singleShot(0,lambda:self._media_status(status)))
        self.player.positionChanged.connect(self._position)
        self.player.playbackStateChanged.connect(lambda state:self.speakingChanged.emit(state == QMediaPlayer.PlaybackState.PlayingState))
        self.player.errorOccurred.connect(lambda error,text:self._error(text))

    def play(self, clip):
        if clip is None:
            return False
        self._init_player()
        self.stop()
        self.clip = clip
        self._started = False
        if isinstance(self.player,_WindowsAudio):
            try:
                duration = self.player.play_clip(clip)
                self._started = True
                self.timer.start(min(clip.end_ms,duration)-clip.start_ms+200)
                self.poll.start()
                self.speakingChanged.emit(True)
                self.statusChanged.emit(f"Memutar rentang {clip.start_ms/1000:.1f}–{clip.end_ms/1000:.1f} detik")
                return True
            except (RuntimeError,ValueError) as exc:
                self._error(str(exc))
                return False
        source = QUrl.fromLocalFile(str(clip.file.resolve()))
        same_source = self.player.source() == source
        self.timer.start(15000)
        self.player.setSource(source)
        self.statusChanged.emit("Memuat sample…")
        if same_source:
            from PySide6.QtMultimedia import QMediaPlayer
            if self.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.EndOfMedia):
                self._media_status(QMediaPlayer.MediaStatus.LoadedMedia)
        return True

    def _poll_native(self):
        try:
            if self.player is not None and not self.player.playing():
                self.stop()
        except RuntimeError as exc:
            self._error(str(exc))

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia) and self.clip and not self._started:
            if self.player.duration() and self.clip.start_ms >= self.player.duration():
                self._error("Waktu mulai melewati durasi file.")
                return
            self._started = True
            self.player.setPosition(self.clip.start_ms)
            self.player.play()
            self.timer.start(self.clip.end_ms-self.clip.start_ms+500)
            self.statusChanged.emit(f"Memutar sample · durasi sumber {self.player.duration()/1000:.1f} detik")
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop()

    def _position(self, position):
        if self.clip and self._started and position >= self.clip.end_ms:
            self.stop()

    def _error(self, text):
        self.stop()
        self.statusChanged.emit("Audio: " + text)

    def stop(self):
        self.timer.stop()
        self.poll.stop()
        self.clip = None
        self._started = False
        if self.player is not None:
            if isinstance(self.player,_WindowsAudio):
                try:
                    self.player.close()
                except RuntimeError as exc:
                    self.statusChanged.emit("Audio: "+str(exc))
            else:
                self.player.stop()
        self.speakingChanged.emit(False)


class VoiceDialog(QDialog):
    narrationPreview = Signal()
    stopRequested = Signal()

    def __init__(self, bank, controller, profile, enabled, parent=None, mode="narration", engine="auto"):
        super().__init__(parent)
        self.bank, self.controller = bank, controller
        self.setWindowTitle(f"Voice · {profile.name}")
        self.resize(570,360)
        self.finished.connect(controller.stop)
        self.setStyleSheet(theme_styles(profile))
        root = QVBoxLayout(self)
        self.enabled = QCheckBox("Aktifkan suara karakter")
        self.enabled.setChecked(enabled)
        root.addWidget(self.enabled)
        help_text = QLabel("Narasi membaca terjemahan Jepang dari subtitle Indonesia. Cepat & Ringan memutar sapaan karakter yang sudah disiapkan; teks lainnya dikirim ke Edge untuk suara sintetis online. Cloning Qwen untuk teks baru berjalan di CPU dan bisa memerlukan puluhan detik. Untuk referensi cloning, pilih audio 3–15 detik berisi satu pembicara tanpa musik.")
        help_text.setWordWrap(True)
        root.addWidget(help_text)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("Narasi dari jawaban AI","narration")
        self.mode.addItem("Klip rekaman sesuai konteks","clips")
        self.mode.setCurrentIndex(max(0,self.mode.findData(mode)))
        form.addRow("Mode suara",self.mode)
        self.engine = QComboBox()
        self.engine.addItem("Cloning lokal · Qwen3, sample karakter (CPU)","qwen-local")
        self.engine.addItem("Cepat & Ringan · sapaan siap putar + Edge online","fast")
        self.engine.addItem("Otomatis · Jepang online, fallback Windows Jepang","auto")
        self.engine.addItem("Jepang online · suara sintetis","edge")
        if sys.platform == "win32":
            self.engine.addItem("Windows offline · suara bawaan","windows")
        self.engine.setCurrentIndex(max(0,self.engine.findData(engine)))
        form.addRow("Mesin narasi",self.engine)
        self.files = QComboBox()
        self.files.setMinimumContentsLength(20)
        self.files.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for file in bank.files():
            self.files.addItem(file.name,str(file))
        form.addRow("File",self.files)
        self.start = QDoubleSpinBox()
        self.start.setRange(0,100000)
        self.start.setSuffix(" detik")
        self.length = QDoubleSpinBox()
        self.length.setRange(0.5,20)
        self.length.setValue(6)
        self.length.setSuffix(" detik")
        form.addRow("Mulai",self.start)
        form.addRow("Durasi klip",self.length)
        self.events = QComboBox()
        for key,label in EVENTS.items():
            self.events.addItem(label,key)
        form.addRow("Konteks",self.events)
        root.addLayout(form)
        clone_reference = QPushButton("Gunakan rentang ini sebagai referensi cloning")
        clone_reference.clicked.connect(self.save_clone_reference)
        root.addWidget(clone_reference)
        self.status = QLabel(f"{len(bank.files())} file · {len(bank.assignments())} konteks ditentukan")
        self.status.setWordWrap(True)
        controller.statusChanged.connect(self.status.setText)
        root.addWidget(self.status)
        buttons = QHBoxLayout()
        preview = QPushButton("Dengarkan Rentang")
        preview.clicked.connect(self.preview)
        stop = QPushButton("Stop")
        stop.clicked.connect(controller.stop)
        stop.clicked.connect(self.stopRequested.emit)
        narrate = QPushButton("Coba Narasi")
        narrate.clicked.connect(self.narrationPreview.emit)
        save = QPushButton("Simpan Konteks")
        save.clicked.connect(self.save)
        done = QPushButton("Selesai")
        done.clicked.connect(self.accept)
        for button in (preview,narrate,stop,save,done):
            buttons.addWidget(button)
        root.addLayout(buttons)

    def selected_clip(self):
        file = self.files.currentData()
        if not file:
            raise ValueError("Belum ada file audio untuk karakter ini.")
        start = round(self.start.value()*1000)
        return VoiceClip(Path(file), start, start+round(self.length.value()*1000))

    def save_clone_reference(self):
        try:
            clip = self.selected_clip()
            duration = (clip.end_ms-clip.start_ms)/1000
            if not 3 <= duration <= 15:
                raise ValueError("Referensi cloning harus 3–15 detik.")
            data = {"file":clip.file.name, "start_seconds":clip.start_ms/1000,
                    "duration_seconds":duration, "review_status":"selected by user",
                    "method":"speaker embedding only; no transcript or fine-tuning"}
            target = clip.file.parent / "clone.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            temporary.replace(target)
            self.status.setText("Referensi cloning tersimpan. Narasi berikutnya memakai rentang ini.")
        except (ValueError,OSError) as exc:
            self.status.setText(str(exc))

    def preview(self):
        try:
            self.controller.play(self.selected_clip())
        except ValueError as exc:
            self.status.setText(str(exc))

    def save(self):
        try:
            self.bank.assign(self.events.currentData(),self.selected_clip())
            self.status.setText("Konteks disimpan. File sumber tetap utuh.")
        except (ValueError,OSError) as exc:
            self.status.setText(str(exc))

    def done(self, result):
        self.controller.stop()
        super().done(result)
