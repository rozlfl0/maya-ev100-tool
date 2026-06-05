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
    LOCAL_LIGHT_PRESETS,
    DirectEV100Settings,
    ExposureSettings,
    default_local_light_rig_settings,
    estimate_hdri_ev_calibration,
    local_light_exposure_from_lumens,
    local_light_intensity_from_lumens,
    meters_to_scene_units,
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
    return "[%s] %s / EV100 %s" % (scenario.category, scenario.name, scenario.display_value)


def show() -> None:
    """Open the physical EV100 / dome calibration UI inside Maya."""
    _require_maya()
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    window = cmds.window(WINDOW_NAME, title="Physical EV100 Lighting Toolkit", sizeable=False)
    root = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))
    tabs = cmds.tabLayout(parent=root, innerMarginWidth=8, innerMarginHeight=8)
    env_tab = cmds.columnLayout(parent=tabs, adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))

    cmds.text(label="1) 라이팅 시나리오 EV100을 고른 뒤 선택한 카메라에 적용합니다.", align="left")
    scenario_menu = cmds.optionMenu(label="라이팅 시나리오")
    for scenario in EV100_SCENARIOS:
        cmds.menuItem(label=_scenario_label(scenario))
    ev100 = cmds.floatFieldGrp(label="적용 EV100", value1=EV100_SCENARIOS[0].ev100, numberOfFields=1)
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
        cmds.text(
            scenario_note,
            edit=True,
            label="%s / 표기 EV100 %s / 적용값 %.1f - %s" % (
                scenario.category,
                scenario.display_value,
                scenario.ev100,
                scenario.description,
            ),
        )
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
    cmds.rowLayout(numberOfColumns=1, columnWidth1=220)
    cmds.button(label="카메라에 EV100 적용", command=apply_to_selected)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.button(label="그레이 캘리브레이션 큐브 생성 (0.18)", command=lambda *_args: create_calibration_cubes())

    cmds.separator(height=8, style="in")
    cmds.text(label="2) Dome HDRI 캘리브레이션: Dome Light를 선택하고 그레이 큐브 측정 RGB를 넣습니다.", align="left")
    calibration_swatch = CALIBRATION_SWATCHES[0]
    cmds.text(label="타겟 픽셀: %s" % calibration_swatch.label, align="left")
    hdri_r = cmds.floatFieldGrp(label="측정 R", value1=0.180, numberOfFields=1, precision=4)
    hdri_g = cmds.floatFieldGrp(label="측정 G", value1=0.180, numberOfFields=1, precision=4)
    hdri_b = cmds.floatFieldGrp(label="측정 B", value1=0.180, numberOfFields=1, precision=4)
    hdri_result = cmds.text(label="Dome 캘리브레이션: -", align="left")

    def _analyze_dome_exposure_with_current(current_dome_exposure=None):
        if current_dome_exposure is None:
            dome_node = get_selected_exposure_node()
            current_dome_exposure = cmds.getAttr("%s.exposure" % dome_node)
        result_data = estimate_hdri_ev_calibration(
            current_ev100=cmds.floatFieldGrp(ev100, query=True, value1=True),
            measured_rgb=(
                cmds.floatFieldGrp(hdri_r, query=True, value1=True),
                cmds.floatFieldGrp(hdri_g, query=True, value1=True),
                cmds.floatFieldGrp(hdri_b, query=True, value1=True),
            ),
            target_reflectance=calibration_swatch.reflectance,
            current_dome_exposure=current_dome_exposure,
        )
        direction = "어두움 → 올리기" if result_data.correction_stops > 0.0 else "밝음 → 낮추기"
        cmds.text(
            hdri_result,
            edit=True,
            label=(
                "현재 Dome %.3f / 평균 %.3f / 타겟 %.3f\n"
                "보정 %.3f stops (%s) → 추천 Dome Exposure %.3f"
            )
            % (
                current_dome_exposure,
                result_data.measured_average,
                result_data.target_reflectance,
                result_data.correction_stops,
                direction,
                result_data.recommended_dome_exposure,
            ),
        )
        return result_data

    def analyze_dome_exposure(*_args):
        return _analyze_dome_exposure_with_current()

    def apply_dome_exposure_to_selected(*_args):
        dome_node = get_selected_exposure_node()
        current_exposure = cmds.getAttr("%s.exposure" % dome_node)
        result_data = _analyze_dome_exposure_with_current(current_exposure)
        cmds.setAttr("%s.exposure" % dome_node, result_data.recommended_dome_exposure)
        cmds.inViewMessage(
            amg="Applied Dome exposure <hl>%.3f</hl> to %s" % (result_data.recommended_dome_exposure, dome_node),
            pos="topCenter",
            fade=True,
        )

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 220), adjustableColumn=2)
    cmds.button(label="선택 Dome Exposure 분석", command=analyze_dome_exposure)
    cmds.button(label="선택한 Dome Light에 적용", command=apply_dome_exposure_to_selected)
    cmds.setParent("..")

    cmds.separator(height=8, style="in")
    cmds.text(
        label="워크플로우: EV100은 카메라/시나리오 기준, 타겟 픽셀 맞추기는 Dome Light exposure 기준입니다.\n"
        "Dome Light를 선택한 상태로 분석/적용합니다. 측정 RGB는 0.18 그레이 큐브 면에서 얻은 linear render value여야 합니다. 모션블러 셔터는 건드리지 않습니다.",
        align="left",
    )

    local_tab = cmds.columnLayout(parent=tabs, adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))
    cmds.text(label="로컬 라이트: 루멘 프리셋으로 Rect / Point / Spot 라이트를 만들고 그레이 픽셀값으로 보정합니다.", align="left")
    local_preset_menu = cmds.optionMenu(label="라이트 프리셋")
    for preset in LOCAL_LIGHT_PRESETS:
        cmds.menuItem(label=_local_light_preset_label(preset))
    local_lumens = cmds.floatFieldGrp(label="루멘", value1=LOCAL_LIGHT_PRESETS[0].lumens, numberOfFields=1, precision=1)
    local_kelvin = cmds.floatFieldGrp(label="색온도 Kelvin", value1=LOCAL_LIGHT_PRESETS[0].kelvin, numberOfFields=1, precision=0)
    rect_width = cmds.floatFieldGrp(label="Rect 가로", value1=1.0, numberOfFields=1, precision=3)
    rect_height = cmds.floatFieldGrp(label="Rect 세로", value1=1.0, numberOfFields=1, precision=3)
    spot_cone = cmds.floatFieldGrp(label="Spot Cone Angle", value1=45.0, numberOfFields=1, precision=1)
    rig_distance = cmds.floatFieldGrp(label="타겟까지 거리 m", value1=0.5, numberOfFields=1, precision=3)
    source_size = cmds.floatFieldGrp(label="소스 크기 m", value1=0.03, numberOfFields=1, precision=3)
    use_selected_target = cmds.checkBox(label="선택 오브젝트 중심을 타겟으로 사용", value=True)
    create_gray_card = cmds.checkBox(label="타겟 위치에 0.18 그레이 카드 생성", value=True)
    local_note = cmds.text(label="", align="left")
    local_r = cmds.floatFieldGrp(label="측정 R", value1=0.180, numberOfFields=1, precision=4)
    local_g = cmds.floatFieldGrp(label="측정 G", value1=0.180, numberOfFields=1, precision=4)
    local_b = cmds.floatFieldGrp(label="측정 B", value1=0.180, numberOfFields=1, precision=4)
    local_result = cmds.text(label="Local Light 캘리브레이션: -", align="left")

    def _selected_local_preset():
        selected_label = cmds.optionMenu(local_preset_menu, query=True, value=True)
        for preset in LOCAL_LIGHT_PRESETS:
            if _local_light_preset_label(preset) == selected_label:
                return preset
        raise RuntimeError("Unknown local light preset: %s" % selected_label)

    def load_local_preset(*_args):
        preset = _selected_local_preset()
        rig = default_local_light_rig_settings(preset.name, preset.light_type)
        cmds.floatFieldGrp(local_lumens, edit=True, value1=preset.lumens)
        cmds.floatFieldGrp(local_kelvin, edit=True, value1=preset.kelvin)
        cmds.floatFieldGrp(rig_distance, edit=True, value1=rig.distance_m)
        cmds.floatFieldGrp(source_size, edit=True, value1=rig.source_size_m)
        if preset.light_type == "Rect":
            cmds.floatFieldGrp(rect_width, edit=True, value1=rig.source_size_m)
            cmds.floatFieldGrp(rect_height, edit=True, value1=rig.source_size_m)
        range_text = " / range %s" % preset.common_range if preset.common_range else ""
        cmds.text(local_note, edit=True, label="%s [%s] / %.1f lm / %.0fK%s / 거리 %.2fm / 크기 %.2fm - %s" % (preset.name, preset.light_type, preset.lumens, preset.kelvin, range_text, rig.distance_m, rig.source_size_m, rig.note))

    def create_local_light_from_ui(*_args):
        node = create_local_light(
            light_type=_selected_local_preset().light_type,
            lumens=cmds.floatFieldGrp(local_lumens, query=True, value1=True),
            kelvin=cmds.floatFieldGrp(local_kelvin, query=True, value1=True),
            rect_width=cmds.floatFieldGrp(rect_width, query=True, value1=True),
            rect_height=cmds.floatFieldGrp(rect_height, query=True, value1=True),
            cone_angle=cmds.floatFieldGrp(spot_cone, query=True, value1=True),
            preset_name=_selected_local_preset().name,
        )
        cmds.inViewMessage(amg="Created local light <hl>%s</hl>" % node, pos="topCenter", fade=True)
        return node

    def create_local_light_rig_from_ui(*_args):
        preset = _selected_local_preset()
        node = create_local_light_distance_rig(
            light_type=preset.light_type,
            lumens=cmds.floatFieldGrp(local_lumens, query=True, value1=True),
            kelvin=cmds.floatFieldGrp(local_kelvin, query=True, value1=True),
            distance_m=cmds.floatFieldGrp(rig_distance, query=True, value1=True),
            source_size_m=cmds.floatFieldGrp(source_size, query=True, value1=True),
            rect_width=cmds.floatFieldGrp(rect_width, query=True, value1=True),
            rect_height=cmds.floatFieldGrp(rect_height, query=True, value1=True),
            cone_angle=cmds.floatFieldGrp(spot_cone, query=True, value1=True),
            preset_name=preset.name,
            use_selected_target=cmds.checkBox(use_selected_target, query=True, value=True),
            create_gray_card=cmds.checkBox(create_gray_card, query=True, value=True),
        )
        cmds.inViewMessage(amg="Created local light distance rig <hl>%s</hl>" % node, pos="topCenter", fade=True)
        return node

    def _analyze_local_light_with_current(node=None):
        light_node = node or get_selected_light_control_node()
        current_value, mode = _get_light_calibration_value(light_node)
        result_data = estimate_hdri_ev_calibration(
            current_ev100=cmds.floatFieldGrp(ev100, query=True, value1=True),
            measured_rgb=(
                cmds.floatFieldGrp(local_r, query=True, value1=True),
                cmds.floatFieldGrp(local_g, query=True, value1=True),
                cmds.floatFieldGrp(local_b, query=True, value1=True),
            ),
            target_reflectance=calibration_swatch.reflectance,
            current_dome_exposure=current_value,
        )
        direction = "어두움 → 올리기" if result_data.correction_stops > 0.0 else "밝음 → 낮추기"
        target_value = result_data.recommended_dome_exposure if mode == "exposure" else current_value * (2.0 ** result_data.correction_stops)
        label = (
            "선택 Light %s %.3f / 평균 %.3f / 타겟 %.3f\n"
            "보정 %.3f stops (%s) → 추천 %s %.3f"
        ) % (
            mode,
            current_value,
            result_data.measured_average,
            result_data.target_reflectance,
            result_data.correction_stops,
            direction,
            mode,
            target_value,
        )
        cmds.text(local_result, edit=True, label=label)
        return light_node, mode, target_value, result_data

    def analyze_local_light(*_args):
        return _analyze_local_light_with_current()

    def apply_local_light(*_args):
        light_node, mode, target_value, result_data = _analyze_local_light_with_current()
        if mode == "exposure":
            cmds.setAttr("%s.exposure" % light_node, target_value)
        else:
            cmds.setAttr("%s.intensity" % light_node, target_value)
        cmds.inViewMessage(amg="Applied %s <hl>%.3f</hl> to %s" % (mode, target_value, light_node), pos="topCenter", fade=True)
        return result_data

    cmds.optionMenu(local_preset_menu, edit=True, changeCommand=load_local_preset)
    cmds.rowLayout(numberOfColumns=4, columnWidth4=(150, 170, 170, 190), adjustableColumn=4)
    cmds.button(label="Local Light 생성", command=create_local_light_from_ui)
    cmds.button(label="거리 Rig 생성", command=create_local_light_rig_from_ui)
    cmds.button(label="선택 Local 분석", command=analyze_local_light)
    cmds.button(label="선택 Local 적용", command=apply_local_light)
    cmds.setParent("..")
    cmds.text(label="거리 Rig는 선택 오브젝트 중심 또는 원점에 타겟/거리 라인/0.18 그레이카드를 만들고, 라이트를 지정 거리만큼 배치해 타겟을 바라보게 합니다. 루멘은 초기 스케일, 최종값은 그레이 측정으로 보정합니다.", align="left")

    cmds.tabLayout(tabs, edit=True, tabLabel=((env_tab, "Env Light"), (local_tab, "Local Light")))
    cmds.showWindow(window)
    load_scenario()
    load_local_preset()


