"""Image clean-up before OCR (OpenCV).

What changed from the original and why (measured on the Bhaskar Book Tech sample, see
docs/ARCHITECTURE.md):

* The original always ran ``fastNlMeansDenoising(h=7)``. On small label text (about 20 px
  high) that smears decimal points and thin strokes -- exactly the characters that carry the
  price (``60.00``) and the plot number (``267/16A``). Denoising is now conditional on a
  measured noise level, and much gentler.
* The original only upscaled images whose longest side was under 1000 px. A 1280 px wide
  photo of a long, thin label was left with ~20 px text. Upscaling is now driven by the
  estimated *text height* (target ~36 px, capped by ``max_side``).
* Uneven illumination (shadows, glare gradients) is corrected by background division, but
  only when the background is measurably uneven.
* Small rotations (0.5 to 15 degrees) are corrected by deskewing on the text mask.
* Printed vertical rules (column separators) are detected so the layout stage can avoid
  merging text across them.
* Perspective correction is implemented but OFF by default: on real packaging the largest
  quadrilateral is often a sticker, and warping to it would crop text outside the sticker.

No binarization is applied for EasyOCR: its recogniser is trained on grey images and hard
thresholding removes the anti-aliasing that small characters depend on. A thresholded
variant is still produced as a fallback candidate (see ``variants``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .layout import Separator

MAX_PIXELS = 40_000_000  # refuse to process decompression bombs


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # honours EXIF rotation
    if img is None:
        raise ValueError("Could not decode image. Upload a JPG, PNG or WEBP photo.")
    h, w = img.shape[:2]
    if h * w > MAX_PIXELS:
        s = (MAX_PIXELS / float(h * w)) ** 0.5
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return img


@dataclass
class PreprocessReport:
    scale: float = 1.0
    text_height_px: Optional[float] = None
    deskew_degrees: float = 0.0
    illumination_corrected: bool = False
    denoised: bool = False
    perspective_corrected: bool = False
    variant: str = "gray_enhanced"
    notes: List[str] = field(default_factory=list)
    # resized (and deskewed) grayscale WITHOUT contrast enhancement, same coordinates as the
    # OCR image. Used for measurements (Rule 8 ink, Rule 9 contrast). Not serialized.
    raw_gray: Optional[np.ndarray] = field(default=None, repr=False)

    def as_dict(self) -> Dict:
        return {
            "scale": round(self.scale, 3),
            "text_height_px": None if self.text_height_px is None else round(self.text_height_px, 1),
            "deskew_degrees": round(self.deskew_degrees, 2),
            "illumination_corrected": self.illumination_corrected,
            "denoised": self.denoised,
            "perspective_corrected": self.perspective_corrected,
            "variant": self.variant,
            "notes": self.notes,
        }


def _gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _text_mask(gray: np.ndarray) -> np.ndarray:
    """Dark-on-light and light-on-dark text strokes via a morphological gradient."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, k)
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return bw


def estimate_text_height(gray: np.ndarray) -> Optional[float]:
    """Median height of character-sized connected components (pixels)."""
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    H, W = gray.shape[:2]
    hs = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 4 <= h <= H * 0.25 and 1 <= w <= h * 3 and area >= 8 and area <= w * h * 0.95:
            hs.append(h)
    if len(hs) < 10:
        return None
    return float(np.median(hs))


def noise_sigma(gray: np.ndarray) -> float:
    """Fast noise estimate (Immerkaer 1996)."""
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
    conv = cv2.filter2D(gray.astype(np.float32), -1, k)
    H, W = gray.shape[:2]
    return float(np.sum(np.abs(conv)) * np.sqrt(0.5 * np.pi) / (6.0 * max(1, (W - 2) * (H - 2))))


def illumination_unevenness(gray: np.ndarray) -> Tuple[float, np.ndarray]:
    k = max(15, (min(gray.shape[:2]) // 8) | 1)
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
    m = float(np.mean(bg)) or 1.0
    return float(np.std(bg)) / m, bg


def estimate_skew(gray: np.ndarray) -> float:
    """Dominant text-line angle in degrees (positive = counter-clockwise), 0 if unsure."""
    mask = _text_mask(gray)
    # join characters into line blobs, then take the median angle of elongated blobs
    kw = max(15, gray.shape[1] // 60)
    joined = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kw, 3)))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles, weights = [], []
    for c in contours:
        rect = cv2.minAreaRect(c)
        w, h = rect[1]
        long_side, short_side = max(w, h), min(w, h)
        if long_side < 40 or short_side < 4 or long_side / max(short_side, 1) < 4:
            continue
        pts = cv2.boxPoints(rect)
        # direction of the long edge, independent of OpenCV's minAreaRect angle convention
        edges = [pts[(i + 1) % 4] - pts[i] for i in range(4)]
        e = max(edges, key=lambda v: float(np.hypot(v[0], v[1])))
        a = float(np.degrees(np.arctan2(e[1], e[0])))  # image coords: + = clockwise
        while a > 90:
            a -= 180
        while a <= -90:
            a += 180
        if abs(a) > 45:
            continue
        angles.append(-a)  # report counter-clockwise as positive
        weights.append(long_side)
    if len(angles) < 3:
        return 0.0
    order = np.argsort(angles)
    a_sorted = np.array(angles)[order]
    w_sorted = np.array(weights)[order]
    cum = np.cumsum(w_sorted)
    return float(a_sorted[np.searchsorted(cum, cum[-1] / 2)])


