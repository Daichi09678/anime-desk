"""Prepare reproducible expression edits from user-provided reference artwork.

No reference file is overwritten. Facial edits are hand-tuned raster/vector
edits, not newly generated illustrations or animation frames.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "assets/sprites/references"
OUTPUT = ROOT / "assets/characters"
EXPRESSIONS = ("neutral", "happy", "talking", "thinking", "surprised", "sleepy")
LABELS = ("Netral", "Senang", "Berbicara", "Berpikir", "Terkejut", "Memejamkan mata")
SCALE = 3


def curve(points, steps=32):
    a, b, c, d = points
    return [((1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0],
             (1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1])
            for t in (i/steps for i in range(steps+1))]


def stroke(image, points, fill, width=1.2):
    ImageDraw.Draw(image).line([(round(x*SCALE), round(y*SCALE)) for x, y in curve(points)],
                               fill=fill, width=max(1, round(width*SCALE)), joint="curve")


def patch_skin(image, box, samples, polygon=None):
    """Small feathered, bilinear skin patch; keep edits away from face outlines."""
    x0, y0, x1, y1 = [round(v*SCALE) for v in box]
    colours = [image.getpixel((round(x*SCALE), round(y*SCALE)))[:3] for x, y in samples]
    patch = Image.new("RGB", (x1-x0, y1-y0))
    pixels = patch.load()
    for y in range(patch.height):
        fy = y/max(1, patch.height-1)
        for x in range(patch.width):
            fx = x/max(1, patch.width-1)
            pixels[x, y] = tuple(round((1-fy)*((1-fx)*colours[0][c]+fx*colours[1][c]) +
                                      fy*((1-fx)*colours[2][c]+fx*colours[3][c])) for c in range(3))
    mask = Image.new("L", patch.size, 0)
    draw = ImageDraw.Draw(mask)
    if polygon:
        draw.polygon([(round(x*SCALE)-x0, round(y*SCALE)-y0) for x, y in polygon], fill=255)
    else:
        draw.ellipse((2, 2, patch.width-3, patch.height-3), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.45*SCALE))
    image.paste(patch, (x0, y0), mask)


def close_eyes(image, name):
    if name == "beatrice":
        patch_skin(image, (243, 107, 284, 134), [(282,113),(284,114),(280,130),(284,129)],
                   [(245,109),(278,110),(282,122),(276,132),(246,129),(243,119)])
        patch_skin(image, (295, 97, 341, 127), [(294,125),(330,126),(300,128),(330,127)],
                   [(298,104),(334,98),(340,103),(337,118),(322,126),(298,122)])
        stroke(image, [(247,118),(255,126),(269,127),(279,119)], "#493329", 1.7)
        stroke(image, [(300,108),(311,116),(326,112),(336,104)], "#493329", 1.8)
    else:
        patch_skin(image, (332, 491, 361, 517), [(342,516),(360,516),(343,520),(360,520)],
                   [(336,493),(353,493),(358,499),(359,508),(349,514),(336,511),(333,504)])
        patch_skin(image, (379, 490, 408, 516), [(382,516),(400,515),(382,520),(400,520)],
                   [(383,493),(399,491),(405,498),(405,509),(394,514),(382,510),(380,502)])
        stroke(image, [(335,501),(341,507),(352,509),(358,501)], "#39313a", 1.8)
        stroke(image, [(382,500),(389,507),(399,506),(405,499)], "#39313a", 1.8)


def edit_expression(source, name, expression, blink=False):
    image = source.convert("RGB").resize((source.width*SCALE, source.height*SCALE), Image.Resampling.LANCZOS)
    if name == "beatrice":
        centre = (303, 155)
        if expression != "talking":
            patch_skin(image, (286, 145, 322, 166), [(284,145),(324,144),(296,165),(318,163)])
    else:
        centre = (370, 531)
        if expression != "talking":
            patch_skin(image, (351, 522, 389, 543), [(348,522),(391,522),(354,543),(388,543)])
    x, y = centre
    ink = "#78504b" if name == "beatrice" else "#75494f"
    if expression in ("neutral", "sleepy"):
        stroke(image, [(x-6,y),(x-2,y+2),(x+3,y+2),(x+6,y-1)], ink)
    elif expression == "thinking":
        stroke(image, [(x-5,y+1),(x-2,y-1),(x+2,y),(x+5,y)], ink)
    elif expression == "happy":
        stroke(image, [(x-9,y-2),(x-5,y+7),(x+5,y+7),(x+10,y-3)], ink, 1.5)
        # A soft lower-lip highlight gives a different smile without changing pose.
        stroke(image, [(x-3,y+5),(x,y+6),(x+3,y+6),(x+5,y+4)], "#d59091", 0.8)
    elif expression == "surprised":
        ImageDraw.Draw(image).ellipse(tuple(round(v*SCALE) for v in (x-3.8,y-4,x+3.8,y+5.5)), fill="#75404c", outline=ink, width=2)
        ImageDraw.Draw(image).ellipse(tuple(round(v*SCALE) for v in (x-2.5,y+1,x+2.5,y+4.5)), fill="#c77c83")
    if blink or expression == "sleepy":
        close_eyes(image, name)
    return image.resize(source.size, Image.Resampling.LANCZOS).convert("RGBA")


def white_background_alpha(source):
    rgb = source.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    visited = bytearray(width*height)
    pending = deque()
    for x in range(width):
        pending.extend(((x,0),(x,height-1)))
    for y in range(height):
        pending.extend(((0,y),(width-1,y)))
    while pending:
        x,y = pending.popleft()
        index = y*width+x
        if visited[index]:
            continue
        visited[index] = 1
        colour = pixels[x,y]
        if min(colour) < 238 or max(colour)-min(colour) > 18:
            continue
        visited[index] = 2
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= nx < width and 0 <= ny < height and not visited[ny*width+nx]:
                pending.append((nx,ny))
    return Image.frombytes("L", rgb.size, bytes(0 if v == 2 else 255 for v in visited))


def portrait_alpha(source, name):
    if name == "beatrice":
        return white_background_alpha(source).filter(ImageFilter.MinFilter(3)), (170,0,470,340)
    mask = Image.new("L", source.size, 0)
    # Trace the supplied collage's lower-right portrait, excluding the nearby
    # central full-body figure and the unrelated wave/background to its right.
    outline = [(313,451),(423,451),(422,487),
               (422,501),(430,515),(432,528),(425,539),(416,546),(411,554),
               (415,567),(430,579),(321,579),(330,565),(329,554),(317,546),
               (309,535),(303,525),(306,513),(304,500),(310,487),(311,473),
               (320,460),(330,453)]
    ImageDraw.Draw(mask).polygon(outline, fill=255)
    cap = Image.new("L", source.size, 0)
    ImageDraw.Draw(cap).ellipse((313,428,423,482), fill=255)
    # The collage cuts through the crown. Extend only this small missing hair
    # cap using existing hair texture, rather than leaving a flat cut edge.
    ImageDraw.Draw(cap).rectangle((0,455,source.width,source.height), fill=0)
    from PIL import ImageChops
    mask = ImageChops.lighter(mask, cap)
    return mask.filter(ImageFilter.GaussianBlur(0.6)), (299,425,440,580)


def place_portrait(image, mask, crop):
    image.putalpha(mask)
    portrait = image.crop(crop)
    # One shared crop/scale for every expression: no face or body jumps.
    scale = min(352/portrait.width, 416/portrait.height)
    portrait = portrait.resize((round(portrait.width*scale), round(portrait.height*scale)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (384,448))
    canvas.alpha_composite(portrait, ((384-portrait.width)//2, 448-16-portrait.height))
    return canvas


def font(size):
    try:
        return ImageFont.truetype("segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def build():
    paths = {"beatrice": REFERENCES / "beatrice/image copy.png", "waguri_kaoruko": REFERENCES / "waguri/image.png"}
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()}
    sheets = []
    for name, path in paths.items():
        source = Image.open(path).convert("RGBA")
        mask, crop = portrait_alpha(source, name)
        folder = OUTPUT / name / "expressions"
        folder.mkdir(parents=True, exist_ok=True)
        sheet = Image.new("RGB", (1056,1000), "#191b26")
        draw = ImageDraw.Draw(sheet)
        draw.text((24,12), "Beatrice" if name == "beatrice" else "Waguri Kaoruko", fill="#f7ead4", font=font(28))
        for index, (expression, label) in enumerate(zip(EXPRESSIONS, LABELS)):
            for blink in (False, True):
                edited = edit_expression(source, name, expression, blink)
                if name == "waguri_kaoruko":
                    texture = source.crop((332,453,411,460)).resize((110,45), Image.Resampling.BICUBIC)
                    texture = ImageEnhance.Brightness(texture).enhance(0.8).filter(ImageFilter.GaussianBlur(0.5))
                    feather = Image.new("L",texture.size)
                    feather_draw = ImageDraw.Draw(feather)
                    for row in range(texture.height):
                        opacity = 255 if row < 22 else round(255 * max(0,1-(row-22)/22))
                        feather_draw.line((0,row,texture.width,row),fill=opacity)
                    edited.paste(texture,(313,428),feather)
                portrait = place_portrait(edited, mask, crop)
                portrait.save(folder / f"{expression}{'_blink' if blink else ''}.png", optimize=True)
            thumb = portrait.copy()
            # Preview the open-eye version except for the intentionally closed pose.
            thumb = Image.open(folder / f"{expression}.png").convert("RGBA")
            thumb.thumbnail((310,380), Image.Resampling.LANCZOS)
            x, y = (index%3)*352+20, (index//3)*470+66
            draw.rounded_rectangle((x,y,x+312,y+388), radius=16, fill="#2a2e3c", outline="#474c61", width=1)
            sheet.paste(thumb, (x+(312-thumb.width)//2,y+388-thumb.height), thumb)
            draw.text((x+12,y+402), label, fill="#f1f3f8", font=font(20))
        sheet.save(OUTPUT / name / "preview.png", optimize=True)
        metadata = {"name": "Beatrice" if name == "beatrice" else "Waguri Kaoruko",
                    "source": str(path.relative_to(ROOT)).replace("\\", "/"), "size": [384,448],
                    "expressions": list(EXPRESSIONS), "method": "reference-based portrait crop and local facial edits",
                    "notes": "Initial 2D portrait assets; body/face anchors are identical across expressions. No new full-body poses are implied."}
        (OUTPUT / name / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        sheets.append(sheet)
    combined = Image.new("RGB", (2112,1000), "#191b26")
    for index, sheet in enumerate(sheets):
        combined.paste(sheet, (1056*index,0))
    combined.save(OUTPUT / "expressions_preview.png", optimize=True)
    closed = Image.open(ROOT / "assets/sprites/pleased.png").convert("RGBA")
    blink_mask = Image.new("L", closed.size, 0)
    eye_draw = ImageDraw.Draw(blink_mask)
    eye_draw.ellipse((177,115,215,143), fill=255)
    eye_draw.ellipse((231,111,274,140), fill=255)
    blink_mask = blink_mask.filter(ImageFilter.GaussianBlur(0.8))
    frieren_folder = OUTPUT / "frieren/blink"
    frieren_folder.mkdir(parents=True, exist_ok=True)
    for state in ("idle", "idle_cozy", "thinking", "thinking_hmmm", "talking", "talking_explain"):
        base = Image.open(ROOT / "assets/sprites" / f"{state}.png").convert("RGBA")
        if base.size == closed.size:
            base.paste(closed, (0,0), blink_mask)
            base.save(frieren_folder / f"{state}.png", optimize=True)
    for path, digest in originals.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"Reference changed: {path}"
    print("Built 6 expressions + 6 blink frames per character; references preserved.")


def inspect_references(folder):
    folder.mkdir(parents=True, exist_ok=True)
    sources = {
        "beatrice": (REFERENCES / "beatrice/image copy.png", (210, 65, 365, 195)),
        "waguri": (REFERENCES / "waguri/image.png", (245, 448, 495, 580)),
        "waguri-single": (REFERENCES / "waguri/image copy.png", (110, 15, 195, 95)),
        "waguri-happy": (REFERENCES / "waguri/image.png", (305, 90, 410, 170)),
        "waguri-excited": (REFERENCES / "waguri/image.png", (65, 90, 170, 175)),
        "waguri-top": (REFERENCES / "waguri/image.png", (315, 420, 435, 480)),
    }
    for name, (path, crop) in sources.items():
        image = Image.open(path).convert("RGBA")
        face = image.crop(crop).resize(((crop[2] - crop[0]) * 4, (crop[3] - crop[1]) * 4))
        draw = ImageDraw.Draw(face)
        for x in range(crop[0], crop[2], 10):
            px = (x - crop[0]) * 4
            draw.line((px, 0, px, face.height), fill=(255, 0, 0, 100), width=1)
            draw.text((px + 1, 0), str(x), fill="red")
        for y in range(crop[1], crop[3], 10):
            py = (y - crop[1]) * 4
            draw.line((0, py, face.width, py), fill=(255, 0, 0, 100), width=1)
            draw.text((1, py), str(y), fill="red")
        face.convert("RGB").save(folder / f"{name}-face-grid.png")
        if name == "beatrice":
            for left, right in ((230,285),(285,345)):
                blue = [(x,y) for y in range(95,135) for x in range(left,right)
                        if image.getpixel((x,y))[2] > image.getpixel((x,y))[0]+12
                        and image.getpixel((x,y))[2] > image.getpixel((x,y))[1]+2
                        and image.getpixel((x,y))[2] > 60]
                if blue:
                    print("Beatrice iris bounds:", (min(x for x,y in blue),min(y for x,y in blue),max(x for x,y in blue),max(y for x,y in blue)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", type=Path)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        inspect_references(args.inspect)
    if args.build:
        build()


if __name__ == "__main__":
    main()
