"""Export the actual companion portraits and placement guide for docs/preview/chat.html."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from character_profiles import PROFILES
from character_widget import FrierenSpriteWidget


def font(size, title=False):
    for face in (("georgia.ttf", "DejaVuSerif.ttf") if title else ("segoeui.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(face, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def main():
    app = QApplication.instance() or QApplication([])
    out = ROOT / "docs/preview"
    sheet = Image.new("RGB", (900, 434), "#f7f6ed")
    draw = ImageDraw.Draw(sheet)
    draw.text((26, 16), "ANIME DESK   /   STUDI POSISI", fill="#536459", font=font(14))
    draw.text((24, 42), "Satu bingkai untuk tiga pendamping", fill="#25382e", font=font(31, True))
    for index, profile in enumerate(PROFILES.values()):
        sprites, blinks = profile.assets(ROOT)
        avatar = FrierenSpriteWidget(sprites, motion_mode="off")
        avatar.set_sprites(sprites, blinks, profile.mouth_frames(ROOT), profile.portrait_frame)
        canvas = QPixmap(avatar.size())
        canvas.fill(Qt.GlobalColor.transparent)
        avatar.render(canvas, renderFlags=avatar.RenderFlag.DrawChildren)
        name = profile.id.split("_")[0]
        path = out / f"{name}.png"
        if not canvas.save(str(path)):
            raise RuntimeError(f"Cannot save {path}")
        x = 26 + index * 288
        draw.rounded_rectangle((x, 100, x + 270, 371), radius=14, fill=profile.colours["hover"])
        with Image.open(path) as portrait:
            portrait = portrait.convert("RGBA")
            sheet.paste(portrait, (x + 18, 119), portrait)
        for y in (178, 359):
            for dx in range(5, 268, 8):
                draw.line((x+dx, y, x+dx+3, y), fill="#a0a58e")
        draw.text((x, 377), profile.name, fill="#25382e", font=font(20, True))
    draw.text((26, 408), "Garis bantu: tinggi mata Frieren dan batas bawah potret pada skala 100%.", fill="#536459", font=font(13))
    sheet.save(out / "posisi.png")


if __name__ == "__main__":
    main()
