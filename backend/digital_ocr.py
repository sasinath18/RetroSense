"""Experimental OCR for industrial digital-display images.

Requires the Tesseract OCR executable installed on the host and pytesseract installed
in the Python environment. This is not a certified measurement instrument.
"""
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
    config = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.-+"
    try:
        data = pytesseract.image_to_data(
            prepared, config=config, output_type=Output.DICT
        )
    except Exception as exc:
        raise DigitalReadError(
            "Tesseract OCR could not run. Check that the Tesseract executable is installed and available on PATH."
        ) from exc

    tokens = []
    confidences = []
    for text, confidence in zip(data["text"], data["conf"]):
        token = re.sub(r"[^0-9.+-]", "", text.strip())
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        tokens.append((token, value))
        try:
            score = float(confidence)
            if score >= 0:
                confidences.append(score)
        except (TypeError, ValueError):
            pass

    if not tokens:
        raise DigitalReadError(
            "No numeric display value detected. Crop the display tightly, reduce glare and ensure the digits are in focus."
        )
    if len(tokens) > 1:
        # Keep the most confident numeric token rather than concatenating unrelated labels.
        best_index = max(
            range(len(tokens)),
            key=lambda i: confidences[i] if i < len(confidences) else -1
        )
    else:
        best_index = 0
    text, value = tokens[best_index]
    confidence = confidences[best_index] if best_index < len(confidences) else None
    return {
        "value": value,
        "raw_text": text,
        "confidence": round(confidence, 1) if confidence is not None else None,
        "confidence_type": "tesseract_token_score_0_to_100",
        "method": "tesseract_ocr_preprocessed",
        "note": "Experimental OCR result. Verify the displayed digits and decimal point manually; OCR confidence is not measurement accuracy.",
    }
