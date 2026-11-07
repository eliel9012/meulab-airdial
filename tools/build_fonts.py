"""Build anti-aliased serif VLW (LovyanGFX/TFT_eSPI "smooth font") arrays for the M5Dial.

Usage:
  python tools/build_fonts.py                 # writes include/fonts_vlw.h
  python tools/build_fonts.py --preview DIR   # also decodes the generated VLW and renders preview PNGs
  python tools/build_fonts.py --accent-ascent # count accented caps in the header ascent (taller line box)

Font: Source Serif 4 (Adobe, SIL OFL 1.1, Reserved Font Name "Source"), optical-size statics
Caption (13/16 px) and SmText (24/32 px). TTFs + OFL.txt live in assets/fonts/.
The generated bitmaps are a derived work; arrays are named generically (FONT_SERIF_*).

VLW layout (all int32 big-endian), as read by lgfx::v1::VLWfont::loadFont/drawChar:
  header  : glyphCount, version(11), fontSize, 0, ascent, descent
  records : unicode, height, width, xAdvance, dY (baseline -> glyph top, +up), dX, 0
  bitmaps : width*height 8-bit alpha per glyph, record order. Glyphs sorted by unicode.
Loader notes (M5GFX lgfx_fonts.cpp):
  - no trailing font name is read; nothing after the bitmaps is needed.
  - unicode truncated to uint16, width/xAdvance to uint8, dX to int8.
  - header fontSize is effectively ignored: yAdvance = maxAscent + maxDescent, where max* start at
    header ascent/descent and grow only from glyphs 0x21..0x9F (except 0x7F) or > 0xFF.
    Latin-1 glyphs 0xA0..0xFF never grow the line box, so accented caps rise above the text box
    top unless --accent-ascent puts them into the header ascent.
  - glyph top y = text_top + (maxAscent - dY); baseline sits at text_top + maxAscent.
  - space (0x20) draws nothing; only its xAdvance (record offset 12) is used.
"""
import argparse
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"
HEADER = ROOT / "include" / "fonts_vlw.h"

CHARSET = (
    [chr(c) for c in range(0x20, 0x7F)]
    + list("ÀÁÂÃÇÉÊÍÓÔÕÚÜàáâãçéêíóôõúü")
    + ["°", "·", "–", "↑", "↓"]
)

# name, ttf, em size px, alpha gamma (<1 thickens AA edges), contrast gain
FONTS = [
    ("SERIF_32", "SourceSerif4SmText-Bold.ttf", 32, 0.90, 1.00),
    ("SERIF_24", "SourceSerif4SmText-Semibold.ttf", 24, 0.85, 1.05),
    ("SERIF_16", "SourceSerif4Caption-Semibold.ttf", 16, 0.80, 1.10),
    ("SERIF_13", "SourceSerif4Caption-Semibold.ttf", 13, 0.72, 1.15),
    # Idle clock: digits only, keeps flash and glyph-table RAM tiny.
    ("SERIF_56D", "SourceSerif4SmText-Semibold.ttf", 56, 0.90, 1.00, "0123456789:- "),
]


def alpha_lut(gamma, gain):
    lut = []
    for a in range(256):
        v = (a / 255.0) ** gamma * gain
        lut.append(max(0, min(255, round(v * 255))))
    lut[0] = 0
    return bytes(lut)


def _render(font, ch):
    l, t, r, b = font.getbbox(ch)
    img = Image.new("L", (max(1, r - l), max(1, b - t)), 0)
    ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=255)
    return img.size, img.tobytes()


def has_glyph(font, ch):
    # Missing glyphs render as .notdef; compare with a private-use codepoint that is surely absent.
    return ch == " " or _render(font, ch) != _render(font, "\uE000")


def rasterize(font, ch, lut):
    adv = int(round(font.getlength(ch)))
    if ch == " ":
        # widen word gaps a touch at small sizes (Source Serif space ~0.23 em)
        return dict(u=ord(ch), w=0, h=0, adv=max(adv, round(font.size * 0.28)), dy=0, dx=0, bmp=b"")
    l, t, r, b = font.getbbox(ch, anchor="ls")
    img = Image.new("L", (max(1, r - l), max(1, b - t)), 0)
    ImageDraw.Draw(img).text((-l, -t), ch, font=font, fill=255, anchor="ls")
    bb = img.getbbox()
    if bb is None:
        return dict(u=ord(ch), w=0, h=0, adv=adv, dy=0, dx=0, bmp=b"")
    img = img.crop(bb)
    w, h = img.size
    return dict(u=ord(ch), w=w, h=h, adv=adv, dy=-(t + bb[1]), dx=l + bb[0],
                bmp=img.tobytes().translate(lut))


