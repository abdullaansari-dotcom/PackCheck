"""Check many labels in one go and write a report (no web page needed).

    python -m scripts.batch_check path/to/labels
    python -m scripts.batch_check path/to/labels --reader ai --category auto --out my_report

Folder layout (mix freely):

    labels/
        haldiram.jpg                one photo = one label
        origami/back.jpg            a sub-folder = one label made of several photos
        origami/front.jpg           (names containing 'front' are the front, anything else is the back)

Writes <out>.csv (one row per label and check) and <out>.md (a readable summary), and prints the verdicts.
The AI reader and OCR are used exactly as in the web app (keys from .env). Use it to test 15-20 labels in one
session and see which patterns are still missing, instead of finding them one product at a time.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def collect(root: Path):
    """Yield (name, [image paths in front, back order])."""
    singles = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
    for p in singles:
        yield p.stem, [p]
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        imgs = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
        if not imgs:
            continue
        front = [p for p in imgs if "front" in p.stem.lower()][:1]
        others = [p for p in imgs if p not in front]
        back = others[:1] if front else others[:2]
        yield d.name, (front + back)[:2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Batch-check label photos.")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--category", default="auto")
    ap.add_argument("--reader", default=None, help="auto | hybrid | ai | ocr (default: from .env)")
    ap.add_argument("--out", default="batch_report", help="output file name without extension")
    a = ap.parse_args(argv)
    if not a.folder.is_dir():
        print(f"Not a folder: {a.folder}")
        return 2
    from app.pipeline import NoTextFound, scan_images_bytes

    rows, summary = [], []
    items = list(collect(a.folder))
    if not items:
        print("No images found.")
        return 2
    for n, (name, paths) in enumerate(items, 1):
        print(f"[{n}/{len(items)}] {name} ({len(paths)} photo{'s' if len(paths) > 1 else ''}) ...", flush=True)
        try:
            r = scan_images_bytes([p.read_bytes() for p in paths], a.category, None, a.reader)
        except NoTextFound as e:
            summary.append((name, "NO TEXT", str(e), ""))
            continue
        except Exception as e:  # keep going: one bad photo must not stop the batch
            summary.append((name, "ERROR", f"{type(e).__name__}: {e}", ""))
            continue
        attention = [f"{f.title or f.field}: {f.status}" for f in r.fields if f.status in ("FAIL", "REVIEW")]
        summary.append((name, r.verdict, r.category, "; ".join(attention)))
        for f in r.fields:
            rows.append([name, r.verdict, r.category, f.field, f.status, f.detected_text or "", (f.detail or "")[:300]])
    csv_path, md_path = Path(a.out + ".csv"), Path(a.out + ".md")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["label", "verdict", "category", "check", "status", "detected", "detail"])
        w.writerows(rows)
    with md_path.open("w", encoding="utf-8") as fh:
        fh.write("| Label | Verdict | Category | Needs attention |\n|---|---|---|---|\n")
        for name, verdict, cat, att in summary:
            fh.write(f"| {name} | {verdict} | {cat} | {att} |\n")
    print()
    for name, verdict, cat, att in summary:
        print(f"{name:32} {verdict:14} {att}")
    print(f"\nWrote {csv_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
