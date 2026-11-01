"""Record a REAL EasyOCR token fixture for regression tests (needs EasyOCR).

Usage: python -m scripts.record_ocr_fixture tests/fixtures/bhaskar_label.jpg tests/fixtures/bhaskar_easyocr_tokens.json

The output has the same format as tests/fixtures/*.json (tokens with English and Devanagari
readings, boxes in preprocessed-image coordinates, separators, image size), so a recorded file
can replace the synthetic fixture in tests/test_regression_bhaskar.py.
"""
import json
import sys
from pathlib import Path

from app import config
from app.ocr import read_tokens
from app.preprocess import decode_image, find_vertical_rules, preprocess_with_report


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dst = Path(argv[0]), Path(argv[1])
    gray, rep = preprocess_with_report(decode_image(src.read_bytes()), max_side=config.PREPROCESS_MAX_SIDE)
    seps = find_vertical_rules(gray)
    res = read_tokens(gray, seps)
    out = {
        "source": str(src), "note": f"Real recording: engines {res.engines}, variant {res.variant}",
        "image_size": [gray.shape[1], gray.shape[0]], "preprocess": rep.as_dict(),
        "separators": [{"x": s.x, "y0": s.y0, "y1": s.y1} for s in seps],
        "tokens": [t.as_dict() for t in res.tokens],
    }
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(res.tokens)} tokens to {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
