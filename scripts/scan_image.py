"""Scan a label photo from the command line (needs EasyOCR).

Usage: python -m scripts.scan_image path/to/label.jpg [category] [--json]
"""
import json
import sys
from pathlib import Path

from app.pipeline import scan_image_bytes


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path = Path(argv[0])
    category = next((a for a in argv[1:] if not a.startswith("--")), "auto")
    r = scan_image_bytes(path.read_bytes(), category)
    if "--json" in argv:
        print(json.dumps(r.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0
    print(f"{r.verdict}  category={r.category} ({r.classification['source']})  summary={r.summary}")
    for f in r.fields:
        print(f"  {f.field:15s} {f.status:24s} {f.violation_code or '':15s} {f.sub_case or ''}")
    print("\n--- regions (reading order)")
    for g in r.ocr["regions"]:
        print(f"  [{g['block']}/{g['column']}] {g['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
