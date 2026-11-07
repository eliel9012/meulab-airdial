"""Build airline logo tiles (RGB565, pre-composited on the UI navy) for the M5Dial radar.

Usage:
  python3 -I tools/build_logos.py               # download missing logos + build header/previews
  python3 -I tools/build_logos.py --sample 6    # also sample the live feed (6x, 20 s apart) for prefixes
  python3 -I tools/build_logos.py --offline     # rebuild only from assets/logos/src (no network)
  python3 -I tools/build_logos.py --refresh     # re-download every logo

Outputs (all git-ignored: logos are trademarks of their owners, personal use only):
  assets/logos/src/<ICAO>.png       downloaded source logo
  assets/logos/out/{24,36}/<ICAO>.png  processed tiles
  assets/logos/preview.png          1x + 3x preview sheet on navy
  assets/logos/SOURCES.md           where each logo came from
  include/airline_logos.h           AIRLINES[] table (sorted by ICAO) + LOGO24_/LOGO36_ arrays

Sources (tried in order, keyed by ICAO code):
  https://github.com/Jxck-S/airline-logos  flightaware_logos/, radarbox_logos/
  https://github.com/sexym0nk3y/airline-logos  logos/
Neither repo has a licence; images belong to the airlines (fair-use identification only).
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = ROOT / "assets" / "logos"
SRC_DIR = LOGO_DIR / "src"
OUT_DIR = LOGO_DIR / "out"
HEADER = ROOT / "include" / "airline_logos.h"
MANIFEST = SRC_DIR / "manifest.json"
FEED_URL = "https://radar.meulab.fun/data/aircraft.json"

NAVY = (8, 12, 32)  # RGB565 0x0864 exactly (r=1, g=3, b=4)
WHITE = (255, 255, 255)
SIZES = (24, 36)
PAD = {24: 2, 36: 3}
SS = 8  # supersampling factor for tile + logo composition

SOURCES = [
    ("fa", "https://raw.githubusercontent.com/Jxck-S/airline-logos/main/flightaware_logos/{icao}.png"),
    ("rb", "https://raw.githubusercontent.com/Jxck-S/airline-logos/main/radarbox_logos/{icao}.png"),
    ("sx", "https://raw.githubusercontent.com/sexym0nk3y/airline-logos/main/logos/{icao}.png"),
]
SOURCE_NAMES = {
    "fa": "Jxck-S/airline-logos flightaware_logos/",
    "rb": "Jxck-S/airline-logos radarbox_logos/",
    "sx": "sexym0nk3y/airline-logos logos/",
}

# ICAO -> display name (uppercase, <= 12 chars, ASCII or PT Latin-1 letters ÁÂÃÇÉÊÍÓÔÕÚ).
AIRLINES = {
    # Brazil
    "GLO": "GOL", "AZU": "AZUL", "TAM": "LATAM", "PTB": "VOEPASS", "ACN": "AZUL CONECTA",
    "TTL": "TOTAL", "SID": "SIDERAL", "ABJ": "ABAETÉ", "MWM": "MODERN", "LTG": "LATAM CARGO",
    "OMI": "OMNI", "TOT": "TOTAL EXPR", "BPC": "BRASPRESS",
    # South / Central America
    "ARG": "AEROLÍNEAS", "FBZ": "FLYBONDI", "JES": "JETSMART", "JAT": "JETSMART",
    "LAN": "LATAM", "LPE": "LATAM", "LXP": "LATAM", "LNE": "LATAM", "ARE": "LATAM",
    "LAP": "LATAM", "LCO": "LATAM CARGO", "TPA": "AVIANCA CRG", "AVA": "AVIANCA",
    "CMP": "COPA", "BOV": "BOA", "SKU": "SKY", "AZN": "AMASZONAS", "VCV": "CONVIASA",
    "DWI": "ARAJET",
    # Long-haul to GRU / VCP / GIG
    "AAL": "AMERICAN", "UAL": "UNITED", "DAL": "DELTA", "ACA": "AIR CANADA",
    "AMX": "AEROMÉXICO", "AFR": "AIR FRANCE", "KLM": "KLM", "DLH": "LUFTHANSA",
    "IBE": "IBERIA", "AEA": "AIR EUROPA", "PUE": "PLUS ULTRA", "LVL": "LEVEL",
    "TAP": "TAP", "BAW": "BRITISH", "SWR": "SWISS", "ITY": "ITA", "THY": "TURKISH",
    "UAE": "EMIRATES", "QTR": "QATAR", "ETH": "ETHIOPIAN", "RAM": "ROYAL MAROC",
    "SAA": "S. AFRICAN", "DTA": "TAAG", "CCA": "AIR CHINA",
    # Cargo
    "FDX": "FEDEX", "UPS": "UPS", "DHK": "DHL", "BCS": "DHL", "CLX": "CARGOLUX",
    "GTI": "ATLAS", "CKS": "KALITTA", "KYE": "SKY LEASE", "WGN": "WESTERN GLB",
    "GEC": "LH CARGO", "MPH": "MARTINAIR", "TNO": "AEROUNION",
    "MAA": "MASAIR", "AJT": "AMERIJET", "ATN": "ATI",
}

# Per-logo tweaks found by looking at preview.png.
#   src:  force a source key ("fa", "rb", "sx")
#   tile: "white" | "navy" (default: auto by contrast against navy)
#   crop: (x0, y0, x1, y1) fractions of the alpha bbox to keep (e.g. emblem of a wordmark)
#   from: take the logo file of another ICAO code (same brand)
#   drop: True -> keep the name, no logo
OVERRIDES = {
    "BCS": {"src": "rb"},                      # yellow DHL square instead of thin wordmark
    "DHK": {"src": "rb", "from": "BCS"},
    "UAE": {"src": "sx", "tile": "white"},     # calligraphy emblem instead of wordmark
    "ITY": {"src": "rb", "tile": "white"},     # emblem instead of wordmark
    "CKS": {"src": "rb"},
    "ATN": {"src": "rb"},
    "AZN": {"src": "rb"},
    "RAM": {"src": "rb", "tile": "white"},
    "WGN": {"drop": True},                     # illegible at 24 px
    "BPC": {"drop": True},
    "LVL": {"drop": True},                     # source image is not the Level brand mark                     # thin wordmark, illegible
}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "meulab-airdial build_logos"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sample_feed(n, interval=20.0):
    seen = {}
    for i in range(n):
        try:
            data = json.loads(fetch(FEED_URL, 15))
            for a in data.get("aircraft", []):
                m = re.match(r"^([A-Z]{3})\d", (a.get("flight") or "").strip())
                if m:
                    seen[m.group(1)] = seen.get(m.group(1), 0) + 1
            print(f"sample {i + 1}/{n}: {sorted(seen)}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"sample {i + 1}/{n} failed: {e}", file=sys.stderr)
        if i + 1 < n:
            time.sleep(interval)
    return seen


def load_manifest():
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        return {}


def download(icaos, refresh):
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    for icao in icaos:
        dst = SRC_DIR / f"{icao}.png"
        ov = OVERRIDES.get(icao, {})
        if ov.get("drop"):
            continue
        forced = ov.get("src")
        src_icao = ov.get("from", icao)
        want = forced and (forced if src_icao == icao else f"{forced}:{src_icao}")
        if dst.exists() and not refresh and (not want or manifest.get(icao) == want):
            continue
        order = [s for s in SOURCES if s[0] == forced] if forced else SOURCES
        for key, tpl in order:
            try:
                blob = fetch(tpl.format(icao=src_icao))
            except (urllib.error.URLError, OSError):
                continue
            if not blob.startswith(b"\x89PNG"):
                continue
            dst.write_bytes(blob)
            manifest[icao] = key if src_icao == icao else f"{key}:{src_icao}"
            print(f"{icao}: {manifest[icao]}")
            break
        else:
            print(f"{icao}: no logo found", file=sys.stderr)
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def pixels(im):
    f = getattr(im, "get_flattened_data", None)
    return list(f() if f else im.getdata())


def luminance(rgb):
    def ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


NAVY_L = luminance(NAVY)


def low_contrast_fraction(im):
    """Alpha-weighted fraction of logo pixels with contrast ratio < 2.2 against navy."""
    small = im.copy()
    small.thumbnail((48, 48))
    tot = low = 0.0
    for r, g, b, a in pixels(small):
        if a < 16:
            continue
        w = a / 255.0
        tot += w
        if (luminance((r, g, b)) + 0.05) / (NAVY_L + 0.05) < 2.2:
            low += w
    return low / tot if tot else 1.0


def prepare(icao):
    im = Image.open(SRC_DIR / f"{icao}.png")
    im.load()
    im = im.convert("RGBA")
    # Flatten near-opaque white backgrounds of non-transparent sources into alpha.
    if im.getextrema()[3][0] == 255:
        px = im.load()
        w, h = im.size
        corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        if all(min(c[:3]) > 240 for c in corners):
            data = [(r, g, b, 0) if min(r, g, b) > 245 else (r, g, b, a) for r, g, b, a in pixels(im)]
            im.putdata(data)
    bbox = im.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    crop = OVERRIDES.get(icao, {}).get("crop")
    if crop:
        w, h = im.size
        im = im.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
        bbox = im.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox()
        if bbox:
            im = im.crop(bbox)
    return im


def make_tile(logo, size, tile):
    big = size * SS
    pad = PAD[size] * SS
    radius = round(big * 0.25)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=255)
    canvas = Image.new("RGB", (big, big), NAVY)
    if tile == "white":
        canvas.paste(Image.new("RGB", (big, big), WHITE), (0, 0), mask)
        inner = big - 2 * pad - 2 * SS  # a bit more breathing room inside a visible tile
    else:
        inner = big - 2 * pad
    lw, lh = logo.size
    s = inner / max(lw, lh)
    nw, nh = max(1, round(lw * s)), max(1, round(lh * s))
    lg = logo.resize((nw, nh), Image.LANCZOS)
    ox, oy = (big - nw) // 2, (big - nh) // 2
    if tile == "white":
        lmask = Image.new("L", (big, big), 0)
        lmask.paste(lg.getchannel("A"), (ox, oy))
        lmask = Image.composite(lmask, Image.new("L", (big, big), 0), mask)
        layer = Image.new("RGB", (big, big), NAVY)
        layer.paste(lg.convert("RGB"), (ox, oy))
        canvas = Image.composite(layer, canvas, lmask)
    else:
        canvas.paste(lg.convert("RGB"), (ox, oy), lg)
    out = canvas.resize((size, size), Image.LANCZOS)
    out = out.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))
    if tile == "white":
        small_mask = mask.resize((size, size), Image.LANCZOS)
        out.paste(Image.new("RGB", (size, size), NAVY), (0, 0), small_mask.point(lambda a: 255 if a == 0 else 0))
    else:
        # sharpening may tint pure-navy background pixels; snap near-navy back to exact navy
        px = out.load()
        for y in range(size):
            for x in range(size):
                if all(abs(px[x, y][i] - NAVY[i]) <= 4 for i in range(3)):
                    px[x, y] = NAVY
    return out


def rgb565(c):
    r, g, b = c
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def emit_array(name, im):
    vals = [rgb565(p) for p in pixels(im)]
    w = im.size[0]
    lines = []
    for y in range(im.size[1]):
        lines.append("  " + ",".join(f"0x{v:04X}" for v in vals[y * w:(y + 1) * w]) + ",")
    return f"const uint16_t {name}[{w} * {w}] PROGMEM = {{\n" + "\n".join(lines) + "\n};\n"


def c_string(s):
    """UTF-8 C literal, non-ASCII bytes as hex escapes (split so following hex digits don't merge)."""
    out = []
    for b in s.encode("utf-8"):
        out.append(chr(b) if b < 128 else f'\\x{b:02X}""')
    return '"' + "".join(out) + '"'


def check_name(icao, name):
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -.&'ÁÂÃÇÉÊÍÓÔÕÚ")
    if len(name) > 12 or not set(name) <= allowed:
        raise SystemExit(f"bad display name for {icao}: {name!r}")


def preview(tiles, path):
    font = ImageFont.load_default()
    cols = 10
    cell_w, cell_h = 36 * 3 + 16, 4 + 36 + 4 + 108 + 4 + 72 + 18
    items = sorted(tiles)
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), NAVY)
    d = ImageDraw.Draw(sheet)
    for i, icao in enumerate(items):
        x0, y0 = (i % cols) * cell_w + 8, (i // cols) * cell_h + 4
        t24, t36 = tiles[icao]
        if t24 is None:
            d.text((x0, y0 + 40), "no logo", fill=(200, 80, 80), font=font)
        else:
            sheet.paste(t24, (x0, y0))
            sheet.paste(t36, (x0 + 30, y0))
            sheet.paste(t36.resize((108, 108), Image.NEAREST), (x0, y0 + 40))
            sheet.paste(t24.resize((72, 72), Image.NEAREST), (x0, y0 + 152))
        d.text((x0 + 80, y0 + 152), AIRLINES[icao][:9].encode("ascii", "replace").decode(), fill=(150, 150, 170), font=font)
        d.text((x0 + 80, y0 + 212), icao, fill=(230, 230, 230), font=font)
    sheet.save(path)


def write_sources(manifest, icaos):
    lines = [
        "# Airline logo sources",
        "",
        "Generated by `tools/build_logos.py`. Not committed (git-ignored).",
        "",
        "- Jxck-S/airline-logos — https://github.com/Jxck-S/airline-logos (flightaware_logos/, radarbox_logos/).",
        "  No licence file; README states images belong to their owners, provided for identification under fair use.",
        "- sexym0nk3y/airline-logos — https://github.com/sexym0nk3y/airline-logos (logos/). No licence file.",
        "",
        "All logos are trademarks of their respective airlines. Personal, non-commercial use only; do not redistribute.",
        "",
        "| ICAO | Name | Source |",
        "|---|---|---|",
    ]
    for icao in icaos:
        key, _, other = (manifest.get(icao) or "").partition(":")
        src = SOURCE_NAMES.get(key, "none") + (f" ({other}.png)" if other else "")
        src = src if (SRC_DIR / f"{icao}.png").exists() else "none"
        if OVERRIDES.get(icao, {}).get("drop"):
            src += " (dropped)"
        lines.append(f"| {icao} | {AIRLINES[icao]} | {src} |")
    (LOGO_DIR / "SOURCES.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=0, help="sample the live feed N times (20 s apart)")
    ap.add_argument("--offline", action="store_true", help="no network; rebuild from assets/logos/src")
    ap.add_argument("--refresh", action="store_true", help="re-download all logos")
    args = ap.parse_args()

    if args.sample and not args.offline:
        for icao in sorted(sample_feed(args.sample)):
            if icao not in AIRLINES:
                print(f"feed prefix {icao} not in AIRLINES; add it with a display name", file=sys.stderr)
                AIRLINES[icao] = icao

    for icao, name in AIRLINES.items():
        check_name(icao, name)
    icaos = sorted(AIRLINES)
    manifest = load_manifest() if args.offline else download(icaos, args.refresh)

    tiles = {}
    for d in SIZES:
        (OUT_DIR / str(d)).mkdir(parents=True, exist_ok=True)
    for icao in icaos:
        ov = OVERRIDES.get(icao, {})
        if ov.get("drop") or not (SRC_DIR / f"{icao}.png").exists():
            tiles[icao] = (None, None)
            continue
        logo = prepare(icao)
        tile = ov.get("tile") or ("white" if low_contrast_fraction(logo) > 0.35 else "navy")
        t = []
        for size in SIZES:
            im = make_tile(logo, size, tile)
            im.save(OUT_DIR / str(size) / f"{icao}.png")
            t.append(im)
        tiles[icao] = tuple(t)
        w, h = logo.size
        note = "  WIDE" if max(w, h) / max(1, min(w, h)) > 1.8 else ""
        print(f"{icao:4} {tile:5} {w}x{h}{note}")

    preview(tiles, LOGO_DIR / "preview.png")
    write_sources(manifest, icaos)

    parts = [
        "#pragma once\n#include <stdint.h>\n#include <stddef.h>\n",
        "#ifndef PROGMEM\n#define PROGMEM\n#endif\n",
        "// Generated by tools/build_logos.py. Logos are trademarks of their owners; personal use only. Not committed.\n",
        "// Pixels: native RGB565 (r>>3<<11 | g>>2<<5 | b>>3), row-major, pre-composited on navy 0x0864.\n",
        "// Names: UTF-8 (same as other UI strings; font has the PT accented capitals).\n",
        "struct AirlineInfo { char icao[4]; const char* name; const uint16_t* logo24; const uint16_t* logo36; };\n\n",
    ]
    for icao in icaos:
        t24, t36 = tiles[icao]
        if t24 is not None:
            parts.append(emit_array(f"LOGO24_{icao}", t24))
            parts.append(emit_array(f"LOGO36_{icao}", t36))
    parts.append("\nconst AirlineInfo AIRLINES[] = {  // sorted by icao (binary-searchable)\n")
    for icao in icaos:
        has = tiles[icao][0] is not None
        l24 = f"LOGO24_{icao}" if has else "nullptr"
        l36 = f"LOGO36_{icao}" if has else "nullptr"
        parts.append(f'  {{"{icao}", {c_string(AIRLINES[icao])}, {l24}, {l36}}},\n')
    parts.append("};\nconst size_t AIRLINES_COUNT = sizeof(AIRLINES) / sizeof(AIRLINES[0]);\n")
    HEADER.write_text("".join(parts), encoding="ascii")

    with_logo = [i for i in icaos if tiles[i][0] is not None]
    flash = len(with_logo) * 2 * (24 * 24 + 36 * 36)
    print(f"{len(icaos)} airlines, {len(with_logo)} logos, ~{flash / 1024:.0f} KB pixel data -> {HEADER}")
    missing = [i for i in icaos if tiles[i][0] is None]
    if missing:
        print("no logo:", " ".join(missing))


if __name__ == "__main__":
    main()
