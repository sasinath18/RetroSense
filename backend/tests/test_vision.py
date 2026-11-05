import numpy as np
import pytest
from vision import angle_to_value, GaugeReadError, _select_gauge_circle
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
