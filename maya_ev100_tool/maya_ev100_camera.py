"""Maya UI for EV100 camera exposure MVP.

Install/use in Maya Script Editor:

import sys
sys.path.insert(0, r"C:/Users/maste/Desktop/maya_ev100_tool")
from maya_ev100_tool import maya_ev100_camera
maya_ev100_camera.show()

MVP behavior:
- Select a camera transform or camera shape.
- Enter EV100 directly.
- Add/update custom physical exposure attrs on the camera shape.
- If the selected camera shape has an Arnold aiExposure attr, set it.
- Never changes Maya/Arnold motion-blur shutter settings.
"""

from __future__ import annotations

from .ev100_core import (
    CALIBRATION_CUBE_ROTATE_X_DEGREES,
    CALIBRATION_SWATCHES,
    EV100_SCENARIOS,
    DirectEV100Settings,
    ExposureSettings,
    estimate_hdri_ev_calibration,
    parse_shutter,
)

try:
    from maya import cmds
except Exception:  # Allows non-Maya import for linting/docs.
    cmds = None


WINDOW_NAME = "mayaEv100CameraTool"
CUSTOM_ATTRS = {
    "pbl_direct_ev100_mode": "Direct EV100 Mode",
    "pbl_ev100": "EV100",
    "pbl_exposure_compensation": "Exposure Compensation",
    "pbl_calibration_offset": "Calibration Offset",
    "pbl_recommended_camera_exposure": "Recommended Camera Exposure",
}

LEGACY_PHYSICAL_ATTRS = {
    "pbl_iso": "ISO",
    "pbl_shutter_seconds": "Exposure Shutter Seconds",
    "pbl_fstop": "F-Stop",
}


def _scenario_label(scenario) -> str:
    return "%s / EV100 %.1f" % (scenario.name, scenario.ev100)


