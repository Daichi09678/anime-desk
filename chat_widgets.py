"""Reusable multiline composer and small, individually removable attachments."""

from pathlib import Path
import re

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


def local_path_candidates(text):
    """Only inspect explicit absolute paths, never URL fragments/UNC hosts."""
    candidates = [a or b for a, b in re.findall(r'"([^"\n]+)"|\'([^\'\n]+)\'', text)]
    stripped = text.strip()
    if len(stripped) < 4096:
        candidates.append(stripped)
    return [value for value in candidates
            if not value.startswith(("//", "\\\\"))
            and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("/"))]


class ChatInputBox(QPlainTextEdit):
    imagePasted = Signal(object)
    filesDropped = Signal(list)
    returnPressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(58)
        self.setMaximumHeight(110)
        self.document().setMaximumBlockCount(200)
        self.setToolTip("Enter untuk mengirim · Shift+Enter untuk baris baru · paste gambar/file didukung")

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self.setPlainText(text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def canInsertFromMimeData(self, source):
        return source.hasImage() or source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.imagePasted.emit(source.imageData())
            return
        if source.hasUrls():
            paths = [url.toLocalFile() for url in source.urls() if url.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
                return
        super().insertFromMimeData(source)


class AttachmentList(QFrame):
    removeRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("attachmentBar")
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(6, 3, 6, 3)
        self.rows.setSpacing(3)
        self.hide()

    def set_paths(self, paths, max_rows=None):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        visible_paths = paths[:max_rows] if max_rows else paths
        for value in visible_paths:
            path = Path(value)
            frame = QFrame(self)
            row = QHBoxLayout(frame)
            row.setContentsMargins(0, 0, 0, 0)
            icon = QLabel("📁" if path.is_dir() else "📄")
            icon.setFixedSize(30, 30)
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
                reader = QImageReader(str(path))
                size = reader.size()
                if size.isValid() and size.width() * size.height() <= 16000000:
                    reader.setScaledSize(size.scaled(QSize(30, 30), Qt.AspectRatioMode.KeepAspectRatio))
                    icon.setPixmap(QPixmap.fromImage(reader.read()))
            name = QLabel(path.name)
            name.setStyleSheet("color: #D8E6FF; font-size: 11px;")
            name.setMinimumWidth(0)
            name.setToolTip(str(path))
            name.setText(name.fontMetrics().elidedText(path.name, Qt.TextElideMode.ElideMiddle, 180))
            remove = QPushButton("Hapus")
            remove.setObjectName("secondaryButton")
            remove.setFixedWidth(55)
            remove.setToolTip(f"Hapus lampiran {path.name}")
            remove.clicked.connect(lambda checked=False, p=value: self.removeRequested.emit(p))
            row.addWidget(icon)
            row.addWidget(name, 1)
            row.addWidget(remove)
            self.rows.addWidget(frame)
        if len(visible_paths) < len(paths):
            self.rows.addWidget(QLabel(f"+{len(paths) - len(visible_paths)} lampiran lainnya di Chat ↗"))
        self.setVisible(bool(paths))
