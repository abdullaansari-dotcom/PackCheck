"""AI vision reader: prompt/response handling, fusion with OCR boxes, reader modes.

No network: the HTTP call (app.vision._post_json) and the OCR step (app.pipeline._run_ocr) are replaced,
so these tests run without API keys, EasyOCR or an internet connection.
"""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app import config, pipeline, vision
from app.fusion import fuse, match_lines
from app.layout import Separator, build_lines, tokens_from_dicts
from app.ocr import OcrResult, OcrUnavailable

FIX = Path(__file__).parent / "fixtures"

BHASKAR_AI = {
    "lines": [
        {"text": "BHASKAR", "region": "logo", "lang": "en"},
        {"text": "BOOK TECH", "region": "logo", "lang": "en"},
        {"text": "Plot No. 267/16A-267/16B, Kiadb Industrial Area,", "region": "address", "lang": "en"},
        {"text": "2nd Road, 2nd Phase, Ramanagar District,", "region": "address", "lang": "en"},
        {"text": "Harohalli - 562112,", "region": "address", "lang": "en"},
        {"text": "E-mail: bhaskarbook@yahoo.in", "region": "address", "lang": "en"},
        {"text": "Help line : 080-29761413", "region": "address", "lang": "en"},
        {"text": "140 Pages - MRP: ₹ 60.00", "region": "price box", "lang": "en"},
        {"text": "(Incl. of Taxes)", "region": "price box", "lang": "en"},
        {"text": "(Inclusive of both end sheets)", "region": "price box", "lang": "en"},
        {"text": "Size 30x18Cms", "region": "price box", "lang": "en"},
    ],
    "category": "notebook", "category_confidence": 0.9, "category_reason": "'140 Pages' and 'end sheets'",
    "pack_type": None, "legible": True, "issues": [], "notes": [],
}


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "")
    monkeypatch.setattr(config, "VISION_MODEL", "")


@pytest.fixture
def photo():
    return cv2.imread(str(FIX / "bhaskar_label.jpg"))


def fake_ai(monkeypatch, payload=None):
    calls = []

    def post(url, headers, body, timeout):
        calls.append((url, headers, body))
        return {"content": [{"type": "text", "text": json.dumps(payload or BHASKAR_AI)}]}

    monkeypatch.setattr(vision, "_post_json", post)
    return calls


# ------------------------------------------------------------------ provider selection
def test_not_configured_by_default(monkeypatch):
    for n in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setattr(config, n, "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "")
    assert not vision.is_configured()
    assert pipeline.resolve_reader("auto") == "ocr"
    with pytest.raises(vision.VisionNotConfigured):
        pipeline.resolve_reader("ai")


def test_provider_and_model_selection(monkeypatch):
    monkeypatch.setattr(config, "VISION_MODEL", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g")
    assert vision.provider() == "gemini" and vision.model_name() == vision.DEFAULT_MODELS["gemini"]
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "a")
    assert vision.provider() == "anthropic"
    monkeypatch.setattr(config, "VISION_PROVIDER", "gemini")
    assert vision.provider() == "gemini"
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "SECRET-A")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "SECRET-G")
    assert "SECRET" not in json.dumps(vision.status())


# ------------------------------------------------------------------ requests and parsing
def test_anthropic_request_shape(key, monkeypatch, photo):
    calls = fake_ai(monkeypatch)
    r = vision.read_label(photo)
    url, headers, body = calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-test" and "anthropic-version" in headers
    block = body["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"
    assert "never guess a digit" in body["system"].lower() or "never guess" in body["system"].lower()
    assert r.category == "notebook" and len(r.lines) == 11


def test_gemini_request_shape(monkeypatch, photo):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-test")
    monkeypatch.setattr(config, "VISION_PROVIDER", "")
    monkeypatch.setattr(config, "VISION_MODEL", "")
    seen = {}

    def post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(BHASKAR_AI)}]}}]}

    monkeypatch.setattr(vision, "_post_json", post)
    r = vision.read_label(photo)
    assert "generativelanguage.googleapis.com" in seen["url"] and "key=" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "g-test"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert r.provider == "gemini" and len(r.lines) == 11