def show() -> None:
    """Open the physical EV100 / dome calibration UI inside Maya."""
    _require_maya()
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(WINDOW_NAME, title="Physical EV100 Lighting Toolkit", sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))

    cmds.text(label="1) Pick a lighting scenario EV100, then apply it to the selected camera.", align="left")
    scenario_menu = cmds.optionMenu(label="Lighting Scenario")
    for scenario in EV100_SCENARIOS:
        cmds.menuItem(label=_scenario_label(scenario))
    ev100 = cmds.floatFieldGrp(label="EV100", value1=EV100_SCENARIOS[0].ev100, numberOfFields=1)
    scenario_note = cmds.text(label="", align="left")
    result = cmds.text(label="EV100: - / Maya exposure: -", align="left")

    def _selected_scenario():
        selected_label = cmds.optionMenu(scenario_menu, query=True, value=True)
        for scenario in EV100_SCENARIOS:
            if _scenario_label(scenario) == selected_label:
                return scenario
        raise RuntimeError("Unknown EV100 scenario: %s" % selected_label)

    def load_scenario(*_args):
        scenario = _selected_scenario()
        cmds.floatFieldGrp(ev100, edit=True, value1=scenario.ev100)
        cmds.text(scenario_note, edit=True, label="%s / EV100 %.1f - %s" % (scenario.category, scenario.ev100, scenario.description))
        return calculate_only()

    def calculate_only(*_args):
        settings = DirectEV100Settings(ev100=cmds.floatFieldGrp(ev100, query=True, value1=True))
        cmds.text(
            result,
            edit=True,
            label="EV100: %.3f / Maya camera exposure: %.3f stops" % (
                settings.ev100,
                settings.maya_camera_exposure,
            ),
        )
        return settings

    def apply_to_selected(*_args):
        settings = calculate_only()
        camera_shape = get_selected_camera_shape()
        apply_settings_to_camera(camera_shape, settings)
        cmds.inViewMessage(
            amg="EV100 <hl>%.3f</hl>, camera exposure <hl>%.3f</hl> applied to %s"
            % (settings.ev100, settings.maya_camera_exposure, camera_shape),
            pos="topCenter",
            fade=True,
        )

    cmds.optionMenu(scenario_menu, edit=True, changeCommand=load_scenario)
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(150, 150, 190), adjustableColumn=3)
    cmds.button(label="Load Scenario EV", command=load_scenario)
    cmds.button(label="Calculate", command=calculate_only)
    cmds.button(label="Apply EV100 to Camera", command=apply_to_selected)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.button(label="Create Calibration Cubes (0.71 / 0.18 / 0.031)", command=lambda *_args: create_calibration_cubes())

    cmds.separator(height=8, style="in")
    cmds.text(label="2) Dome HDRI Calibration: enter sampled target RGB, then adjust Dome Light exposure.", align="left")
    hdri_target = cmds.optionMenu(label="Target Pixel")
    for swatch in CALIBRATION_SWATCHES:
        cmds.menuItem(label=swatch.label)
    dome_exposure = cmds.floatFieldGrp(label="Current Dome Exposure", value1=0.0, numberOfFields=1)
    hdri_r = cmds.floatFieldGrp(label="Measured R", value1=0.18, numberOfFields=1)
    hdri_g = cmds.floatFieldGrp(label="Measured G", value1=0.18, numberOfFields=1)
    hdri_b = cmds.floatFieldGrp(label="Measured B", value1=0.18, numberOfFields=1)
    hdri_result = cmds.text(label="Dome calibration: -", align="left")

    def _selected_calibration_swatch():
        selected_label = cmds.optionMenu(hdri_target, query=True, value=True)
        for swatch in CALIBRATION_SWATCHES:
            if swatch.label == selected_label:
                return swatch
        raise RuntimeError("Unknown calibration target: %s" % selected_label)

    def analyze_dome_exposure(*_args):
        swatch = _selected_calibration_swatch()
        result_data = estimate_hdri_ev_calibration(
            current_ev100=cmds.floatFieldGrp(ev100, query=True, value1=True),
            measured_rgb=(
                cmds.floatFieldGrp(hdri_r, query=True, value1=True),
                cmds.floatFieldGrp(hdri_g, query=True, value1=True),
                cmds.floatFieldGrp(hdri_b, query=True, value1=True),
            ),
            target_reflectance=swatch.reflectance,
            current_dome_exposure=cmds.floatFieldGrp(dome_exposure, query=True, value1=True),
        )
        direction = "brighter" if result_data.correction_stops > 0.0 else "darker"
        cmds.text(
            hdri_result,
            edit=True,
            label=(
                "Avg %.3f / target %.3f / correction %.3f stops (%s)\n"
                "Recommended Dome Exposure %.3f"
            )
            % (
                result_data.measured_average,
                result_data.target_reflectance,
                result_data.correction_stops,
                direction,
                result_data.recommended_dome_exposure,
            ),
        )
        return result_data

    def apply_dome_exposure_to_selected(*_args):
        result_data = analyze_dome_exposure()
        dome_node = get_selected_exposure_node()
        cmds.setAttr("%s.exposure" % dome_node, result_data.recommended_dome_exposure)
        cmds.floatFieldGrp(dome_exposure, edit=True, value1=result_data.recommended_dome_exposure)
        cmds.inViewMessage(
            amg="Applied Dome exposure <hl>%.3f</hl> to %s" % (result_data.recommended_dome_exposure, dome_node),
            pos="topCenter",
            fade=True,
        )

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 220), adjustableColumn=2)
    cmds.button(label="Analyze Dome Exposure", command=analyze_dome_exposure)
    cmds.button(label="Apply to Selected Dome Light", command=apply_dome_exposure_to_selected)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.text(
        label="Workflow: EV100 belongs to the camera scenario. Target pixel matching belongs to Dome Light exposure.\n"
        "Measured RGB must be linear render values from the calibration cube face. Motion blur settings are never changed.",
        align="left",
    )

    cmds.showWindow(window)
    load_scenario()