def counts_for_metrics(u):
    return u > 0xFF or (0x20 < u < 0xA0 and u != 0x7F)


def build_vlw(ttf, size, gamma, gain, accent_ascent, charset=None):
    charset = list(charset) if charset else CHARSET
    font = ImageFont.truetype(str(FONT_DIR / ttf), size)
    lut = alpha_lut(gamma, gain)
    glyphs = [rasterize(font, ch, lut) for ch in charset if has_glyph(font, ch)]
    glyphs.sort(key=lambda g: g["u"])
    for g in glyphs:
        assert 0 <= g["w"] < 256 and 0 <= g["adv"] < 256 and -128 <= g["dx"] < 128, g["u"]
    pool = glyphs if accent_ascent else [g for g in glyphs if counts_for_metrics(g["u"])]
    ascent = max(g["dy"] for g in pool if g["h"])
    descent = max(g["h"] - g["dy"] for g in pool if g["h"])
    out = bytearray(struct.pack(">6i", len(glyphs), 11, size, 0, ascent, descent))
    for g in glyphs:
        out += struct.pack(">7i", g["u"], g["h"], g["w"], g["adv"], g["dy"], g["dx"], 0)
    for g in glyphs:
        out += g["bmp"]
    missing = [c for c in charset if not has_glyph(font, c)]
    return bytes(out), missing


# ---------------------------------------------------------------- decoder / preview

