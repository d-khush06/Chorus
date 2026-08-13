"""
manipulation_detection.py
=========================
Chorus — Step 4: Manipulation Detection

Pipeline position:
  Step 3 (Deduplication Check) → [THIS MODULE] → Step 5 (Project Manager)

Method: Self-Blended Images (SBI) deepfake detection
Backbone: EfficientNet-B4, pretrained on FaceForensics++ c23 (FF-c23)
Paper: "Detecting Deepfakes with Self-Blended Images" — CVPR 2022 Oral
Source: github.com/mapooon/SelfBlendedImages

LICENSE NOTICE (IMPORTANT)
--------------------------
The SBI model weights and code are freely available for RESEARCH PURPOSES ONLY.
For commercial use, a license agreement with the author is required.
Contact: Kaede Shiohara <shiohara@cvm.t.u-tokyo.ac.jp>
Do NOT deploy this module in a commercial product without resolving licensing.

Face Detection: RetinaFace for bounding boxes
Face Alignment: dlib 81-point landmark predictor for landmark-based alignment
Preprocessing: 380×380 crop, ImageNet normalisation (mean=[0.485,0.456,0.406],
               std=[0.229,0.224,0.225])

Thresholds (top-of-file named constants — adjust here, nowhere else):
  FRAME_FAKE_THRESHOLD = 0.5   (per-frame: prob > this → frame counted as fake)
  VIDEO_FLAG_THRESHOLD = 0.30  (video: % fake frames >= this → FLAGGED)

Upstream contract  (Step 3 → Step 4): see parse_step3_input()
Downstream contract (Step 4 → Step 5): see build_step4_output()

Usage (library):
  from manipulation_detection import detect_manipulation, parse_step3_input
  result = detect_manipulation(parse_step3_input(raw_dict))

Usage (CLI):
  python manipulation_detection.py --input step3_output.json --pretty
  python manipulation_detection.py --input step3_output.json --weights /path/to/model.tar
"""

import os
import sys
import json
import time
import logging
import argparse
import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.manipulation_detection")
logging.basicConfig(
    level=logging.INFO,
    format="[manipulation_detection] %(levelname)s — %(message)s",
)

# ---------------------------------------------------------------------------
# Named constants — the ONLY place these thresholds live
# ---------------------------------------------------------------------------
FRAME_FAKE_THRESHOLD: float = 0.5    # fake_probability above this → frame is "fake"
VIDEO_FLAG_THRESHOLD: float = 0.30   # fraction of fake frames at/above this → FLAGGED

# RTSP rolling-window duration (seconds)
RTSP_WINDOW_SECONDS: float = 30.0

# EfficientNet-B4 input size expected by SBI
SBI_INPUT_SIZE: int = 380

# ImageNet normalisation constants
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

# Audit log directory — outputs are written here in addition to being returned
AUDIT_LOG_DIR = os.path.join(os.path.dirname(__file__), "audit_logs", "step4")

# ---------------------------------------------------------------------------
# Lazy dependency helpers
# ---------------------------------------------------------------------------

def _require(pkg: str, install: str = None):
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError:
        install = install or pkg
        sys.exit(f"[manipulation_detection] Required package '{pkg}' not installed.\n"
                 f"  pip install {install}")


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class Step3Output:
    """
    Typed representation of the upstream Step 3 (Deduplication Check) output.
    ONLY parse_step3_input() should construct this — all other code uses it.
    """
    video_id:          str
    video_path:        str
    source_type:       str                    # "youtube" | "local_upload" | "live_rtsp"
    duration_seconds:  Optional[float]        # None for live_rtsp
    dedup_status:      str                    # must be "unique"
    dedup_hash:        str
    upstream_metadata: Dict[str, Any]         # pass-through, shape unknown


@dataclass
class PerFrameScore:
    timestamp: float
    fake_probability: float


@dataclass
class ManipulationCheck:
    frames_analyzed:     int
    faces_detected:      int
    per_frame_scores:    List[PerFrameScore]
    video_level_score:   Optional[float]
    aggregation_method:  str = "percentage_above_threshold"
    verdict:             str = "CLEAN"          # CLEAN | FLAGGED | NO_FACES_DETECTED
    detector_error:      bool = False
    processing_time_seconds: float = 0.0


