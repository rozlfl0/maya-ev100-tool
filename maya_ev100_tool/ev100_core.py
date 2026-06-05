"""Core EV100 / physical exposure helpers for the Maya EV100 tool.

This module intentionally has no Maya dependency so it can be tested outside Maya.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


MIDDLE_GRAY_LINEAR = 0.18
CALIBRATION_CUBE_ROTATE_X_DEGREES = 45.0


@dataclass(frozen=True)
class CalibrationSwatch:
    """Neutral reflectance target for exposure/light calibration."""

    name: str
    label: str
    reflectance: float
    description: str

    @property
    def rgb(self) -> tuple[float, float, float]:
        return (self.reflectance, self.reflectance, self.reflectance)


@dataclass(frozen=True)
class HDRIEVCalibrationResult:
    """Recommended dome-light correction from a rendered reflectance target."""

    current_ev100: float
    target_reflectance: float
    measured_average: float
    correction_stops: float
    recommended_dome_exposure: float
    current_dome_exposure: float = 0.0
    current_calibration_offset: float = 0.0
    recommended_calibration_offset: float = 0.0
    recommended_ev100: float = 0.0


@dataclass(frozen=True)
class EV100Scenario:
    """Reference EV100 preset for physical lighting setup."""

    name: str
    ev100: float
    category: str
    description: str
    value_label: str | None = None

    @property
    def display_value(self) -> str:
        return self.value_label or ("%.1f" % self.ev100).rstrip("0").rstrip(".")


CALIBRATION_SWATCHES = (
    CalibrationSwatch(
        name="white_paper",
        label="White Paper 0.71",
        reflectance=0.71,
        description="Bright diffuse reference; should not clip when calibrating highlights.",
    ),
    CalibrationSwatch(
        name="middle_gray",
        label="Middle Gray 0.18",
        reflectance=0.18,
        description="18% middle-gray reference for neutral exposure checks.",
    ),
    CalibrationSwatch(
        name="charcoal",
        label="Charcoal 0.031",
        reflectance=0.031,
        description="Dark diffuse reference for shadow/min EV calibration.",
    ),
)


EV100_SCENARIOS = (
    EV100Scenario("밝은 모래/눈, 직사광 또는 약간 흐린 햇빛", 16.0, "야외 낮", "Light sand or snow in full or slightly hazy sunlight"),
    EV100Scenario("맑은 직사광, 깨끗한 하늘 배경", 15.0, "야외 낮", "Full or slightly hazy sunlight, clear sky background"),
    EV100Scenario("흐릿한 햇빛, 구름 낀 하늘 배경", 14.0, "야외 낮", "Hazy sunlight, cloudy sky background"),
    EV100Scenario("밝은 흐린 날", 13.0, "야외 낮", "Cloudy bright"),
    EV100Scenario("강한 흐림, 일몰 무렵", 12.0, "야외 낮", "Heavy overcast, at sunset"),
    EV100Scenario("일몰 직전", 13.0, "야외 낮", "Just before sunset", "12-14"),
    EV100Scenario("일몰 직후", 10.0, "야외 낮", "Just after sunset", "9-11"),
    EV100Scenario("네온/밝은 간판", 9.5, "야외 밤", "Neon and Bright signs", "9-10"),
    EV100Scenario("야간 스포츠, 화재/불타는 건물", 9.0, "야외 밤", "Night Sport, fires & burning buildings"),
    EV100Scenario("밝은 밤거리", 8.0, "야외 밤", "Bright street scenes"),
    EV100Scenario("밤거리와 쇼윈도", 7.5, "야외 밤", "Night street scenes and window displays", "7-8"),
    EV100Scenario("축제/놀이공원", 7.0, "야외 밤", "Fairs & amusement parks"),
    EV100Scenario("야간 차량 통행", 5.0, "야외 밤", "Night vehicle traffic"),
    EV100Scenario("투광 조명 건축물", 4.0, "야외 밤", "Floodlit architecture", "3-5"),
    EV100Scenario("멀리 보이는 불 켜진 건물들", 2.0, "야외 밤", "Distant views of lighted buildings"),
    EV100Scenario("갤러리", 9.5, "실내", "Galleries", "8-11"),
    EV100Scenario("무대 쇼/스포츠 이벤트", 8.5, "실내", "Stage shows & Sport Events", "8-9"),
    EV100Scenario("사무실/작업 공간", 7.5, "실내", "Offices & work areas", "7-8"),
    EV100Scenario("주거 실내", 6.0, "실내", "Home interiors", "5-7"),
)


def calibration_swatch_by_name(name: str) -> CalibrationSwatch:
    for swatch in CALIBRATION_SWATCHES:
        if swatch.name == name:
            return swatch
    raise KeyError(f"Unknown calibration swatch: {name!r}")


@dataclass(frozen=True)
class DirectEV100Settings:
    """Direct EV100 settings for artist-friendly camera exposure control.

    This mode intentionally does not require or imply shutter speed, f-stop, or ISO.
    It is safe for motion blur workflows because renderer shutter/motion-blur
    attributes should remain independent from EV100 exposure metadata.
    """

    ev100: float = 10.0
    exposure_compensation: float = 0.0
    calibration_offset: float = 0.0

    @property
    def maya_camera_exposure(self) -> float:
        return camera_exposure_from_ev100(
            self.ev100,
            exposure_compensation=self.exposure_compensation,
            calibration_offset=self.calibration_offset,
        )


@dataclass(frozen=True)
class ExposureSettings:
    """Physical camera settings expressed in real camera terms.

    Kept for advanced users who want to derive EV100 from ISO/shutter/f-stop.
    The shutter value is exposure metadata only; UI code must not sync it to
    Maya/Arnold motion-blur shutter attributes unless explicitly requested.
    """

    fstop: float = 16.0
    shutter_seconds: float = 1 / 125.0
    iso: float = 100.0
    exposure_compensation: float = 0.0
    calibration_offset: float = 0.0

    @property
    def ev100(self) -> float:
        return ev100_from_camera_settings(
            fstop=self.fstop,
            shutter_seconds=self.shutter_seconds,
            iso=self.iso,
        )

    @property
    def maya_camera_exposure(self) -> float:
        return camera_exposure_from_ev100(
            self.ev100,
            exposure_compensation=self.exposure_compensation,
            calibration_offset=self.calibration_offset,
        )


def ev100_from_camera_settings(fstop: float, shutter_seconds: float, iso: float = 100.0) -> float:
    """Return EV100 from f-stop, shutter time in seconds, and ISO.

    Formula:
        EV100 = log2((N^2 / t) * (100 / ISO))

    Examples:
        f/16, 1/125, ISO100 ≈ EV15, the classic Sunny 16 baseline.
    """
    _require_positive("fstop", fstop)
    _require_positive("shutter_seconds", shutter_seconds)
    _require_positive("iso", iso)
    return math.log2((fstop * fstop / shutter_seconds) * (100.0 / iso))


def camera_exposure_from_ev100(
    ev100: float,
    exposure_compensation: float = 0.0,
    calibration_offset: float = 0.0,
) -> float:
    """Convert EV100 to a renderer exposure-stop offset.

    Arnold/Maya exposure attributes are stop offsets: +1 doubles brightness,
    -1 halves brightness. Higher photographic EV means a darker exposure,
    so the neutral starting mapping is negative EV100.

    calibration_offset exists because each studio's Arnold/OCIO/HDRI pipeline may
    define a different baseline after gray-card calibration.
    """
    return -float(ev100) + float(exposure_compensation) + float(calibration_offset)


def parse_shutter(value: str | float | int) -> float:
    """Parse shutter input like '1/48', '1/125', 0.02 into seconds."""
    if isinstance(value, (int, float)):
        seconds = float(value)
        _require_positive("shutter", seconds)
        return seconds

    text = str(value).strip()
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        seconds = float(numerator.strip()) / float(denominator.strip())
    else:
        seconds = float(text)
    _require_positive("shutter", seconds)
    return seconds


def luminance_stops_from_middle_gray(luminance: float, middle_gray: float = MIDDLE_GRAY_LINEAR) -> float:
    """Return how many stops a linear luminance is above/below 18% middle gray."""
    _require_positive("luminance", luminance)
    _require_positive("middle_gray", middle_gray)
    return math.log2(float(luminance) / float(middle_gray))


def average_linear_rgb(rgb: tuple[float, float, float]) -> float:
    """Return the simple average of a linear RGB sample."""
    if len(rgb) != 3:
        raise ValueError("rgb must contain exactly three values")
    r, g, b = (float(channel) for channel in rgb)
    _require_positive("red", r)
    _require_positive("green", g)
    _require_positive("blue", b)
    return (r + g + b) / 3.0


def estimate_hdri_ev_calibration(
    current_ev100: float,
    measured_rgb: tuple[float, float, float],
    target_reflectance: float = MIDDLE_GRAY_LINEAR,
    current_dome_exposure: float = 0.0,
    current_calibration_offset: float = 0.0,
) -> HDRIEVCalibrationResult:
    """Estimate EV100/calibration correction for an unknown-exposure HDRI.

    Render a known reflectance target under the HDRI, sample the lit face in
    linear RGB, then compare the measured average to the target reflectance.

    correction_stops is the camera-exposure/calibration offset to apply:
        log2(target_reflectance / measured_average)

    Negative correction darkens. The equivalent recommended EV100 moves in the
    opposite direction because higher EV100 means a darker photographic exposure.
    """
    _require_positive("target_reflectance", target_reflectance)
    measured_average = average_linear_rgb(measured_rgb)
    correction_stops = math.log2(float(target_reflectance) / measured_average)
    current_ev100 = float(current_ev100)
    current_dome_exposure = float(current_dome_exposure)
    current_calibration_offset = float(current_calibration_offset)
    return HDRIEVCalibrationResult(
        current_ev100=current_ev100,
        target_reflectance=float(target_reflectance),
        measured_average=measured_average,
        correction_stops=correction_stops,
        recommended_dome_exposure=current_dome_exposure + correction_stops,
        current_dome_exposure=current_dome_exposure,
        current_calibration_offset=current_calibration_offset,
        recommended_calibration_offset=current_calibration_offset + correction_stops,
        recommended_ev100=current_ev100 - correction_stops,
    )


def _require_positive(name: str, value: float) -> None:
    if float(value) <= 0.0:
        raise ValueError(f"{name} must be positive, got {value!r}")
