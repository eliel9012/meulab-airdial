"""Compare simulator renders against the committed baseline.

  python3 compare.py [--out out] [--baseline baseline] [--threshold 50] [--tol 8]
  python3 compare.py --update      # copy out/*.png (no sheets) into baseline/

A pixel differs when any RGB channel differs by more than --tol. An image fails
when more than --threshold pixels differ (or its size changed, or it vanished).
Diff images (changed pixels in red over a dimmed baseline) go to out/diff/.
Exit 1 on any failure. Images with no baseline are reported as new, not failed.
"""
import argparse
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent


def renders(folder):
    return sorted(p for p in folder.glob("*.png") if not p.name.startswith("sheet_"))


def diff_count(a, b, tol):
    delta = ImageChops.difference(a, b).split()
    mask = None
    for ch in delta:
        m = ch.point(lambda v: 255 if v > tol else 0)
        mask = m if mask is None else ImageChops.lighter(mask, m)
    return mask.histogram()[255], mask


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--baseline", type=Path, default=HERE / "baseline")
    ap.add_argument("--threshold", type=int, default=50, help="max differing pixels per image")
    ap.add_argument("--tol", type=int, default=8, help="per-channel tolerance (0-255)")
    ap.add_argument("--update", action="store_true", help="overwrite baseline with current renders")
    args = ap.parse_args()

    current = renders(args.out)
    if not current:
        print(f"no renders in {args.out}", file=sys.stderr)
        return 1

    if args.update:
        args.baseline.mkdir(parents=True, exist_ok=True)
        for old in renders(args.baseline):
            if not (args.out / old.name).exists():
                old.unlink()
                print(f"removed {old.name}")
        for p in current:
            shutil.copy2(p, args.baseline / p.name)
        print(f"baseline updated: {len(current)} images -> {args.baseline}")
        return 0

    diff_dir = args.out / "diff"
    if diff_dir.exists():
        shutil.rmtree(diff_dir)
    failed = []
    names = {p.name for p in current}
    for p in current:
        base = args.baseline / p.name
        if not base.exists():
            print(f"NEW   {p.name}")
            continue
        a = Image.open(base).convert("RGB")
        b = Image.open(p).convert("RGB")
        if a.size != b.size:
            print(f"FAIL  {p.name}: size {a.size} -> {b.size}")
            failed.append(p.name)
            continue
        n, mask = diff_count(a, b, args.tol)
        status = "FAIL" if n > args.threshold else ("ok~" if n else "ok")
        print(f"{status:5} {p.name}: {n} px")
        if n:
            diff_dir.mkdir(parents=True, exist_ok=True)
            dimmed = Image.blend(Image.new("RGB", a.size), a, 0.35)
            red = Image.new("RGB", a.size, (255, 0, 0))
            Image.composite(red, dimmed, mask).save(diff_dir / p.name)
        if n > args.threshold:
            failed.append(p.name)
    for base in renders(args.baseline):
        if base.name not in names:
            print(f"FAIL  {base.name}: missing from {args.out}")
            failed.append(base.name)

    if failed:
        print(f"{len(failed)} image(s) differ beyond threshold {args.threshold}: {', '.join(failed)}")
        return 1
    print("all renders match baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
