import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from cli_process import ProcessResult
from local_voice import reference_for, cpu_settings
from speech_synthesis import NarrationWorker, speech_style, narration_text
from codex_backend import CodexBackend


class LocalVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        folder = self.root / "assets/voices/beatrice"
        folder.mkdir(parents=True)
        self.sample = folder / "sample.wav"
        self.audio(self.sample)
        self.manifest = folder / "clone.json"
        self.manifest.write_text(json.dumps({"file":"sample.wav","start_seconds":0,"duration_seconds":4}))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def audio(path):
        with wave.open(str(path),"wb") as wav:
            wav.setparams((1,2,24000,0,"NONE","not compressed"))
            wav.writeframes(b"\x00\x01"*2400)

    def test_reference_cannot_escape_character_folder(self):
        self.manifest.write_text(json.dumps({"file":"../other.wav"}))
        with self.assertRaises(ValueError):
            reference_for(self.root,"beatrice")

    def test_cpu_tuning_is_bounded(self):
        self.assertEqual(cpu_settings(self.root)["attention"], "eager")
        (self.root / "config.json").write_text(json.dumps({"voice_runtime":{
            "cpu_threads":999, "attention":"sdpa"}}))
        with patch("local_voice.os.cpu_count", return_value=12):
            self.assertEqual(cpu_settings(self.root), {"cpu_threads":12,
                             "attention":"sdpa"})

    def test_nonfinite_reference_range_is_rejected(self):
        for start in (float("nan"), float("inf")):
            self.manifest.write_text(json.dumps({"file":"sample.wav", "start_seconds":start}))
            with self.assertRaises(ValueError):
                reference_for(self.root,"beatrice")

    def test_clone_payload_uses_actual_japanese_answer_and_character_sample(self):
        calls=[]
        def run(base_dir, payload, cancel, on_stdout):
            calls.append(payload)
            self.audio(Path(payload["output"]))
            return ProcessResult(0,"","")
        ready=[]
        with patch("speech_synthesis.clone_service.synthesize",side_effect=run):
            for emotion in ("senang", "tenang"):
                worker=NarrationWorker(self.root,"beatrice","計算結果は四十二だ。",emotion,engine="qwen-local")
                worker.ready.connect(ready.append)
                worker.run()
        self.assertEqual(len(calls),1)  # Qwen cache survives UI mood changes
        payload=calls[0]
        self.assertEqual(payload["text"],"計算結果は四十二だ。")
        self.assertEqual(Path(payload["reference"]["file"]),self.sample.resolve())
        self.assertFalse(payload["stream_chunks"])
        self.assertEqual(len(ready),2)
        self.assertEqual(ready[0].engine,"qwen-local")
        self.assertFalse(list((self.root/"data/tts/beatrice").glob("*.part.*")))

    def test_pre_cancel_never_launches_clone_model(self):
        worker=NarrationWorker(self.root,"beatrice","こんにちは。",engine="qwen-local")
        worker.cancel()
        with patch("speech_synthesis.clone_service.synthesize") as run:
            worker.run()
            run.assert_not_called()

    def test_first_sentence_ready_before_next_sentence_is_generated(self):
        ready, texts = [], []
        def run(command, **kwargs):
            payload = json.loads(kwargs["input_text"])
            if texts:
                self.assertEqual(len(ready), 1)
            texts.append(payload["text"])
            self.audio(Path(payload["output"]))
            return ProcessResult(0, "", "")
        worker = NarrationWorker(self.root, "beatrice", "結果は四十二だ。次の手順を説明する。", engine="windows")
        worker.ready.connect(ready.append)
        with patch("speech_synthesis.ProcessRunner.run", side_effect=run):
            worker.run()
        self.assertEqual(texts, ["結果は四十二だ。", "次の手順を説明する。"])
        self.assertEqual(len(ready), 2)
        self.assertTrue(all(audio.file.is_file() for audio in ready))

    def test_clone_waits_for_complete_audio_to_avoid_mid_reply_underruns(self):
        ready = []
        def run(base_dir, payload, cancel, on_stdout):
            output = Path(payload["output"])
            chunk = output.with_name(output.stem + ".chunk-0.wav")
            self.audio(chunk)
            on_stdout(json.dumps({"chunk_file":str(chunk), "duration_ms":100}))
            self.assertFalse(payload["stream_chunks"])
            self.assertEqual(len(ready), 0)
            self.audio(output)
            return ProcessResult(0, "", "")
        worker = NarrationWorker(self.root, "beatrice", "結果は四十二だ。次の手順を説明する。", engine="qwen-local")
        worker.ready.connect(ready.append)
        with patch("speech_synthesis.clone_service.synthesize", side_effect=run):
            worker.run()
        self.assertEqual(len(ready), 1)
        self.assertNotIn("chunk-", ready[0].file.name)

    def test_japanese_text_survives_cleanup_and_persona_prompt(self):
        self.assertEqual(narration_text("詳細: https://example.com"), "詳細: リンク先")
        self.assertEqual(narration_text("結果は**四十二**です。[EMOTION: senang]"),"結果は四十二です。")
        for character in ("frieren","beatrice","waguri_kaoruko"):
            self.assertTrue(speech_style(character,None)["voice"].startswith("ja-JP-"))
        prompt=CodexBackend(self.root).build_prompt("Jelaskan hasil 6 kali 7")
        self.assertIn("bahasa Jepang",prompt)
        self.assertIn("6 kali 7",prompt)


if __name__ == "__main__":
    unittest.main()
