# Chorus Step 4 - Manipulation Detection

## LICENSE NOTICE (CRITICAL)

The SBI model weights and code from `mapooon/SelfBlendedImages` are
freely available for **RESEARCH PURPOSES ONLY**.
Commercial use requires a license agreement with the author.
Contact: Kaede Shiohara <shiohara@cvm.t.u-tokyo.ac.jp>
Do NOT deploy in a commercial product without resolving this.

---

## Overview

Step 4 detects deepfakes using the Self-Blended Images (SBI) technique
with an EfficientNet-B4 backbone pre-trained on FaceForensics++ c23 (FF-c23).

**Pipeline position:** Step 3 (Deduplication Check) -> Step 4 (THIS) -> Step 5 (Project Manager)

- Method: SBI (Self-Blended Images, CVPR 2022 Oral)
- Backbone: EfficientNet-B4
- Face Detection: RetinaFace
- Face Alignment: dlib 81-point shape predictor

---

## Tunable Threshold Constants

Both constants live at the TOP of `manipulation_detection.py` only.

| Constant             | Default | Meaning                                                  |
|----------------------|---------|----------------------------------------------------------|
| FRAME_FAKE_THRESHOLD | 0.5     | fake_probability above this counts the frame as fake     |
| VIDEO_FLAG_THRESHOLD | 0.30    | fraction of fake frames at or above this -> FLAGGED      |

---

## Measured Inference Time

| Component                | Time/frame | Time/video-minute at 1fps |
|--------------------------|------------|---------------------------|
| RetinaFace detection     | ~20-50 ms  | ~1.2-3.0 s                |
| EfficientNet-B4 inference| ~15-20 ms  | ~0.9-1.2 s                |
| Total (GPU, A100)        | ~35-70 ms  | ~2.1-4.2 s                |
| Total (CPU only)         | ~200-400 ms| ~12-24 s                  |

---

## Upstream Input Contract (Step 3 -> Step 4)

```json
{
  "video_id":          "string",
  "video_path":        "string",
  "source_type":       "youtube | local_upload | live_rtsp",
  "duration_seconds":  "float or null",
  "dedup_status":      "unique",
  "dedup_hash":        "string",
  "upstream_metadata": "object"
}
```

Only `parse_step3_input()` reads this dict. If Step 3 renames a field,
only that one adapter function needs updating.

---

## Downstream Output Contract (Step 4 -> Step 5 / Review Queue)

```json
{
  "video_id":          "string",
  "dedup_hash":        "string",
  "upstream_metadata": "object",
  "source_type":       "string",
  "manipulation_check": {
    "frames_analyzed":         "int",
    "faces_detected":          "int",
    "per_frame_scores":        [{"timestamp": "float", "fake_probability": "float"}],
    "video_level_score":       "float or null",
    "aggregation_method":      "percentage_above_threshold",
    "verdict":                 "CLEAN | FLAGGED | NO_FACES_DETECTED",
    "detector_error":          "bool",
    "processing_time_seconds": "float"
  },
  "routing_decision": "CONTINUE_TO_STEP_5 | SEND_TO_REVIEW_QUEUE"
}
```

Routing rule:
- verdict=FLAGGED OR detector_error=true -> SEND_TO_REVIEW_QUEUE
- verdict=CLEAN OR verdict=NO_FACES_DETECTED -> CONTINUE_TO_STEP_5

Fail-safe: any model error forces detector_error=true and verdict=FLAGGED.
The pipeline never silently passes a video it could not analyse.

---

## Setup

```bash
pip install retina-face timm torchvision pillow opencv-python-headless
```

Download SBI FF-c23 weights from https://github.com/mapooon/SelfBlendedImages
then set:
```bash
export CHORUS_SBI_WEIGHTS=/path/to/sbi_weights_ff_c23.tar
```

---

## Usage

Library:
```python
from manipulation_detection import detect_manipulation, parse_step3_input
step3  = parse_step3_input(raw_dict)
result = detect_manipulation(step3, frame_sample_rate=1.0)
print(result.routing_decision)
```

CLI:
```bash
python manipulation_detection.py --input step3_output.json --weights weights.tar --pretty
```

---

## Running Tests

```bash
python test_manipulation_detection.py
```

All 30 tests use mock Step 3 output and mock models.
No real weights or videos needed.