def create_calibration_cubes(size: float = 1.0, spacing: float = 1.4) -> str:
    """Create neutral reflectance cubes for PBL exposure calibration.

    The cube uses a Lambert material with 0.18 linear RGB reflectance.
    It is intended for render/pixel-inspector calibration, not beauty shading.
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
        amg="Created <hl>PBL middle gray calibration cube</hl>: 0.18",
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


def _local_light_preset_label(preset) -> str:
    range_text = " / %s" % preset.common_range if preset.common_range else ""
    return "[%s] %s / %.0f lm / %.0fK%s" % (preset.light_type, preset.name, preset.lumens, preset.kelvin, range_text)


def create_local_light(
    light_type: str,
    lumens: float,
    kelvin: float,
    rect_width: float = 1.0,
    rect_height: float = 1.0,
    cone_angle: float = 45.0,
    preset_name: str = "Local Light",
) -> str:
    """Create a practical local light with lumen metadata and a useful starting scale."""
    _require_maya()
    safe_name = "PBL_%s_%s" % (preset_name.replace(" ", "_"), light_type)
    light_type = light_type.lower()
    if light_type == "rect":
        try:
            node = cmds.shadingNode("aiAreaLight", asLight=True, name=safe_name)
        except Exception:
            node = cmds.shadingNode("areaLight", asLight=True, name=safe_name)
        _set_rect_light_size(node, rect_width, rect_height)
    elif light_type == "spot":
        node = cmds.spotLight(name=safe_name)
        if cmds.attributeQuery("coneAngle", node=node, exists=True):
            cmds.setAttr("%s.coneAngle" % node, float(cone_angle))
    elif light_type == "point":
        node = cmds.pointLight(name=safe_name)
    else:
        raise ValueError("Unsupported local light type: %s" % light_type)

    control_node = get_light_control_node(node)
    _apply_light_color_temperature(control_node, kelvin)
    _set_initial_local_light_scale(control_node, lumens)
    _set_or_add_double_attr(control_node, "pbl_lumens", lumens)
    _set_or_add_double_attr(control_node, "pbl_kelvin", kelvin)
    _set_or_add_double_attr(control_node, "pbl_lumen_exposure", local_light_exposure_from_lumens(lumens))
    cmds.select(control_node, replace=True)
    return control_node


def create_local_light_distance_rig(
    light_type: str,
    lumens: float,
    kelvin: float,
    distance_m: float,
    source_size_m: float,
    rect_width: float = 1.0,
    rect_height: float = 1.0,
    cone_angle: float = 45.0,
    preset_name: str = "Local Light",
    use_selected_target: bool = True,
    create_gray_card: bool = True,
) -> str:
    """Create a local light with target locator, distance guide, and optional gray card."""
    _require_maya()
    if float(distance_m) <= 0.0:
        raise ValueError("distance_m must be positive")
    if float(source_size_m) <= 0.0:
        raise ValueError("source_size_m must be positive")

    target_position = _selected_target_position() if use_selected_target else (0.0, 0.0, 0.0)
    distance_scene = _meters_to_scene_units(distance_m)
    source_size_scene = _meters_to_scene_units(source_size_m)
    safe_name = preset_name.replace(" ", "_")
    group = cmds.group(empty=True, name="PBL_%s_DistanceRig_GRP" % safe_name)

    target = cmds.spaceLocator(name="PBL_%s_Target_LOC" % safe_name)[0]
    cmds.xform(target, worldSpace=True, translation=target_position)
    cmds.parent(target, group, absolute=True)

    light_node = create_local_light(
        light_type=light_type,
        lumens=lumens,
        kelvin=kelvin,
        rect_width=source_size_scene if light_type.lower() == "rect" else rect_width,
        rect_height=source_size_scene if light_type.lower() == "rect" else rect_height,
        cone_angle=cone_angle,
        preset_name=preset_name,
    )
    light_transform = _transform_for_node(light_node) or light_node
    light_position = (target_position[0], target_position[1] + source_size_scene * 0.5, target_position[2] + distance_scene)
    cmds.xform(light_transform, worldSpace=True, translation=light_position)
    cmds.parent(light_transform, group, absolute=True)
    _aim_light_at_target(light_transform, target)

    guide = _create_distance_curve("PBL_%s_Distance_GUIDE" % safe_name, target_position, light_position, distance_m)
    if guide:
        cmds.parent(guide, group, absolute=True)

    if create_gray_card:
        card = _create_middle_gray_card("PBL_%s_GrayCard_0p18" % safe_name, target_position, source_size_scene)
        cmds.parent(card, group, absolute=True)

    for node in (group, light_node):
        _set_or_add_double_attr(node, "pbl_distance_m", distance_m)
        _set_or_add_double_attr(node, "pbl_source_size_m", source_size_m)
    _set_or_add_double_attr(group, "pbl_lumens", lumens)
    _set_or_add_double_attr(group, "pbl_kelvin", kelvin)

    cmds.select(light_node, replace=True)
    return light_node


def _meters_to_scene_units(meters: float) -> float:
    """Convert artist-facing meters to current Maya units at 1/10 rig scale."""
    unit = "cm"
    try:
        unit = cmds.currentUnit(query=True, linear=True)
    except Exception:
        pass
    return meters_to_scene_units(meters, unit)


def _selected_target_position() -> tuple[float, float, float]:
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        return (0.0, 0.0, 0.0)
    try:
        bbox = cmds.exactWorldBoundingBox(selection[0])
        return ((bbox[0] + bbox[3]) * 0.5, (bbox[1] + bbox[4]) * 0.5, (bbox[2] + bbox[5]) * 0.5)
    except Exception:
        return tuple(cmds.xform(selection[0], query=True, worldSpace=True, translation=True))


def _create_distance_curve(name: str, start: tuple[float, float, float], end: tuple[float, float, float], distance_m: float) -> str | None:
    try:
        curve = cmds.curve(name=name, degree=1, point=[start, end])
        _set_or_add_double_attr(curve, "pbl_distance_m", distance_m)
        return curve
    except Exception:
        return None


def _create_middle_gray_card(name: str, target_position: tuple[float, float, float], source_size_scene: float) -> str:
    size = max(_meters_to_scene_units(0.15), min(_meters_to_scene_units(1.0), float(source_size_scene) * 2.0))
    card = cmds.polyCube(name=name, width=size, height=size, depth=_meters_to_scene_units(0.02))[0]
    cmds.xform(card, worldSpace=True, translation=(target_position[0], target_position[1], target_position[2]))
    cmds.setAttr("%s.rotateX" % card, CALIBRATION_CUBE_ROTATE_X_DEGREES)
    shader = _create_lambert_reflectance_shader("local_gray_card", CALIBRATION_SWATCHES[0].rgb)
    cmds.select(card, replace=True)
    cmds.hyperShade(assign=shader)
    _set_or_add_double_attr(card, "pbl_reflectance", CALIBRATION_SWATCHES[0].reflectance)
    return card


def _aim_light_at_target(light_transform: str, target: str) -> None:
    if not light_transform or cmds.nodeType(light_transform) != "transform":
        return
    try:
        constraint = cmds.aimConstraint(
            target,
            light_transform,
            aimVector=(0, 0, -1),
            upVector=(0, 1, 0),
            worldUpType="scene",
        )[0]
        cmds.delete(constraint)
    except Exception:
        pass


def _set_rect_light_size(node: str, width: float, height: float) -> None:
    transform = _transform_for_node(node)
    if cmds.attributeQuery("width", node=node, exists=True):
        cmds.setAttr("%s.width" % node, float(width))
    if cmds.attributeQuery("height", node=node, exists=True):
        cmds.setAttr("%s.height" % node, float(height))
    if transform:
        cmds.setAttr("%s.scaleX" % transform, float(width))
        cmds.setAttr("%s.scaleY" % transform, float(height))


def _set_initial_local_light_scale(node: str, lumens: float) -> None:
    if cmds.attributeQuery("exposure", node=node, exists=True):
        cmds.setAttr("%s.exposure" % node, local_light_exposure_from_lumens(lumens))
        if cmds.attributeQuery("intensity", node=node, exists=True):
            cmds.setAttr("%s.intensity" % node, 1.0)
    elif cmds.attributeQuery("intensity", node=node, exists=True):
        cmds.setAttr("%s.intensity" % node, local_light_intensity_from_lumens(lumens))


def _apply_light_color_temperature(node: str, kelvin: float) -> None:
    rgb = _kelvin_to_rgb(kelvin)
    if cmds.attributeQuery("color", node=node, exists=True):
        cmds.setAttr("%s.color" % node, rgb[0], rgb[1], rgb[2], type="double3")
    if cmds.attributeQuery("aiColorTemperature", node=node, exists=True):
        cmds.setAttr("%s.aiColorTemperature" % node, float(kelvin))
    if cmds.attributeQuery("aiUseColorTemperature", node=node, exists=True):
        cmds.setAttr("%s.aiUseColorTemperature" % node, 1)


def _kelvin_to_rgb(kelvin: float) -> tuple[float, float, float]:
    """Approximate Kelvin to RGB for light color fallback."""
    import math

    temperature = max(1000.0, min(40000.0, float(kelvin))) / 100.0
    if temperature <= 66.0:
        red = 255.0
        green = 99.4708025861 * math.log(temperature) - 161.1195681661
        blue = 0.0 if temperature <= 19.0 else 138.5177312231 * math.log(temperature - 10.0) - 305.0447927307
    else:
        red = 329.698727446 * ((temperature - 60.0) ** -0.1332047592)
        green = 288.1221695283 * ((temperature - 60.0) ** -0.0755148492)
        blue = 255.0
    return tuple(max(0.0, min(1.0, channel / 255.0)) for channel in (red, green, blue))


def get_light_control_node(node: str) -> str:
    candidates = [node]
    candidates.extend(cmds.listRelatives(node, shapes=True, fullPath=True) or [])
    parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
    if parent:
        candidates.append(parent)
    for candidate in candidates:
        if candidate and (cmds.attributeQuery("exposure", node=candidate, exists=True) or cmds.attributeQuery("intensity", node=candidate, exists=True)):
            return candidate
    return node


def get_selected_light_control_node() -> str:
    _require_maya()
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        raise RuntimeError("Select a local light transform or shape first.")
    return get_light_control_node(selection[0])


def _get_light_calibration_value(node: str) -> tuple[float, str]:
    if cmds.attributeQuery("exposure", node=node, exists=True):
        return float(cmds.getAttr("%s.exposure" % node)), "exposure"
    if cmds.attributeQuery("intensity", node=node, exists=True):
        return float(cmds.getAttr("%s.intensity" % node)), "intensity"
    raise RuntimeError("Selected light has no exposure or intensity attribute: %s" % node)


def _transform_for_node(node: str) -> str | None:
    if cmds.nodeType(node) == "transform":
        return node
    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    return parents[0] if parents else None


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
