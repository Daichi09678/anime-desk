"""Compare local CPU settings using the same character, text and random seed."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import soundfile as sf
import torch
from local_voice import reference_for
from local_voice_process import load_model


def main():
    model = load_model({"cpu_threads":4, "attention":"eager"})
    reference = reference_for(ROOT, "frieren")
    with sf.SoundFile(reference["file"]) as source:
        source.seek(round(reference["start_seconds"] * source.samplerate))
        audio = source.read(round(reference["duration_seconds"] * source.samplerate),
                            dtype="float32", always_2d=True).mean(axis=1)
        rate = source.samplerate
    prompt = model.create_voice_clone_prompt(ref_audio=(audio, rate), x_vector_only_mode=True)
    settings = (("eager", 4), ("sdpa", 3), ("sdpa", 4), ("sdpa", 6))
    text = "六掛ける七の答えは四十二だ。" if "--reply" in sys.argv else "うん、わかったよ。"
    for attention, threads in settings:
        model.model.set_attn_implementation(attention)
        torch.set_num_threads(threads)
        torch.manual_seed(42)
        started = time.monotonic()
        with torch.inference_mode():
            wavs, sr = model.generate_voice_clone(
                text=text, language="Japanese", voice_clone_prompt=prompt,
                max_new_tokens=256,
            )
        print(json.dumps({"attention":attention, "threads":threads,
                          "seconds":round(time.monotonic()-started, 3),
                          "audio_seconds":len(wavs[0])/sr,
                          "finite":bool(np.isfinite(wavs[0]).all())}), flush=True)


if __name__ == "__main__":
    main()
