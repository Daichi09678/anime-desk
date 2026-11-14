"""Short-lived TTS subprocess: keeps network/audio synthesis out of the GUI."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys


def main():
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    output = Path(payload["output"])
    style = payload["style"]
    if payload["engine"] == "edge":
        import edge_tts
        async def generate():
            await edge_tts.Communicate(payload["text"],style["voice"],rate=f"{style['rate']:+d}%",
                                       pitch=f"{style['pitch']:+d}Hz",connect_timeout=8,receive_timeout=15).save(str(output))
        asyncio.run(asyncio.wait_for(generate(),timeout=40))
    elif payload["engine"] == "windows" and sys.platform == "win32":
        script = r'''
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voice = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1
  if (-not $voice) { throw 'Suara Jepang Windows belum terpasang. Pilih engine Jepang online.' }
  $s.SelectVoice($voice.VoiceInfo.Name)
  $s.Rate = [int]$p.style.system_rate
  $s.Volume = 85
  $s.SetOutputToWaveFile([string]$p.output)
  $s.Speak([string]$p.text)
} finally { $s.Dispose() }
'''
        completed = subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],
                                   input=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode("utf-8","replace")[-600:])
    else:
        raise RuntimeError("Engine TTS tidak tersedia pada sistem ini.")


if __name__ == "__main__":
    main()
