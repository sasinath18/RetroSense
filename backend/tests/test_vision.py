import pytest
from vision import angle_to_value, GaugeReadError

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