def test_parse_handles_fences_and_bad_category():
    raw = "```json\n" + json.dumps({"lines": [{"text": "Net Wt. 100 g"}, {"text": "[illegible]"}],
                                    "category": "lpg", "category_confidence": 0.99}) + "\n```"
    r = vision.parse_reading(raw, "anthropic", "m")
    assert [l.text for l in r.lines] == ["Net Wt. 100 g"]
    assert r.category is None  # exemption / unknown categories are never taken from the AI
    assert any("illegible" in n for n in r.notes)


def test_parse_rejects_garbage():
    with pytest.raises(vision.VisionError):
        vision.parse_reading("sorry, I cannot help", "anthropic", "m")
    with pytest.raises(vision.VisionError):
        vision.parse_reading(json.dumps({"lines": []}), "anthropic", "m")


def test_prompt_tells_model_to_ignore_label_instructions():
    assert "DATA" in vision.SYSTEM_PROMPT and "do not follow" in vision.SYSTEM_PROMPT
    assert "lpg" not in vision._category_menu()  # exemption categories are not offered


# ------------------------------------------------------------------ fusion
def ocr_lines_from(name):
    d = json.loads((FIX / name).read_text(encoding="utf-8"))
    toks = [t for t in tokens_from_dicts(d["tokens"]) if t.conf >= 0.3]
    return toks, [Separator(**s) for s in d["separators"]], tuple(d["image_size"])


def test_fuse_grounds_ai_lines_on_ocr_boxes():
    toks, seps, _ = ocr_lines_from("bhaskar_synthetic_phrase_boxes.json")
    ocr_lines = build_lines(toks, seps)
    reading = vision.parse_reading(json.dumps(BHASKAR_AI), "anthropic", "m")
    lines, rep = fuse(reading, ocr_lines)
    assert len(lines) == 11 and rep["grounded"] >= 6
    mrp = next(l for l in lines if "MRP" in l.text)
    assert mrp.bbox is not None and mrp.text == "140 Pages - MRP: ₹ 60.00"


def test_fuse_flags_number_disagreement(monkeypatch):
    toks, seps, _ = ocr_lines_from("bhaskar_synthetic_phrase_boxes.json")
    ocr_lines = build_lines(toks, seps)
    bad = json.loads(json.dumps(BHASKAR_AI))
    bad["lines"][7]["text"] = "190 Pages - MRP: ₹ 65.00"  # a number the OCR never saw
    reading = vision.parse_reading(json.dumps(bad), "anthropic", "m")
    lines, rep = fuse(reading, ocr_lines)
    assert rep["disagreements"], "a number the OCR did not see must be reported"
    line = next(l for l in lines if "190" in l.text)
    assert line.conf == config.AI_DISAGREEMENT_CONF


def test_fuse_without_ocr_has_no_geometry():
    reading = vision.parse_reading(json.dumps(BHASKAR_AI), "anthropic", "m")
    lines, rep = fuse(reading, [])
    assert all(l.bbox is None for l in lines) and rep["grounded"] == 0


def test_match_lines_each_ocr_line_used_once():
    toks, seps, _ = ocr_lines_from("bhaskar_synthetic_phrase_boxes.json")
    ocr_lines = build_lines(toks, seps)
    m = match_lines([l["text"] for l in BHASKAR_AI["lines"]], ocr_lines)
    used = [j for js in m.values() for j in js]
    assert len(used) == len(set(used))


# ------------------------------------------------------------------ pipeline modes
def fake_ocr(monkeypatch, name="bhaskar_synthetic_phrase_boxes.json", fail=None):
    toks, seps, size = ocr_lines_from(name)
    gray = cv2.cvtColor(cv2.imread(str(FIX / "bhaskar_label.jpg")), cv2.COLOR_BGR2GRAY)

    def run(img, lean=False):
        if fail:
            raise fail
        res = OcrResult(toks, build_lines(toks, seps), seps, size, "gray_enhanced", ["fake-ocr"], [])
        return res, seps, gray, {"variant": "gray_enhanced"}

    monkeypatch.setattr(pipeline, "_run_ocr", run)


