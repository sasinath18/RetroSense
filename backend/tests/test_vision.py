import cv2
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from vision import (
    angle_to_value, GaugeReadError, _select_gauge_circle,
    _detect_pointer_angle, _detect_pointer_angle_hough,
)
from evaluate_samples import calculate_metrics


def test_start_angle_maps_to_minimum():
    assert angle_to_value(135, 0, 100, 135, 45) == 0


def test_midpoint_maps_to_midscale():
    assert angle_to_value(270, 0, 100, 135, 45) == pytest.approx(50)


def test_end_angle_maps_to_maximum():
    assert angle_to_value(45, 0, 100, 135, 45) == pytest.approx(100)


def test_pointer_outside_scale_is_rejected():
    with pytest.raises(GaugeReadError):
        angle_to_value(90, 0, 100, 135, 45)




def test_hough_detector_uses_long_pointer_side_not_short_counterweight():
    size, center, radius = 400, (200, 200), 160

    def point(angle, distance):
        radians = np.deg2rad(angle)
        return (int(center[0] + distance * np.cos(radians)),
                int(center[1] + distance * np.sin(radians)))

    image = np.full((size, size), 245, dtype=np.uint8)
    cv2.line(image, point(220, radius * 0.82), point(40, radius * 0.30), 15, 7)
    detected = _detect_pointer_angle_hough(image, *center, radius)

    assert detected is not None
    angle, line_length, hub_offset = detected
    assert angle == pytest.approx(220, abs=2)
    assert line_length >= radius * 0.55
    assert hub_offset <= radius * 0.08


def test_angle_mapping_snaps_small_pointer_error_to_scale_endpoint():
    assert angle_to_value(132, 0, 100, 135, 45) == pytest.approx(0)
    assert angle_to_value(48, 0, 100, 135, 45) == pytest.approx(100)


def test_invalid_value_range_is_rejected():
    with pytest.raises(GaugeReadError):
        angle_to_value(135, 100, 0, 135, 45)


def test_circle_selection_prefers_central_dial_over_off_center_background_circle():
    circles = np.array([[
        [148.2, 72.6, 495.3],
        [509.4, 402.6, 327.7],
    ]], dtype=np.float32)
    cx, cy, radius = _select_gauge_circle(circles, 1000, 1000)
    assert (cx, cy, radius) == pytest.approx((509.4, 402.6, 327.7))


def test_circle_selection_rejects_no_central_candidate():
    circles = np.array([[[20.0, 30.0, 300.0]]], dtype=np.float32)
    with pytest.raises(GaugeReadError):
        _select_gauge_circle(circles, 1000, 1000)


def test_radial_detector_finds_needle_tip_not_short_counterweight():
    size, center, radius = 400, (200, 200), 160
    image = np.full((size, size), 245, dtype=np.uint8)
    # Long pointer at 220 degrees; short counterweight points in the opposite direction.
    def point(angle, distance):
        radians = np.deg2rad(angle)
        return (int(center[0] + distance * np.cos(radians)),
                int(center[1] + distance * np.sin(radians)))
    cv2.line(image, point(220, radius * .12), point(220, radius * .76), 15, 7)
    cv2.line(image, point(40, radius * .12), point(40, radius * .30), 15, 5)
    angle, run, separation = _detect_pointer_angle(image, *center, radius, 135, 45)
    assert angle == pytest.approx(220, abs=2)
    assert run >= 24


def test_radial_detector_rejects_image_without_pointer():
    image = np.full((300, 300), 245, dtype=np.uint8)
    with pytest.raises(GaugeReadError):
        _detect_pointer_angle(image, 150, 150, 120, 135, 45)


def test_accuracy_metrics_calculate_mae_rmse_and_mape():
    metrics = calculate_metrics([(12, 10), (18, 20)])
    assert metrics["count"] == 2
    assert metrics["mae"] == 2
    assert metrics["rmse"] == pytest.approx(2)
    assert metrics["mape_percent"] == pytest.approx(15)


def test_accuracy_metrics_exclude_zero_reference_from_mape_only():
    metrics = calculate_metrics([(2, 0), (11, 10)])
    assert metrics["mae"] == 1.5
    assert metrics["mape_percent"] == 10
    assert metrics["mape_excluded_zero_reference"] == 1


def test_accuracy_metrics_handle_no_ground_truth():
    assert calculate_metrics([]) == {
        "count": 0, "mae": None, "rmse": None, "mape_percent": None
    }


def test_digital_ocr_reports_missing_tesseract(monkeypatch):
    import digital_ocr
    image = np.full((80, 180, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    monkeypatch.setattr(digital_ocr, "pytesseract", None)
    with pytest.raises(digital_ocr.DigitalReadError, match="dependency is missing"):
        digital_ocr.read_digital_display(encoded.tobytes())


def test_digital_ocr_extracts_numeric_token_and_confidence(monkeypatch):
    import digital_ocr
    class FakeOutput:
        DICT = "dict"
    class FakeTesseract:
        @staticmethod
        def image_to_data(image, config, output_type):
            return {"text": ["TEMP", "72.5", "C"], "conf": ["-1", "91.2", "-1"]}
    image = np.full((80, 180, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    monkeypatch.setattr(digital_ocr, "pytesseract", FakeTesseract)
    monkeypatch.setattr(digital_ocr, "Output", FakeOutput)
    result = digital_ocr.read_digital_display(encoded.tobytes())
    assert result["value"] == 72.5
    assert result["raw_text"] == "72.5"
    assert result["confidence"] == 91.2
