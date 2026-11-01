"""Image-geometry assessments that do not need real-world scale.

Rule 8 (clear space around the net quantity)
    The requirement is relative to the numeral's own height: above/below >= 1 x height,
    left/right >= 2 x height. Ratios inside one photo do not depend on camera distance, so the
    check can be estimated from the image -- unlike Rule 7, which needs millimetres and is
    skipped by team decision. Two independent pieces of evidence are used:

    1. OCR boxes of *other* text inside the required clear zone (box geometry), and
    2. ink inside the clear zone in the image itself, so fine print the OCR did not detect is
       still noticed.

    A PASS is only returned when both are clean with a margin and the zone lies inside the
    photo. Anything else is REVIEW with the measurements. A FAIL is never produced
    automatically: OCR box heights are only an approximation of numeral height.

Rule 9 contrast
    Luminance contrast between text pixels and background pixels inside each declaration's box
    (Otsu split). This is a measurement of the photo, not of the printed label under standard
    lighting, so low values are routed to review, never failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

BBox = Tuple[float, float, float, float]

# EasyOCR adds ~10% margin around a detected box and the box covers ascenders/descenders;
# digit cap height is roughly 0.7 of the box height.
NUMERAL_HEIGHT_FRACTION = 0.7
PASS_MARGIN = 1.25  # clearances must exceed the requirement by 25% to be passed
INK_THRESHOLD = 0.02  # fraction of dark/light pixels in a zone that counts as "printed matter"


@dataclass
class ClearSpace:
    status: str  # PASS | REVIEW | NOT_ASSESSABLE
    numeral_height_px: float
    measurements: Dict[str, Optional[float]] = field(default_factory=dict)  # clearance / required, per side
    crowded_by: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def _ink_fraction(gray: np.ndarray, box: BBox) -> Optional[float]:
    import cv2

    H, W = gray.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x1 - x0 < 2 or y1 - y0 < 2:
        return None
    zone = gray[y0:y1, x0:x1]
    # local contrast against the zone's own background (works for dark-on-light and light-on-dark)
    bg = float(np.median(zone))
    diff = np.abs(zone.astype(np.int16) - int(bg))
    k = max(1, min(zone.shape) // 20)
    diff = cv2.medianBlur(diff.astype(np.uint8), 3) if k >= 1 else diff
    return float(np.mean(diff > 60))


def assess_clear_space(
    decl_box: BBox,
    other_boxes: Sequence[Tuple[str, BBox]],
    image_size: Tuple[int, int],
    gray: Optional[np.ndarray] = None,
) -> ClearSpace:
    x0, y0, x1, y1 = decl_box
    nh = max(1.0, (y1 - y0) * NUMERAL_HEIGHT_FRACTION)
    pad = (y1 - y0 - nh) / 2  # box margin already counts as clearance
    req = {"above": nh, "below": nh, "left": 2 * nh, "right": 2 * nh}
    W, H = image_size
    zones = {
        "above": (x0, y0 - req["above"] + pad, x1, y0),
        "below": (x0, y1, x1, y1 + req["below"] - pad),
        "left": (x0 - req["left"] + pad, y0, x0, y1),
        "right": (x1, y0, x1 + req["right"] - pad, y1),
    }
    res = ClearSpace("PASS", round(nh, 1))

    # 1. OCR box evidence: nearest other text on each side
    for side in ("above", "below", "left", "right"):
        best = None
        for name, b in other_boxes:
            if side in ("above", "below"):
                if min(b[2], x1) - max(b[0], x0) <= 0:
                    continue
                d = (y0 - b[3]) if side == "above" else (b[1] - y1)
            else:
                if min(b[3], y1) - max(b[1], y0) <= 0.3 * (y1 - y0):
                    continue
                d = (x0 - b[2]) if side == "left" else (b[0] - x1)
            if d < -0.5 * (y1 - y0):
                continue  # on the other side
            d = max(0.0, d) + pad
            if best is None or d < best[0]:
                best = (d, name)
        if best is None:
            res.measurements[side] = None
        else:
            ratio = best[0] / req[side]
            res.measurements[side] = round(ratio, 2)
            if ratio < 1.0:
                res.crowded_by.append(f"{side}: '{best[1]}' at {ratio:.2f}x the required space")
                res.status = "REVIEW"
            elif ratio < PASS_MARGIN:
                res.reasons.append(f"{side}: clearance {ratio:.2f}x the requirement, too close to call")
                res.status = "REVIEW"

    # 2. the zone must be inside the photo, otherwise it may simply be cropped
    for side, z in zones.items():
        if z[0] < 0 or z[1] < 0 or z[2] > W or z[3] > H:
            res.reasons.append(f"{side}: required clear zone runs off the photo edge; cannot verify")
            res.status = "REVIEW"

    # 3. ink inside the zones (catches fine print OCR did not detect)
    if gray is None:
        res.reasons.append("image pixels not available: undetected fine print could not be ruled out")
        res.status = "REVIEW"
    else:
        for side, z in zones.items():
            frac = _ink_fraction(gray, z)
            if frac is not None and frac > INK_THRESHOLD:
                res.reasons.append(f"{side}: printed matter inside the required clear zone ({frac:.0%} of pixels)")
                res.status = "REVIEW"
    return res


def text_contrast(gray: np.ndarray, box: BBox) -> Optional[float]:
    """Luminance contrast (0..1) between text and background inside a box, via Otsu split."""
    import cv2

    H, W = gray.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    roi = gray[y0:y1, x0:x1]
    t, mask = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    a, b = roi[mask > 0], roi[mask == 0]
    if a.size < 5 or b.size < 5:
        return None
    # text is the minority class
    fg, bg = (a, b) if a.size < b.size else (b, a)
    return round(abs(float(np.median(bg)) - float(np.median(fg))) / 255.0, 3)
