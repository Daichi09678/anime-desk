from pathlib import Path
import tempfile
import unittest
import wave

from character_voice import VoiceBank, VoiceClip, VoiceController
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


class VoiceBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bank = VoiceBank(Path(self.temp.name),"beatrice")
        self.bank.folder.mkdir(parents=True)
        self.file = self.bank.folder / "long reference.wav"
        with wave.open(str(self.file),"wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\0\0"*1600)

    def tearDown(self):
        self.temp.cleanup()

    def test_unclassified_reference_is_not_used_as_success_or_explanation(self):
        self.assertEqual(self.bank.files(),[self.file])
        self.assertIsNone(self.bank.clip_for("success"))
        self.assertIsNone(self.bank.clip_for("explaining"))

    def test_assigned_ranges_persist_and_source_is_not_modified(self):
        original = self.file.read_bytes()
        self.bank.assign("explaining",VoiceClip(self.file,20,150))
        clip = VoiceBank(Path(self.temp.name),"beatrice").clip_for("explaining")
        self.assertEqual((clip.file,clip.start_ms,clip.end_ms),(self.file,20,150))
        self.assertEqual(self.file.read_bytes(),original)

    def test_invalid_or_unbounded_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            self.bank.assign("success",VoiceClip(self.file,20,200000))
        with self.assertRaises(ValueError):
            self.bank.assign("success",VoiceClip(self.file,200,100))

    def test_malformed_manifest_does_not_activate_unclassified_audio(self):
        (self.bank.folder / "manifest.json").write_text('{"events": []}',encoding="utf-8")
        self.assertIsNone(self.bank.clip_for("success"))

    def test_player_loads_only_on_demand_and_stops_a_short_muted_clip(self):
        controller = VoiceController()
        self.assertIsNone(controller.player)
        controller._init_player()
        controller.output.setMuted(True)
        states = []
        controller.speakingChanged.connect(states.append)
        try:
            for index in range(2):
                controller.play(VoiceClip(self.file,0,100))
                QTest.qWait(900)
                self.assertIsNone(controller.clip)
                self.assertFalse(controller.timer.isActive())
                self.assertGreaterEqual(states.count(True),index+1)
        finally:
            controller.stop()
            controller.deleteLater()


if __name__ == "__main__":
    unittest.main()
