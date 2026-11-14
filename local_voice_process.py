"""Opt-in, short-lived CPU voice cloning. Run only with .venv-voice Python."""
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent


def synthesize(payload):
    # Never download models implicitly during a chat request.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    torch.set_num_threads(max(1, min(4, (os.cpu_count() or 2) // 2)))
    torch.set_num_interop_threads(1)
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
    model = Qwen3TTSModel.from_pretrained(
        str(ROOT / "data/models/Qwen3-TTS-12Hz-0.6B-Base"),
        device_map="cpu", dtype=torch.float32, attn_implementation="eager",
        local_files_only=True,
    )
    prompt = model.create_voice_clone_prompt(ref_audio=(sample, rate), x_vector_only_mode=True)
    # Bound the token budget per sentence; preserve the whole answer in order.
    sentences = re.findall(r"[^。！？!?\n]+[。！？!?]?", payload["text"])
    chunks = [sentence[i:i+160] for sentence in sentences for i in range(0, len(sentence), 160)]
    started = time.monotonic()
    with sf.SoundFile(payload["output"], mode="w", samplerate=24000, channels=1, subtype="PCM_16") as output:
        for chunk in chunks:
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
    print(json.dumps({"engine":"qwen-local", "elapsed_seconds":round(time.monotonic()-started, 2)}), flush=True)


if __name__ == "__main__":
    synthesize(json.loads(sys.stdin.buffer.read().decode("utf-8")))