def decode_vlw(data):
    """Mirror of VLWfont::loadFont: returns dict with glyph table and line metrics."""
    n, _ver, size, _z, asc, desc = struct.unpack_from(">6i", data, 0)
    asc, desc = abs(asc), abs(desc)
    max_a, max_d = asc, desc
    ptr = 24 + n * 28
    glyphs = {}
    for i in range(n):
        u, h, w, adv, dy, dx, _ = struct.unpack_from(">7i", data, 24 + i * 28)
        u &= 0xFFFF
        w &= 0xFF
        adv &= 0xFF
        dx = struct.unpack("b", bytes([dx & 0xFF]))[0]
        if counts_for_metrics(u):
            max_a = max(max_a, dy)
            max_d = max(max_d, h - dy)
        glyphs[u] = (w, h, adv, dy, dx, data[ptr:ptr + w * h])
        ptr += w * h
    assert ptr == len(data), (ptr, len(data))
    return dict(size=size, glyphs=glyphs, ascent=max_a, height=max_a + max_d,
                space=(max(size, asc + desc) * 2) // 7)


def draw_text(img, x, y, text, font, rgb):
    """Draw like LovyanGFX top_left datum: y is the text box top."""
    px = img.load()
    for ch in text:
        g = font["glyphs"].get(ord(ch))
        if g is None:
            x += font["space"]
            continue
        w, h, adv, dy, dx, bmp = g
        top = y + font["ascent"] - dy
        for j in range(h):
            for i in range(w):
                a = bmp[j * w + i]
                if not a:
                    continue
                X, Y = x + dx + i, top + j
                if 0 <= X < img.width and 0 <= Y < img.height:
                    p = 1 + a
                    br, bg, bb = px[X, Y]
                    px[X, Y] = tuple((f * p + b_ * (257 - p)) >> 8 for f, b_ in zip(rgb, (br, bg, bb)))
        x += adv
    return x


def text_width(font, text):
    return sum(font["glyphs"].get(ord(c), (0, 0, font["space"]))[2] for c in text)


BG = (0x06, 0x15, 0x22)
COLORS = [(255, 255, 255), (0x38, 0xD6, 0xD0), (0xFF, 0x77, 0x5D), (0x8F, 0xAA, 0xBD)]
SAMPLES = ["GLO1490", "PR-XMM · B38M", "38000 ft  458 kt", "CÉU LIVRE",
           "DADOS ANTIGOS 76s", "RUMO 344° · 15.8 NM", "MEULAB / SIMK"]


def preview(fonts, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    for name, data in fonts:
        f = decode_vlw(data)
        lh = f["height"] + 2
        width = max(text_width(f, s) for s in SAMPLES) + 12
        img = Image.new("RGB", (width * 2, lh * len(SAMPLES) + 8), BG)
        for k, s in enumerate(SAMPLES):
            col = COLORS[k % len(COLORS)]
            draw_text(img, 6, 4 + k * lh, s, f, col)
            draw_text(img, width + 6, 4 + k * lh, s, f, COLORS[(k + 1) % len(COLORS)])
        img.save(outdir / f"{name}_1x.png")
        img.resize((img.width * 3, img.height * 3), Image.NEAREST).save(outdir / f"{name}_3x.png")
    # combined round-screen mock at 1x and 3x
    dec = {n: decode_vlw(d) for n, d in fonts}
    scr = Image.new("RGB", (240, 240), BG)
    ImageDraw.Draw(scr).ellipse((0, 0, 239, 239), outline=(0x1A, 0x33, 0x48))

    def center(y, s, n, c):
        f = dec[n]
        draw_text(scr, (240 - text_width(f, s)) // 2, y, s, f, c)
        return y + f["height"]

    y = 30
    y = center(y, "MEULAB / SIMK", "SERIF_13", COLORS[3]) + 4
    y = center(y, "GLO1490", "SERIF_32", COLORS[0]) + 2
    y = center(y, "PR-XMM · B38M", "SERIF_16", COLORS[1]) + 4
    y = center(y, "38000 ft  458 kt", "SERIF_16", COLORS[0]) + 2
    y = center(y, "RUMO 344° · 15.8 NM", "SERIF_13", COLORS[3]) + 6
    y = center(y, "CÉU LIVRE", "SERIF_24", COLORS[1]) + 2
    y = center(y, "DADOS ANTIGOS 76s", "SERIF_13", COLORS[2])
    scr.save(outdir / "screen_1x.png")
    scr.resize((720, 720), Image.NEAREST).save(outdir / "screen_3x.png")


# ---------------------------------------------------------------- header

def write_header(fonts, path):
    lines = [
        "#pragma once",
        "#include <stdint.h>",
        "#ifndef PROGMEM",
        "#define PROGMEM",
        "#endif",
        "// Generated by tools/build_fonts.py from Source Serif 4 Caption/SmText (Adobe, SIL OFL 1.1,",
        "// Reserved Font Name \"Source\"; see assets/fonts/OFL.txt). LovyanGFX VLW smooth fonts:",
        "//   d.loadFont(FONT_SERIF_24); ... d.unloadFont();  (include from ONE .cpp: const = internal linkage)",
        "// Glyphs: ASCII 0x20-0x7E, PT Latin-1 letters, ° · – ↑ ↓ (when present in the font).",
        "",
    ]
    for name, data, meta in fonts:
        lines.append(f"// {meta}")
        lines.append(f"const uint8_t FONT_{name}[] PROGMEM = {{")
        for i in range(0, len(data), 24):
            lines.append("  " + ",".join(f"0x{b:02X}" for b in data[i:i + 24]) + ",")
        lines.append("};")
        lines.append(f"const uint32_t FONT_{name}_LEN = sizeof(FONT_{name});")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, help="render previews (decoded from VLW) into DIR")
    ap.add_argument("--accent-ascent", action="store_true",
                    help="include Latin-1 accented glyphs in header ascent")
    args = ap.parse_args()
    built = []
    total = 0
    for name, ttf, size, gamma, gain, *charset in FONTS:
        data, missing = build_vlw(ttf, size, gamma, gain, args.accent_ascent, *charset)
        f = decode_vlw(data)
        meta = (f"{name}: {ttf} @ {size}px em, gamma {gamma}, gain {gain}, "
                f"{len(f['glyphs'])} glyphs, ascent {f['ascent']}, line {f['height']}px, {len(data)} B")
        print(meta + (f"  missing: {''.join(missing)}" if missing else ""))
        built.append((name, data, meta))
        total += len(data)
    print(f"total {total} B")
    write_header(built, HEADER)
    print(f"wrote {HEADER}")
    if args.preview:
        preview([(n, d) for n, d, _ in built], args.preview)
        print(f"previews in {args.preview}")


if __name__ == "__main__":
    sys.exit(main())
