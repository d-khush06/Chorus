# Chorus - Universal Video Intelligence Platform

Chorus is a comprehensive 17-step pipeline designed for video ingestion, analysis, and narration. This repository currently contains the implementation of **Steps 1 through 4 and Step 7**.

## Pipeline Progress: Completed Steps

### Step 1: Source Adapters (Data Ingestion)
The pipeline supports three distinct video source types natively:
1. **YouTube (`youtube`)**: Uses `yt-dlp` to resolve streams without requiring full video downloads.
2. **Local Upload (`local_upload`)**: Processes locally stored video files with enriched metadata extraction (fps, codec, resolution, duration).
3. **Live RTSP (`live_rtsp`)**: Handles live streams using a threaded producer (`deque(maxlen=1)`) with auto-reconnect, stream gap tracking, and sliding window management.

*(Sample JSON payloads for all three sources are included in the repository: `sample_youtube.json`, `sample_local.json`, and `sample_rtsp.json`)*

---

### Step 2: Quality Gate (`quality_gate.py`)
A robust, rule-based fused timeline verifier that ensures incoming video data meets quality standards before further processing.
* **8 Validation Rules:**
  1. **Timestamp integrity:** Bounds checking based on source (duration for VOD, stream position for RTSP).
  2. **Confidence floor:** `FAIL` < 0.55, `WARN` 0.55–0.70.
  3. **Cross-source contradiction:** Requires 2+ exclusive key tokens; generic words filtered.
  4. **Speaker consistency:** Filters generic speaker placeholders like "Speaker", "Male", "Unknown".
  5. **Coverage gaps:** 45s threshold for VOD; last-45s-window for live RTSP.
  6. **Hallucination guard:** Flags unrecognised source signals.
  7. **Format completeness:** Reports exact missing fields per event.
  8. **Stream continuity (RTSP only):** `FAIL` if stream gaps > 10s; graceful handling of malformed gaps.
* **Entry-point Validation:** Enforces `source_type` presence and protects against empty timelines.

---

### Step 3: Duplication Check (`duplication_check.py`)
A perceptual hashing gate that immediately halts the pipeline if the video is a duplicate of already-processed content.
* **Algorithms Supported:** `phash` (default), `dhash`, `ahash`, `whash`.
* **Detection Modes:** 
  * Consecutive frame O(n) scanning (default, highly scalable).
  * Global O(n·W) scanning.
* **Scene-Change Awareness:** Sliding window resets cleanly at scene boundaries to prevent cross-scene false positives.
* **RTSP Support:** Time-based sliding window pruning (default 10s) specifically optimized for unbounded live streams.

---

### Step 4: Manipulation Detection (`manipulation_detection.py`)
A deepfake detection module using the **Self-Blended Images (SBI)** technique. 
*(See `README_step4.md` for specific model and licensing details).*
* **Backbone:** EfficientNet-B4 (pretrained on FF-c23).
* **Face Detection:** `RetinaFace` (with a fallback to `dlib`/`MTCNN`).
* **Processing:** 
  * `FRAME_FAKE_THRESHOLD` = 0.5
  * `VIDEO_FLAG_THRESHOLD` = 0.30
* **Verdicts & Routing (Fail-Safe):** 
  * Outputs `CLEAN`, `FLAGGED`, or `NO_FACES_DETECTED`.
  * Deterministic routing to Step 5 (`CONTINUE_TO_STEP_5`) or the Review Queue (`SEND_TO_REVIEW_QUEUE`).
  * If the model crashes or fails to load, it fail-safes to `FLAGGED` (`detector_error=True`) ensuring un-analyzed videos never bypass security checks.

---

### Pipeline Orchestrator (`pipeline_runner.py`)
A lightweight runner script that sequences the currently built pipeline steps.
* **Execution Flow:** Runs Step 3 (Duplication Check) → if unique, runs Step 2 (Quality Gate).
* **Combined Report:** Returns a consolidated JSON containing `started_at`, `completed_at`, `halt_step`, and the detailed results of all executed checks.
* **Audit Logging:** Implements JSONL-based audit trails stored by date in `audit_logs/`.

---

## Getting Started / Testing

Run the full verification suite (tests Steps 2, 3, and 4 against edge cases, mock data, and expected outputs) by invoking `pytest` or Python directly on the test suites:

```bash
# Verify Manipulation Detection (Step 4) unit tests (30/30)
python test_manipulation_detection.py

# Verify Scene Segmentation (Step 7) unit tests (43/43)
python test_scene_segmentation.py
```

---

### Step 7: Scene Segmentation (`scene_segmentation.py`)
Deterministic shot/scene boundary detection using **PySceneDetect** — no AI model, no LLM, no per-video parameter tuning.

* **Purpose:** Produces a canonical `scenes` list that every downstream agent (Perception, Geo-estimation, Correlation, Fusion) keys its timestamps against.
* **Detectors (Rule 1):**
  * `general` mode → `ContentDetector` (standard, reliable default)
  * `cyber` mode → `AdaptiveDetector` (tolerates handheld/bodycam camera shake without false cuts)
* **Fixed Threshold (Rule 2):** `CONTENT_THRESHOLD = 27.0` — never tuned per-video; only changed after validation against a representative sample set.
* **Minimum Scene Length (Rule 3):** Any cut producing a scene shorter than `MIN_SCENE_DURATION_S = 0.6 s` is dropped and absorbed into the adjacent scene. Sub-0.6 s scenes are almost always compression artefacts or flash frames.
* **RTSP Chunked Detection (Rule 4):** Never runs on an open-ended live stream directly. Buffers into `RTSP_CHUNK_SECONDS = 30 s` fixed-length chunks; runs detection per chunk; offsets timestamps by the chunk's absolute stream position so `scene_id` / timestamps are consistent with the fused timeline.
* **Empty Result Fallback (Rule 5):** If zero cuts are detected, returns exactly one scene spanning the full video duration. Downstream agents always receive at least one scene.
* **Determinism Guarantee (Rule 6):** Same `video_path` + same detector/threshold always produces identical output. Non-determinism is treated as a pipeline bug, not normal variance.

**Output format:**
```json
{
  "scenes": [
    { "scene_id": 0, "start_seconds": 0.0, "end_seconds": 12.4 },
    { "scene_id": 1, "start_seconds": 12.4, "end_seconds": 30.1 }
  ],
  "detector_used": "content",
  "source_type": "local_upload"
}
```

**CLI usage:**
```bash
python scene_segmentation.py --video clip.mp4 --source-type local_upload --mode general --pretty
python scene_segmentation.py --video clip.mp4 --source-type local_upload --mode cyber  --pretty
python scene_segmentation.py --url  rtsp://cam/stream --source-type live_rtsp --mode general --pretty
```

**Dependency:** `pip install scenedetect[opencv]`

