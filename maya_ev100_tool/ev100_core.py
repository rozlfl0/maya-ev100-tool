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


@dataclass(frozen=True)
class LocalLightPreset:
    """Reference lumen preset for local light creation."""

    name: str
    lumens: float
    category: str
    kelvin: float
    light_type: str
    description: str = ""
    common_range: str = ""


@dataclass(frozen=True)
class LocalLightRigSettings:
    """Artist-facing distance/size defaults for a local light rig."""

    distance_m: float
    source_size_m: float
    recommended_type: str
    note: str


CALIBRATION_SWATCHES = (
    CalibrationSwatch(
        name="middle_gray",
        label="Middle Gray 0.18",
        reflectance=0.18,
        description="18% middle-gray reference for neutral Dome exposure calibration.",
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


LOCAL_LIGHT_PRESETS = (
    LocalLightPreset("촛불 가까이", 13.0, "starter", 1800.0, "Point", "Small candle close to the subject"),
    LocalLightPreset("책상 스탠드", 500.0, "starter", 2700.0, "Point", "Warm desk lamp practical"),
    LocalLightPreset("방 천장등", 1000.0, "starter", 4000.0, "Rect", "Soft room ceiling light"),
    LocalLightPreset("차량 헤드라이트", 1500.0, "starter", 4300.0, "Spot", "Car headlight coming from outside frame"),
    LocalLightPreset("가로등 느낌", 60000.0, "starter", 2200.0, "Spot", "Warm sodium-vapor street light feel"),
    LocalLightPreset("작은 LED Practical", 400.0, "starter", 5600.0, "Point", "Small visible LED practical"),
)


def local_light_exposure_from_lumens(lumens: float, baseline_lumens: float = 1000.0) -> float:
    """Return a practical exposure-stop starting point from lumens.

    This is an artist-friendly initial scale, not a claim that Arnold intensity is a true lumen unit.
    1000 lm maps to exposure 0; each doubling adds +1 stop.
    """
    _require_positive("lumens", lumens)
    _require_positive("baseline_lumens", baseline_lumens)
    return math.log2(float(lumens) / float(baseline_lumens))


def local_light_intensity_from_lumens(lumens: float, baseline_lumens: float = 0.01) -> float:
    """Return a practical Maya-light intensity fallback when no exposure attr exists.

    Maya's default Point/Spot light ``intensity`` does not behave like a physical
    lumen input. In the user's EV100 -12 camera workflow, a 13 lm candle only
    became visible around intensity 1300, so the fallback maps 0.01 lm -> 1.0
    intensity, i.e. intensity = lumens * 100.
    """
    _require_positive("lumens", lumens)
    _require_positive("baseline_lumens", baseline_lumens)
    return float(lumens) / float(baseline_lumens)


def meters_to_scene_units(meters: float, linear_unit: str = "cm", scene_scale: float = 0.1) -> float:
    """Convert meters to Maya scene units for a given linear unit.

    Maya commonly defaults to centimeters, where true 1.0 meter is 100 scene
    units. For practical VFX layout in this tool we apply a 1/10 rig scale by
    default, so 1.0 UI meter becomes 10 units in a default centimeter scene.
    """
    meters_to_unit = {
        "mm": 1000.0,
        "millimeter": 1000.0,
        "cm": 100.0,
        "centimeter": 100.0,
        "m": 1.0,
        "meter": 1.0,
        "km": 0.001,
        "kilometer": 0.001,
        "in": 39.37007874,
        "inch": 39.37007874,
        "ft": 3.280839895,
        "foot": 3.280839895,
        "yd": 1.093613298,
        "yard": 1.093613298,
    }
    return float(meters) * meters_to_unit.get(str(linear_unit).strip().lower(), 100.0) * float(scene_scale)


def default_local_light_rig_settings(preset_name: str, light_type: str | None = None) -> LocalLightRigSettings:
    """Return practical distance/source-size defaults for a local-light preset.

    These are not strict physical values. They are starting points that help an
    artist place a light at a believable scale before gray-card calibration.
    """
    aliases = {
        "candle": "촛불 가까이",
        "촛불": "촛불 가까이",
        "incandescent": "책상 스탠드",
        "desk lamp": "책상 스탠드",
        "functional lighting": "책상 스탠드",
        "general lighting": "방 천장등",
        "interior light": "방 천장등",
        "car headlights": "차량 헤드라이트",
        "street lights": "가로등 느낌",
        "가로등": "가로등 느낌",
        "led": "작은 LED Practical",
        "led 전구": "작은 LED Practical",
    }
    key = aliases.get(str(preset_name).strip().lower(), str(preset_name).strip())
    requested_type = (light_type or "").strip().lower()
    defaults = {
        "촛불 가까이": LocalLightRigSettings(0.5, 0.03, "Point", "피사체 가까운 촛불 시작점. 거리/크기는 필요할 때만 조절."),
        "책상 스탠드": LocalLightRigSettings(1.0, 0.12, "Point", "따뜻한 스탠드/practical 시작점."),
        "방 천장등": LocalLightRigSettings(1.5, 0.8, "Rect", "위쪽에서 부드럽게 퍼지는 방 천장등 시작점."),
        "차량 헤드라이트": LocalLightRigSettings(5.0, 0.18, "Spot", "프레임 밖 차량 헤드라이트 시작점."),
        "가로등 느낌": LocalLightRigSettings(8.0, 0.6, "Spot", "높은 가로등/나트륨등 느낌 시작점."),
        "작은 LED Practical": LocalLightRigSettings(1.0, 0.08, "Point", "작은 LED practical 시작점."),
    }
    settings = defaults.get(key, LocalLightRigSettings(1.0, 0.1, "Point", "Generic local light: adjust distance, then gray-card calibrate."))
    if requested_type:
        normalized_type = requested_type.capitalize()
        if normalized_type == "Rect":
            settings = LocalLightRigSettings(settings.distance_m, max(settings.source_size_m, 0.1), "Rect", settings.note)
        elif normalized_type in {"Point", "Spot"}:
            settings = LocalLightRigSettings(settings.distance_m, settings.source_size_m, normalized_type, settings.note)
    return settings


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
    """Convert EV100 to a Maya/Arnold camera exposure-stop offset.

    Arnold/Maya exposure attributes are stop offsets: +1 doubles brightness,
    -1 halves brightness. In the default EV100 workflow, higher scene EV means
    a darker photographic/view exposure, so EV100 12 maps to aiExposure -12.

    Positive exposure_compensation/calibration_offset values still brighten from
    that base, e.g. EV100 12 with +1 compensation maps to -11.

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
