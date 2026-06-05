"""Core EV100 / physical exposure helpers for the Maya EV100 tool.

This module intentionally has no Maya dependency so it can be tested outside Maya.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


MIDDLE_GRAY_LINEAR = 0.18


@dataclass(frozen=True)
class ExposureSettings:
    """Physical camera settings expressed in real camera terms."""

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


def _require_positive(name: str, value: float) -> None:
    if float(value) <= 0.0:
        raise ValueError(f"{name} must be positive, got {value!r}")
