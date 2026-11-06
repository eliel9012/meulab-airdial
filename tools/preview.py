"""Create an approximate desktop preview from a saved aircraft.json feed."""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[2])
data = json.loads(Path(sys.argv[1]).read_text())
planes = sorted(
    (p for p in data["aircraft"] if p.get("seen", 999) < 60),
    key=lambda p: p.get("r_dst", 1e9),
)
selected = planes[0] if planes else {}
im = Image.open(ROOT / "assets/map_franca.png").convert("RGB")
d = ImageDraw.Draw(im)
font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
bold_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
small = ImageFont.truetype(font_path, 9)
medium = ImageFont.truetype(font_path, 11)
large = ImageFont.truetype(bold_path, 18)
navy, cyan, coral, muted = "#061522", "#38D6D0", "#FF775D", "#8FAABD"
for radius in (30, 60, 96, 117):
    d.ellipse((120-radius, 120-radius, 120+radius, 120+radius), outline="#1B536D")
d.line((27, 120, 213, 120), fill="#17455C")
d.line((120, 38, 120, 202), fill="#17455C")
d.ellipse((117, 117, 123, 123), fill="white")
for name, x, y, tx, ty in (("SIMK", 120, 120, 136, 128), ("UBERABA", 102, 93, 71, 85), ("RIB. PRETO", 106, 144, 126, 150)):
    d.ellipse((x-2,y-2,x+2,y+2), fill=muted)
    d.text((tx, ty), name, font=small, fill=muted)
for p in planes:
    dist, bearing = p.get("r_dst", 1e9), p.get("r_dir")
    if dist > 160 or bearing is None:
        continue
    a = math.radians(bearing)
    x, y = 120+math.sin(a)*dist*.6, 120-math.cos(a)*dist*.6
    active = p is selected
    heading = math.radians(p.get("track", bearing))
    dx, dy = math.sin(heading), -math.cos(heading)
    sx, sy = -dy, dx
    length = 7 if active else 5
    points = [(x+dx*length,y+dy*length),(x-dx*length*.6+sx*length*.55,y-dy*length*.6+sy*length*.55),(x-dx*length*.6-sx*length*.55,y-dy*length*.6-sy*length*.55)]
    if active: d.ellipse((x-10,y-10,x+10,y+10), outline=coral)
    d.polygon(points, fill=coral if active else cyan)
d.rounded_rectangle((43,15,197,52), radius=9, fill=navy, outline="#274455")
d.text((120,26), "MEULAB RADAR / SIMK", font=medium, fill="white", anchor="mm")
d.ellipse((180,24,186,30), fill=cyan)
d.text((120,42), f"{len(planes)} VOOS / 160 NM", font=small, fill=cyan, anchor="mm")
d.rounded_rectangle((28,170,212,223), radius=12, fill=navy, outline=cyan)
call=(selected.get("flight") or selected.get("hex") or "--").strip()
d.text((120,182), call[:10], font=large, fill=coral, anchor="mm")
meta=f"{selected.get('t','--')} / {selected.get('r_dst',0):.1f} NM"
d.text((120,198),meta,font=medium,fill="white",anchor="mm")
values=f"{selected.get('alt_baro','--')} FT     {selected.get('gs',0):.0f} KT"
d.text((120,212),values,font=small,fill=muted,anchor="mm")
im.resize((960,960),Image.Resampling.NEAREST).save(OUT)
print(OUT)