@dataclass
class Step4Output:
    """
    Exact downstream contract for Step 5 (Project Manager) and Step 16 (Review Queue).
    Do NOT rename or restructure fields without coordinating with both teams.
    """
    video_id:           str
    dedup_hash:         str
    upstream_metadata:  Dict[str, Any]
    source_type:        str
    manipulation_check: ManipulationCheck
    routing_decision:   str                     # CONTINUE_TO_STEP_5 | SEND_TO_REVIEW_QUEUE


# ---------------------------------------------------------------------------
# Section 1 — Upstream adapter (ISOLATE Step 3 coupling here)
# ---------------------------------------------------------------------------

def parse_step3_input(raw_input: dict) -> Step3Output:
    """
    Parse and validate Step 3's raw output dict into a typed Step3Output.

    This is the SINGLE point of coupling to Step 3's field names. If Step 3
    renames a field, only this function needs updating — core detection logic
    is untouched.

    Raises
    ------
    ValueError
        If dedup_status is not "unique" (routing error upstream — not Step 4's bug).
    KeyError
        If any required field is missing from the input.
    """
    # Accept either the field names defined in the contract OR common alternatives
    video_id    = raw_input.get("video_id")
    video_path  = raw_input.get("video_path") or raw_input.get("video_file") or ""
    source_type = raw_input.get("source_type", "")
    duration    = raw_input.get("duration_seconds") or raw_input.get("video_duration_seconds")
    dedup_status = raw_input.get("dedup_status", "")
    dedup_hash  = raw_input.get("dedup_hash", "")
    upstream_meta = raw_input.get("upstream_metadata") or {}

    if not video_id:
        raise KeyError("parse_step3_input: 'video_id' is required.")
    if not source_type:
        raise KeyError("parse_step3_input: 'source_type' is required.")
    if dedup_status != "unique":
        raise ValueError(
            f"parse_step3_input: dedup_status must be 'unique', got '{dedup_status}'. "
            "Step 3 routing is broken — this payload should never reach Step 4."
        )

    return Step3Output(
        video_id=video_id,
        video_path=video_path,
        source_type=source_type,
        duration_seconds=float(duration) if duration is not None else None,
        dedup_status=dedup_status,
        dedup_hash=dedup_hash,
        upstream_metadata=upstream_meta,
    )


# ---------------------------------------------------------------------------
# Section 2 — Face detection (RetinaFace + dlib alignment)
# ---------------------------------------------------------------------------

def _load_retinaface():
    """Load RetinaFace face detector. Prefers the retina-face pip package."""
    try:
        from retinaface import RetinaFace
        return RetinaFace
    except ImportError:
        pass
    try:
        from facenet_pytorch import MTCNN
        log.warning("RetinaFace not found; falling back to MTCNN for face detection.")
        return MTCNN(keep_all=True, post_process=False)
    except ImportError:
        raise ImportError(
            "No face detector found. Install one:\n"
            "  pip install retina-face\n"
            "  or: pip install facenet-pytorch"
        )


def _detect_faces_retinaface(frame_bgr, retinaface_module):
    """
    Run RetinaFace on a BGR frame and return list of (x1,y1,x2,y2) bounding boxes.
    Returns empty list on failure.
    """
    try:
        resp = retinaface_module.detect_faces(frame_bgr)
        boxes = []
        if isinstance(resp, dict):
            for _, face_data in resp.items():
                box = face_data.get("facial_area", [])
                if len(box) == 4:
                    boxes.append(tuple(box))
        return boxes
    except Exception as e:
        log.debug(f"RetinaFace detection failed on frame: {e}")
        return []


