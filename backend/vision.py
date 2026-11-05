"""Experimental analog dial reader using radial pointer segmentation and OpenCV."""
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
        if radius < min_dimension * 0.25 or offset > min_dimension * 0.22:
            continue
        score = offset - radius * 0.02
        candidates.append((score, float(x), float(y), float(radius)))
    if not candidates:
        raise GaugeReadError(
            "Could not identify a dial circle near the image centre. Crop the gauge and try again."
        )
    _, cx, cy, radius = min(candidates)
    return cx, cy, radius


def _longest_true_run(mask):
    """Length of the longest contiguous True run in a one-dimensional array."""
    padded = np.concatenate(([False], mask, [False]))
    changes = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return int(np.max(ends - starts)) if len(starts) else 0


def _detect_pointer_angle(gray, cx, cy, radius, start_angle, end_angle):
    """Find the strongest dark radial pointer segment while excluding outer tick marks."""
    height, width = gray.shape
    sweep = _wrap_delta(end_angle, start_angle)
    if sweep < 1 or sweep > 359:
        raise GaugeReadError("Invalid calibration angles.")

    # Search only the dial interior: tick marks and printed numerals are mostly outside this band.
    radii = np.linspace(radius * 0.20, radius * 0.80, 180)
    angles = np.linspace(start_angle, start_angle + sweep, max(361, int(sweep * 2) + 1))
    angle_grid, radius_grid = np.meshgrid(np.deg2rad(angles), radii)
    map_x = (cx + radius_grid * np.cos(angle_grid)).astype(np.float32)
    map_y = (cy + radius_grid * np.sin(angle_grid)).astype(np.float32)
    polar = cv2.remap(gray, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                      borderMode=cv2.BORDER_CONSTANT, borderValue=255)

    # Dark needle pixels form a relatively long radial run. Otsu adapts to dial brightness.
    _, binary = cv2.threshold(polar, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Ignore near-hub screw details; require a continuous run across the radial band.
    scores = np.zeros(len(angles), dtype=np.float32)
    run_lengths = np.zeros(len(angles), dtype=np.int32)
    for index in range(len(angles)):
        ray = binary[:, index].astype(bool)
        run = _longest_true_run(ray)
        run_lengths[index] = run
        # Reward long uninterrupted runs, with a small preference for reaching farther out.
        scores[index] = run + 0.12 * int(np.flatnonzero(ray)[-1] if np.any(ray) else 0)

    # Smooth neighbouring rays to tolerate a pointer wider than one pixel.
    scores = np.convolve(scores, np.ones(5, dtype=np.float32) / 5, mode="same")
    best = int(np.argmax(scores))
    if run_lengths[best] < 14:
        raise GaugeReadError("No continuous pointer segment found inside the dial. Improve focus or lighting.")

    angle = float(angles[best] % 360.0)
    # Contrast against the next-best direction gives a cautious heuristic diagnostic.
    exclusion = np.ones(len(scores), dtype=bool)
    exclusion[max(0, best - 8):min(len(scores), best + 9)] = False
    runner_up = float(np.max(scores[exclusion])) if np.any(exclusion) else 0.0
    separation = float(scores[best] - runner_up)
    return angle, int(run_lengths[best]), round(separation, 2)


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
    pointer_angle, pointer_run, separation = _detect_pointer_angle(
        gray, cx, cy, radius, start_angle, end_angle
    )
    value = angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle)

    # Heuristic only: the score gap is not a statistically calibrated probability.
    confidence = "experimental" if separation >= 5 and pointer_run >= 24 else "low"
    return {
        "value": round(value, 2),
        "pointer_angle_deg": round(pointer_angle, 2),
        "dial": {"center_x": round(cx, 1), "center_y": round(cy, 1), "radius": round(radius, 1)},
        "confidence": confidence,
        "diagnostics": {
            "pointer_radial_run_px": pointer_run,
            "direction_score_separation": separation,
            "detection_method": "polar_radial_dark_run",
        },
        "note": "Experimental radial pointer estimate; confidence is heuristic, not a probability. Verify against a calibrated reference.",
    }
