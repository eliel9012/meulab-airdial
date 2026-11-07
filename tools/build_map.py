"""Render dark 240px Franca basemaps (one per radar range) from Overpass extracts.

Usage:
  python tools/build_map.py fetch  [--cache DIR] [--levels 160,80,40,20] [--force]
  python tools/build_map.py render [--cache DIR] [--levels ...]   # PNGs + include/map_layers.h
  python tools/build_map.py header                                # map_layers.h from assets/map_<n>.png
Ranges are 160/80/40/20 NM; the 96 px radar radius equals the range, so px_per_nm = 96 / range.
Data: (c) OpenStreetMap contributors, ODbL. See https://www.openstreetmap.org/copyright
"""
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = 240
SCALE = 3
LAT = -20.512504
LON = -47.400830
RADIUS_PX = 96
MARGIN_PX = 24  # extra bbox around the 240 px square so lines enter from off-screen
ROOT = Path(__file__).resolve().parents[1]
LAYERS_HEADER = ROOT / "include" / "map_layers.h"
DEFAULT_CACHE = Path("/private/tmp/claude-501/-Users-eliel/b0ba4f55-55f0-4852-bd78-e6ff244e86c3/scratchpad")
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
LEVELS = [160, 80, 40, 20]
HIGHWAYS = {
    160: ["motorway", "trunk", "primary"],
    80: ["motorway", "trunk", "primary", "secondary"],
    40: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential"],  # residential = town texture
    20: ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"],
}
# Per level: (highway, colour, width in output px), drawn in order (minor first).
# *_link ways are drawn with their parent style.
STYLES = {
    160: [
        ("primary", (17, 48, 68), 1),
        ("trunk", (25, 65, 87), 2),
        ("motorway", (31, 75, 100), 2),
    ],
    80: [
        ("secondary", (14, 40, 60), 1),
        ("primary", (17, 48, 68), 1),
        ("trunk", (25, 65, 87), 2),
        ("motorway", (31, 75, 100), 2),
    ],
    40: [
        ("residential", (26, 64, 88), 0.34),
        ("tertiary", (12, 36, 54), 1),
        ("secondary", (14, 40, 59), 1),
        ("primary", (19, 52, 73), 1.5),
        ("trunk", (25, 65, 87), 2),
        ("motorway", (31, 75, 100), 2),
    ],
    20: [
        ("residential", (28, 70, 96), 0.67),
        ("unclassified", (13, 38, 56), 0.67),
        ("tertiary", (12, 35, 53), 1),
        ("secondary", (15, 43, 62), 1.33),
        ("primary", (19, 52, 73), 1.67),
        ("trunk", (25, 65, 87), 2),
        ("motorway", (31, 75, 100), 2.33),
    ],
}


def px_per_nm(level):
    return RADIUS_PX / level


def bbox(level):
    """(south, west, north, east) covering the 240 px square plus margin."""
    half = SIZE / 2 + MARGIN_PX
    ppn = px_per_nm(level)
    dlat = half / (60.0 * ppn)
    dlon = half / (56.2 * ppn)
    return LAT - dlat, LON - dlon, LAT + dlat, LON + dlon


def cache_file(cache, level):
    return Path(cache) / f"overpass_{level}.json"


def overpass_query(level):
    s, w, n, e = bbox(level)
    names = "|".join(HIGHWAYS[level])
    return (
        "[out:json][timeout:180];"
        f'way["highway"~"^({names})(_link)?$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});'
        "out geom;"
    )


