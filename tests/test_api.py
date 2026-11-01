import pytest

pytest.importorskip("fastapi")  # API tests need the web stack from requirements.txt
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app

client = TestClient(app)


def test_health_and_static():
    assert client.get("/health").json()["status"] == "ok"
    assert "PackCheck" in client.get("/").text


def test_categories_and_samples():
    assert any(c["key"] == "tea" for c in client.get("/api/categories").json())
    assert len(client.get("/api/samples").json()) >= 3


def test_check_text_returns_schema():
    r = client.post("/api/check-text", json={"text": "Tea\nNet Wt. approx 120g", "category": "tea"})
    assert r.status_code == 200
    body = r.json()
    nq = next(f for f in body["fields"] if f["field"] == "net_quantity")
    assert nq["violation_code"] == "VAGUE_LANGUAGE" and nq["rule_reference"] == "Rule 6(1)(c)"
    assert body["verdict"] == "NON_COMPLIANT"


def test_validation_errors():
    assert client.post("/api/check-text", json={"text": "x", "category": "nope"}).status_code == 422
    assert client.post("/api/check-text", json={"text": "  "}).status_code == 422
    assert client.post("/api/check-text", json={"text": "x", "pack_type": "jar"}).status_code == 422


def test_scan_rejects_non_image():
    r = client.post("/api/scan", files={"file": ("a.txt", b"hello", "text/plain")}, data={"category": "tea"})
    assert r.status_code == 415


def test_scan_rejects_corrupt_image():
    pytest.importorskip("cv2")
    r = client.post("/api/scan", files={"file": ("a.jpg", b"not an image", "image/jpeg")}, data={"category": "tea"})
    assert r.status_code in (400, 503)


def test_history_without_supabase():
    assert client.get("/api/history").json() == {"enabled": False, "scans": []}
    assert client.get("/api/scans/abc").status_code == 404


# ---------------------------------------------------------------- PackCheck 2 additions
def test_categories_include_auto_and_stationery():
    keys = {c["key"] for c in client.get("/api/categories").json()}
    assert {"auto", "notebook", "exercise_book", "register", "diary", "writing_pad"} <= keys


def test_rules_endpoint_lists_rule7_and_rule8_separately():
    body = client.get("/api/rules").json()
    refs = {r["field"]: r["rule_reference"] for r in body["rules"]}
    assert refs["numeral_height"] == "Rule 7" and refs["clear_space"] == "Rule 8"
    assert body["open_legal_questions"]


def test_check_text_defaults_to_auto_category():
    r = client.post("/api/check-text", json={"text": "Long Notebook\n172 Pages\nNet Qty: 1 N"})
    body = r.json()
    assert r.status_code == 200 and body["category"] == "notebook"
    assert body["classification"]["source"] == "inferred"
    statuses = {f["field"]: f["status"] for f in body["fields"]}
    assert statuses["numeral_height"] == "SKIPPED_BY_TEAM_DECISION"


def test_scan_real_photo_end_to_end():
    pytest.importorskip("easyocr")
    from pathlib import Path
    data = (Path(__file__).parent / "fixtures" / "bhaskar_label.jpg").read_bytes()
    r = client.post("/api/scan", files={"file": ("bhaskar.jpg", data, "image/jpeg")}, data={"category": "auto"})
    assert r.status_code == 200, r.text
    fields = {f["field"]: f for f in r.json()["fields"]}
    assert fields["mrp"]["violation_code"] != "MISSING"


# ---------------------------------------------------------------- front + back photos
def _fake_scan(monkeypatch, seen):
    pytest.importorskip("cv2")
    from app import pipeline
    from app.engine import analyze_text

    def fake(blobs, category="auto", pack_type=None, reader=None):
        seen["blobs"] = list(blobs)
        return analyze_text("MRP Rs. 60.00", "other")

    monkeypatch.setattr(pipeline, "scan_images_bytes", fake)


def test_scan_accepts_front_and_back(monkeypatch):
    seen = {}
    _fake_scan(monkeypatch, seen)
    r = client.post("/api/scan", files={"file": ("f.jpg", b"front", "image/jpeg"),
                                        "file_back": ("b.png", b"back", "image/png")}, data={"category": "other"})
    assert r.status_code == 200, r.text
    assert seen["blobs"] == [b"front", b"back"]


def test_scan_back_is_optional(monkeypatch):
    seen = {}
    _fake_scan(monkeypatch, seen)
    r = client.post("/api/scan", files={"file": ("f.jpg", b"front", "image/jpeg")}, data={"category": "other"})
    assert r.status_code == 200 and seen["blobs"] == [b"front"]


def test_scan_rejects_non_image_back(monkeypatch):
    _fake_scan(monkeypatch, {})
    r = client.post("/api/scan", files={"file": ("f.jpg", b"front", "image/jpeg"),
                                        "file_back": ("b.txt", b"hello", "text/plain")}, data={"category": "other"})
    assert r.status_code == 415 and "Back photo" in r.json()["detail"]


def test_scan_back_only_is_enough(monkeypatch):
    seen = {}
    _fake_scan(monkeypatch, seen)
    r = client.post("/api/scan", files={"file_back": ("b.png", b"back", "image/png")}, data={"category": "other"})
    assert r.status_code == 200 and seen["blobs"] == [b"back"]


def test_scan_back_and_optional_front(monkeypatch):
    seen = {}
    _fake_scan(monkeypatch, seen)
    r = client.post("/api/scan", files={"file_back": ("b.png", b"back", "image/png"),
                                        "file_front": ("f.jpg", b"front", "image/jpeg")}, data={"category": "other"})
    assert r.status_code == 200 and seen["blobs"] == [b"front", b"back"]  # fixed order: front, back


def test_scan_needs_at_least_one_photo(monkeypatch):
    _fake_scan(monkeypatch, {})
    r = client.post("/api/scan", data={"category": "other"})
    assert r.status_code == 422
