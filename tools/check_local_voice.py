"""Real opt-in CPU synthesis smoke test, including the runtime process tree RAM."""
from pathlib import Path
import json
import subprocess
import sys
import time
import threading
import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_voice import reference_for
from cli_process import ProcessRunner, ProcessCancelled


def main():
    destination=ROOT/"data/voice_checks"
    destination.mkdir(parents=True,exist_ok=True)
    text="六を七回足すと、四十二になる。これが掛け算の意味だ。"
    payload={"text":text,"reference":reference_for(ROOT,"beatrice"),"output":str(destination/"beatrice_answer.wav")}
    if "--cancel" in sys.argv:
        payload["output"]=str(destination/"cancelled.part.wav")
        cancel=threading.Event()
        timer=threading.Timer(2,cancel.set)
        timer.start()
        runner=ProcessRunner(cancel)
        started=time.monotonic()
        try:
            runner.run([sys.executable,str(ROOT/"local_voice_process.py")],cwd=ROOT,timeout=60,
                       input_text=json.dumps(payload,ensure_ascii=False))
            raise AssertionError("Cloning was not cancelled")
        except ProcessCancelled:
            assert runner.proc.poll() is not None
            print("CLONE_CANCEL_OK",round(time.monotonic()-started,2),"seconds; owned process terminated")
        finally:
            timer.cancel()
            Path(payload["output"]).unlink(missing_ok=True)
        return
    started=time.monotonic()
    process=subprocess.Popen([sys.executable,str(ROOT/"local_voice_process.py")],stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    process.stdin.write(json.dumps(payload,ensure_ascii=False).encode("utf-8"))
    process.stdin.close()
    peak=0
    while process.poll() is None:
        try:
            parent=psutil.Process(process.pid)
            peak=max(peak,sum(p.memory_info().rss for p in [parent,*parent.children(recursive=True)]))
        except psutil.NoSuchProcess:
            pass
        if time.monotonic()-started>300:
            process.kill()
            raise TimeoutError("Local synthesis smoke test exceeded five minutes")
        time.sleep(.1)
    out=process.stdout.read().decode("utf-8","replace")
    error=process.stderr.read().decode("utf-8","replace")
    if process.returncode:
        raise RuntimeError(error[-2000:])
    import soundfile as sf
    info=sf.info(payload["output"])
    report={"text":text,"audio":payload["output"],"duration_seconds":info.duration,
            "elapsed_seconds":round(time.monotonic()-started,2),"peak_rss_mb":round(peak/1024**2,1),
            "engine":"Qwen3-TTS-12Hz-0.6B-Base, CPU, speaker embedding", "sample_review":"draft"}
    (destination/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=True))


if __name__=="__main__":
    main()
