# OpenCV Usage Audit

## Overview
Currently, the pipeline opens and decodes the same video multiple times across different modules, often using inefficient and inaccurate blind seeking (`cap.set(cv2.CAP_PROP_POS_FRAMES)`). This leads to redundant disk I/O, heavy CPU/RAM usage, and timestamp inaccuracies for variable-frame-rate (VFR) videos.

## Findings by File

| File | OpenCV Usage | Decoding Method |
|------|--------------|-----------------|
| `ai_generation_detection.py` | Optical flow (`calcOpticalFlowFarneback`), image remapping (`remap`), blur estimation (`Laplacian`) | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` |
| `chorus_input.py` | Extracts frames for VL models (local & RTSP) | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` (local) or sequential `cap.read()` (RTSP) |
| `duplication_check.py` | Metadata extraction (`CAP_PROP_FPS`, `WIDTH`, `HEIGHT`, etc.), perceptual hashing | Opens `VideoCapture`, decodes specific frames via looping and `cap.read()` |
| `face_reid_agent.py` | Extracts frames for face recognition | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` |
| `geo_estimation_agent.py`| Extracts frames for geolocation | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` |
| `manipulation_detection.py`| Extracts metadata (fps) | Opens `VideoCapture` for probe |
| `pipeline_runner.py` | Fast probe for metadata, extracts keyframes | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` |
| `run_vl_agent.py` | Extracts frames for Vision-Language model | Opens `VideoCapture`, seeks via `CAP_PROP_POS_FRAMES` |
| `scene_segmentation.py` | RTSP recording, duration probe | Opens `VideoCapture`, sequential `cap.read()`, uses `VideoWriter` |

## Summary of Issues
1. **Redundant Decodes:** A single video run currently opens the video roughly 5-8 times depending on which agents are activated, parsing the container and decoding frames independently each time.
2. **Blind Seeking:** `cap.set(cv2.CAP_PROP_POS_FRAMES, idx)` is widely used. This is unsafe for VFR or missing frames, often returning the nearest keyframe rather than the exact frame requested.
3. **Package Conflicts:** The environment historically had conflicting packages (`opencv-python`, `opencv-python-headless`, `opencv-contrib-python`).

## Resolution
- **Package Pinning:** Removed `opencv-python` and `opencv-python-headless`. Pinned exactly one variant: `opencv-contrib-python==4.11.0.86`.
- **Architecture Shift:** Build a centralized `video_engine/` to decode the video *exactly once* (sequential read) and fan-out frames to all analyzers.
