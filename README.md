# Maya EV100 Physical Lighting Toolkit

A small Maya/Arnold helper for a physically based lighting workflow:

```text
Choose lighting scenario EV100 -> apply to camera -> calibrate HDRI Dome Light exposure with target pixels
```

The UI is split into two tabs:

```text
Env Light   -> camera EV100 + HDRI/Dome exposure calibration
Local Light -> lumen-preset Rect / Point / Spot light creation and gray-card calibration
```

The core EV100 math lives in `maya_ev100_tool.ev100_core` and has no Maya dependency, so it can be tested outside Maya. The Maya UI and camera/light attribute updates live in `maya_ev100_tool.maya_ev100_camera`.

## What It Does

- Provides EV100 scenario presets for exterior/interior lighting references.
- Applies the selected EV100 to a Maya/Arnold camera exposure:

```text
camera exposure = -EV100
```

- Stores the calculated values as custom attributes on the selected camera shape:
  - `pbl_direct_ev100_mode`
  - `pbl_ev100`
  - `pbl_exposure_compensation`
  - `pbl_calibration_offset`
  - `pbl_recommended_camera_exposure`
- Applies the recommendation to Arnold `aiExposure` when that attribute exists on the camera shape.
- Creates a neutral `0.18` middle-gray calibration cube for pixel-inspector/light-meter workflows.
- Analyzes sampled target RGB values and recommends how much to raise/lower Arnold Dome Light `exposure`.
- Reads the selected dome light/shape's current `exposure` and applies the correction as `current exposure + correction`.
- Creates local Rect / Point / Spot lights from real-world lumen presets and color-temperature starting points.
- Calibrates selected local lights from a `0.18` gray cube by adjusting `exposure` when available, or `intensity` as a fallback.
- Does **not** change Maya/Arnold motion-blur shutter, shutter angle, shutter open/close, or render motion-blur settings.

## Physical Workflow

The intended workflow mirrors Unreal-style physically based lighting:

```text
1. Pick a time/weather/interior scenario.
2. Use the reference EV100 for the camera.
3. Put the HDRI in an Arnold SkyDome/Dome Light.
4. Render calibration cubes.
5. Match target pixel values by changing Dome Light exposure, not camera EV.
```

EV100 belongs to the **camera/scenario**. HDRI target-pixel matching belongs to the **Dome Light exposure**.

## Use In Maya

Run this from the Maya Script Editor Python tab:

```python
import sys

sys.path.insert(0, r"C:/Users/maste/Desktop/maya_ev100_tool")

from maya_ev100_tool import maya_ev100_camera

maya_ev100_camera.show()
```

If Maya already imported an older version during the same session, use this reload-safe snippet instead:

```python
import sys
import importlib

sys.path.insert(0, r"C:/Users/maste/Desktop/maya_ev100_tool")

import maya_ev100_tool.ev100_core as ev100_core
import maya_ev100_tool.maya_ev100_camera as maya_ev100_camera

importlib.reload(ev100_core)
importlib.reload(maya_ev100_camera)

maya_ev100_camera.show()
```

## EV100 시나리오 프리셋

UI의 **라이팅 시나리오** 드롭다운은 형님이 첨부한 EV100 표 기준을 한국어로 옮긴 것입니다.
범위 값은 드롭다운에는 원래 범위로 표시하고, 실제 적용 EV100은 중간값을 사용합니다.

```text
[야외 낮] 밝은 모래/눈, 직사광 또는 약간 흐린 햇빛        EV100 16
[야외 낮] 맑은 직사광, 깨끗한 하늘 배경                  EV100 15
[야외 낮] 흐릿한 햇빛, 구름 낀 하늘 배경                 EV100 14
[야외 낮] 밝은 흐린 날                                  EV100 13
[야외 낮] 강한 흐림, 일몰 무렵                          EV100 12
[야외 낮] 일몰 직전                                    EV100 12-14, 적용값 13
[야외 낮] 일몰 직후                                    EV100 9-11, 적용값 10

[야외 밤] 네온/밝은 간판                                EV100 9-10, 적용값 9.5
[야외 밤] 야간 스포츠, 화재/불타는 건물                  EV100 9
[야외 밤] 밝은 밤거리                                   EV100 8
[야외 밤] 밤거리와 쇼윈도                               EV100 7-8, 적용값 7.5
[야외 밤] 축제/놀이공원                                 EV100 7
[야외 밤] 야간 차량 통행                                EV100 5
[야외 밤] 투광 조명 건축물                              EV100 3-5, 적용값 4
[야외 밤] 멀리 보이는 불 켜진 건물들                    EV100 2

[실내] 갤러리                                           EV100 8-11, 적용값 9.5
[실내] 무대 쇼/스포츠 이벤트                            EV100 8-9, 적용값 8.5
[실내] 사무실/작업 공간                                 EV100 7-8, 적용값 7.5
[실내] 주거 실내                                       EV100 5-7, 적용값 6
```

## Camera EV100 Setup

1. Select a camera transform or camera shape.
2. Choose a lighting scenario from the dropdown.
3. Click **Apply EV100 to Camera**.

The tool sets Arnold camera exposure when `aiExposure` exists:

```text
aiExposure = -EV100
```

This is an artist-facing Maya/Arnold exposure mapping: `EV100 12` sets camera `aiExposure` to `-12` stops. Higher EV100 represents a darker photographic/view exposure. Positive exposure compensation or calibration offset values still brighten from that base. The shot EV is kept as the global viewing/exposure reference, while Env/Local Light tabs calibrate light brightness against the 0.18 gray cube.

No exposure compensation or calibration offset is required in the default workflow. If the core still stores offset-related custom attrs, they remain `0` for compatibility.

## Calibration Cube

