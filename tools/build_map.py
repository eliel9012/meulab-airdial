"""Render a dark 240px Franca basemap from an Overpass JSON extract.

Usage: python tools/build_map.py path/to/overpass.json
Data: © OpenStreetMap contributors, ODbL. See https://www.openstreetmap.org/copyright
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 240
SCALE = 3
LAT = -20.512504
LON = -47.400830
PX_PER_NM = 0.60  # 160 NM is 96 px


def project(point):
    x = 120 + (point["lon"] - LON) * 56.2 * PX_PER_NM
    y = 120 - (point["lat"] - LAT) * 60.0 * PX_PER_NM
    return round(x * SCALE), round(y * SCALE)


def main(source):
    elements = json.loads(Path(source).read_text())["elements"]
    n = SIZE * SCALE
    bg = Image.new("RGB", (n, n))
    pixels = bg.load()
    for y in range(n):
        for x in range(n):
            radius = math.hypot(x - n / 2, y - n / 2) / (n / 2)
            glow = max(0, 1 - radius)
            pixels[x, y] = (5, int(17 + glow * 10), int(30 + glow * 18))

    styles = [
        ("primary", (17, 48, 68), 1),
        ("trunk", (25, 65, 87), 2),
        ("motorway", (31, 75, 100), 2),
    ]
    road = Image.new("RGB", (n, n), (0, 0, 0))
    draw = ImageDraw.Draw(road)
    for highway, color, width in styles:
        for element in elements:
            if element.get("tags", {}).get("highway") != highway:
                continue
            geometry = element.get("geometry")
            if geometry and len(geometry) > 1:
                draw.line([project(p) for p in geometry], fill=color, width=width * SCALE, joint="curve")
    mask = road.convert("L").point(lambda value: min(255, value * 4))
    glow = road.filter(ImageFilter.GaussianBlur(6 * SCALE))
    bg = Image.blend(bg, glow, 0.11)
    bg.paste(road, (0, 0), mask)
    bg = bg.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    out = Path(__file__).resolve().parents[1] / "assets" / "map_franca.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.save(out, optimize=True)
    header = Path(__file__).resolve().parents[1] / "include" / "map_franca.h"
    data = out.read_bytes()
    rows = [", ".join(f"0x{byte:02x}" for byte in data[i:i + 16]) for i in range(0, len(data), 16)]
    header.write_text("#pragma once\n#include <stdint.h>\nconst uint8_t MAP_FRANCA_PNG[] PROGMEM = {\n  " + ",\n  ".join(rows) + "\n};\nconst uint32_t MAP_FRANCA_PNG_SIZE = sizeof(MAP_FRANCA_PNG);\n")
    print(out, len(data), "bytes")


if __name__ == "__main__":
    main(sys.argv[1])
