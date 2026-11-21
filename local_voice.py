"""Lightweight local-clone configuration, with no ML imports in the Qt process."""
import json
import math
import os
from pathlib import Path
import sys


DEFAULT_CPU_THREADS = 3
DEFAULT_ATTENTION = "sdpa"


def runtime(base_dir):
    folder = Path(base_dir) / ".venv-voice"
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def cpu_settings(base_dir):
    """Machine-specific CPU tuning with bounded thread usage."""
    try:
        config = json.loads((Path(base_dir) / "config.json").read_text(encoding="utf-8"))
        settings = config.get("voice_runtime", {})
        threads = int(settings.get("cpu_threads", DEFAULT_CPU_THREADS))
        attention = settings.get("attention", DEFAULT_ATTENTION)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        threads, attention = DEFAULT_CPU_THREADS, DEFAULT_ATTENTION
    return {"cpu_threads":max(1, min(threads, os.cpu_count() or 1)),
            "attention":attention if attention in ("eager", "sdpa") else DEFAULT_ATTENTION}


def reference_for(base_dir, character):
    folder = Path(base_dir) / "assets/voices" / character
    manifest = folder / "clone.json"
    if not manifest.is_file():
        raise ValueError(f"Referensi cloning {character} belum dikonfigurasi.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    path = (folder / data["file"]).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise ValueError("File sample cloning tidak valid.")
    start, duration = float(data.get("start_seconds", 0)), float(data.get("duration_seconds", 8))
    if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or not 3 <= duration <= 15:
        raise ValueError("Pilih referensi cloning 3–15 detik dengan waktu mulai valid.")
    return {"file":str(path), "start_seconds":start, "duration_seconds":duration,
            "modified_ns":path.stat().st_mtime_ns, "size":path.stat().st_size}
