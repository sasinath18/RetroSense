"""Experimental OCR for industrial digital-display images.

Requires the Tesseract OCR executable installed on the host and pytesseract installed
in the Python environment. This is not a certified measurement instrument.
"""
import math
import re

import cv2
import numpy as np

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # Keep analog-only installations usable.
    pytesseract = None
    Output = None


class DigitalReadError(ValueError):
    pass


def _normalise_display(gray):
    """Create an enlarged, high-contrast display image for OCR."""
    height, width = gray.shape
    scale = max(2, min(4, 1200 // max(width, height)))
    enlarged = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(enlarged)
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    _, thresholded = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    # OCR works with dark text on a light background.
    if np.mean(thresholded) < 127:
        thresholded = cv2.bitwise_not(thresholded)
    return thresholded


def read_digital_display(image_bytes):
    if pytesseract is None:
        raise DigitalReadError(
            "Digital OCR dependency is missing. Install pytesseract and the Tesseract OCR system executable."
        )
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise DigitalReadError("Could not decode image. Upload a valid JPG or PNG.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    prepared = _normalise_display(gray)

    # Different page-segmentation modes help with single-line meters and displays
    # containing separate groups of digits. Disagreement is surfaced to the user.
    configs = (6, 7, 8, 13)
    candidates = []
    errors = []
    for psm in configs:
        config = (
            f"--oem 3 --psm {psm} "
            "-c tessedit_char_whitelist=0123456789.-+"
        )
        try:
            data = pytesseract.image_to_data(
                prepared, config=config, output_type=Output.DICT
            )
        except Exception as exc:
            errors.append(exc)
            continue

        tokens = []
        for text, raw_confidence in zip(data["text"], data["conf"]):
            token = re.sub(r"[^0-9.+-]", "", text.strip())
            if not token:
                continue
            try:
                value = float(token)
                score = float(raw_confidence)
            except (TypeError, ValueError):
                continue
            tokens.append({
                "text": token,
                "value": value,
                "confidence": score if score >= 0 else None,
                "psm": psm,
            })

        if tokens:
            candidates.append(max(
                tokens,
                key=lambda item: item["confidence"]
                if item["confidence"] is not None else -1,
            ))

    if not candidates:
        if errors and len(errors) == len(configs):
            raise DigitalReadError(
                "Tesseract OCR could not run. Check that the Tesseract executable is installed and available on PATH."
            ) from errors[0]
        raise DigitalReadError(
            "No numeric display value detected. Crop the display tightly, reduce glare and ensure the digits are in focus."
        )

    # Keep the previous highest-confidence selection, but explicitly identify
    # when alternate segmentation modes disagree instead of hiding ambiguity.
    selected = max(
        candidates,
        key=lambda item: item["confidence"]
        if item["confidence"] is not None else -1,
    )
    candidate_values = []
    for candidate in candidates:
        if not any(
            math.isclose(candidate["value"], value, rel_tol=0.0, abs_tol=1e-9)
            for value in candidate_values
        ):
            candidate_values.append(candidate["value"])
    ambiguous = len(candidate_values) > 1
    confidence = selected["confidence"]
    note = (
        "OCR configurations disagree. Check the displayed digits and decimal point manually; "
        "candidate readings are provided. OCR confidence is not measurement accuracy."
        if ambiguous else
        "Experimental OCR result. Verify the displayed digits and decimal point manually; "
        "OCR confidence is not measurement accuracy."
    )
    return {
        "value": selected["value"],
        "raw_text": selected["text"],
        "confidence": round(confidence, 1) if confidence is not None else None,
        "confidence_type": "tesseract_token_score_0_to_100",
        "method": "tesseract_ocr_multi_psm",
        "psm_used": selected["psm"],
        "candidate_values": candidate_values,
        "ambiguous": ambiguous,
        "note": note,
    }