def field(r, name):
    return next(x for x in r.fields if x.field == name)


def test_hybrid_scan_uses_ai_text_and_category(key, monkeypatch):
    fake_ai(monkeypatch)
    fake_ocr(monkeypatch)
    r = pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "auto", reader="hybrid")
    assert r.ocr["reader"]["mode"] == "hybrid"
    assert any(e.startswith("vision:") for e in r.ocr["engines"]) and "fake-ocr" in r.ocr["engines"]
    assert r.category == "notebook"
    assert field(r, "mrp").violation_code != "MISSING" and "60" in (field(r, "mrp").detected_text or "")
    assert not any("०" <= ch <= "९" for ch in r.raw_text)
    assert r.ocr["ai"]["model"] and r.ocr["ai"]["lines"]


def test_ai_category_never_overrides_user_choice(key, monkeypatch):
    fake_ai(monkeypatch)
    fake_ocr(monkeypatch)
    r = pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "tea", reader="hybrid")
    assert r.category == "tea" and r.classification["source"] == "user"
    assert r.classification["suggestion"] == "notebook"


def test_hybrid_falls_back_to_ocr_when_ai_fails(key, monkeypatch):
    def boom(*a, **k):
        raise vision.VisionError("The AI service timed out")

    monkeypatch.setattr(vision, "_post_json", boom)
    fake_ocr(monkeypatch)
    r = pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "auto", reader="hybrid")
    assert r.ocr["reader"]["fallback"] == "ocr"
    assert any("AI reader was unavailable" in n for n in r.ocr["notes"])


def test_ai_mode_raises_when_ai_fails(key, monkeypatch):
    def boom(*a, **k):
        raise vision.VisionError("quota")

    monkeypatch.setattr(vision, "_post_json", boom)
    with pytest.raises(vision.VisionError):
        pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "auto", reader="ai")


def test_hybrid_uses_ai_only_when_ocr_missing(key, monkeypatch):
    fake_ai(monkeypatch)
    fake_ocr(monkeypatch, fail=OcrUnavailable("EasyOCR is not installed"))
    r = pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "auto", reader="hybrid")
    assert r.ocr["reader"]["fallback"] == "ai"
    assert field(r, "mrp").status != "MISSING" and r.category == "notebook"
    assert field(r, "clear_space").status in ("NOT_APPLICABLE", "REVIEW")  # no geometry, never auto-fail


def test_illegible_photo_goes_to_review(key, monkeypatch):
    bad = json.loads(json.dumps(BHASKAR_AI))
    bad["legible"] = False
    fake_ai(monkeypatch, bad)
    fake_ocr(monkeypatch)
    r = pipeline.scan_image_bytes((FIX / "bhaskar_label.jpg").read_bytes(), "auto", reader="hybrid")
    assert r.verdict == "NEEDS_REVIEW" and field(r, "legibility").status == "REVIEW"


def test_gemini_model_discovery_ranks_newest_flash(monkeypatch):
    from app import vision
    assert vision._model_rank("gemini-3.8-flash") > vision._model_rank("gemini-2.5-flash")
    assert vision._model_rank("gemini-3.10-flash") > vision._model_rank("gemini-3.8-flash")


def test_model_not_found_switches_to_discovered_model(monkeypatch):
    import numpy as np
    from app import vision, config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k"); monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "gemini"); monkeypatch.setattr(config, "VISION_MODEL", "")
    monkeypatch.setattr(config, "VISION_MODEL_STRICT", False); vision._resolved.clear()
    calls = []
    def fake(image, mt, model, timeout=None):
        calls.append(model)
        if model == vision.DEFAULT_MODELS["gemini"]:
            raise vision.VisionError("AI model not found. Check VISION_MODEL.")
        return '{"lines":[{"text":"NET WT 200 g"}]}'
    monkeypatch.setattr(vision, "_call_gemini", fake)
    monkeypatch.setattr(vision, "discover_gemini_models", lambda: ["gemini-9.9-flash"])
    r = vision.read_label(np.full((50, 50, 3), 255, np.uint8))
    assert calls == [vision.DEFAULT_MODELS["gemini"], "gemini-9.9-flash"] and r.lines[0].text == "NET WT 200 g"
    vision._resolved.clear()


