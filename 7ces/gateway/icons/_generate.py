"""Generate the PWA icons (192/512). Build-time only — run once with Pillow installed:
   pip install pillow && python icons/_generate.py
The PNGs it writes are committed; the gateway just serves them statically."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
BG = (13, 17, 23)     # #0d1117
ACC = (46, 160, 67)   # #2ea043
FG = (230, 237, 243)  # #e6edf3


def _font(size: int):
    for fp in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(fp, int(size * 0.40))
        except Exception:
            continue
    return ImageFont.load_default()


def make(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    pad = int(size * 0.11)
    d.ellipse([pad, pad, size - pad, size - pad], outline=ACC, width=max(2, size // 28))
    text = "7C"
    font = _font(size)
    b = d.textbbox((0, 0), text, font=font)
    w, h = b[2] - b[0], b[3] - b[1]
    d.text(((size - w) / 2 - b[0], (size - h) / 2 - b[1]), text, fill=FG, font=font)
    return img


if __name__ == "__main__":
    for s in (192, 512):
        make(s).save(OUT / f"icon-{s}.png")
        print("wrote", OUT / f"icon-{s}.png")