def create_calibration_cubes(size: float = 1.0, spacing: float = 1.4) -> str:
    """Create neutral reflectance cubes for PBL exposure calibration.

    The cubes use Lambert materials with linear RGB reflectance values:
    0.71 white paper, 0.18 middle gray, and 0.031 charcoal.
    They are intended for render/pixel-inspector calibration, not beauty shading.
    """
    _require_maya()
    group = cmds.group(empty=True, name="PBL_Calibration_Cubes_GRP")

    start_x = -spacing * (len(CALIBRATION_SWATCHES) - 1) / 2.0
    for index, swatch in enumerate(CALIBRATION_SWATCHES):
        cube = cmds.polyCube(name="PBL_%s_cube" % swatch.name, width=size, height=size, depth=size)[0]
        cmds.setAttr("%s.translateX" % cube, start_x + spacing * index)
        cmds.setAttr("%s.translateY" % cube, size / 2.0)
        cmds.setAttr("%s.rotateX" % cube, CALIBRATION_CUBE_ROTATE_X_DEGREES)
        cmds.parent(cube, group)

        shader = _create_lambert_reflectance_shader(swatch.name, swatch.rgb)
        cmds.select(cube, replace=True)
        cmds.hyperShade(assign=shader)

        shape = (cmds.listRelatives(cube, shapes=True, fullPath=True) or [cube])[0]
        _set_or_add_double_attr(shape, "pbl_reflectance", swatch.reflectance)
        _set_or_add_double_attr(cube, "pbl_reflectance", swatch.reflectance)

        label = _create_text_label(swatch.label, cube, y_offset=size * 1.15)
        if label:
            cmds.parent(label, group)

    cmds.select(group, replace=True)
    cmds.inViewMessage(
        amg="Created <hl>PBL calibration cubes</hl>: 0.71 / 0.18 / 0.031",
        pos="topCenter",
        fade=True,
    )
    return group


def _create_lambert_reflectance_shader(name: str, rgb: tuple[float, float, float]) -> str:
    shader = cmds.shadingNode("lambert", asShader=True, name="PBL_%s_lambert" % name)
    shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="%sSG" % shader)
    cmds.connectAttr("%s.outColor" % shader, "%s.surfaceShader" % shading_group, force=True)
    cmds.setAttr("%s.color" % shader, rgb[0], rgb[1], rgb[2], type="double3")
    cmds.setAttr("%s.diffuse" % shader, 1.0)
    _set_or_add_double_attr(shader, "pbl_reflectance", rgb[0])
    return shader


def _create_text_label(text: str, target: str, y_offset: float) -> str | None:
    try:
        label = cmds.textCurves(name="PBL_%s_label" % target, text=text, font="Arial", constructionHistory=False)[0]
    except Exception:
        return None

    bbox = cmds.exactWorldBoundingBox(label)
    label_width = bbox[3] - bbox[0]
    cmds.setAttr("%s.scaleX" % label, 0.12)
    cmds.setAttr("%s.scaleY" % label, 0.12)
    cmds.setAttr("%s.scaleZ" % label, 0.12)
    cmds.setAttr("%s.translateX" % label, cmds.getAttr("%s.translateX" % target) - label_width * 0.06)
    cmds.setAttr("%s.translateY" % label, y_offset)
    cmds.setAttr("%s.translateZ" % label, 0.65)
    return label


def _set_or_add_double_attr(node: str, attr: str, value: float) -> None:
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, longName=attr, attributeType="double", keyable=True)
    cmds.setAttr("%s.%s" % (node, attr), float(value))


