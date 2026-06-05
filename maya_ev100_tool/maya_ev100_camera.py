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

from .ev100_core import DirectEV100Settings, ExposureSettings, parse_shutter

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


def show() -> None:
    """Open the EV100 MVP UI inside Maya."""
    _require_maya()
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(WINDOW_NAME, title="EV100 Camera Exposure MVP", sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))

    cmds.text(label="Select a Maya camera, enter EV100, then Apply.", align="left")
    ev100 = cmds.floatFieldGrp(label="EV100", value1=10.0, numberOfFields=1)
    comp = cmds.floatFieldGrp(label="Exposure Comp", value1=0.0, numberOfFields=1)
    calib = cmds.floatFieldGrp(label="Calibration Offset", value1=0.0, numberOfFields=1)
    result = cmds.text(label="EV100: - / Maya exposure: -", align="left")

    def calculate_only(*_args):
        settings = _read_direct_ev100_settings(ev100, comp, calib)
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

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180), adjustableColumn=2)
    cmds.button(label="Calculate", command=calculate_only)
    cmds.button(label="Apply to Selected Camera", command=apply_to_selected)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.text(
        label="Note: recommended exposure = -EV100 + exposure comp + calibration offset.\n"
        "EV100 is exposure metadata only; this tool does not change motion-blur shutter settings.\n"
        "Calibration offset should be adjusted later with a grey-card/HDRI test.",
        align="left",
    )

    cmds.showWindow(window)
    calculate_only()


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
