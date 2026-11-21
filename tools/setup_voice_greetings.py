"""Prepare reusable local clones of each character's standard tap greetings."""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from character_profiles import PROFILES
from clone_service import clone_service
from speech_synthesis import NarrationWorker


def main():
    try:
        for profile in PROFILES.values():
            for number, text in enumerate(profile.voice_taps, 1):
                audio, errors = [], []
                worker = NarrationWorker(ROOT, profile.id, text, engine="qwen-local")
                worker.ready.connect(audio.append)
                worker.failed.connect(errors.append)
                start = time.monotonic()
                worker.run()
                if len(audio) != 1:
                    raise RuntimeError(f"{profile.name} #{number}: {errors or 'audio tidak tersedia'}")
                print(f"{profile.name} #{number}: {audio[0].duration_ms / 1000:.2f} s audio, "
                      f"siap dalam {time.monotonic() - start:.3f} s", flush=True)
    finally:
        clone_service.stop()


if __name__ == "__main__":
    main()
