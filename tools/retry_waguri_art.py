"""Retry the single failed image-generator sheet; user-authorized AGY work."""
from pathlib import Path
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ai_providers import run_agy
from cli_process import resolve_binary
from tools.generate_character_art import report

def main():
    target=ROOT/"assets/generated/production/waguri_poses.png"
    ref=ROOT/"assets/sprites/references/waguri/image.png"
    prompt=f"""User authorizes image generation via AGY. The earlier Waguri image-generator
subagent failed/stalled; the other four image tasks succeeded. Retry ONLY Waguri.
Use invoke_subagent TypeName=image-generator with this brief:
Generate a NEW anime 2D sprite sheet of Waguri Kaoruko, identity/outfit strictly
from {ref}: long dark wavy hair, blue eyes, dusty pink sailor school uniform,
white collar, black ribbon. Clean anime line art, NOT chibi or photo. 3 columns
and 4 rows, 12 equal cells, 896x1200 or larger, consistent sitting/bust-to-thigh
camera/scale and baseline. Pure flat neon magenta #ff00ff backdrop, NO text or
grid lines. Left-to-right top-to-bottom: idle, reading, thinking hand-to-chin,
explaining open palm, talking (same body as idle), happy wave, surprised, holding
tea, working with notebook/laptop, gentle confident gesture, stretching, sleepy.
Leave safe margins; hands stay inside each cell. Make genuinely new poses, not
cropped or recoloured reference images. Save final PNG to {target}.
After invoking, use manage_subagents to WAIT/poll until the actual image file is
returned. Copy the generator image to the target and verify its actual dimensions.
Only write that image and waguri_retry_report.json in the same folder. Do not
change application code/config/audio/reference files. If the tool reports an
error, report the exact error. Do not end with 'launched/pending' as success.
"""
    report("Retrying failed Waguri sprite generation")
    reply=run_agy(resolve_binary("agy","agy"),"gemini-3.8-flash-low","low",prompt,[str(ref)],ROOT,True,
                  1200,threading.Event(),report,lambda text:None,keep_alive=lambda:target.is_file())
    report(reply.text)
    (target.parent/"waguri_retry_agent.txt").write_text(reply.text+"\n"+reply.log,encoding="utf-8")
if __name__=="__main__":
    try: main()
    except Exception as exc: report(f"Waguri generation failed: {exc}")
