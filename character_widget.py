"""Small, bounded sprite cache and calm, time-based motion for Frieren."""

from __future__ import annotations

from collections import OrderedDict
import math
from pathlib import Path
import random
import time
from typing import Dict, Optional

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QBitmap, QImageReader, QPainter, QPixmap, QRegion, QTransform
from PySide6.QtWidgets import QWidget


class FrierenSpriteWidget(QWidget):
    """Animate existing artwork without retaining full-resolution textures."""

    CACHE_LIMIT = 6
    MOTION_MODES = ("natural", "reduced", "off")

    def __init__(
        self, sprites: Dict[str, Path], fade_ms: int = 320,
        parent: Optional[QWidget] = None, motion_mode: str = "natural",
    ) -> None:
        super().__init__(parent)
        self._base_normal_size = (235, 245)
        self._base_mini_size = (88, 92)
        self._scale_factor = 1.0
        self.is_minimized = False
        self.setFixedSize(*self._base_normal_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paths = dict(sprites)
        self._blink_keys = {}
        self._mouth_keys = {}
        self._speaking = False
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.8, 5.8)
        self.pixmaps: OrderedDict[str, QPixmap] = OrderedDict()
        self.alpha_masks: Dict[str, QRegion] = {}
        self.current_state = self.previous_state = "idle"
        self.state_started_at = time.monotonic()
        self._fade_progress = 1.0
        self._transition_source: Optional[QPixmap] = None
        self._transition_region = QRegion()
        self._motion_time = random.uniform(0.0, 6.0)
        self._last_tick = time.monotonic()
        self.motion_mode = motion_mode if motion_mode in self.MOTION_MODES else "natural"
        self._load_pose("idle")

        self.fade_anim = QPropertyAnimation(self, b"fadeProgress", self)
        self.fade_anim.setDuration(max(280, fade_ms))
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.fade_anim.finished.connect(self._release_transition)
        self.motion_timer = QTimer(self)
        self.motion_timer.timeout.connect(self._on_motion_tick)

    def _load_pose(self, state: str) -> QPixmap:
        if state in self.pixmaps:
            self.pixmaps.move_to_end(state)
            return self.pixmaps[state]
        # Decode to display size; do not retain a second set of original PNGs.
        reader = QImageReader(str(self._paths[state]))
        target_size = QSize(max(1, self.width() - 8), max(1, self.height() - 8))
        image = reader.read()
        # Align visible artwork, not differently padded source canvases. Matching
        # mouth/blink alpha gives exactly the same crop and body anchor.
        bounds = QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
        if not bounds.isEmpty():
            image = image.copy(bounds)
        pix = QPixmap.fromImage(image).scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.SmoothTransformation)
        self.pixmaps[state] = pix
        px, py = (self.width() - pix.width()) // 2, self.height() - 4 - pix.height()
        mask = pix.mask()
        self.alpha_masks[state] = QRegion(mask).translated(px, py) if not mask.isNull() else QRegion()
        while len(self.pixmaps) > self.CACHE_LIMIT:
            oldest, _ = self.pixmaps.popitem(last=False)
            self.alpha_masks.pop(oldest, None)
        return pix

    def _apply_geometry_and_rebuild(self) -> None:
        self.fade_anim.stop()
        self._fade_progress = 1.0
        self._transition_source = None
        self._transition_region = QRegion()
        base = self._base_mini_size if self.is_minimized else self._base_normal_size
        self.setFixedSize(max(64, int(base[0] * self._scale_factor)), max(68, int(base[1] * self._scale_factor)))
        self.pixmaps.clear()
        self.alpha_masks.clear()
        self._load_pose(self.current_state)
        self._sync_motion_timer()
        self.update()

    def set_scale_factor(self, scale: float) -> None:
        self._scale_factor = max(0.65, min(1.55, float(scale)))
        self._apply_geometry_and_rebuild()

    def set_minimized_mode(self, minimized: bool) -> None:
        if self.is_minimized != minimized:
            self.is_minimized = minimized
            self._apply_geometry_and_rebuild()

    def set_motion_mode(self, mode: str) -> None:
        if mode not in self.MOTION_MODES:
            return
        self.motion_mode = mode
        if mode == "off":
            self.fade_anim.stop()
            self._fade_progress = 1.0
            self._release_transition()
        self._sync_motion_timer()
        self.update()

    def set_sprites(self, sprites, blink_sprites=None, mouth_sprites=None) -> None:
        """Release the previous character's textures before loading the next."""
        self.fade_anim.stop()
        self._transition_source = None
        self._transition_region = QRegion()
        self._fade_progress = 1.0
        self._paths = dict(sprites)
        self._blink_keys = {}
        self._mouth_keys = {}
        for state, path in (blink_sprites or {}).items():
            if path.is_file():
                key = "__blink_" + state
                self._paths[key] = path
                self._blink_keys[state] = key
        for state,path in (mouth_sprites or {}).items():
            if path.is_file():
                key = "__mouth_"+state
                self._paths[key] = path
                self._mouth_keys[state] = key
                blink_path = path.with_name(path.stem+"_blink.png")
                if blink_path.is_file():
                    blink_key = "__blink_mouth_"+state
                    self._paths[blink_key] = blink_path
                    self._blink_keys[key] = blink_key
        self.current_state = self.previous_state = "idle"
        self.state_started_at = time.monotonic()
        self._speaking = False
        self._blink_until = 0.0
        self._next_blink = time.monotonic() + random.uniform(2.8, 5.8)
        self.pixmaps.clear()
        self.alpha_masks.clear()
        self._apply_geometry_and_rebuild()

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = bool(speaking)
        self.update()

    def react_to_click(self) -> None:
        # Click feedback is a pose change handled by the window, not a wobble.
        self.update()

    def _sync_motion_timer(self) -> None:
        self._last_tick = time.monotonic()
        if self.isVisible() and not self.is_minimized and self.motion_mode != "off":
            self.motion_timer.start(40 if self.motion_mode == "natural" else 100)
        else:
            self.motion_timer.stop()

    def _on_motion_tick(self) -> None:
        now = time.monotonic()
        self._motion_time += min(0.2, now - self._last_tick)
        self._last_tick = now
        if now >= self._next_blink:
            self._blink_until = now + (0.16 if self.motion_mode == "natural" else 0.22)
            self._next_blink = now + random.uniform(3.0, 6.5)
        self.update()

    def _frame_key(self) -> str:
        state = self.current_state
        if self.motion_mode == "off" or self.is_minimized:
            return state
        if self._speaking and state.startswith("talking"):
            # Alternate matching mouth frames without switching the body pose.
            if math.sin(self._motion_time * math.tau / 0.34) < -0.15:
                state = self._mouth_keys.get(state,state)
        if time.monotonic() < self._blink_until:
            return self._blink_keys.get(state, state)
        return state

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_motion_timer()

    def hideEvent(self, event) -> None:
        self.motion_timer.stop()
        self.fade_anim.stop()
        self._fade_progress = 1.0
        self._release_transition()
        super().hideEvent(event)

    def get_fade_progress(self) -> float:
        return self._fade_progress

    def set_fade_progress(self, val: float) -> None:
        self._fade_progress = float(val)
        self.update()

    fadeProgress = Property(float, get_fade_progress, set_fade_progress)

    def _release_transition(self) -> None:
        self._transition_source = None
        self._transition_region = QRegion()
        self.update()

    def set_state(self, state: str) -> None:
        if state not in self._paths or state == self.current_state:
            return
        if self._paths[state] == self._paths[self.current_state]:
            self.current_state = state
            self.state_started_at = time.monotonic()
            self._load_pose(state)
            self.update()
            return
        if self.isVisible() and self.motion_mode != "off":
            # Snapshot the current blend so quick status changes never jump back
            # to an older pose. Only one display-sized transition buffer is kept.
            snapshot = QPixmap(self.size())
            snapshot.fill(Qt.GlobalColor.transparent)
            painter = QPainter(snapshot)
            self._draw_layers(painter)
            painter.end()
        else:
            snapshot = None
        self.fade_anim.stop()
        self.previous_state = self.current_state
        self.current_state = state
        self.state_started_at = time.monotonic()
        self._load_pose(state)
        self._transition_source = snapshot
        self._transition_region = QRegion(snapshot.mask()) if snapshot is not None else QRegion()
        self._fade_progress = 1.0 if snapshot is None else 0.0
        if snapshot is not None:
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()
        self.update()

    def _motion_transform(self) -> QTransform:
        # Keep the body fixed during idle, clicks, speech and pose transitions.
        # The timer only drives facial frames; pose opacity still uses easing.
        return QTransform()

    def opaque_region(self) -> QRegion:
        region = self.alpha_masks.get(self.current_state, QRegion())
        if self._transition_source is not None:
            # Include all currently visible layers during a cross-fade.
            region = region.united(self._transition_region)
        return self._motion_transform().map(region)

    def _draw_layers(self, painter: QPainter) -> None:
        if self._transition_source is not None:
            # Fade through instead of overlapping different bodies: no ghost
            # hands/faces when switching between genuinely different poses.
            painter.setOpacity(max(0.0,1.0-2*self._fade_progress))
            if self._fade_progress < 0.5:
                painter.drawPixmap(0,0,self._transition_source)
        pix = self._load_pose(self._frame_key())
        painter.setOpacity(max(0.0,2*self._fade_progress-1) if self._transition_source is not None else 1.0)
        painter.drawPixmap((self.width() - pix.width()) // 2, self.height() - 4 - pix.height(), pix)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setTransform(self._motion_transform())
        self._draw_layers(painter)
        painter.end()
