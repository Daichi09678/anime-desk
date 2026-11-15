"""Local character cloning with a reusable model. Run with .venv-voice Python."""
import json
import os
from pathlib import Path
import re
import sys
import time
from local_voice import cpu_settings

ROOT = Path(__file__).resolve().parent
_model = None
_prompts = {}


def load_model(settings=None):
    global _model
    if _model is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from qwen_tts import Qwen3TTSModel
        settings = settings or cpu_settings(ROOT)
        torch.set_num_threads(settings["cpu_threads"])
        torch.set_num_interop_threads(1)
        _model = Qwen3TTSModel.from_pretrained(
            str(ROOT / "data/models/Qwen3-TTS-12Hz-0.6B-Base"),
            device_map="cpu", dtype=torch.float32, attn_implementation=settings["attention"],
            local_files_only=True,
        )
    return _model


def synthesize(payload):
    # Never download models implicitly during a chat request.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile as sf
    import torch
    model = load_model()
    reference = payload["reference"]
    with sf.SoundFile(reference["file"]) as audio:
        audio.seek(round(reference["start_seconds"] * audio.samplerate))
        sample = audio.read(round(reference["duration_seconds"] * audio.samplerate), dtype="float32", always_2d=True)
        rate = audio.samplerate
    if len(sample) < rate * 3:
        raise ValueError("Referensi cloning harus berisi setidaknya 3 detik audio.")
    sample = sample.mean(axis=1)
    if np.max(np.abs(sample)) < 0.005:
        raise ValueError("Referensi cloning terlalu hening.")
    key = json.dumps(reference, sort_keys=True)
    if key not in _prompts:
        if len(_prompts) >= 3:
            _prompts.clear()
        _prompts[key] = model.create_voice_clone_prompt(ref_audio=(sample, rate), x_vector_only_mode=True)
    prompt = _prompts[key]
    # Bound the token budget per sentence; preserve the whole answer in order.
    sentences = re.findall(r"[^。！？!?\n]+[。！？!?]?", payload["text"])
    chunks = [sentence[i:i+160] for sentence in sentences for i in range(0, len(sentence), 160)]
    started = time.monotonic()
    with sf.SoundFile(payload["output"], mode="w", samplerate=24000, channels=1, subtype="PCM_16") as output:
        for index, chunk in enumerate(chunks):
            with torch.inference_mode():
                wavs, sr = model.generate_voice_clone(
                    text=chunk, language="Japanese", voice_clone_prompt=prompt,
                    max_new_tokens=min(1024, max(128, len(chunk) * 12)),
                )
            if sr != 24000:
                raise ValueError(f"Unexpected cloning sample rate: {sr}")
            if len(wavs[0]) / sr > max(14, len(chunk) * 0.6):
                raise RuntimeError("Cloning menghasilkan pengulangan terlalu panjang; pilih potongan sample yang lebih bersih lalu coba lagi.")
            output.write(wavs[0])
            output.write(np.zeros(round(sr * 0.12), dtype=np.float32))
            if payload.get("stream_chunks"):
                target = Path(payload["output"])
                chunk_file = target.with_name(f"{target.stem}.chunk-{index}.wav")
                sf.write(str(chunk_file), wavs[0], sr, subtype="PCM_16")
                print(json.dumps({"chunk_file":str(chunk_file),
                                  "duration_ms":round(len(wavs[0]) / sr * 1000)}), flush=True)
    print(json.dumps({"engine":"qwen-local", "elapsed_seconds":round(time.monotonic()-started, 2)}), flush=True)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        load_model()
        for line in sys.stdin.buffer:
            try:
                synthesize(json.loads(line.decode("utf-8")))
                print(json.dumps({"done":True}), flush=True)
            except Exception as exc:
                print(json.dumps({"done":True, "error":str(exc)}), flush=True)
    else:
        synthesize(json.loads(sys.stdin.buffer.read().decode("utf-8")))
