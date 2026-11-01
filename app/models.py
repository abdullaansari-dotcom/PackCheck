from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

# REVIEW is the "NEEDS REVIEW" status (value kept as REVIEW for API compatibility).
Status = Literal[
    "PASS",
    "FAIL",
    "REVIEW",
    "NOT_APPLICABLE",
    "EXEMPT",
    "SKIPPED_BY_TEAM_DECISION",
    "NOT_CONFIGURED",
]
STATUSES = ["PASS", "FAIL", "REVIEW", "NOT_APPLICABLE", "EXEMPT", "SKIPPED_BY_TEAM_DECISION", "NOT_CONFIGURED"]
ViolationCode = Literal[
    "MISSING",
    "FORMAT_ERROR",
    "UNIT_ERROR",
    "NONSTANDARD_PACK",
    "VAGUE_LANGUAGE",
    "LANGUAGE_ERROR",
    "LOW_CONFIDENCE",
]
Verdict = Literal["COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW", "EXEMPT"]


class Evidence(BaseModel):
    """One piece of supporting text: what was read, what it was normalized to, and how sure we are."""

    label: str
    text: str  # normalized reading
    original: Optional[str] = None  # raw OCR reading, if different
    confidence: Optional[float] = None
    bbox: Optional[List[float]] = None
    normalizations: List[Dict[str, Any]] = []
    image: Optional[int] = None  # 0 = front, 1 = back (only set when two photos were scanned)


class FieldResult(BaseModel):
    """Superset of the per-field schema in the rulebook (Part D)."""

    field: str
    status: Status
    violation_code: Optional[ViolationCode] = None
    detected_text: Optional[str] = None
    rule_reference: str
    detail: Optional[str] = None
    sub_case: Optional[str] = None
    confidence: Optional[float] = None
    # added in PackCheck 2
    title: Optional[str] = None
    original_text: Optional[str] = None
    normalized_text: Optional[str] = None
    evidence: List[Evidence] = []
    applicability: Optional[str] = None
    limitation: Optional[str] = None
    legal_question: Optional[str] = None


class ScanResult(BaseModel):
    scan_id: Optional[str] = None
    input_mode: Literal["image", "text"]
    category: str
    pack_type: Optional[str] = None
    verdict: Verdict
    summary: Dict[str, int]
    exemption: Optional[Dict[str, str]] = None
    fields: List[FieldResult]
    limitations: List[str]
    raw_text: str  # normalized text the rules read (one line per layout line)
    avg_ocr_confidence: Optional[float] = None
    # added in PackCheck 2
    original_text: Optional[str] = None  # OCR text exactly as recognised
    classification: Optional[Dict[str, Any]] = None
    product_info: Dict[str, Any] = {}
    legal_questions: List[Dict[str, str]] = []
    ocr: Optional[Dict[str, Any]] = None  # engines, preprocessing report, regions, tokens


class TextCheckRequest(BaseModel):
    text: str
    category: str = "auto"
    pack_type: Optional[str] = None