def apply_settings_to_camera(camera_shape: str, settings: DirectEV100Settings | ExposureSettings) -> None:
    """Store EV100 data on a camera and set Arnold exposure when available.

    This function intentionally does not touch Maya/Arnold motion-blur shutter
    attributes. EV100 exposure and motion blur timing must remain independent.
    """
    _require_maya()
    if not camera_shape or cmds.nodeType(camera_shape) != "camera":
        raise ValueError("Expected a Maya camera shape, got %r" % camera_shape)

    values = {
        "pbl_direct_ev100_mode": 1.0 if isinstance(settings, DirectEV100Settings) else 0.0,
        "pbl_ev100": settings.ev100,
        "pbl_exposure_compensation": settings.exposure_compensation,
        "pbl_calibration_offset": settings.calibration_offset,
        "pbl_recommended_camera_exposure": settings.maya_camera_exposure,
    }

    if isinstance(settings, ExposureSettings):
        values.update(
            {
                "pbl_iso": settings.iso,
                "pbl_shutter_seconds": settings.shutter_seconds,
                "pbl_fstop": settings.fstop,
            }
        )

    for attr, nice_name in CUSTOM_ATTRS.items():
        full_attr = "%s.%s" % (camera_shape, attr)
        if not cmds.attributeQuery(attr, node=camera_shape, exists=True):
            cmds.addAttr(camera_shape, longName=attr, niceName=nice_name, attributeType="double", keyable=True)
        cmds.setAttr(full_attr, float(values[attr]))

    for attr, nice_name in LEGACY_PHYSICAL_ATTRS.items():
        if attr not in values:
            continue
        full_attr = "%s.%s" % (camera_shape, attr)
        if not cmds.attributeQuery(attr, node=camera_shape, exists=True):
            cmds.addAttr(camera_shape, longName=attr, niceName=nice_name, attributeType="double", keyable=True)
        cmds.setAttr(full_attr, float(values[attr]))

    # Arnold for Maya commonly exposes camera stop offset as aiExposure on the camera shape.
    # If the attr is absent, we still keep the PBL custom attrs so the tool remains renderer-safe.
    # Motion-blur shutter attributes are intentionally never changed here.
    if cmds.attributeQuery("aiExposure", node=camera_shape, exists=True):
        cmds.setAttr("%s.aiExposure" % camera_shape, settings.maya_camera_exposure)


def get_selected_camera_shape() -> str:
    """Return selected camera shape from selected transform or shape."""
    _require_maya()
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        raise RuntimeError("Select a camera transform or camera shape first.")

    node = selection[0]
    if cmds.nodeType(node) == "camera":
        return node

    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    cameras = [shape for shape in shapes if cmds.nodeType(shape) == "camera"]
    if not cameras:
        raise RuntimeError("Selected node is not a camera: %s" % node)
    return cameras[0]


def get_selected_exposure_node() -> str:
    """Return selected node or child shape that has an exposure attribute."""
    _require_maya()
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        raise RuntimeError("Select an Arnold dome light transform or shape first.")

    candidates = []
    node = selection[0]
    candidates.append(node)
    candidates.extend(cmds.listRelatives(node, shapes=True, fullPath=True) or [])

    for candidate in candidates:
        if cmds.attributeQuery("exposure", node=candidate, exists=True):
            return candidate
    raise RuntimeError("Selected node has no exposure attribute: %s" % node)


def _read_settings(iso_field, shutter_field, fstop_field, comp_field, calib_field) -> ExposureSettings:
    """Read advanced physical camera settings.

    Kept for future/advanced UI modes. The shutter value is exposure metadata only.
    """
    return ExposureSettings(
        iso=cmds.floatFieldGrp(iso_field, query=True, value1=True),
        shutter_seconds=parse_shutter(cmds.textFieldGrp(shutter_field, query=True, text=True)),
        fstop=cmds.floatFieldGrp(fstop_field, query=True, value1=True),
        exposure_compensation=cmds.floatFieldGrp(comp_field, query=True, value1=True),
        calibration_offset=cmds.floatFieldGrp(calib_field, query=True, value1=True),
    )


def _read_direct_ev100_settings(ev100_field, comp_field, calib_field) -> DirectEV100Settings:
    return DirectEV100Settings(
        ev100=cmds.floatFieldGrp(ev100_field, query=True, value1=True),
        exposure_compensation=cmds.floatFieldGrp(comp_field, query=True, value1=True),
        calibration_offset=cmds.floatFieldGrp(calib_field, query=True, value1=True),
    )


def _require_maya() -> None:
    if cmds is None:
        raise RuntimeError("This module must be run inside Maya for UI/camera operations.")
