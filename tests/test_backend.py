import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ai_providers import ProviderReply, ProviderState
from codex_backend import CodexBackend


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.backend = CodexBackend(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_project_history_and_facts_are_isolated_and_global_facts_survive(self):
        a, b = self.root / "A", self.root / "B"
        a.mkdir()
        b.mkdir()
        self.backend.append_memory("user", "Percakapan umum")
        self.backend.add_ltm("Nama pengguna Rina", "global")
        self.backend.set_project(str(a))
        self.backend.append_memory("assistant", "Hasil A", "npm test: 42 passed")
        self.backend.add_ltm("Proyek A memakai SQLite")
        self.backend.set_project(str(b))
        self.assertEqual(self.backend.load_memory(), [])
        self.assertEqual(self.backend.load_ltm("project"), [])
        prompt = self.backend.build_prompt("Database proyek ini apa?")
        self.assertIn("Rina", prompt)
        self.assertNotIn("SQLite", prompt)
        self.backend.set_project(str(a))
        self.assertIn("42 passed", self.backend.build_prompt("Apa hasil tes?"))
        self.assertIn("SQLite", self.backend.build_prompt("database"))
        self.backend.set_project(None)
        self.assertEqual(self.backend.load_memory()[0]["text"], "Percakapan umum")

    def test_relevant_old_fact_is_not_lost_behind_recent_unrelated_facts(self):
        self.backend.add_ltm("Database proyek memakai PostgreSQL", "global")
        for index in range(20):
            self.backend.add_ltm(f"Preferensi warna nomor {index}", "global")
        self.assertIn("PostgreSQL", self.backend.build_prompt("database proyek"))

    def test_failure_does_not_save_facts_or_successful_technical_context(self):
        with patch.object(self.backend, "check_engine_prerequisites", return_value=(True, "OK")), \
                patch("codex_backend.run_codex", side_effect=RuntimeError("provider offline")):
            result = self.backend.ask("analisis proyek")
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.backend.load_ltm(), [])
        self.assertEqual(self.backend.load_memory()[-1]["status"], "failed")
        self.assertNotIn("provider offline", self.backend.build_prompt("lanjut"))

    def test_success_streams_and_keeps_output_in_context(self):
        def provider(*args):
            args[10]("Berhasil.\n```output\n2 tests passed\n```\n[EMOTION: senang]")
            return ProviderReply("Berhasil.\n```output\n2 tests passed\n```\n[MEMORY_SAVE: Framework pytest]\n[EMOTION: senang]", "pytest -q")
        streamed = []
        with patch.object(self.backend, "check_engine_prerequisites", return_value=(True, "OK")), \
                patch("codex_backend.run_codex", side_effect=provider):
            result = self.backend.ask("tes", on_text=streamed.append)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.technical_output, "2 tests passed")
        self.assertTrue(streamed)
        self.assertIn("2 tests passed", self.backend.build_prompt("hasil sebelumnya"))
        self.assertEqual(self.backend.load_ltm()[0]["fact"], "Framework pytest")

    def test_pre_cancel_does_not_create_history(self):
        cancel = threading.Event()
        cancel.set()
        result = self.backend.ask("halo", cancel_event=cancel)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.backend.load_memory(), [])

    def test_explicit_global_and_project_memory_commands(self):
        project = self.root / "project"
        project.mkdir()
        self.backend.set_project(str(project))
        self.assertEqual(self.backend.ask("ingat umum: nama saya Rina").status, "completed")
        self.assertEqual(self.backend.ask("ingat proyek: gunakan pytest").status, "completed")
        self.assertEqual(self.backend.load_ltm()[0]["fact"], "nama saya Rina")
        self.assertEqual(self.backend.load_ltm("project")[0]["fact"], "gunakan pytest")

    def test_model_selection_requires_discovery_and_persists(self):
        self.backend.providers["codex"] = ProviderState("codex", True, "OK", [{"id": "test-model", "name": "Test", "efforts": ["high"], "default_effort": "high"}])
        self.backend.set_model("codex", "test-model")
        self.assertEqual(self.backend.reasoning_effort, "high")
        fresh = CodexBackend(self.root)
        self.assertEqual(fresh.model, "test-model")
        with self.assertRaises(ValueError):
            self.backend.set_model("codex", "invented-model")

    def test_preview_hides_partial_control_tags_and_technical_blocks(self):
        self.assertEqual(self.backend.preview_speech("Halo [EMO"), "Halo")
        self.assertEqual(self.backend.preview_speech("Halo\n```output\npartial"), "Halo")

    def test_dub_is_separate_from_subtitles_stream_and_memory(self):
        raw = "Hasilnya 42.\n[VOICE_JA]答えは四十二だ。[/VOICE_JA]\n[EMOTION: senang]"
        with patch.object(self.backend, "check_engine_prerequisites", return_value=(True, "OK")), \
                patch("codex_backend.run_codex", return_value=ProviderReply(raw, "")):
            result = self.backend.ask("6 kali 7?")
        self.assertEqual(result.speech, "Hasilnya 42.")
        self.assertEqual(result.narration_ja, "答えは四十二だ。")
        self.assertNotIn("四十二", self.backend.load_memory()[-1]["text"])
        for partial in ("[VO", "[VOICE_JA]答え", "[VOICE_JA]答え[/VOICE_JA]"):
            self.assertEqual(self.backend.preview_speech("Hasilnya 42.\n" + partial), "Hasilnya 42.")


if __name__ == "__main__":
    unittest.main()