def rotate(gray: np.ndarray, degrees: float) -> np.ndarray:
    H, W = gray.shape[:2]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), degrees, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nW, nH = int(H * sin + W * cos), int(H * cos + W * sin)
    M[0, 2] += nW / 2 - W / 2
    M[1, 2] += nH / 2 - H / 2
    border = int(np.median(gray))
    return cv2.warpAffine(gray, M, (nW, nH), flags=cv2.INTER_CUBIC, borderValue=border)


def correct_perspective(img: np.ndarray) -> Tuple[np.ndarray, bool]:
    """Warp to the dominant label quadrilateral if one clearly exists. Off by default."""
    gray = _gray(img)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = gray.shape[:2]
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and 0.4 * H * W < area < 0.98 * H * W:
            pts = approx.reshape(4, 2).astype(np.float32)
            s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
            tl, br, tr, bl = pts[np.argmin(s)], pts[np.argmax(s)], pts[np.argmin(d)], pts[np.argmax(d)]
            w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
            h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
            M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl]), np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32))
            return cv2.warpPerspective(img, M, (w, h)), True
    return img, False


def find_vertical_rules(gray: np.ndarray, min_frac: float = 0.2) -> List[Separator]:
    """Printed vertical lines (column separators). Long, thin, dark-or-light strokes."""
    H, W = gray.shape[:2]
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 10)
    klen = max(15, int(H * min_frac))
    # tolerate a residual tilt of a degree or two: widen strokes slightly before the vertical opening
    bw = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, klen)))
    contours, _ = cv2.findContours(vert, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    seps = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if h >= klen and w <= max(14, W * 0.012):
            seps.append(Separator(x + w / 2.0, float(y), float(y + h)))
    return sorted(seps, key=lambda s: s.x)


def preprocess_with_report(
    img: np.ndarray,
    max_side: int = 2000,
    min_side: int = 1000,
    target_text_px: float = 36.0,
    deskew: bool = True,
    perspective: bool = False,
) -> Tuple[np.ndarray, PreprocessReport]:
    rep = PreprocessReport()
    if perspective and img.ndim == 3:
        img, rep.perspective_corrected = correct_perspective(img)

    h, w = img.shape[:2]
    longest = max(h, w)
    gray0 = _gray(img)
    th = estimate_text_height(gray0) if longest <= max_side * 2 else None
    rep.text_height_px = th
    scale = 1.0
    if longest > max_side:
        scale = max_side / longest
    else:
        if th and th < target_text_px:
            scale = min(target_text_px / th, max_side / longest, 4.0)
        if longest * scale < min_side:
            scale = min_side / longest
    if abs(scale - 1.0) > 1e-3:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
    rep.scale = scale
    gray = _gray(img)
    raw = gray.copy()

    unevenness, bg = illumination_unevenness(gray)
    if unevenness > 0.08:
        gray = cv2.divide(gray, np.maximum(bg, 1), scale=255)
        rep.illumination_corrected = True
        rep.notes.append(f"background unevenness {unevenness:.2f} > 0.08: divided out")

    sigma = noise_sigma(gray)
    if sigma > 6.0:
        gray = cv2.fastNlMeansDenoising(gray, None, h=min(7.0, sigma * 0.6), templateWindowSize=7, searchWindowSize=21)
        rep.denoised = True
        rep.notes.append(f"noise sigma {sigma:.1f} > 6: gentle denoise")

    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    if deskew:
        angle = estimate_skew(gray)
        if 0.5 <= abs(angle) <= 15:
            gray = rotate(gray, -angle)
            raw = rotate(raw, -angle)
            rep.deskew_degrees = angle
            rep.notes.append(f"deskewed by {angle:.1f} degrees")
    rep.raw_gray = raw
    return gray, rep


def preprocess(img: np.ndarray, max_side: int = 2000, min_side: int = 1000) -> np.ndarray:
    """Backward-compatible single-variant entry point (grayscale out)."""
    return preprocess_with_report(img, max_side=max_side, min_side=min_side)[0]


def variants(gray: np.ndarray) -> Dict[str, np.ndarray]:
    """Fallback candidates, tried only when the primary OCR pass is weak (see app.ocr)."""
    sharp = cv2.addWeighted(gray, 1.5, cv2.GaussianBlur(gray, (0, 0), 1.2), -0.5, 0)
    binar = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
    return {"sharpened": sharp, "adaptive_threshold": binar}
