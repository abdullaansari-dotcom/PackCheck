"""Supabase logging over the REST API (no SDK needed). Every function degrades gracefully:
if Supabase is not configured or a call fails, the scan still works and nothing is raised."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import httpx

from . import config
from .models import ScanResult

log = logging.getLogger("packcheck.db")
_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _h(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"apikey": config.SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}"}
    h.update(extra or {})
    return h


def save_scan(result: ScanResult, image_bytes: Optional[bytes] = None,
              content_type: str = "image/jpeg") -> Optional[str]:
    if not config.supabase_enabled():
        return None
    sid = str(uuid.uuid4())
    try:
        with httpx.Client(timeout=20) as c:
            image_path = None
            if image_bytes:
                path = f"{sid}.{_EXT.get(content_type, 'jpg')}"
                r = c.post(f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{path}",
                           headers=_h({"Content-Type": content_type, "x-upsert": "true"}), content=image_bytes)
                if r.is_success:
                    image_path = path
                else:
                    log.warning("image upload failed: %s %s", r.status_code, r.text[:200])
            row = {
                "id": sid,
                "category": result.category,
                "pack_type": result.pack_type,
                "input_mode": result.input_mode,
                "image_path": image_path,
                "raw_text": result.raw_text,
                "avg_ocr_confidence": result.avg_ocr_confidence,
                "verdict": result.verdict,
                "fail_count": result.summary.get("FAIL", 0),
                "review_count": result.summary.get("REVIEW", 0),
                "result": result.model_dump(mode="json"),
            }
            r = c.post(f"{config.SUPABASE_URL}/rest/v1/scans",
                       headers=_h({"Content-Type": "application/json", "Prefer": "return=minimal"}), json=row)
            r.raise_for_status()
        return sid
    except Exception:
        log.exception("could not save scan to Supabase")
        return None


def list_scans(limit: int = 20) -> List[Dict[str, Any]]:
    if not config.supabase_enabled():
        return []
    try:
        r = httpx.get(f"{config.SUPABASE_URL}/rest/v1/scans", headers=_h(), timeout=15, params={
            "select": "id,created_at,category,verdict,fail_count,review_count,input_mode",
            "order": "created_at.desc", "limit": str(limit)})
        r.raise_for_status()
        return r.json()
    except Exception:
        log.exception("could not list scans")
        return []


def get_scan(scan_id: str) -> Optional[Dict[str, Any]]:
    if not config.supabase_enabled():
        return None
    try:
        r = httpx.get(f"{config.SUPABASE_URL}/rest/v1/scans", headers=_h(), timeout=15,
                      params={"select": "result", "id": f"eq.{scan_id}", "limit": "1"})
        r.raise_for_status()
        rows = r.json()
        return rows[0]["result"] if rows else None
    except Exception:
        log.exception("could not fetch scan")
        return None
