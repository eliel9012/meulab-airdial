"""Apply the round-display mask to simulator PNGs and tile them into sheets."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

src = Path(sys.argv[1])
scale, cols = 2, int(sys.argv[2]) if len(sys.argv) > 2 else 3
files = sorted(src.glob("[0-9]*.png"))
mask = Image.new("L", (240, 240), 0)
ImageDraw.Draw(mask).ellipse((0, 0, 239, 239), fill=255)
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
cell = 240 * scale
for page in range(0, len(files), cols * 2):
    chunk = files[page:page + cols * 2]
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell + 20) + 20, rows * (cell + 50) + 10), "#222")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(chunk):
        im = Image.composite(Image.open(f).convert("RGB"), Image.new("RGB", (240, 240)), mask)
        x, y = 20 + (i % cols) * (cell + 20), 40 + (i // cols) * (cell + 50)
        sheet.paste(im.resize((cell, cell), Image.Resampling.NEAREST), (x, y))
        d.text((x, y - 28), f.stem, font=font, fill="#ddd")
    out = src / f"sheet_{page // (cols * 2) + 1}.png"
    sheet.save(out)
    print(out)