def fetch(cache, levels, force=False):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    for level in levels:
        out = cache_file(cache, level)
        if out.exists() and not force:
            print(f"{level}: cached {out}")
            continue
        data = urllib.parse.urlencode({"data": overpass_query(level)}).encode()
        body = None
        for attempt in range(8):
            endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
            try:
                req = urllib.request.Request(endpoint, data=data, headers={"User-Agent": "meulab-airdial build_map.py"})
                with urllib.request.urlopen(req, timeout=240) as resp:
                    body = resp.read()
                json.loads(body)  # validate
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
                wait = min(120, 10 * 2 ** attempt)
                print(f"{level}: {endpoint} failed ({err}); retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
        if body is None:
            sys.exit(f"{level}: Overpass fetch failed")
        out.write_bytes(body)
        print(f"{level}: {len(json.loads(body)['elements'])} ways -> {out} ({len(body)} bytes)")
        time.sleep(5)  # be polite between sequential queries


def background(n):
    bg = Image.new("RGB", (n, n))
    pixels = bg.load()
    for y in range(n):
        for x in range(n):
            radius = math.hypot(x - n / 2, y - n / 2) / (n / 2)
            glow = max(0, 1 - radius)
            pixels[x, y] = (5, int(17 + glow * 10), int(30 + glow * 18))
    return bg


def render_level(elements, level):
    n = SIZE * SCALE
    ppn = px_per_nm(level)

    def project(point):
        x = 120 + (point["lon"] - LON) * 56.2 * ppn
        y = 120 - (point["lat"] - LAT) * 60.0 * ppn
        return round(x * SCALE), round(y * SCALE)

    road = Image.new("RGB", (n, n), (0, 0, 0))
    draw = ImageDraw.Draw(road)
    counts = {}
    for highway, color, width in STYLES[level]:
        for element in elements:
            tag = element.get("tags", {}).get("highway", "")
            if tag != highway and tag != highway + "_link":
                continue
            geometry = element.get("geometry")
            if geometry and len(geometry) > 1:
                draw.line([project(p) for p in geometry], fill=color, width=max(1, round(width * SCALE)), joint="curve")
                counts[highway] = counts.get(highway, 0) + 1
    mask = road.convert("L").point(lambda value: min(255, value * 4))
    glow = road.filter(ImageFilter.GaussianBlur(6 * SCALE))
    bg = Image.blend(background(n), glow, 0.11)
    bg.paste(road, (0, 0), mask)
    return bg.resize((SIZE, SIZE), Image.Resampling.LANCZOS), counts


def rgb565_values(png_path):
    im = Image.open(png_path).convert("RGB")
    if im.size != (SIZE, SIZE):
        raise ValueError(f"{png_path} is {im.size}, expected {SIZE}x{SIZE}")
    return [((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b in zip(*[iter(im.tobytes())] * 3)]


def array_lines(name, values):
    lines = [f"const uint16_t {name}[{SIZE} * {SIZE}] PROGMEM = {{"]
    for i in range(0, len(values), 12):
        lines.append("  " + ", ".join(f"0x{v:04X}" for v in values[i:i + 12]) + ",")
    lines.append("};")
    return lines


HEADER_PREAMBLE = [
    "#pragma once",
    "#include <stdint.h>",
    "// Generated by tools/build_map.py. Map data (c) OpenStreetMap contributors, ODbL.",
]


# ---------------------------------------------------------------- static overlay
# Range rings, ring labels, towns and home are baked into the firmware maps so the
# device does not redraw ~80 halo'd text passes every frame. Mirrors the firmware
# layout (src/main.cpp drawRadar); keep PLACES in sync with what you want labelled.
PLACES = [  # name, lat, lon, airport, labelled at this range (NM) or closer
    ("SIMK", -20.5922, -47.3829, True, 20),
    ("UBERABA", -19.7472, -47.9381, False, 160),
    ("RIB. PRETO", -21.1775, -47.8103, False, 160),
    ("BATATAIS", -20.8911, -47.5850, False, 80),
    ("IBIRACI", -20.4611, -47.1219, False, 40),
    ("PATROCINIO", -20.6394, -47.2817, False, 40),
    ("CRISTAIS", -20.4033, -47.4200, False, 20),
]


def rgb(c565):
    r, g, b = c565 >> 11, (c565 >> 5) & 63, c565 & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


GRID, MUTED, WHITE, BG_RGB = rgb(0x1A6B), rgb(0x9473), rgb(0xF7BE), rgb(0x0864)


def overlay(img, level):
    sys.path.insert(0, str(ROOT / "tools"))
    import build_fonts  # noqa: E402  (our own module, same folder)
    name, ttf, size, gamma, gain = build_fonts.FONTS[3][:5]
    assert name == "SERIF_13"
    font = build_fonts.decode_vlw(build_fonts.build_vlw(ttf, size, gamma, gain, False)[0])
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    for r in (96, 48, 24):
        draw.ellipse((120 - r, 120 - r, 120 + r, 120 + r), outline=GRID)
    draw.line((24, 120, 215, 120), fill=GRID)
    draw.line((120, 24, 120, 215), fill=GRID)

    def text(s, x, y, color, datum):
        w, h = build_fonts.text_width(font, s), font["height"]
        dx = {"c": -w // 2, "l": 0, "r": -w}[datum[1]]
        dy = {"m": -h // 2, "t": 0, "b": -h}[datum[0]]
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                if ox or oy:
                    build_fonts.draw_text(img, x + dx + ox, y + dy + oy, s, font, BG_RGB)
        build_fonts.draw_text(img, x + dx, y + dy, s, font, color)

    nm = lambda v: str(round(v))  # noqa: E731
    text(nm(level / 4), 144, 115, MUTED, "bc")
    text(nm(level / 2), 168, 115, MUTED, "bc")
    text(nm(level) + " NM", 26, 115, MUTED, "bl")
    ppn = px_per_nm(level)
    for pname, lat, lon, airport, max_range in PLACES:
        if level > max_range:
            continue
        x = 120 + round((lon - LON) * 56.2 * ppn)
        y = 120 - round((lat - LAT) * 60.0 * ppn)
        if (x - 120) ** 2 + (y - 120) ** 2 > 100 ** 2:
            continue
        if airport:
            draw.rectangle((x - 2, y - 2, x + 2, y + 2), outline=MUTED)
        else:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=MUTED)
        text(pname, x, y + 9, MUTED, "mc")
    draw.ellipse((117, 117, 123, 123), fill=WHITE)
    text("FRANCA", 114, 129, WHITE, "tr")
    return img


def write_layers_header(levels=LEVELS):
    lines = list(HEADER_PREAMBLE) + ["#ifndef PROGMEM", "#define PROGMEM", "#endif"]
    for level in levels:
        baked = overlay(Image.open(ROOT / "assets" / f"map_{level}.png"), level)
        out = ROOT / "assets" / f"map_{level}_baked.png"
        baked.save(out, optimize=True)
        lines += array_lines(f"MAP_RGB565_{level}", rgb565_values(out))
    LAYERS_HEADER.parent.mkdir(parents=True, exist_ok=True)
    LAYERS_HEADER.write_text("\n".join(lines) + "\n")
    print(LAYERS_HEADER, LAYERS_HEADER.stat().st_size, "bytes")


def render(cache, levels):
    for level in levels:
        src = cache_file(cache, level)
        if not src.exists():
            sys.exit(f"missing {src}; run: python tools/build_map.py fetch --cache {cache}")
        elements = json.loads(src.read_text())["elements"]
        image, counts = render_level(elements, level)
        out = ROOT / "assets" / f"map_{level}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        image.save(out, optimize=True)
        print(f"{level}: {out} {out.stat().st_size} bytes, ways drawn {counts}")
    write_layers_header(LEVELS)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fetch", "render", "header"])
    parser.add_argument("cache_dir", nargs="?", help="cache dir (same as --cache)")
    parser.add_argument("--cache", default=None)
    parser.add_argument("--levels", default=",".join(map(str, LEVELS)))
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()
    cache = Path(args.cache or args.cache_dir or DEFAULT_CACHE)
    levels = [int(v) for v in args.levels.split(",")]
    for level in levels:
        if level not in HIGHWAYS:
            sys.exit(f"unknown level {level}; choose from {LEVELS}")
    if args.command == "fetch":
        fetch(cache, levels, args.force)
    elif args.command == "render":
        render(cache, levels)
    else:
        write_layers_header(LEVELS)


if __name__ == "__main__":
    main()
