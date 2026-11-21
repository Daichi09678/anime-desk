"""Exercise real sprite decoding, transition lifecycle, and bounded caching."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QAbstractAnimation, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from character_widget import FrierenSpriteWidget
from sprite_helper import STATES


class CharacterWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        folder = Path(__file__).resolve().parents[1] / "assets" / "sprites"
        cls.sprites = {state: folder / f"{state}.png" for state in STATES}

    def setUp(self):
        self.widget = FrierenSpriteWidget(self.sprites)
        self.widget.show()
        self.app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def test_all_poses_decode_and_cache_stays_bounded_after_repeated_switches(self):
        for _ in range(3):
            for state in STATES:
                self.widget.set_state(state)
                pix = self.widget.pixmaps[state]
                self.assertFalse(pix.isNull(), state)
                self.assertLessEqual(pix.width(), self.widget.width())
                self.assertLessEqual(pix.height(), self.widget.height())
                self.assertFalse(self.widget.opaque_region().isEmpty(), state)
                self.assertLessEqual(len(self.widget.pixmaps), self.widget.CACHE_LIMIT)
                self.assertEqual(set(self.widget.alpha_masks), set(self.widget.pixmaps))
        texture_bytes = sum(p.width() * p.height() * p.depth() // 8 for p in self.widget.pixmaps.values())
        self.assertLess(texture_bytes, 2 * 1024 * 1024)

    def test_transition_finishes_and_releases_snapshot(self):
        self.widget.set_state("thinking")
        self.assertIsNotNone(self.widget._transition_source)
        QTest.qWait(450)
        self.assertEqual(self.widget.get_fade_progress(), 1.0)
        self.assertIsNone(self.widget._transition_source)
        self.assertTrue(self.widget._transition_region.isEmpty())

    def test_click_and_response_never_rotate_or_move_body(self):
        self.widget.react_to_click()
        self.widget.set_speaking(True)
        for mode in ("natural", "reduced", "off"):
            self.widget.set_motion_mode(mode)
            for state in ("idle", "pleased", "talking", "talking_explain"):
                self.widget.set_state(state)
                for phase in (0.0, 0.2, 1.0, 3.0):
                    self.widget._motion_time = phase
                    self.assertTrue(self.widget._motion_transform().isIdentity())

    def test_characters_share_size_center_and_visible_baseline(self):
        from character_profiles import PROFILES
        root = Path(__file__).resolve().parents[1]
        self.widget.set_motion_mode("off")
        for scale in (0.65, 1.0, 1.55):
            self.widget.set_scale_factor(scale)
            for profile in PROFILES.values():
                sprites, blinks = profile.assets(root)
                self.widget.set_sprites(sprites, blinks, profile.mouth_frames(root), profile.portrait_frame)
                self.assertEqual(self.widget.width(), int(235 * scale))
                self.assertEqual(self.widget.height(), int(245 * scale))
                for state in ("idle", "talking", "thinking"):
                    self.widget.set_state(state)
                    region = self.widget.opaque_region()
                    bounds = region.boundingRect()
                    # Hair or a hand can widen the silhouette on one side. The face
                    # should still be clickable at Frieren's central eye line.
                    self.assertTrue(region.contains(QPoint(self.widget.width() // 2,
                                                           round(self.widget.height() * .25))))
                    self.assertLessEqual(abs(bounds.bottom() - (self.widget.height() - 5)), 2)

    def test_interrupted_transition_and_resize_release_old_buffers(self):
        self.widget.set_state("thinking")
        QTest.qWait(80)
        self.widget.set_state("talking")
        self.assertEqual(self.widget.current_state, "talking")
        self.assertIsNotNone(self.widget._transition_source)
        self.widget.set_scale_factor(1.5)
        self.assertIsNone(self.widget._transition_source)
        self.assertEqual(list(self.widget.pixmaps), ["talking"])
        self.assertFalse(self.widget.opaque_region().isEmpty())

    def test_hidden_mini_and_off_stop_motion_and_resume_correctly(self):
        self.assertTrue(self.widget.motion_timer.isActive())
        self.widget.hide()
        self.assertFalse(self.widget.motion_timer.isActive())
        self.widget.set_state("sleeping")
        self.assertEqual(self.widget.get_fade_progress(), 1.0)
        self.widget.show()
        self.app.processEvents()
        self.assertTrue(self.widget.motion_timer.isActive())
        self.widget.set_minimized_mode(True)
        self.assertFalse(self.widget.motion_timer.isActive())
        self.widget.set_minimized_mode(False)
        self.assertTrue(self.widget.motion_timer.isActive())
        self.widget.set_motion_mode("reduced")
        self.assertEqual(self.widget.motion_timer.interval(), 100)
        self.widget.set_motion_mode("off")
        self.assertFalse(self.widget.motion_timer.isActive())
        self.assertTrue(self.widget._motion_transform().isIdentity())
        self.widget.set_state("idle")
        self.assertEqual(self.widget.fade_anim.state(), QAbstractAnimation.State.Stopped)

    def test_window_integration_preserves_work_pose_when_clicked(self):
        from main import FrierenDeskWindow

        # Keep configuration, generated audio, native hotkeys, and live CLI
        # processes out of this integration check.
        with tempfile.TemporaryDirectory() as folder, \
                patch("main.ensure_sprites", return_value=self.sprites), \
                patch("main.TypingSoundPlayer") as sound, \
                patch.object(FrierenDeskWindow, "_init_shortcuts_and_tray"), \
                patch.object(FrierenDeskWindow, "_update_mask_and_clickthrough"):
            sound.return_value.enabled = False
            window = FrierenDeskWindow(Path(folder), auto_discover=False)
            try:
                window.show()
                self.app.processEvents()
                window.sprite.set_state("action_magic")
                window._worker = Mock()
                window._worker.isRunning.return_value = True
                window._pet_frieren()
                self.assertEqual(window.sprite.current_state, "action_magic")
                window._on_state_timer()
                self.assertEqual(window.sprite.current_state, "action_magic")
                window._set_motion_mode("reduced")
                self.assertEqual(window.config["ui"]["motion_mode"], "reduced")
                self.assertEqual(window.sprite.motion_timer.interval(), 100)
            finally:
                window._worker = None
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
