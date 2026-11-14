"""Resizable work panel; the small desktop companion remains available."""

from pathlib import Path
import re

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QHBoxLayout,
                              QLabel, QPlainTextEdit, QPushButton, QSplitter,
                              QTextBrowser, QVBoxLayout, QWidget, QScrollArea, QSpinBox)

from chat_widgets import AttachmentList, ChatInputBox
from character_profiles import PROFILES, EXPRESSION_LABELS
from character_theme import theme_styles
from scene_theme import SceneSurface
from PySide6.QtGui import QPainter


class ChatPanel(QDialog):
    stopVoiceRequested = Signal()
    timeoutSelected = Signal(int)
    voiceRequested = Signal()
    characterSelected = Signal(str)
    expressionSelected = Signal(object)
    panelResized = Signal(int, int)
    sendRequested = Signal(str)
    cancelRequested = Signal()
    refreshRequested = Signal()
    modelSelected = Signal(str, str)
    chooseProjectRequested = Signal()
    projectSelected = Signal(object)
    revealProjectRequested = Signal()
    attachRequested = Signal()
    removeAttachmentRequested = Signal(str)
    imagePasted = Signal(object)
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Frieren · Chat & Proyek")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.setMinimumSize(420, 420)
        self.setSizeGripEnabled(True)
        self.resize(800, 720)
        self._history = []
        self._partial = ""
        self._pending_user = ""
        self._last_answer = ""
        self.character_name = "Frieren"
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(lambda: self.panelResized.emit(self.width(), self.height()))
        root = QVBoxLayout(self)
        root.setSpacing(10)

        character_row = QHBoxLayout()
        character_row.addWidget(QLabel("Karakter"))
        self.character_combo = QComboBox()
        self.character_combo.setMinimumContentsLength(10)
        self.character_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.character_combo.activated.connect(lambda i: self.characterSelected.emit(self.character_combo.itemData(i)))
        character_row.addWidget(self.character_combo, 1)
        character_row.addWidget(QLabel("Ekspresi"))
        self.expression_combo = QComboBox()
        self.expression_combo.addItem("Otomatis", None)
        for key, label in EXPRESSION_LABELS.items():
            self.expression_combo.addItem(label, key)
        self.expression_combo.activated.connect(lambda i: self.expressionSelected.emit(self.expression_combo.itemData(i)))
        character_row.addWidget(self.expression_combo, 1)
        root.addLayout(character_row)

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Model AI"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.setToolTip("Model yang tersedia dari akun/CLI yang terhubung")
        self.model_combo.activated.connect(self._model_changed)
        provider_row.addWidget(self.model_combo, 1)
        self.refresh_btn = QPushButton("Refresh Model")
        self.refresh_btn.clicked.connect(self.refreshRequested.emit)
        provider_row.addWidget(self.refresh_btn)
        root.addLayout(provider_row)
        self.connections = QLabel("Memeriksa koneksi CLI…")
        self.connections.setWordWrap(True)
        self.connections.setTextFormat(Qt.TextFormat.PlainText)
        self.connections.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        connection_row = QHBoxLayout()
        connection_row.addWidget(self.connections,1)
        timeout_column = QVBoxLayout()
        timeout_column.addWidget(QLabel("Batas waktu (detik)"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30,1800)
        self.timeout_spin.setSingleStep(30)
        self.timeout_spin.setValue(300)
        self.timeout_spin.setToolTip("Batas keseluruhan permintaan AI. Tugas panjang dapat memerlukan lebih dari 90 detik.")
        self.timeout_spin.valueChanged.connect(self.timeoutSelected.emit)
        timeout_column.addWidget(self.timeout_spin)
        connection_row.addLayout(timeout_column)
        root.addLayout(connection_row)

        project_row = QHBoxLayout()
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Riwayat dan memori dipisahkan per folder proyek")
        self.project_combo.activated.connect(lambda index: self.projectSelected.emit(self.project_combo.itemData(index)))
        self.project_btn = QPushButton("Pilih Folder Proyek")
        self.project_btn.clicked.connect(self.chooseProjectRequested.emit)
        self.reveal_btn = QPushButton("Buka Folder")
        self.reveal_btn.clicked.connect(self.revealProjectRequested.emit)
        project_row.addWidget(self.project_combo, 1)
        project_row.addWidget(self.project_btn)
        project_row.addWidget(self.reveal_btn)
        root.addLayout(project_row)
        self.project_path = QLabel()
        self.project_path.setWordWrap(True)
        self.project_path.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.project_path)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        splitter.addWidget(self.transcript)
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_header = QHBoxLayout()
        output_header.addWidget(QLabel("Output teknis / log"))
        copy_output = QPushButton("Salin Output")
        copy_output.clicked.connect(lambda: QApplication.clipboard().setText(self.output.toPlainText()))
        output_header.addStretch()
        output_header.addWidget(copy_output)
        output_layout.addLayout(output_header)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(1500)
        output_layout.addWidget(self.output)
        splitter.addWidget(output_widget)
        splitter.setSizes([380, 120])
        root.addWidget(splitter, 1)

        self.attachments = AttachmentList()
        self.attachments.removeRequested.connect(self.removeAttachmentRequested.emit)
        self.attach_scroll = QScrollArea()
        self.attach_scroll.setWidgetResizable(True)
        self.attach_scroll.setMaximumHeight(125)
        self.attach_scroll.setWidget(self.attachments)
        self.attach_scroll.hide()
        root.addWidget(self.attach_scroll)
        self.input = ChatInputBox()
        self.input.setMaximumHeight(150)
        self.input.setPlaceholderText("Tulis instruksi… Enter kirim, Shift+Enter baris baru")
        self.input.returnPressed.connect(self._send)
        self.input.imagePasted.connect(self.imagePasted.emit)
        self.input.filesDropped.connect(self.filesDropped.emit)
        root.addWidget(self.input)

        actions = QHBoxLayout()
        self.attach_btn = QPushButton("Lampirkan")
        self.attach_btn.clicked.connect(self.attachRequested.emit)
        copy_answer = QPushButton("Salin Jawaban")
        copy_answer.clicked.connect(lambda: QApplication.clipboard().setText(self._last_answer))
        self.voice_btn = QPushButton("Voice…")
        self.voice_btn.setToolTip("Dengarkan sample dan pilih rentang audio sesuai konteks")
        self.voice_btn.clicked.connect(self.voiceRequested.emit)
        self.stop_voice_btn = QPushButton("Stop Suara")
        self.stop_voice_btn.clicked.connect(self.stopVoiceRequested.emit)
        self.stop_voice_btn.hide()
        self.cancel_btn = QPushButton("Batalkan")
        self.cancel_btn.clicked.connect(self.cancelRequested.emit)
        self.cancel_btn.hide()
        self.send_btn = QPushButton("Kirim")
        self.send_btn.clicked.connect(self._send)
        actions.addWidget(self.attach_btn)
        actions.addWidget(copy_answer)
        actions.addWidget(self.voice_btn)
        actions.addWidget(self.stop_voice_btn)
        actions.addStretch()
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.send_btn)
        root.addLayout(actions)
        self.status = QLabel("Siap")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.setStyleSheet("""
            QDialog { background: #191b26; color: #f5f7fa; }
            QLabel { color: #e1e5ef; }
            QTextBrowser, QPlainTextEdit, QComboBox {
                background: #11141e; color: #f5f7fa; border: 1px solid #454a60;
                border-radius: 6px; padding: 7px; font-size: 13px;
            }
            QPushButton { background: #632e40; color: #fff; border: 1px solid #985067;
                          border-radius: 6px; padding: 7px 10px; min-height: 18px; }
            QPushButton:hover { background: #8b3e55; }
            QPushButton:disabled { color: #858592; background: #292b37; }
            QComboBox QAbstractItemView { background: #191b26; color: #fff; selection-background-color: #632e40; }
            QSplitter::handle { background: #36394b; height: 5px; }
        """)

    def _send(self):
        if not self.send_btn.isEnabled():
            return
        self.sendRequested.emit(self.input.text().strip())

    def _model_changed(self, index):
        value = self.model_combo.itemData(index)
        if value:
            self.modelSelected.emit(value[0], value[1])

    def update_context(self, backend):
        self.timeout_spin.blockSignals(True)
        self.timeout_spin.setValue(backend.agy_timeout_seconds if backend.active_engine == "antigravity" else backend.timeout_seconds)
        self.timeout_spin.blockSignals(False)
        self.character_name = backend.character.name
        self.setWindowTitle(f"{self.character_name} · Chat & Proyek")
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        for identifier, profile in PROFILES.items():
            if profile.available(backend.base_dir):
                self.character_combo.addItem(profile.name, identifier)
        self.character_combo.setCurrentIndex(self.character_combo.findData(backend.character.id))
        self.character_combo.blockSignals(False)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        selected = -1
        for engine, label in (("codex", "Codex"), ("antigravity", "AGY")):
            state = backend.providers[engine]
            if state.connected:
                for model in state.models:
                    self.model_combo.addItem(f"{label} · {model['name']} ({model['id']})", (engine, model["id"]))
                    if engine == backend.active_engine and model["id"] == backend.active_model:
                        selected = self.model_combo.count() - 1
        if selected < 0:
            self.model_combo.insertItem(0, f"{backend.active_engine} · {backend.active_model} — belum terverifikasi", None)
            selected = 0
        self.model_combo.setCurrentIndex(selected)
        self.model_combo.blockSignals(False)
        self.connections.setText("\n".join(f"{'Codex' if k == 'codex' else 'AGY'}: {v.message}" for k, v in backend.providers.items()))
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("Percakapan umum", None)
        for value in backend.config.get("project", {}).get("recent", []):
            self.project_combo.addItem(Path(value).name, value)
        current = self.project_combo.findData(str(backend.project_dir)) if backend.project_dir else 0
        if current < 0 and backend.project_dir:
            self.project_combo.addItem(backend.project_dir.name, str(backend.project_dir))
            current = self.project_combo.count() - 1
        self.project_combo.setCurrentIndex(current)
        self.project_combo.blockSignals(False)
        self.project_path.setText(backend.project_warning or str(backend.working_directory))

    def apply_theme(self, profile):
        self.setStyleSheet(theme_styles(profile))
        self.surface = SceneSurface(profile)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if hasattr(self,"surface"):
            painter = QPainter(self)
            self.surface.paint(painter,self.rect())
            painter.end()

    def set_busy(self, busy):
        for widget in (self.input, self.send_btn, self.attach_btn, self.model_combo,
                       self.project_combo, self.project_btn, self.character_combo, self.expression_combo, self.voice_btn, self.timeout_spin):
            widget.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)

    def set_attachment_paths(self, paths):
        self.attachments.set_paths(paths)
        self.attach_scroll.setVisible(bool(paths))

    def set_history(self, items):
        self._history = items[-40:]
        self._partial = self._pending_user = ""
        last = next((m for m in reversed(items) if m.get("role") == "assistant"), {})
        self._last_answer = last.get("text", "")
        if last.get("technical_output"):
            self._last_answer += "\n\n" + last["technical_output"]
        self._render_history()

    def begin_message(self, text):
        self._partial = ""
        self._pending_user = text or "[Lampiran]"
        self.input.clear()
        self._render_history()

    def set_partial(self, text):
        self._partial = text
        self._render_history()

    def _render_history(self):
        scroll = self.transcript.verticalScrollBar()
        follow = scroll.value() >= scroll.maximum() - 30
        position = scroll.value()
        parts = []
        remaining = 80000
        for item in reversed(self._history):
            who = "Kamu" if item.get("role") == "user" else item.get("speaker", "Frieren")
            text = item.get("text", "")
            if item.get("technical_output"):
                technical = item["technical_output"]
                if len(technical) > 6000:
                    technical = "[… ringkasan tampilan: 6.000 karakter terakhir …]\n" + technical[-6000:]
                text += "\n\n```text\n" + technical + "\n```"
            text = text[-remaining:]
            remaining -= len(text)
            parts.append(f"### {who}\n\n{text}")
            if remaining <= 0:
                break
        parts.reverse()
        if self._pending_user:
            parts.append("### Kamu\n\n" + self._pending_user)
        if self._partial:
            # Hide control tags while streaming; they are not user-facing text.
            partial = re.sub(r"\[(?:MEMORY_SAVE|EMOTION):[^\]]*(?:\]|$)", "", self._partial, flags=re.I)
            parts.append(f"### {self.character_name} · sedang menjawab\n\n" + partial)
        self.transcript.setMarkdown("\n\n---\n\n".join(parts) or "Belum ada percakapan. Pilih proyek dan model, lalu tulis pesan.")
        scroll.setValue(scroll.maximum() if follow else position)

    def closeEvent(self, event):
        # Closing this panel hides it; the companion and active request continue.
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_resize_timer"):
            self._resize_timer.start(350)
