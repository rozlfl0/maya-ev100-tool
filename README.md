# Maya EV100 Physical Lighting Toolkit

A small Maya/Arnold helper for a physically based lighting workflow:

```text
Choose lighting scenario EV100 -> apply to camera -> calibrate HDRI Dome Light exposure with target pixels
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
- Creates calibration cubes with neutral diffuse reflectance values `0.71`, `0.18`, and `0.031` for pixel-inspector/light-meter workflows.
- Analyzes sampled target RGB values and recommends how much to raise/lower Arnold Dome Light `exposure`.
- Can apply the recommended dome exposure to a selected dome light/shape when it has an `exposure` attribute.
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

## EV100 Scenario Presets

The UI includes a **Lighting Scenario** dropdown. Current starter references:

```text
Sunny exterior noon          EV100 15.0
Sunny exterior morning 8AM   EV100 13.5
Sunny exterior late afternoon EV100 13.0
Overcast exterior            EV100 12.0
Open shade exterior          EV100 11.0
Bright studio / stage        EV100 9.0
Bright office interior       EV100 8.0
Home interior                EV100 6.0
Dim interior                 EV100 5.0
Night street                 EV100 2.0
```

These are practical starting values. Replace/refine them with a studio reference sheet when exact production values are available.

## Camera EV100 Setup

1. Select a camera transform or camera shape.
2. Choose a lighting scenario from the dropdown.
3. Click **Load Scenario EV** if needed.
4. Click **Apply EV100 to Camera**.

The tool sets Arnold camera exposure when `aiExposure` exists:

```text
aiExposure = -EV100
```

No exposure compensation or calibration offset is required in the default workflow. If the core still stores offset-related custom attrs, they remain `0` for compatibility.

## Calibration Cubes

Click **Create Calibration Cubes (0.71 / 0.18 / 0.031)** to create a grouped three-cube calibration target:

```text
White Paper : 0.71
Middle Gray : 0.18
Charcoal    : 0.031
```

Each cube receives a neutral Lambert material whose linear RGB values match the target reflectance. The cubes are created with `Rotate X = 45` degrees so angled/side light can be sampled more easily. The cube transform, shape, and shader also store `pbl_reflectance` metadata.

## Dome HDRI Calibration

Use this when an HDRI has no trustworthy exposure metadata and you want to tune the Arnold Dome Light brightness against target pixels.

Workflow:

1. Apply the EV100 scenario to the camera.
2. Load the HDRI into the Dome/SkyDome Light.
3. Keep Dome `exposure` at `0` for the first test.
4. Render the calibration cubes.
5. Sample a lit cube face in **linear RGB**.
6. In **Dome HDRI Calibration**, choose the matching target:
   - `White Paper 0.71`
   - `Middle Gray 0.18`
   - `Charcoal 0.031`
7. Enter sampled `R`, `G`, and `B`.
8. Enter the current Dome Light exposure.
9. Click **Analyze Dome Exposure**.

The calculation is:

```text
measured_average = (R + G + B) / 3
correction_stops = log2(target_reflectance / measured_average)
recommended_dome_exposure = current_dome_exposure + correction_stops
```

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

To apply automatically, select the Arnold dome light transform or shape and click **Apply to Selected Dome Light**. The selected node or its shape must have an `exposure` attribute.

## Test Outside Maya

The pure EV100 helpers can be tested with pytest:

```bash
python -m pytest -q
python -m compileall maya_ev100_tool -q
```
