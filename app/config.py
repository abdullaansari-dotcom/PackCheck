import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SAMPLES_FILE = BASE_DIR / "samples" / "samples.json"


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


OCR_LANGS = [s.strip() for s in os.getenv("OCR_LANGS", "en,hi").split(",") if s.strip()]
OCR_GPU = _bool("OCR_GPU", False)
# Hindi (or any non-English language in OCR_LANGS) is read by a *secondary* recogniser on the
# same boxes; English is always the primary reading. See app/ocr.py.
OCR_SECONDARY_SCRIPT = _bool("OCR_SECONDARY_SCRIPT", True)
OCR_FALLBACK_VARIANTS = _bool("OCR_FALLBACK_VARIANTS", True)
MIN_TOKEN_CONF = _float("MIN_TOKEN_CONF", 0.10)  # boxes below this are treated as noise
PREPROCESS = _bool("PREPROCESS", True)
PREPROCESS_MAX_SIDE = int(_float("PREPROCESS_MAX_SIDE", 2560))  # EasyOCR's default canvas size (OCR-only mode)
# When the AI reader runs alongside, OCR only supplies positions and a second opinion: a smaller image and no
# Hindi / fallback passes make it several times faster. Set to 0 to use the full OCR settings in hybrid mode too.
HYBRID_OCR_MAX_SIDE = int(_float("HYBRID_OCR_MAX_SIDE", 1400))
# Load the OCR models in the background at server start. Off by default: with `uvicorn --reload` a restart in the
# middle of loading can make the old process hang on shutdown. Turn on for normal (non-reload) running.
OCR_WARMUP = _bool("OCR_WARMUP", False)
PERSPECTIVE_CORRECTION = _bool("PERSPECTIVE_CORRECTION", False)

MIN_FIELD_CONF = _float("MIN_FIELD_CONF", 0.40)
MIN_OVERALL_CONF = _float("MIN_OVERALL_CONF", 0.45)
# product-category inference is used only at or above this score (0..1)
MIN_CATEGORY_CONF = _float("MIN_CATEGORY_CONF", 0.6)
# Rule 9 contrast proxy: luminance contrast between text and background below this -> review
MIN_TEXT_CONTRAST = _float("MIN_TEXT_CONTRAST", 0.25)
MAX_UPLOAD_BYTES = int(_float("MAX_UPLOAD_MB", 10) * 1024 * 1024)

# --- AI vision reader -----------------------------------------------------------------------------
# READER_MODE: auto  = hybrid (AI + OCR cross-check) when an AI key is configured, else OCR only
#              hybrid = AI reads the label, OCR supplies box positions and a second opinion
#              ai     = AI only (no EasyOCR needed; Rule 8 / Rule 9 position checks are limited)
#              ocr    = EasyOCR only (the original behaviour)
READER_MODE = os.getenv("READER_MODE", "auto").strip().lower()
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "").strip().lower()  # anthropic | gemini | "" (auto)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")).strip()
VISION_MODEL = os.getenv("VISION_MODEL", "").strip()  # empty -> provider default (see app/vision.py)
VISION_TIMEOUT_S = _float("VISION_TIMEOUT_S", 45.0)
VISION_FALLBACK_TIMEOUT_S = _float("VISION_FALLBACK_TIMEOUT_S", 40.0)  # wait for each backup model
# Gemini 3.x thinking level for the transcription call: minimal | low | medium | high ("" = model default)
# If True, a retired model is an error. If False (default) the app finds a working Gemini flash model by itself.
VISION_MODEL_STRICT = _bool("VISION_MODEL_STRICT", False)
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
VISION_MAX_SIDE = int(_float("VISION_MAX_SIDE", 1400))  # longest image side sent to the AI, in pixels
# Confidence given to a line where the AI and OCR read different numbers. Below MIN_FIELD_CONF (0.40)
# such a field becomes "Needs review"; the default only flags it in the report.
AI_DISAGREEMENT_CONF = _float("AI_DISAGREEMENT_CONF", 0.70)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "label-images")

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)
