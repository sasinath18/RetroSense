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
    # Small endpoint tolerance absorbs a few degrees of circle/line-detection error.
    # This is a calibration tolerance, not a general allowance for out-of-scale pointers.
    endpoint_tolerance = 5.0
    if position > sweep:
        distance_before_start = 360.0 - position
        distance_after_end = position - sweep
        if distance_before_start <= endpoint_tolerance:
            position = 0.0
        elif distance_after_end <= endpoint_tolerance:
            position = sweep
        else:
            raise GaugeReadError("Pointer appears outside the calibrated scale. Check start/end angles.")
    fraction = position / sweep
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


def _detect_pointer_angle_hough(gray, cx, cy, radius):
    """Find the longer measuring arm of a straight pointer near the dial hub.

    The farthest endpoint from the hub defines the reading direction. This rule
    intentionally does not use needle thickness: some gauges have a thick,
    short counterweight opposite the long measuring arm.
    Returns (angle_deg, line_length_px, centre_offset_px), or None.
    """
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 40, 120)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(25, int(radius * 0.20)),
        minLineLength=max(30, int(radius * 0.35)),
        maxLineGap=max(5, int(radius * 0.08)),
    )
    if lines is None:
        return None

    candidates = []
    max_hub_offset = max(6.0, radius * 0.08)
    for x1, y1, x2, y2 in lines[:, 0]:
        vx, vy = float(x2 - x1), float(y2 - y1)
        length = math.hypot(vx, vy)
        denominator = vx * vx + vy * vy
        if denominator <= 0:
            continue

        projection = max(
            0.0,
            min(1.0, ((cx - x1) * vx + (cy - y1) * vy) / denominator),
        )
        closest_x = x1 + projection * vx
        closest_y = y1 + projection * vy
        hub_offset = math.hypot(closest_x - cx, closest_y - cy)

        distance_1 = math.hypot(x1 - cx, y1 - cy)
        distance_2 = math.hypot(x2 - cx, y2 - cy)
        far_distance = max(distance_1, distance_2)
        near_distance = min(distance_1, distance_2)

        # Reject dial markings and text. The arrowhead can be shorter than its
        # thin counterweight tail, so do not require the longer side to reach
        # 55% of the radius.
        if hub_offset > max_hub_offset:
            continue
        if far_distance < radius * 0.30:
            continue
        if far_distance - near_distance < radius * 0.12:
            continue

        # RetroSense uses the longer arm as the reading pointer. Many gauges
        # have a short counterweight or triangular balance on the opposite side;
        # thickness is not a reliable indicator of the measurement direction.
        # Hough may return only one half of the axis, so use the endpoint farthest
        # from the detected hub and retain its outward direction.
        far_endpoint = (x1, y1) if distance_1 >= distance_2 else (x2, y2)
        angle = math.degrees(
            math.atan2(far_endpoint[1] - cy, far_endpoint[0] - cx)
        ) % 360.0

        score = (
            length
            + 0.50 * far_distance
            + 0.25 * (far_distance - near_distance)
            - 2.0 * hub_offset
        )
        candidates.append((score, angle, length, hub_offset))

    if not candidates:
        return None
    _, angle, length, hub_offset = max(candidates, key=lambda item: item[0])
    return float(angle), float(length), float(hub_offset)


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
    hough_result = _detect_pointer_angle_hough(gray, cx, cy, radius)
    if hough_result is not None:
        pointer_angle, pointer_length, hub_offset = hough_result
        try:
            value = angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle)
        except GaugeReadError:
            # A long printed mark can occasionally resemble a pointer. If its
            # angle falls outside the calibrated sweep, try the radial detector.
            hough_result = None

    if hough_result is not None:
        confidence = "experimental" if pointer_length >= radius * 0.55 and hub_offset <= radius * 0.05 else "low"
        diagnostics = {
            "pointer_line_length_px": round(pointer_length, 2),
            "pointer_hub_offset_px": round(hub_offset, 2),
            "pointer_direction_rule": "longer_arm",
            "detection_method": "hough_center_crossing_line",
        }
    else:
        pointer_angle, pointer_run, separation = _detect_pointer_angle(
            gray, cx, cy, radius, start_angle, end_angle
        )
        value = angle_to_value(pointer_angle, min_value, max_value, start_angle, end_angle)
        confidence = "experimental" if separation >= 5 and pointer_run >= 24 else "low"
        diagnostics = {
            "pointer_radial_run_px": pointer_run,
            "direction_score_separation": separation,
            "detection_method": "polar_radial_dark_run",
        }

    return {
        "value": round(value, 2),
        "pointer_angle_deg": round(pointer_angle, 2),
        "dial": {"center_x": round(cx, 1), "center_y": round(cy, 1), "radius": round(radius, 1)},
        "confidence": confidence,
        "diagnostics": diagnostics,
        "note": "Experimental pointer estimate using line geometry or radial image segmentation. Confidence is heuristic, not a probability. Verify against a calibrated reference.",
    }
