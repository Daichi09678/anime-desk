"""Opt-in audible GUI-path check: click and reply -> local clone -> native playback.

Run with .venv313 Python. Uses temporary preferences and real local voice samples.
"""
from pathlib import Path
import logging
import os
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from character_profiles import CharacterProfile, PROFILES
from codex_backend import CodexResult
from main import FrierenDeskWindow


def main():
    logging.basicConfig(level=logging.INFO)
    identifier = sys.argv[1] if len(sys.argv) > 1 else "frieren"
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    assets, available, mouths = CharacterProfile.assets, CharacterProfile.available, CharacterProfile.mouth_frames
    with tempfile.TemporaryDirectory() as temporary, \
            patch.object(CharacterProfile, "assets", lambda p, _: assets(p, ROOT)), \
            patch.object(CharacterProfile, "available", lambda p, _: available(p, ROOT)), \
            patch.object(CharacterProfile, "mouth_frames", lambda p, _: mouths(p, ROOT)), \
            patch("main.ensure_sprites", return_value=PROFILES["frieren"].assets(ROOT)[0]), \
            patch.object(FrierenDeskWindow, "_init_shortcuts_and_tray"), \
            patch.object(FrierenDeskWindow, "_update_mask_and_clickthrough"), \
            patch("main.TypingSoundPlayer"):
        window = FrierenDeskWindow(Path(temporary), auto_discover=False)
        window.config.setdefault("ui", {})["voice_enabled"] = False
        window._set_character(identifier)
        window.base_dir = ROOT  # Real synthesis runtime/sample/cache, temporary UI preferences.
        window.config["ui"].update(voice_enabled=True, voice_mode="narration", tts_engine="qwen-local")
        window.show()
        outcomes = []
        phase = ["click"]
        started = time.monotonic()

        def speaking(active):
            if active:
                outcomes.append(phase[0])
                print("PLAYBACK_STARTED", identifier, phase[0], flush=True)
            elif outcomes and not window._tts_pending:
                if phase[0] == "click":
                    phase[0] = "reply"
                    QTimer.singleShot(100, lambda: window._on_codex_result(CodexResult(
                        "Hasil enam kali tujuh adalah empat puluh dua.", "", [],
                        narration_ja="六掛ける七の答えは四十二だ。")))
                elif outcomes == ["click", "reply"]:
                    app.quit()

        def watchdog():
            if time.monotonic() - started > 180:
                app.quit()
            elif not window._tts_pending and not window._voice_active and not outcomes:
                print("PLAYBACK_FAILED", window.chat_panel.status.text(), flush=True)
                app.quit()

        window.voice.speakingChanged.connect(speaking)
        window.voice.statusChanged.connect(lambda text: print("AUDIO_STATUS", text, flush=True))
        timer = QTimer()
        timer.timeout.connect(watchdog)
        timer.start(1000)
        window._pet_frieren()
        app.exec()
        window._cleanup_workers()
        window.hide()
        window.deleteLater()
        assert outcomes == ["click", "reply"], outcomes
        print("CLICK_AND_REPLY_PLAYBACK_OK", identifier, flush=True)


if __name__ == "__main__":
    main()