Click **그레이 캘리브레이션 큐브 생성 (0.18)** to create one middle-gray calibration target:

```text
Middle Gray : 0.18
```

The cube receives a neutral Lambert material whose linear RGB values match the target reflectance. The cube is created with `Rotate X = 45` degrees so angled/side light can be sampled more easily. The cube transform, shape, and shader also store `pbl_reflectance` metadata.

Why middle gray only: `0.18` is the most stable neutral exposure reference. `0.71` white is useful as a highlight/clipping guard, but it can be affected more easily by clipping, bloom/glare, display transforms, or render-view sampling mistakes. `0.031` charcoal is mostly a shadow/crushing check. For a simple Maya Dome exposure calibration workflow, one `0.18` gray cube is the cleanest default.

## Dome HDRI Calibration

Use this when an HDRI has no trustworthy exposure metadata and you want to tune the Arnold Dome Light brightness against target pixels.

Workflow:

1. Apply the EV100 scenario to the camera.
2. Load the HDRI into the Dome/SkyDome Light.
3. Keep Dome `exposure` at `0` for the first test.
4. Render the gray calibration cube.
5. Sample the lit gray cube face in **linear RGB**.
6. Select the Arnold dome light transform or shape.
7. Enter sampled `R`, `G`, and `B`.
8. Click **선택 Dome Exposure 분석** or **선택한 Dome Light에 적용**.

The calculation is:

```text
measured_average = (R + G + B) / 3
correction_stops = log2(target_reflectance / measured_average)
recommended_dome_exposure = current_dome_exposure + correction_stops
```

The UI reads `current_dome_exposure` directly from the selected Dome Light `exposure` attribute. You do not need to type the current exposure manually.

Example:

```text
Target: Middle Gray 0.18
Current Dome Exposure: 0
Measured RGB: 0.247 / 0.246 / 0.268
Average: 0.254

correction_stops ≈ -0.49
recommended_dome_exposure ≈ -0.49
```

Meaning: the HDRI/Dome is about half a stop too bright for the chosen EV100 camera setup, so lower the Dome Light exposure by about `-0.5` stop.

To apply automatically, select the Arnold dome light transform or shape and click **선택한 Dome Light에 적용**. The selected node or its shape must have an `exposure` attribute.

## Local Light Tab

Use this tab for fast practical/local light starters. The default workflow is now intentionally simple: choose a situation preset, select a subject/object, then click **선택 오브젝트 앞에 생성**. Distance, source size, lumen, and Kelvin controls are hidden under **Advanced** for when you actually need them.

Current situation presets. Each preset has a fixed light type, so there is no separate Rect / Point / Spot selector in the UI:

```text
[Point] 촛불 가까이          13 lm     1800K
[Point] 책상 스탠드          500 lm    2700K
[Rect]  방 천장등            1000 lm   4000K
[Spot]  차량 헤드라이트      1500 lm   4300K
[Spot]  가로등 느낌          60000 lm  2200K
[Point] 작은 LED Practical   400 lm    5600K
```

Workflow:

```text
1. Keep the camera EV100 as the shot-wide physical exposure reference.
2. Open Local Light tab.
3. Choose a situation preset.
4. Select a subject/object.
5. Click 선택 오브젝트 앞에 생성.
6. If the result needs art direction, open Advanced and adjust distance/source size/lumen/Kelvin.
7. Render the generated 0.18 gray card under that local light.
8. Enter sampled linear RGB.
9. Select the local light and click 선택 Local 분석 or 선택 Local 적용.
```

`선택 오브젝트 앞에 생성` creates:

```text
PBL_<Preset>_DistanceRig_GRP
PBL_<Preset>_Target_LOC
PBL_<Preset>_Distance_GUIDE
PBL_<Preset>_GrayCard_0p18
PBL_<Preset>_<Type> light
```

The light is placed at the requested meter distance from the target and aimed toward it. If **선택 오브젝트 중심을 타겟으로 사용** is enabled, the selected object's bounding-box center becomes the target; otherwise the rig starts at world origin. The rig converts meters to the current Maya scene unit, then applies a practical **1/10 rig scale**, so in a default centimeter scene `0.5m` becomes `5` Maya units and `5m` becomes `50` Maya units. The rig stores `pbl_distance_m`, `pbl_source_size_m`, `pbl_lumens`, and `pbl_kelvin` metadata.

Default distance/source-size starting points:

```text
촛불 가까이          Point  0.5m  / 0.03m source
책상 스탠드          Point  1.0m  / 0.12m source
방 천장등            Rect   1.5m  / 0.8m source
차량 헤드라이트      Spot   5.0m  / 0.18m source
가로등 느낌          Spot   8.0m  / 0.6m source
작은 LED Practical   Point  1.0m  / 0.08m source
```

The lumen value is used as a practical starting scale:

```text
Lights with exposure attr:
1000 lm -> exposure 0
2000 lm -> exposure +1
500 lm  -> exposure -1

Maya Point/Spot fallback with intensity only:
13 lm   -> intensity 1300
500 lm  -> intensity 50000
```

This is intentionally an artist-safe initial scale, not a claim that every Maya/Arnold light type interprets `intensity` as true lumens. Maya default Point/Spot `intensity` needs a much larger practical fallback scale under EV100 camera exposure, so the tool uses `intensity = lumens * 100` when no `exposure` attribute exists. The final reliable step is the same gray-pixel calibration:

```text
correction_stops = log2(0.18 / measured_average)
new exposure = current exposure + correction_stops
```

If the selected local light has no `exposure` attribute, the tool falls back to multiplying `intensity` by `2 ** correction_stops`.

## Test Outside Maya

The pure EV100 helpers can be tested with pytest:

```bash
python -m pytest -q
python -m compileall maya_ev100_tool -q
```
