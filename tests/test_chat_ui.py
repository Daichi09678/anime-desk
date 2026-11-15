from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from ai_providers import ProviderState
from chat_widgets import ChatInputBox, local_path_candidates
from codex_backend import CodexResult
from main import FrierenDeskWindow
from sprite_helper import STATES
from character_profiles import CharacterProfile, get_profile
from codex_backend import CodexBackend
from character_voice import VoiceClip
from speech_synthesis import NarrationAudio

NATIVE_SETUP = FrierenDeskWindow._init_shortcuts_and_tray


class ChatUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = Path(__file__).resolve().parents[1] / "assets/sprites"
        sprites = {state: folder / f"{state}.png" for state in STATES}
        source_root = folder.parents[1]
        available = CharacterProfile.available
        assets = CharacterProfile.assets
        mouths = CharacterProfile.mouth_frames
        self.patches = [patch("main.ensure_sprites", return_value=sprites),
                        patch.object(CharacterProfile,"available",lambda profile,base: available(profile,source_root)),
                        patch.object(CharacterProfile,"assets",lambda profile,base: assets(profile,source_root)),
                        patch.object(CharacterProfile,"mouth_frames",lambda profile,base: mouths(profile,source_root)),
                        patch("main.TypingSoundPlayer"),
                        patch.object(FrierenDeskWindow, "_init_shortcuts_and_tray"),
                        patch.object(FrierenDeskWindow, "_update_mask_and_clickthrough")]
        for patcher in self.patches:
            patcher.start()
        self.window = FrierenDeskWindow(self.root, auto_discover=False)
        self.window.config.setdefault("ui",{})["voice_enabled"] = False
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window._cleanup_workers()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def test_shift_enter_inserts_newline_and_enter_submits(self):
        composer = ChatInputBox(self.window)
        submitted = []
        composer.returnPressed.connect(lambda: submitted.append(composer.text()))
        composer.setText("baris pertama")
        cursor = composer.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        composer.setTextCursor(cursor)
        QTest.keyClick(composer, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertIn("\n", composer.text())
        QTest.keyClick(composer, Qt.Key.Key_Return)
        self.assertTrue(submitted)

    def test_urls_are_not_probed_as_network_attachment_paths(self):
        self.assertEqual(local_path_candidates("buka https://example.com"), [])
        self.assertEqual(local_path_candidates('lihat "https://example.com/a.png"'), [])
        self.assertEqual(local_path_candidates("//server/share"), [])
        self.assertEqual(local_path_candidates('lihat "C:\\Project Files\\main.py"'), ["C:\\Project Files\\main.py"])

    def test_models_from_both_connected_providers_and_active_model_selection(self):
        states = {"codex": ProviderState("codex", True, "OK", [{"id": "model-a", "name": "A"}]),
                  "antigravity": ProviderState("antigravity", True, "OK", [{"id": "model-b", "name": "B"}])}
        self.window._on_models_ready(states)
        combo = self.window.chat_panel.model_combo
        index = next((i for i in range(combo.count()) if tuple(combo.itemData(i) or []) == ("antigravity", "model-b")), -1)
        self.assertGreaterEqual(index, 0)
        combo.activated.emit(index)
        self.assertEqual(self.window.backend.active_engine, "antigravity")
        self.assertEqual(self.window.backend.active_model, "model-b")
        self.assertIn("model-b", self.window.bubble.runtime_label.toolTip())

    def test_character_switch_updates_identity_theme_and_releases_old_cache(self):
        for identifier in ("beatrice","waguri_kaoruko","frieren"):
            self.window._set_character(identifier)
            profile = get_profile(identifier)
            self.assertEqual(self.window.backend.character.id,identifier)
            self.assertEqual(self.window.bubble.name_label.text(),"✦ "+profile.name)
            self.assertIn(profile.colours["surface"],self.window.chat_panel.styleSheet())
            self.assertLessEqual(len(self.window.sprite.pixmaps),self.window.sprite.CACHE_LIMIT)
            self.assertEqual(self.window.sprite.current_state,"idle")
        self.window._set_character("beatrice")
        self.assertIn("Beatrice",self.window.backend.load_persona())
        self.window.backend.append_memory("assistant","Pesan karakter")
        self.assertEqual(self.window.backend.load_memory()[-1]["speaker"],"Beatrice")
        self.assertEqual(CodexBackend(self.root).character.id,"beatrice")

    def test_mouth_and_blink_frames_change_without_changing_body_state(self):
        self.window._set_character("waguri_kaoruko")
        sprite = self.window.sprite
        sprite.set_state("talking")
        sprite.set_speaking(True)
        sprite._motion_time = 0.255
        self.assertEqual(sprite._frame_key(),"__mouth_talking")
        sprite._motion_time = 0.085
        self.assertEqual(sprite._frame_key(),"talking")
        sprite._blink_until = time.monotonic()+1
        self.assertEqual(sprite._frame_key(),"__blink_talking")
        self.assertEqual(sprite.current_state,"talking")
        sprite.set_motion_mode("off")
        self.assertEqual(sprite._frame_key(),"talking")

    def test_panel_resize_is_saved_and_manual_expression_does_not_auto_cycle(self):
        self.window.open_chat_panel()
        self.window.chat_panel.resize(620,570)
        QTest.qWait(420)
        self.assertEqual(self.window.config["ui"]["chat_panel_size"],
                         [self.window.chat_panel.width(),self.window.chat_panel.height()])
        self.window._set_character("beatrice")
        self.window._preview_expression("surprised")
        self.window._cycle_idle_pose()
        self.window._on_state_timer()
        self.assertEqual(self.window.sprite.current_state,"thinking_lookup")
        self.window._preview_expression(None)
        self.assertEqual(self.window.sprite.current_state,"idle")

    def test_context_menu_tracks_character_theme_and_model_actions(self):
        with patch("main.WinGlobalHotKey"), patch("main.MacGlobalHotKey"), patch("main.QSystemTrayIcon") as tray:
            tray.isSystemTrayAvailable.return_value = True
            NATIVE_SETUP(self.window)
            self.window._set_character("beatrice")
            self.assertEqual(self.window.menu_character_name.text(),"Beatrice")
            self.assertIn(get_profile("beatrice").colours["accent"],self.window.context_menu.styleSheet())
            self.window._on_models_ready({"codex":ProviderState("codex",True,"OK",[{"id":"chosen","name":"Chosen"}]),
                                          "antigravity":ProviderState("antigravity",False,"Offline")})
            self.window.model_menus["codex"].actions()[0].trigger()
            self.assertEqual(self.window.backend.model,"chosen")
            self.window._preview_expression("happy")
            self.window._set_character("waguri_kaoruko")
            self.assertTrue(self.window.expression_actions[None].isChecked())

    def test_failure_selects_error_voice_context_instead_of_success(self):
        self.window.config["ui"].update(voice_enabled=True,voice_mode="clips")
        with patch("main.VoiceBank") as bank, patch.object(self.window.voice,"play") as play:
            bank.return_value.clip_for.side_effect = lambda event: VoiceClip(self.root/f"{event}.wav")
            self.window._on_codex_result(CodexResult("Ada kendala","error",[],status="failed"))
            self.assertEqual(play.call_args.args[0].file.name,"error.wav")

    def test_narration_uses_actual_result_and_stop_rejects_late_audio(self):
        self.window.config["ui"].update(voice_enabled=True,voice_mode="narration")
        with patch("main.NarrationWorker") as factory, patch.object(self.window.voice,"play") as play:
            worker = factory.return_value
            self.window._on_codex_result(CodexResult("Hasil perhitungan adalah 42.","",[],status="completed",
                                                     narration_ja="計算結果は四十二だ。"))
            self.assertEqual(factory.call_args.args[2],"計算結果は四十二だ。")
            token = self.window._tts_token
            self.window.stop_all_voice()
            self.window._on_narration_ready(token,NarrationAudio(self.root/"old.mp3",1000,"edge"))
            worker.cancel.assert_called()
            play.assert_not_called()
            self.assertFalse(self.window._tts_pending)
            self.window._tts_workers.clear()

    def test_narration_mode_does_not_substitute_reference_clips(self):
        self.window.config["ui"].update(voice_enabled=True,voice_mode="narration")
        with patch("main.VoiceBank") as bank:
            self.window._play_voice_event("explaining")
            bank.assert_not_called()

    def test_click_generates_matching_dub_and_repeated_click_keeps_pending_voice(self):
        self.window.config["ui"].update(voice_enabled=True,voice_mode="narration")
        with patch("main.NarrationWorker") as factory:
            self.window._pet_frieren()
            index = self.window._last_pet_idx
            self.assertEqual(factory.call_args.args[2], self.window.profile.voice_taps[index])
            self.assertTrue(self.window._tts_pending)
            self.assertTrue(self.window._tts_clock.isActive())
            token = self.window._tts_token
            self.window._pet_frieren()
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(self.window._tts_token, token)
            self.window.stop_all_voice()
            self.assertFalse(self.window._tts_clock.isActive())
            self.window._tts_workers.clear()

    def test_narration_error_is_visible_without_hover(self):
        self.window._on_narration_failed(self.window._tts_token, "Sample tidak valid")
        self.assertIn("Sample tidak valid", self.window.chat_panel.status.text())

    def test_chat_is_immediate_while_character_subtitle_waits_for_audio(self):
        window = self.window
        window.config["ui"].update(voice_enabled=True, voice_mode="narration")
        answer = "Hasil perhitungan adalah 42."
        result = CodexResult(answer, "", [], narration_ja="計算結果は四十二だ。")
        with patch("main.NarrationWorker"):
            window._on_stream_text(answer)
            self.assertNotIn(answer, window.bubble.text_label.text())
            self.assertIn(answer, window.chat_panel.transcript.toPlainText())
            window.backend.append_memory("assistant", answer)
            window._on_codex_result(result)
            self.assertNotIn(answer, window.bubble.text_label.text())
            self.assertIn(answer, window.chat_panel.transcript.toPlainText())
            window._on_voice_speaking(True)
            self.assertIn(answer, window.bubble.text_label.text())
            self.assertIn(answer, window.chat_panel.transcript.toPlainText())
            self.assertFalse(window.bubble.typing_timer.isActive())
            self.assertIsNone(window._synced_subtitle)
            window._tts_workers.clear()

    def test_subtitle_is_not_lost_when_voice_fails_or_is_stopped(self):
        window = self.window
        window.config["ui"].update(voice_enabled=True, voice_mode="narration")
        with patch("main.NarrationWorker"):
            for action in (lambda:window._on_narration_failed(window._tts_token, "gagal"), window.stop_all_voice):
                window._on_codex_result(CodexResult("Jawaban tetap tersedia.", "", [], narration_ja="答えだよ。"))
                action()
                self.assertIn("Jawaban tetap tersedia.", window.bubble.text_label.text())
                self.assertIsNone(window._synced_subtitle)
            window._tts_workers.clear()

    def test_stream_prefetch_is_reused_and_playback_waits_for_subtitle(self):
        window = self.window
        window.config["ui"].update(voice_enabled=True, voice_mode="narration", tts_engine="qwen-local")
        with patch("main.NarrationWorker") as factory, patch.object(window.voice, "play") as play:
            window._on_stream_text("[VOICE_JA]計算結果は四十二だ。[/VOICE_JA]")
            window._on_narration_ready(window._tts_token, NarrationAudio(self.root / "reply.wav", 1000, "qwen-local"))
            play.assert_not_called()
            window._on_codex_result(CodexResult("Hasilnya 42.", "", [], narration_ja="計算結果は四十二だ。"))
            self.assertEqual(factory.call_count, 1)
            play.assert_called_once()
            window._tts_workers.clear()

    def test_stop_during_prefetch_does_not_restart_on_next_stream_update(self):
        window = self.window
        window.config["ui"].update(voice_enabled=True, voice_mode="narration", tts_engine="qwen-local")
        with patch("main.NarrationWorker") as factory:
            text = "[VOICE_JA]計算結果は四十二だ。[/VOICE_JA]"
            window._on_stream_text(text)
            window._stop_voice_requested()
            window._on_stream_text(text + "Hasilnya 42.")
            window._on_codex_result(CodexResult("Hasilnya 42.", "", [], narration_ja="計算結果は四十二だ。"))
            self.assertEqual(factory.call_count, 1)
            window._tts_workers.clear()

    def test_narration_chunks_wait_for_playback_and_stop_clears_queue(self):
        window = self.window
        token = window._tts_token
        first = NarrationAudio(self.root / "first.wav", 1000, "edge")
        second = NarrationAudio(self.root / "second.wav", 1000, "edge")
        def play(clip):
            window._on_voice_speaking(True)
            return True
        with patch.object(window.voice, "play", side_effect=play) as playback:
            window._on_narration_ready(token, first)
            window._on_narration_ready(token, second)
            self.assertEqual(playback.call_count, 1)
            window._on_voice_speaking(False)
            self.app.processEvents()
            self.assertEqual(playback.call_count, 2)
            self.assertEqual(playback.call_args.args[0].file, second.file)
            window._on_narration_ready(token, first)
            window.stop_all_voice()
            self.assertEqual(window._tts_queue, [])
            window._on_narration_ready(token, second)
            self.assertEqual(playback.call_count, 2)

    def test_missing_dub_never_reads_indonesian_with_japanese_voice(self):
        self.window.config["ui"].update(voice_enabled=True,voice_mode="narration")
        with patch("main.NarrationWorker") as factory:
            self.window._on_codex_result(CodexResult("Hasilnya 42.", "", []))
            factory.assert_not_called()

    def test_timeout_stops_spinner_and_retry_clears_previous_output(self):
        self.window._on_codex_result(CodexResult("Waktu habis.","[Timeout]",[],status="timeout"))
        self.assertFalse(self.window.bubble.loading_row.isVisible())
        self.assertFalse(self.window.request_clock.isActive())
        def ask(message, **kwargs):
            kwargs["cancel_event"].wait(2)
            return CodexResult("Dibatalkan","",[],status="cancelled")
        with patch.object(self.window.backend,"ask",side_effect=ask):
            self.window.send_message("Coba lagi")
            self.assertNotIn("[Timeout]",self.window.chat_panel.output.toPlainText())
            self.window.cancel_request()
            deadline=time.monotonic()+4
            while self.window._worker is not None and time.monotonic()<deadline:
                QTest.qWait(20)
        self.assertTrue(self.window.chat_panel.input.isEnabled())

    def test_project_switch_updates_history_and_individual_attachment_removal(self):
        project = self.root / "sample"
        project.mkdir()
        self.window.backend.append_memory("user", "Pesan umum")
        self.window._select_project(str(project))
        self.assertEqual(self.window.backend.working_directory, project)
        self.assertNotIn("Pesan umum", self.window.chat_panel.transcript.toPlainText())
        first, second = project / "a.txt", project / "b.txt"
        first.write_text("A")
        second.write_text("B")
        self.window._add_attachment_path(str(first))
        self.window._add_attachment_path(str(second))
        self.window.remove_attachment(str(first))
        self.assertEqual(self.window.pending_attachments, [str(second)])
        self.window._select_project(None)
        self.assertIn("Pesan umum", self.window.chat_panel.transcript.toPlainText())

    def test_stream_cancel_and_reenable_composers(self):
        def ask(message, **kwargs):
            kwargs["on_text"]("Jawaban sebagian")
            kwargs["cancel_event"].wait(4)
            return CodexResult("Dibatalkan", "[Dibatalkan]", [], status="cancelled")

        with patch.object(self.window.backend, "ask", side_effect=ask):
            self.window.send_message("Pesan uji")
            QTest.qWait(80)
            self.assertFalse(self.window.chat_panel.input.isEnabled())
            self.assertIn("Jawaban sebagian", self.window.chat_panel.transcript.toPlainText())
            self.window.cancel_request()
            deadline = time.monotonic() + 5
            while self.window._worker is not None and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertIsNone(self.window._worker)
            self.assertTrue(self.window.chat_panel.input.isEnabled())
            self.assertIn("Dibatalkan", self.window.chat_panel.status.text())

    def test_shutdown_waits_for_cancelled_worker_before_hiding(self):
        def ask(message, **kwargs):
            kwargs["cancel_event"].wait(4)
            return CodexResult("Dibatalkan", "", [], status="cancelled")

        with patch.object(self.window.backend, "ask", side_effect=ask):
            self.window.send_message("Pesan uji")
            QTest.qWait(30)
            worker = self.window._worker
            self.window.request_shutdown()
            deadline = time.monotonic() + 5
            while self.window.isVisible() and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertFalse(self.window.isVisible())
            self.assertTrue(self.window._worker is None or not self.window._worker.isRunning())


if __name__ == "__main__":
    unittest.main()
