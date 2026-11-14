"""Lightweight local-clone configuration, with no ML imports in the Qt process."""
import json
import math
from pathlib import Path
import sys


def runtime(base_dir):
    folder = Path(base_dir) / ".venv-voice"
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


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
