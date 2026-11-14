"""Render all character themes offscreen without changing personal settings."""

from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from main import FrierenDeskWindow
from character_profiles import CharacterProfile, PROFILES


def main():
    app = QApplication.instance() or QApplication([])
    assets = CharacterProfile.assets
    available = CharacterProfile.available
    mouths = CharacterProfile.mouth_frames
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
        destination = ROOT / "data/previews"
        destination.mkdir(parents=True, exist_ok=True)
        window.show()
        if not window.input_container.isVisible():
            window.toggle_input_box()
        for identifier in PROFILES:
            window._set_character(identifier)
            window.resize(560, 680)
            window.sprite.set_motion_mode("off")
            app.processEvents()
            window.grab().save(str(destination / f"{identifier}_companion.png"))
            window.open_chat_panel()
            for width, height in ((440, 640), (900, 760)):
                window.chat_panel.resize(width, height)
                app.processEvents()
                window.chat_panel.grab().save(str(destination / f"{identifier}_panel_{width}.png"))
            window.chat_panel.hide()
        window._cleanup_workers()
        window.close()
        app.processEvents()
        print(destination)


if __name__ == "__main__":
    main()
