"""Geometry conversion and validation tests."""

import pytest

from app.geometry import app_to_viewbox, provider_to_app, validate_app_box


def test_provider_to_app_basic():
    assert provider_to_app([220, 150, 480, 670]) == pytest.approx([0.15, 0.22, 0.67, 0.48])


def test_provider_to_app_full_page():
    assert provider_to_app([0, 0, 1000, 1000]) == pytest.approx([0.0, 0.0, 1.0, 1.0])


def test_provider_to_app_rejects_zero_area():
    with pytest.raises(ValueError):
        provider_to_app([100, 100, 100, 200])
    with pytest.raises(ValueError):
        provider_to_app([100, 100, 200, 100])


def test_provider_to_app_rejects_out_of_range():
    with pytest.raises(ValueError):
        provider_to_app([-1, 0, 500, 500])
    with pytest.raises(ValueError):
        provider_to_app([0, 0, 500, 1001])


def test_provider_to_app_rejects_swapped_axes():
    with pytest.raises(ValueError):
        provider_to_app([480, 150, 220, 670])


def test_provider_to_app_rejects_non_finite():
    with pytest.raises(ValueError):
        provider_to_app([float("nan"), 0, 500, 500])
    with pytest.raises(ValueError):
        provider_to_app([0, 0, float("inf"), 500])


def test_validate_app_box_ok():
    assert validate_app_box([0.1, 0.2, 0.5, 0.6]) == [0.1, 0.2, 0.5, 0.6]


def test_validate_app_box_rejects_bad():
    with pytest.raises(ValueError):
        validate_app_box([0.5, 0.5, 0.5, 0.6])
    with pytest.raises(ValueError):
        validate_app_box([0.0, 0.0, 1.5, 1.0])


def test_app_to_viewbox():
    assert app_to_viewbox([0.15, 0.22, 0.67, 0.48]) == pytest.approx([150.0, 220.0, 520.0, 260.0])
