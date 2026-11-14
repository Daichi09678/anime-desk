"""Cancellable Japanese narration using local cloning or explicit synthetic engines."""

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import threading
import uuid

from PySide6.QtCore import QThread, Signal

from cli_process import ProcessCancelled, ProcessRunner
from local_voice import reference_for, runtime as clone_runtime

CLONE_LOCK = threading.Lock()


STYLES = {
    "frieren": {"voice":"ja-JP-NanamiNeural","rate":-12,"pitch":-4,"system_rate":-2},
    "beatrice": {"voice":"ja-JP-NanamiNeural","rate":-3,"pitch":-9,"system_rate":-1},
    "waguri_kaoruko": {"voice":"ja-JP-NanamiNeural","rate":0,"pitch":8,"system_rate":0},
}


def narration_text(text):
    text = re.sub(r"```.*?```", "",text,flags=re.S)
    text = re.sub(r"\[(?:MEMORY_SAVE|EMOTION):[^\]]*\]", "",text,flags=re.I)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)",r"\1",text)
    text = re.sub(r"https?://\S+","リンク先",text)
    text = re.sub(r"[*_#`~]","",html.unescape(text))
    text = re.sub(r"[\U00010000-\U0010ffff]","",text)
    return re.sub(r"\s+"," ",text).strip()[:4000]


def speech_style(character, emotion):
    style = dict(STYLES.get(character,STYLES["frieren"]))
    if emotion in ("senang","ceria","antusias"):
        style["rate"] += 3
        style["pitch"] += 2
    elif emotion in ("mengantuk","nostalgia","tenang"):
        style["rate"] -= 3
    return style


@dataclass
class NarrationAudio:
    file: Path
    duration_ms: int
    engine: str


class NarrationWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, base_dir, character, text, emotion=None, engine="auto", parent=None):
        super().__init__(parent)
        self.base_dir = Path(base_dir)
        self.character = character
        self.text = narration_text(text)
        self.style = speech_style(character,emotion)
        self.engine = engine
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            if not self.text:
                if not self.cancel_event.is_set():
                    self.failed.emit("Tidak ada teks yang dapat dinarasikan.")
                return
            folder = self.base_dir / "data/tts" / self.character
            folder.mkdir(parents=True,exist_ok=True)
            reference = reference_for(self.base_dir, self.character) if self.engine == "qwen-local" else None
            key = hashlib.sha256(json.dumps([self.text,self.style,self.engine,reference,"ja-clone-v2"],sort_keys=True).encode()).hexdigest()[:24]
            python = Path(sys.executable)
            console = python.with_name("python.exe") if sys.platform == "win32" else python
            if not console.is_file():
                console = python
            engines = ["edge","windows"] if self.engine == "auto" and sys.platform == "win32" else ["edge" if self.engine == "auto" else self.engine]
            errors = []
            for engine in engines:
                if self.cancel_event.is_set():
                    raise ProcessCancelled()
                output = folder / f"{key}_{engine}{'.wav' if engine in ('windows','qwen-local') else '.mp3'}"
                temporary = output.with_name(output.stem+"."+uuid.uuid4().hex+".part"+output.suffix)
                try:
                    if not output.is_file() or output.stat().st_size < 100:
                        payload = {"text":self.text,"style":self.style,"output":str(temporary),"engine":engine}
                        if engine == "qwen-local":
                            payload["reference"] = reference
                            while not CLONE_LOCK.acquire(timeout=0.1):
                                if self.cancel_event.is_set():
                                    raise ProcessCancelled()
                            try:
                                if self.cancel_event.is_set():
                                    raise ProcessCancelled()
                                result = ProcessRunner(self.cancel_event).run(
                                    [str(clone_runtime(self.base_dir)),str(Path(__file__).with_name("local_voice_process.py"))],
                                    cwd=self.base_dir,timeout=1800,input_text=json.dumps(payload,ensure_ascii=False))
                            finally:
                                CLONE_LOCK.release()
                        else:
                            result = ProcessRunner(self.cancel_event).run(
                                [str(console),str(Path(__file__).with_name("tts_process.py"))],
                                cwd=self.base_dir,timeout=50,input_text=json.dumps(payload,ensure_ascii=False))
                        if result.returncode or not temporary.is_file() or temporary.stat().st_size < 100:
                            raise RuntimeError(result.stderr[-600:] or "TTS tidak menghasilkan audio.")
                        temporary.replace(output)
                    from mutagen import File
                    info = File(str(output))
                    duration = round(info.info.length*1000) if info is not None else 0
                    if duration <= 0:
                        raise RuntimeError("Durasi narasi tidak valid.")
                    for old in sorted((p for p in folder.glob("*") if ".part." not in p.name),key=lambda p:p.stat().st_mtime,reverse=True)[4:]:
                        if old.is_file() and old != output:
                            try:
                                old.unlink()
                            except OSError:
                                pass
                    if not self.cancel_event.is_set():
                        self.ready.emit(NarrationAudio(output,duration,engine))
                    return
                except ProcessCancelled:
                    raise
                except Exception as exc:
                    errors.append(f"{engine}: {exc}")
                finally:
                    temporary.unlink(missing_ok=True)
            self.failed.emit("; ".join(errors)[-800:])
        except ProcessCancelled:
            pass
        except Exception as exc:
            self.failed.emit(str(exc))
