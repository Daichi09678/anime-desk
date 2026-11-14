"""Request new full-body Beatrice artwork from the authorized image agent."""
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai_providers import run_agy
from cli_process import resolve_binary


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    folder = ROOT / "assets/generated/beatrice_reference"
    folder.mkdir(parents=True, exist_ok=True)
    reference = ROOT / "assets/sprites/references/beatrice/image.png"
    retry = "--retry-sheet" in sys.argv
    prompt = f"""Use your image-generator subagent to generate actual NEW anime artwork
of Beatrice from Umineko matching this exact user reference: {reference}.
The user explicitly requests the canonical full black/dark-brown gothic ball gown,
burgundy layered underskirt, fine gold vine embroidery, white ruffled sleeves,
pink chest bow, blonde updo with dark rose, blue eyes, long elegant golden pipe.
Create {folder / 'beatrice_fullbody.png'}: one polished full-body idle standing
illustration, all of the skirt and pipe visible, 8 percent safety margin on every
side, clean flat neon magenta background for chroma removal. No text or UI.
Create {folder / 'beatrice_poses.png'}: 3 columns x 4 rows, equal-sized cells,
same full-body design, head size and baseline throughout, every hand and skirt
fully contained in its cell. Poses in row order: idle, reading, thinking,
explaining, speaking, happy, surprised, tea, working with book, signature pipe,
gentle stretch, sleepy. Each is a newly drawn illustration, not crops or edits
of the reference. Target at least 1536x2048. No text, cell borders, or watermark.
Only write generated images and reports inside {folder}; do not modify app code,
configuration, originals, audio, or existing assets. If image generation is not
available report that honestly. Use invoke_subagent image-generator; do not draw
substitute characters with Python/SVG. Wait for your existing image jobs and copy
their real saved files into the target folder before reporting completion."""
    if retry:
        prompt = f"""Use the image-generator subagent for a corrected NEW Beatrice sprite sheet.
The user's exact canonical reference is {reference}. The accepted new full-body
illustration is {folder / 'beatrice_fullbody.png'}: keep that exact dress, face,
pipe, proportions, and art quality. Previous sheet was rejected: its white
background and chopped skirt hems in top two rows do not meet requirements.
Generate ONLY {folder / 'beatrice_poses_v2.png'}. Do not alter existing files.
Canvas 1536x2048, 3 columns x 4 rows, each cell 512x512. Twelve newly illustrated
FULL LENGTH figures, scaled DOWN within cells: head at y=40 and skirt hem y=460
relative to each cell. Keep entire gown, hands and props inside 40px cell margin.
Flat saturated magenta #ff00ff everywhere outside figures, NO white background.
Poses row order: idle; reading; thinking; explaining; speaking; happy; surprised;
tea; working with book; signature pipe; gentle stretch; sleepy. Canonical dark
gothic gold-embroidered gown, layered maroon underskirt, white pleated cuffs,
pink bow, blonde updo dark rose. No text, borders or watermark. Every pose must
show the complete bottom hem of the skirt. Wait for existing image-generator
job to complete and copy actual output to requested path. Only modify files in
{folder}. Do not use Python/SVG substitute artwork or crop the reference."""
    outputs = ("beatrice_poses_v2.png",) if retry else ("beatrice_fullbody.png", "beatrice_poses.png")
    reply = run_agy(resolve_binary("agy", "agy"), "gemini-3.8-flash-high", "low",
                    prompt, [str(reference),str(folder / "beatrice_fullbody.png")] if retry else [str(reference)], ROOT, True, 900, threading.Event(),
                    lambda s: print(s, flush=True), lambda s: None,
                    keep_alive=lambda: all((folder / n).is_file() for n in outputs))
    (folder / ("retry_report.txt" if retry else "report.txt")).write_text(reply.text + "\n" + reply.log, encoding="utf-8")
    print(reply.text)


if __name__ == "__main__":
    main()
