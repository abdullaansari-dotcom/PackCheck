import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
from app.preprocess import decode_image, preprocess


def test_roundtrip_and_shape():
    img = np.full((600, 900, 3), 255, np.uint8)
    cv2.putText(img, "Net Wt. 100g", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 6)
    ok, buf = cv2.imencode(".png", img)
    out = preprocess(decode_image(buf.tobytes()))
    assert out.ndim == 2 and max(out.shape) >= 1000   # grayscale, small images upscaled


def test_big_images_are_downscaled():
    out = preprocess(np.zeros((4000, 3000, 3), np.uint8))
    assert max(out.shape) == 2000


def test_bad_bytes():
    with pytest.raises(ValueError):
        decode_image(b"junk")


# ---------------------------------------------------------------- PackCheck 2 additions
from pathlib import Path

from app.preprocess import estimate_skew, find_vertical_rules, preprocess_with_report, rotate

LABEL = Path(__file__).parent / "fixtures" / "bhaskar_label.jpg"


def test_small_text_is_upscaled_by_text_height():
    img = cv2.imread(str(LABEL))
    out, rep = preprocess_with_report(img, max_side=2560)
    assert rep.text_height_px and rep.text_height_px < 30
    assert rep.scale > 1.5 and max(out.shape) <= 2560
    assert rep.raw_gray is not None and rep.raw_gray.shape == out.shape


def test_vertical_rules_found_on_real_label():
    out, _ = preprocess_with_report(cv2.imread(str(LABEL)), max_side=2560)
    xs = [s.x for s in find_vertical_rules(out)]
    assert any(1700 < x < 1790 for x in xs) and any(2320 < x < 2420 for x in xs)


@pytest.mark.parametrize("deg", [-6, 4, 10])
def test_rotation_is_corrected(deg):
    gray = cv2.cvtColor(cv2.imread(str(LABEL)), cv2.COLOR_BGR2GRAY)
    M = cv2.getRotationMatrix2D((gray.shape[1] / 2, gray.shape[0] / 2), deg, 1)
    tilted = cv2.warpAffine(gray, M, (gray.shape[1], gray.shape[0]), borderValue=255)
    est = estimate_skew(tilted)
    assert abs(est - deg) < 1.5
    assert abs(estimate_skew(rotate(tilted, -est))) < abs(deg) / 2


def test_straight_label_is_not_rotated():
    _, rep = preprocess_with_report(cv2.imread(str(LABEL)), max_side=2560)
    assert rep.deskew_degrees == 0.0


def test_clean_image_is_not_denoised():
    """Strong denoising erased decimal points on small text in the original pipeline."""
    _, rep = preprocess_with_report(cv2.imread(str(LABEL)), max_side=2560)
    assert rep.denoised is False
