# Maya EV100 Camera Exposure MVP

Maya에서 EV100 기준으로 카메라 노출 메타데이터와 Arnold `aiExposure`를 맞추는 첫 MVP입니다.

## 설치/실행

Maya Script Editor의 Python 탭에서 실행:

```python
import sys
sys.path.insert(0, r"C:/Users/maste/Desktop/maya_ev100_tool")
from maya_ev100_tool import maya_ev100_camera
maya_ev100_camera.show()
```

## 현재 기능

- ISO / shutter / f-stop 입력
- EV100 계산
- `recommended camera exposure = -EV100 + exposure compensation + calibration offset` 계산
- 선택한 Maya camera shape에 custom attrs 저장
  - `pbl_ev100`
  - `pbl_iso`
  - `pbl_shutter_seconds`
  - `pbl_fstop`
  - `pbl_exposure_compensation`
  - `pbl_calibration_offset`
  - `pbl_recommended_camera_exposure`
- camera shape에 Arnold `aiExposure` attr가 있으면 자동 적용

## 중요한 전제

이 MVP의 Arnold 노출 매핑은 시작점입니다.

```text
Maya/Arnold exposure stops = -EV100 + exposure compensation + calibration offset
```

다음 MVP에서 18% gray card / HDRI calibration rig를 붙여서 `calibration_offset`을 실제 파이프라인 기준으로 보정하면 됩니다.
