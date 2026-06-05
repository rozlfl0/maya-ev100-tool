import math

from maya_ev100_tool.ev100_core import (
    CALIBRATION_SWATCHES,
    DirectEV100Settings,
    ExposureSettings,
    calibration_swatch_by_name,
    ev100_from_camera_settings,
    camera_exposure_from_ev100,
    parse_shutter,
    luminance_stops_from_middle_gray,
)


def test_sunny_16_iso100_1_125_f16_is_about_ev15():
    ev = ev100_from_camera_settings(fstop=16.0, shutter_seconds=1 / 125.0, iso=100.0)
    assert ev == pytest_approx(14.966, abs=0.001)


def test_iso800_converts_to_ev100_lower_than_metered_ev():
    ev = ev100_from_camera_settings(fstop=2.8, shutter_seconds=1 / 48.0, iso=800.0)
    expected = math.log2((2.8 ** 2) / (1 / 48.0) * (100.0 / 800.0))
    assert ev == pytest_approx(expected, abs=0.001)


def test_camera_exposure_is_negative_ev_with_compensation_and_calibration():
    assert camera_exposure_from_ev100(15.0) == pytest_approx(-15.0)
    assert camera_exposure_from_ev100(15.0, exposure_compensation=1.0) == pytest_approx(-14.0)
    assert camera_exposure_from_ev100(15.0, calibration_offset=2.0) == pytest_approx(-13.0)


def test_parse_shutter_accepts_fraction_and_decimal():
    assert parse_shutter("1/125") == pytest_approx(1 / 125.0)
    assert parse_shutter("0.02") == pytest_approx(0.02)


def test_luminance_stops_from_middle_gray():
    assert luminance_stops_from_middle_gray(0.18) == pytest_approx(0.0)
    assert luminance_stops_from_middle_gray(0.36) == pytest_approx(1.0)
    assert luminance_stops_from_middle_gray(0.09) == pytest_approx(-1.0)


def test_direct_ev100_settings_do_not_need_physical_camera_shutter_values():
    settings = DirectEV100Settings(ev100=10.0)
    assert settings.ev100 == pytest_approx(10.0)
    assert settings.maya_camera_exposure == pytest_approx(-10.0)


def test_direct_ev100_settings_apply_compensation_and_calibration():
    settings = DirectEV100Settings(ev100=5.0, exposure_compensation=1.0, calibration_offset=-0.5)
    assert settings.maya_camera_exposure == pytest_approx(-4.5)


def test_exposure_settings_keep_legacy_physical_camera_calculation():
    settings = ExposureSettings(fstop=16.0, shutter_seconds=1 / 125.0, iso=100.0)
    assert settings.ev100 == pytest_approx(14.966, abs=0.001)


def test_calibration_swatches_match_reference_reflectance_values():
    assert [swatch.name for swatch in CALIBRATION_SWATCHES] == [
        "white_paper",
        "middle_gray",
        "charcoal",
    ]
    assert [swatch.reflectance for swatch in CALIBRATION_SWATCHES] == pytest_approx([0.71, 0.18, 0.031])


def test_calibration_swatch_rgb_is_neutral_reflectance_triplet():
    white = calibration_swatch_by_name("white_paper")
    assert white.rgb == pytest_approx((0.71, 0.71, 0.71))


def pytest_approx(value, **kwargs):
    import pytest
    return pytest.approx(value, **kwargs)
