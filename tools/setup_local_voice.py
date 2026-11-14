"""Download the opt-in local cloning model without uploading reference audio."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    destination = ROOT / "data/models/Qwen3-TTS-12Hz-0.6B-Base"
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download("Qwen/Qwen3-TTS-12Hz-0.6B-Base", local_dir=destination,
                      max_workers=2, ignore_patterns=["*.md", ".gitattributes"])
    print("Local model downloaded:", destination)
