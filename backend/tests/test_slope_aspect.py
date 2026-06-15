"""Pure slope/aspect math + provider tests. Offline."""
import math
from app.providers.slope_aspect import (
    compute_slope_aspect, slope_bucket_label, aspect_compass,
)


def test_flat_surface_is_zero_slope():
    slope, _aspect = compute_slope_aspect(100, 100, 100, 100, 100, spacing_m=50)
    assert slope == 0.0


def test_east_facing_slope_has_east_aspect():
    # elevation drops toward the east: east lower, west higher -> faces east (~90)
    slope, aspect = compute_slope_aspect(center=100, north=100, east=50, south=100, west=150, spacing_m=50)
    assert slope > 0
    assert abs(aspect - 90.0) < 0.5


def test_north_facing_slope_has_north_aspect():
    # drops toward the north -> faces north (~0/360)
    _slope, aspect = compute_slope_aspect(center=100, north=50, east=100, south=150, west=100, spacing_m=50)
    assert aspect < 0.5 or aspect > 359.5


def test_slope_bucket_labels():
    assert slope_bucket_label(5) == "0–15°"
    assert slope_bucket_label(32) == "30–35°"
    assert slope_bucket_label(40) == "35–45°"
    assert slope_bucket_label(60) == "45°+"


def test_aspect_compass_directions():
    assert aspect_compass(0) == "N"
    assert aspect_compass(90) == "E"
    assert aspect_compass(180) == "S"
    assert aspect_compass(270) == "W"
    assert aspect_compass(45) == "NE"
