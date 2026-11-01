import json
import logging
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, vision
from .data import CATEGORIES, CATEGORY_INFO, CATEGORY_KEYS, LEGAL_QUESTIONS
from .engine import analyze_text
from .models import ScanResult, TextCheckRequest
from .rules import RULES

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("packcheck.api")
app = FastAPI(title="PackCheck", version="2.10.0",
              description="Label compliance checker for the Legal Metrology (Packaged Commodities) Rules, 2011")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")

@app.on_event("startup")
def _warm_up_ocr():
    """Load the OCR models in the background so the first scan does not pay for it."""
    import threading

    if not config.OCR_WARMUP:
        return

    def go():
        try:
            from .ocr import _get_reader, secondary_enabled
            _get_reader("primary")
            if secondary_enabled() and not config.HYBRID_OCR_MAX_SIDE:
                _get_reader("secondary")
            log.info("OCR models loaded")
        except Exception as e:  # OCR may be missing on purpose (AI-only use)
            log.info("OCR warm-up skipped: %s", e)
    threading.Thread(target=go, daemon=True).start()


PACK_TYPES = {"can", "bottle", "other"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _check_inputs(category: str, pack_type: Optional[str]) -> Optional[str]:
    if category not in CATEGORY_KEYS:
        raise HTTPException(422, f"Unknown category '{category}'. See GET /api/categories.")
    pack_type = (pack_type or "").strip().lower() or None
    if pack_type and pack_type not in PACK_TYPES:
        raise HTTPException(422, f"pack_type must be one of {sorted(PACK_TYPES)}")
    return pack_type


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "supabase": config.supabase_enabled(), "ocr_langs": config.OCR_LANGS,
            "reader": config.READER_MODE, "vision": vision.status()}


@app.get("/api/vision-test")
def vision_test():
    """Sends a tiny generated image to the AI reader and reports how long it took, or the exact error."""
    import time

    import cv2
    import numpy as np

    if not vision.is_configured():
        return {"ok": False, "error": "No API key is set in .env (GEMINI_API_KEY or ANTHROPIC_API_KEY)."}
    img = np.full((220, 640, 3), 255, np.uint8)
    cv2.putText(img, "NET WT 200 g", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    cv2.putText(img, "MRP Rs. 60.00", (30, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    t0 = time.time()
    try:
        rd = vision.read_label(img)
    except vision.VisionError as e:
        return {"ok": False, "seconds": round(time.time() - t0, 1), "error": str(e), **vision.status()}
    return {"ok": True, "seconds": round(time.time() - t0, 1), "lines": [l.text for l in rd.lines],
            "provider": rd.provider, "model": rd.model}


@app.get("/api/categories")
def categories():
    return [{"key": k, "label": v, "group": CATEGORY_INFO[k]["group"]} for k, v in CATEGORIES]


@app.get("/api/rules")
def rules():
    """The rule registry: what is checked, under which clause, and the stated limitations."""
    return {"rules": [{"field": r.field, "title": r.title, "rule_reference": r.rule_reference,
                       "limitation": r.limitation} for r in RULES],
            "open_legal_questions": [{"id": k, "question": v} for k, v in LEGAL_QUESTIONS.items()]}


@app.get("/api/samples")
def samples():
    return json.loads(config.SAMPLES_FILE.read_text(encoding="utf-8"))


@app.post("/api/check-text", response_model=ScanResult)
def check_text(req: TextCheckRequest):
    """Run the rules engine on pasted label text (no OCR). Handy for demos and testing."""
    pack_type = _check_inputs(req.category, req.pack_type)
    if not req.text.strip():
        raise HTTPException(422, "text is empty")
    result = analyze_text(req.text, req.category, pack_type)
    result.scan_id = db.save_scan(result)
    return result


@app.post("/api/scan", response_model=ScanResult)
def scan(
    file_back: Optional[UploadFile] = File(None),
    file_front: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    category: str = Form("auto"),
    pack_type: Optional[str] = Form(None),
    reader: Optional[str] = Form(None),
):
    """Photo in, compliance report out: AI vision reader and/or EasyOCR -> layout -> extract -> classify -> rules.

    Send the back of the pack as ``file_back`` (most labels carry their declarations there) and, optionally, the
    front as ``file_front``. At least one is required. With both, each photo is read on its own and the two are checked
    together as one label. ``file`` is the older name for the front photo and still works.

    ``reader``: auto (default; AI + OCR when a key is configured), hybrid, ai or ocr."""
    pack_type = _check_inputs(category, pack_type)
    if reader and reader.strip().lower() not in ("auto", "hybrid", "ai", "ocr"):
        raise HTTPException(422, "reader must be one of auto, hybrid, ai, ocr")
    def given(up):
        return up is not None and bool(getattr(up, "filename", None))

    front = file_front if given(file_front) else (file if given(file) else None)
    back = file_back if given(file_back) else None
    if front is None and back is None:
        raise HTTPException(422, "Add a photo of the back of the pack (or the front).")
    both = front is not None and back is not None
    uploads = ([("Front photo" if both else "Photo", front)] if front is not None else []) + \
              ([("Back photo" if both else "Photo", back)] if back is not None else [])
    blobs = []
    for name, up in uploads:
        if up.content_type not in IMAGE_TYPES:
            raise HTTPException(415, f"{name}: upload a JPG, PNG or WEBP image.")
        data = up.file.read(config.MAX_UPLOAD_BYTES + 1)
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{name} is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        blobs.append(data)
    data = blobs[0]

    try:
        from .ocr import OcrUnavailable
        from .pipeline import NoTextFound, scan_images_bytes
    except ImportError as e:  # pragma: no cover - depends on environment
        raise HTTPException(503, f"OCR dependencies are not installed: {e}")
    try:
        result = scan_images_bytes(blobs, category, pack_type, reader)
    except NoTextFound as e:
        raise HTTPException(422, str(e))
    except vision.VisionNotConfigured as e:
        raise HTTPException(503, str(e))
    except vision.VisionError as e:
        raise HTTPException(502, str(e))
    except OcrUnavailable as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ImportError as e:
        raise HTTPException(503, f"OCR dependencies are not installed: {e}")
    except Exception:  # never let an OCR/CV failure crash the server
        log.exception("scan failed")
        raise HTTPException(500, "The image could not be processed. Try another photo; the error was logged.")
    result.scan_id = db.save_scan(result, data, uploads[0][1].content_type)
    return result


@app.get("/api/history")
def history(limit: int = 20):
    return {"enabled": config.supabase_enabled(), "scans": db.list_scans(max(1, min(limit, 100)))}


@app.get("/api/scans/{scan_id}", response_model=ScanResult)
def get_scan(scan_id: str):
    row = db.get_scan(scan_id)
    if not row:
        raise HTTPException(404, "Scan not found (or Supabase is not configured).")
    return row
