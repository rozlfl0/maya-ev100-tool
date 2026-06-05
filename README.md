# Maya EV100 Camera Exposure MVP

A small Maya helper for calculating EV100 from physical camera settings and applying the recommended exposure stop offset to a selected Maya camera.

The core EV100 math lives in `maya_ev100_tool.ev100_core` and has no Maya dependency, so it can be tested outside Maya. The Maya UI and camera attribute updates live in `maya_ev100_tool.maya_ev100_camera`.

## What It Does

- Accepts ISO, shutter speed, f-stop, exposure compensation, and calibration offset.
- Calculates EV100 from the physical camera settings.
- Calculates the recommended Maya/Arnold camera exposure:

```text
camera exposure = -EV100 + exposure compensation + calibration offset
```

- Stores the calculated values as custom attributes on the selected camera shape:
  - `pbl_ev100`
  - `pbl_iso`
  - `pbl_shutter_seconds`
  - `pbl_fstop`
  - `pbl_exposure_compensation`
  - `pbl_calibration_offset`
  - `pbl_recommended_camera_exposure`
- Applies the recommendation to Arnold `aiExposure` when that attribute exists on the camera shape.

## Use In Maya

Run this from the Maya Script Editor Python tab:

```python
import sys

sys.path.insert(0, r"C:/Users/maste/Desktop/maya_ev100_tool")

from maya_ev100_tool import maya_ev100_camera

maya_ev100_camera.show()
```

Then select a camera transform or camera shape, enter the physical camera settings, and click **Apply to Selected Camera**.

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