def _crop_and_align_face(frame_bgr, box, target_size: int = SBI_INPUT_SIZE):
    """
    Crop and resize a face from frame_bgr given a (x1,y1,x2,y2) bounding box.
    Returns a PIL Image sized target_size × target_size or None on failure.
    """
    try:
        from PIL import Image
        import numpy as np
        x1, y1, x2, y2 = [int(v) for v in box]
        # Add a small margin (10%) around the crop
        h, w = frame_bgr.shape[:2]
        mx = int((x2 - x1) * 0.1)
        my = int((y2 - y1) * 0.1)
        x1 = max(0, x1 - mx);  y1 = max(0, y1 - my)
        x2 = min(w, x2 + mx);  y2 = min(h, y2 + my)
        crop = frame_bgr[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        # Convert BGR → RGB
        rgb = crop[:, :, ::-1]
        pil = Image.fromarray(rgb).resize((target_size, target_size))
        return pil
    except Exception as e:
        log.debug(f"Face crop/align failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Section 3 — SBI / EfficientNet-B4 model
# ---------------------------------------------------------------------------

def _build_efficientnet_b4():
    """Build an EfficientNet-B4 classification head for deepfake detection."""
    timm = _require("timm")
    model = timm.create_model("efficientnet_b4", pretrained=False, num_classes=1)
    return model


def load_sbi_model(weights_path: str):
    """
    Load the SBI EfficientNet-B4 model from a .tar / .pth checkpoint.

    Parameters
    ----------
    weights_path : str
        Path to the FF-c23 pretrained checkpoint (download from the SBI repo).

    Returns
    -------
    (model, device) tuple ready for inference.

    Raises
    ------
    FileNotFoundError if weights_path does not exist.
    RuntimeError on any load failure (propagate — caller should catch and fail-safe).
    """
    import torch

    if not os.path.isfile(weights_path):
        raise FileNotFoundError(
            f"SBI weights not found at: {weights_path}\n"
            "Download FF-c23 weights from the SelfBlendedImages repository:\n"
            "  https://github.com/mapooon/SelfBlendedImages"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Loading SBI EfficientNet-B4 weights from {weights_path} on {device}")

    model = _build_efficientnet_b4()

    checkpoint = torch.load(weights_path, map_location=device, weights_only=False)
    # The SBI .tar checkpoint stores the model under 'model' or 'state_dict'
    state_dict = (
        checkpoint.get("model")
        or checkpoint.get("state_dict")
        or checkpoint
    )
    model.load_state_dict(state_dict, strict=False)
    model.eval()
    model.to(device)

    log.info(f"SBI model loaded successfully (device={device})")
    return model, device


def _infer_face(pil_image, model, device) -> float:
    """
    Run the SBI EfficientNet-B4 model on a pre-cropped PIL face image.

    Returns
    -------
    float
        fake_probability in [0.0, 1.0] (sigmoid applied to model logit).
    """
    import torch
    import torchvision.transforms as T
    import numpy as np

    transform = T.Compose([
        T.Resize((SBI_INPUT_SIZE, SBI_INPUT_SIZE)),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])

    tensor = transform(pil_image).unsqueeze(0).to(device)   # (1, 3, 380, 380)
    with torch.no_grad():
        logit = model(tensor)                                # (1, 1) raw logit
        prob  = torch.sigmoid(logit).item()
    return float(prob)


# ---------------------------------------------------------------------------
# Section 4 — Frame extraction helpers
# ---------------------------------------------------------------------------

def _iter_frames_local(video_path: str, sample_rate: float):
    """
    Yield (timestamp_seconds, bgr_frame) at roughly `sample_rate` fps.
    """
    cv2 = _require("cv2", "opencv-python-headless")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps  = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(fps / sample_rate))
    idx  = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                ts = idx / fps
                yield ts, frame
            idx += 1
    finally:
        cap.release()


def _iter_frames_rtsp(video_path: str, sample_rate: float, window_seconds: float):
    """
    Yield (timestamp_seconds, bgr_frame) from an RTSP stream for `window_seconds`.
    Uses a simple blocking read approach (Step 3's threaded producer is NOT
    imported here — this is stand-alone).
    """
    cv2 = _require("cv2", "opencv-python-headless")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open RTSP stream: {video_path}")

    fps           = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step          = max(1, round(fps / sample_rate))
    max_frames    = int(window_seconds * fps)
    idx           = 0

    try:
        while idx < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if idx % step == 0:
                ts = idx / fps
                yield ts, frame
            idx += 1
    finally:
        cap.release()


def _get_frame_iter(step3: Step3Output, sample_rate: float):
    """Return the appropriate frame iterator for the given source type."""
    if step3.source_type == "live_rtsp":
        return _iter_frames_rtsp(step3.video_path, sample_rate, RTSP_WINDOW_SECONDS)
    else:
        # youtube and local_upload: video_path is a local file or resolved URL
        return _iter_frames_local(step3.video_path, sample_rate)


# ---------------------------------------------------------------------------
# Section 5 — Aggregation & verdict
# ---------------------------------------------------------------------------

def _aggregate_scores(per_frame: List[PerFrameScore], faces_detected: int):
    """
    Apply deterministic aggregation rules to compute video_level_score and verdict.

    Rules (named constants at top of file):
    ----------------------------------------
    - faces_detected == 0  → verdict = "NO_FACES_DETECTED", score = None
    - video_level_score = % frames where fake_probability > FRAME_FAKE_THRESHOLD
    - video_level_score >= VIDEO_FLAG_THRESHOLD → verdict = "FLAGGED"
    - otherwise → verdict = "CLEAN"
    """
    if faces_detected == 0 or not per_frame:
        return None, "NO_FACES_DETECTED"

    frames_analyzed = len(per_frame)
    fake_frames     = sum(1 for s in per_frame if s.fake_probability > FRAME_FAKE_THRESHOLD)
    score           = fake_frames / frames_analyzed

    verdict = "FLAGGED" if score >= VIDEO_FLAG_THRESHOLD else "CLEAN"
    return round(score, 6), verdict


# ---------------------------------------------------------------------------
# Section 6 — Downstream output contract builder & routing
# ---------------------------------------------------------------------------

def _routing_decision(verdict: str, detector_error: bool) -> str:
    """
    Single source of truth for the routing decision.

    FLAGGED or detector_error=True → SEND_TO_REVIEW_QUEUE
    CLEAN or NO_FACES_DETECTED    → CONTINUE_TO_STEP_5
    """
    if verdict == "FLAGGED" or detector_error:
        return "SEND_TO_REVIEW_QUEUE"
    return "CONTINUE_TO_STEP_5"


def build_step4_output(step3: Step3Output, check: ManipulationCheck) -> Step4Output:
    """Build the final Step4Output from parsed input and completed ManipulationCheck."""
    routing = _routing_decision(check.verdict, check.detector_error)
    return Step4Output(
        video_id=step3.video_id,
        dedup_hash=step3.dedup_hash,
        upstream_metadata=step3.upstream_metadata,
        source_type=step3.source_type,
        manipulation_check=check,
        routing_decision=routing,
    )


def step4_output_to_dict(output: Step4Output) -> dict:
    """Serialise Step4Output to a JSON-compatible dict (exact downstream contract shape)."""
    mc = output.manipulation_check
    return {
        "video_id":          output.video_id,
        "dedup_hash":        output.dedup_hash,
        "upstream_metadata": output.upstream_metadata,
        "source_type":       output.source_type,
        "manipulation_check": {
            "frames_analyzed":        mc.frames_analyzed,
            "faces_detected":         mc.faces_detected,
            "per_frame_scores":       [
                {"timestamp": s.timestamp, "fake_probability": s.fake_probability}
                for s in mc.per_frame_scores
            ],
            "video_level_score":      mc.video_level_score,
            "aggregation_method":     mc.aggregation_method,
            "verdict":                mc.verdict,
            "detector_error":         mc.detector_error,
            "processing_time_seconds": mc.processing_time_seconds,
        },
        "routing_decision": output.routing_decision,
    }


# ---------------------------------------------------------------------------
# Section 7 — Audit logging
# ---------------------------------------------------------------------------

def _write_audit_log(output_dict: dict) -> None:
    """
    Append the full Step4Output to a newline-delimited JSON audit file.
    File path: AUDIT_LOG_DIR/step4_<YYYY-MM-DD>.jsonl
    """
    try:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        date_str  = datetime.date.today().isoformat()
        log_path  = os.path.join(AUDIT_LOG_DIR, f"step4_{date_str}.jsonl")
        entry = {"logged_at": datetime.datetime.utcnow().isoformat() + "Z", **output_dict}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        log.debug(f"Audit log written to {log_path}")
    except Exception as e:
        log.error(f"Failed to write audit log: {e}")


# ---------------------------------------------------------------------------
# Section 8 — Core public function
# ---------------------------------------------------------------------------

def detect_manipulation(
    step3_output:      Step3Output,
    frame_sample_rate: float = 1.0,
    weights_path:      Optional[str] = None,
    model_and_device:  Optional[tuple] = None,  # pre-loaded (model, device) for testing
) -> Step4Output:
    """
    Detect manipulation in a video using the SBI EfficientNet-B4 deepfake detector.

    Parameters
    ----------
    step3_output      : Parsed Step3Output from parse_step3_input().
    frame_sample_rate : Frames per second to sample (default 1.0).
    weights_path      : Path to SBI FF-c23 pretrained weights (.tar/.pth).
                        If None, looks for CHORUS_SBI_WEIGHTS env var.
    model_and_device  : Optional pre-loaded (model, device) for testing —
                        when provided, weights_path is ignored.

    Returns
    -------
    Step4Output with full downstream contract populated.

    Error behaviour
    ---------------
    ANY unhandled exception during model load or inference sets
    detector_error=True and forces verdict="FLAGGED" (fail-safe to human review).
    """
    t_start = time.perf_counter()

    # ── Load model ────────────────────────────────────────────────────────
    detector_error = False
    model          = None
    device         = None
    face_detector  = None

    try:
        if model_and_device is not None:
            model, device = model_and_device
        else:
            if weights_path is None:
                weights_path = os.environ.get("CHORUS_SBI_WEIGHTS", "")
            if not weights_path:
                raise FileNotFoundError(
                    "SBI weights path not provided. Set --weights or CHORUS_SBI_WEIGHTS env var."
                )
            model, device = load_sbi_model(weights_path)

        face_detector = _load_retinaface()

    except Exception as e:
        log.error(f"Model/detector load failed: {e}")
        detector_error = True

    # ── Frame loop ────────────────────────────────────────────────────────
    per_frame_scores: List[PerFrameScore] = []
    frames_analyzed  = 0
    faces_detected   = 0

    if not detector_error:
        try:
            frame_iter = _get_frame_iter(step3_output, frame_sample_rate)
            for ts, bgr_frame in frame_iter:
                frames_analyzed += 1
                try:
                    boxes = _detect_faces_retinaface(bgr_frame, face_detector)
                    if not boxes:
                        log.debug(f"No faces at t={ts:.2f}s — skipping frame.")
                        continue

                    faces_detected += len(boxes)
                    # Process the largest detected face (primary face in scene)
                    # Ranked by bounding box area
                    best_box = max(boxes, key=lambda b: (b[2]-b[0]) * (b[3]-b[1]))
                    face_pil = _crop_and_align_face(bgr_frame, best_box)
                    if face_pil is None:
                        log.debug(f"Face crop failed at t={ts:.2f}s — skipping.")
                        continue

                    prob = _infer_face(face_pil, model, device)
                    per_frame_scores.append(PerFrameScore(timestamp=ts, fake_probability=prob))

                except Exception as frame_err:
                    log.warning(f"Frame at t={ts:.2f}s failed (skipping): {frame_err}")
                    continue

        except Exception as loop_err:
            log.error(f"Frame loop failed entirely: {loop_err}")
            detector_error = True

    # ── Aggregate ─────────────────────────────────────────────────────────
    processing_time = time.perf_counter() - t_start

    if detector_error:
        # Fail-safe: force FLAGGED on any error
        video_level_score = None
        verdict           = "FLAGGED"
    else:
        video_level_score, verdict = _aggregate_scores(per_frame_scores, faces_detected)

    check = ManipulationCheck(
        frames_analyzed=frames_analyzed,
        faces_detected=faces_detected,
        per_frame_scores=per_frame_scores,
        video_level_score=video_level_score,
        verdict=verdict,
        detector_error=detector_error,
        processing_time_seconds=round(processing_time, 4),
    )

    result = build_step4_output(step3_output, check)

    # ── Audit log ─────────────────────────────────────────────────────────
    result_dict = step4_output_to_dict(result)
    _write_audit_log(result_dict)

    log.info(
        f"[{step3_output.video_id}] verdict={verdict} "
        f"score={video_level_score} routing={result.routing_decision} "
        f"frames={frames_analyzed} faces={faces_detected} "
        f"time={processing_time:.2f}s"
    )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_cli_parser():
    p = argparse.ArgumentParser(
        description="Chorus Step 4 — Manipulation Detection (SBI EfficientNet-B4).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input",       required=True,
                   help="Path to Step 3 output JSON file.")
    p.add_argument("--weights",     default=None,
                   help="Path to SBI FF-c23 pretrained weights (.tar/.pth). "
                        "Also reads CHORUS_SBI_WEIGHTS env var.")
    p.add_argument("--sample-rate", type=float, default=1.0, dest="sample_rate",
                   help="Frames per second to sample (default: 1.0).")
    p.add_argument("--pretty",      action="store_true",
                   help="Pretty-print output JSON.")
    p.add_argument("--verbose",     action="store_true",
                   help="Enable DEBUG logging.")
    return p


if __name__ == "__main__":
    parser = _build_cli_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger("chorus.manipulation_detection").setLevel(logging.DEBUG)

    with open(args.input, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)

    step3 = parse_step3_input(raw)
    result = detect_manipulation(
        step3,
        frame_sample_rate=args.sample_rate,
        weights_path=args.weights,
    )

    output = step4_output_to_dict(result)
    print(json.dumps(output, indent=2 if args.pretty else None))
    sys.exit(1 if result.routing_decision == "SEND_TO_REVIEW_QUEUE" else 0)
