# Maya EV100 Camera Exposure MVP

A small Maya helper for setting camera exposure from a direct EV100 value without touching motion-blur shutter settings.

The core EV100 math lives in `maya_ev100_tool.ev100_core` and has no Maya dependency, so it can be tested outside Maya. The Maya UI and camera attribute updates live in `maya_ev100_tool.maya_ev100_camera`.

## What It Does

- Accepts a direct EV100 value, exposure compensation, and calibration offset.
- Calculates the recommended Maya/Arnold camera exposure:

```text
camera exposure = -EV100 + exposure compensation + calibration offset
```

- Stores the calculated values as custom attributes on the selected camera shape:
  - `pbl_direct_ev100_mode`
  - `pbl_ev100`
  - `pbl_exposure_compensation`
  - `pbl_calibration_offset`
  - `pbl_recommended_camera_exposure`
- Applies the recommendation to Arnold `aiExposure` when that attribute exists on the camera shape.
- Creates calibration cubes with neutral diffuse reflectance values `0.71`, `0.18`, and `0.031` for pixel-inspector/light-meter workflows.
- Estimates an unknown HDRI's practical EV/calibration offset by comparing sampled linear RGB from a rendered calibration cube against its target reflectance.
- Does **not** change Maya/Arnold motion-blur shutter, shutter angle, shutter open/close, or render motion-blur settings.

## Why Direct EV100?

For VFX lighting work, ISO, shutter speed, and f-stop can be confusing because shutter values may also imply motion-blur behavior. This MVP keeps the workflow simple:

```text
Enter EV100 -> Apply camera exposure
```

The EV100 value is treated as exposure metadata only. Motion blur timing remains controlled by the normal Maya/Arnold render settings.

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

Then select a camera transform or camera shape, enter EV100, and click **Apply to Selected Camera**.

Example starting points:

```text
EV100 15: bright sunny daylight
EV100 12: overcast daylight
EV100 8 : bright office / studio interior
EV100 5 : dim interior
EV100 2 : night street / low light
```

## Calibration Cubes

Click **Create Calibration Cubes (0.71 / 0.18 / 0.031)** to create a grouped three-cube calibration target:

```text
White Paper : 0.71
Middle Gray : 0.18
Charcoal    : 0.031
```

Each cube receives a neutral Lambert material whose linear RGB values match the target reflectance. The cube transform, shape, and shader also store `pbl_reflectance` metadata.

Suggested workflow:

1. Set the camera EV100 value for the lighting condition, for example `EV100 15` for bright noon daylight.
2. Place the calibration cubes where you want to measure the light response.
3. Render with your normal Maya/Arnold/OCIO setup.
4. Use a pixel inspector or sampled render value on the lit face of each cube.
5. Average linear RGB roughly as `(R + G + B) / 3`.
6. Adjust exposure/calibration until the sampled values are near the cube references:
   - bright/lit reference: `0.71`
   - middle gray: `0.18`
   - dark/shadow reference: `0.031`

This mirrors the Unreal calibration note: find the value where white paper does not clip and charcoal does not crush, then use the resulting EV/calibration range as the shot or environment baseline.

## HDRI EV Calibrator

Use this when an HDRI has no trustworthy exposure metadata and you want to find the practical EV100 or offset for your Maya/Arnold setup.

Important limitation: the tool does **not** prove the absolute real-world EV from the HDRI file alone. It estimates the EV/calibration correction from a rendered known target in your current scene, renderer, and color pipeline.

Workflow:

1. Load the HDRI into your sky dome/environment.
2. Create the calibration cubes and place them at the measurement position.
3. Set a starting EV100, for example `12` or `15`.
4. Render.
5. Sample the lit face of a cube in **linear RGB**.
6. In **HDRI EV Calibrator**, choose the same target:
   - `White Paper 0.71`
   - `Middle Gray 0.18`
   - `Charcoal 0.031`
7. Enter sampled `R`, `G`, and `B`.
8. Click **Estimate HDRI EV**.

The calculation is:

```text
measured_average = (R + G + B) / 3
correction_stops = log2(target_reflectance / measured_average)
recommended_ev100 = current_ev100 - correction_stops
recommended_calibration_offset = current_calibration_offset + correction_stops
```

Example:

```text
Current EV100: 12
Target: Middle Gray 0.18
Measured RGB: 0.72 / 0.72 / 0.72

correction_stops = -2
recommended_ev100 = 14
```

Meaning: the HDRI is rendering the gray card two stops too bright at EV100 12, so either use roughly `EV100 14` or apply a `-2` stop calibration offset.

Click **Apply Suggested Offset** to write the recommended calibration offset into the main `Calibration Offset` field, then apply the camera settings if desired.

## Test Outside Maya

The pure EV100 helpers can be tested with pytest:

```bash
python -m pytest -q
```

## Calibration Note

This MVP uses a simple exposure-stop mapping:

```text
Maya/Arnold exposure stops = -EV100 + exposure compensation + calibration offset
```

For production use, calibrate `calibration_offset` with your studio's Arnold, OCIO, HDRI, and grey-card workflow.