def test_timeout_falls_back_to_next_model_and_remembers_it(monkeypatch):
    import numpy as np
    from app import vision, config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k"); monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "gemini"); monkeypatch.setattr(config, "VISION_MODEL", "slow-model")
    monkeypatch.setattr(config, "VISION_MODEL_STRICT", False); vision._resolved.clear()
    def fake(image, mt, model, timeout=None):
        if model == "slow-model":
            raise vision.VisionTimeout("AI reader unavailable: the AI service did not answer within 45 s")
        return '{"lines":[{"text":"MRP Rs. 60.00"}]}'
    monkeypatch.setattr(vision, "_call_gemini", fake)
    monkeypatch.setattr(vision, "discover_gemini_models", lambda: ["slow-model", "fast-model"])
    r = vision.read_label(np.full((50, 50, 3), 255, np.uint8))
    assert r.model == "fast-model" and vision.model_name() == "fast-model"
    vision._resolved.clear()


def test_all_models_failing_reports_every_attempt(monkeypatch):
    import numpy as np, pytest
    from app import vision, config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k"); monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "gemini"); monkeypatch.setattr(config, "VISION_MODEL", "a")
    monkeypatch.setattr(config, "VISION_MODEL_STRICT", False); vision._resolved.clear()
    def fake(image, mt, model, timeout=None):
        raise vision.VisionTimeout("timed out")
    monkeypatch.setattr(vision, "_call_gemini", fake)
    monkeypatch.setattr(vision, "discover_gemini_models", lambda: ["b"])
    with pytest.raises(vision.VisionError) as e:
        vision.read_label(np.full((50, 50, 3), 255, np.uint8))
    assert "a:" in str(e.value) and "b:" in str(e.value)
    vision._resolved.clear()


def test_overloaded_503_falls_back_to_another_model(monkeypatch):
    import numpy as np
    from app import vision, config
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k"); monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "VISION_PROVIDER", "gemini"); monkeypatch.setattr(config, "VISION_MODEL", "busy-model")
    monkeypatch.setattr(config, "VISION_MODEL_STRICT", False); vision._resolved.clear()
    def fake(image, mt, model, timeout=None):
        if model == "busy-model":
            raise vision.VisionBusy("AI reader unavailable: the AI service answered 503: high demand")
        return '{"lines":[{"text":"NET WT 200 g"}]}'
    monkeypatch.setattr(vision, "_call_gemini", fake)
    monkeypatch.setattr(vision, "discover_gemini_models", lambda: ["busy-model", "other-model"])
    assert vision.read_label(np.full((50, 50, 3), 255, np.uint8)).model == "other-model"
    vision._resolved.clear()


def test_post_json_raises_busy_after_retries(monkeypatch):
    import pytest
    httpx = pytest.importorskip("httpx")
    from app import vision
    class R:
        status_code = 503
        text = "x"
        def json(self): return {"error": {"message": "high demand"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: R())
    monkeypatch.setattr(vision.time, "sleep", lambda s: None)
    with pytest.raises(vision.VisionBusy):
        vision._post_json("http://x", {}, {}, 5)


def test_parse_reading_keeps_structured_fields_and_drops_nulls():
    from app import vision
    raw = ('{"lines":[{"text":"Item : Origami Face Tissue Box"}],'
           '"fields":{"product_name":"Origami Face Tissue Box","net_quantity":null}}')
    rd = vision.parse_reading(raw, "gemini", "m")
    assert rd.fields == {"product_name": "Origami Face Tissue Box"}
    assert rd.as_dict()["fields"] == {"product_name": "Origami Face Tissue Box"}
