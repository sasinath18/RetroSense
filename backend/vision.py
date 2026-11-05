"""Experimental analog dial reader using OpenCV; requires a clear, front-facing circular gauge."""
import math

import cv2
import numpy as np


class GaugeReadError(ValueError):
    pass


def _wrap_delta(angle, start):
    return (angle - start + 360.0) % 360.0


def angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle):
    """Map an image-coordinate angle onto a calibrated dial sweep."""
    if max_value <= min_value:
        raise GaugeReadError("Maximum value must be greater than minimum value.")
    sweep = _wrap_delta(end_angle, start_angle)
    if sweep < 1 or sweep > 359:
        raise GaugeReadError("Invalid calibration angles.")
    position = _wrap_delta(pointer_angle, start_angle)
    fraction = position / sweep
    if fraction > 1.0:
        raise GaugeReadError("Pointer appears outside the calibrated scale. Check start/end angles.")
    return min_value + fraction * (max_value - min_value)


def _select_gauge_circle(circles, image_width, image_height):
    """Prefer a plausible dial circle near the image centre over large background arcs."""
    if circles is None:
        raise GaugeReadError("Gauge dial circle not detected. Use a clear, front-facing image.")
    min_dimension = min(image_width, image_height)
    candidates = []
    for x, y, radius in circles[0]:
        offset = math.hypot(x - image_width / 2, y - image_height / 2)
        if radius < min_dimension * 0.25:
            continue
        if offset > min_dimension * 0.22:
            continue
        # Centrality is the primary criterion; a modest radius preference breaks ties.
        score = offset - radius * 0.02
        candidates.append((score, float(x), float(y), float(radius)))
    if not candidates:
        raise GaugeReadError(
            "Could not identify a dial circle near the image centre. Crop the gauge and try again."
        )
    _, cx, cy, radius = min(candidates)
    return cx, cy, radius


def read_analog_gauge(image_bytes, min_value, max_value, start_angle=135.0, end_angle=45.0):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise GaugeReadError("Could not decode image. Upload a valid JPG or PNG.")
    if max_value <= min_value:
        raise GaugeReadError("Maximum value must be greater than minimum value.")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.GaussianBlur(gray, (5, 5), 1.2)
    h, w = gray.shape
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=max(30, min(h, w) // 3), param1=120, param2=38,
        minRadius=max(20, min(h, w) // 8), maxRadius=min(h, w) // 2
    )
    cx, cy, radius = _select_gauge_circle(circles, w, h)

    edges = cv2.Canny(gray, 45, 130)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=max(25, int(radius * 0.22)),
        minLineLength=max(20, int(radius * 0.28)),
        maxLineGap=max(8, int(radius * 0.08))
    )
    if lines is None:
        raise GaugeReadError("No pointer-like line detected in the dial.")

    sweep = _wrap_delta(end_angle, start_angle)
    if sweep < 1 or sweep > 359:
        raise GaugeReadError("Invalid calibration angles.")

    candidates = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        d1 = math.hypot(x1 - cx, y1 - cy)
        d2 = math.hypot(x2 - cx, y2 - cy)
        if d1 < d2:
            near, far, fx, fy = d1, d2, x2, y2
        else:
            near, far, fx, fy = d2, d1, x1, y1
        if near > radius * 0.23 or far < radius * 0.35 or far > radius * 1.08:
            continue
        angle = math.degrees(math.atan2(fy - cy, fx - cx)) % 360
        if _wrap_delta(angle, start_angle) > sweep:
            continue
        score = (far - near) - near * 0.8
        candidates.append((score, angle, far, near))

    if not candidates:
        raise GaugeReadError("Could not isolate a pointer from dial markings. Try a sharper, tightly cropped image.")

    candidates.sort(reverse=True)
    best_score, pointer_angle, pointer_length, near_distance = candidates[0]
    value = angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle)
    score_gap = best_score - candidates[1][0] if len(candidates) > 1 else best_score
    confidence = "low" if near_distance > radius * 0.12 or score_gap < radius * 0.08 else "experimental"

    return {
        "value": round(value, 2),
        "pointer_angle_deg": round(pointer_angle, 2),
        "dial": {"center_x": round(cx, 1), "center_y": round(cy, 1), "radius": round(radius, 1)},
        "confidence": confidence,
        "diagnostics": {
            "candidate_lines": len(candidates),
            "pointer_length_px": round(pointer_length, 1),
            "pointer_center_offset_px": round(near_distance, 1),
        },
        "note": "Experimental Hough-line estimate; confidence is not a probability. Verify against a calibrated reference.",
    }
