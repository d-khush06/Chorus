"""
acoustic_event_detection.py
===========================
Chorus Pipeline — Cyber Step C1: Acoustic Event Detection Agent

Pipeline position
-----------------
  Runs AFTER : Source Adapter (audio track available), Scene Segmentation
  Runs BEFORE: Fusion Agent, Alert System
  Depends on : A local video/audio file path.

Purpose
-------
Classifies NON-SPEECH audio events from the video's audio track:
gunshots, explosions, glass breaking, alarms, sirens, screams, impacts,
vehicle sounds and fire. Speech itself is handled by asr_agent.py.

Model
-----
  Primary  : YAMNet (TensorFlow Hub, AudioSet 521-class CNN)
             https://tfhub.dev/google/yamnet/1
             ~minimal VRAM (runs on CPU comfortably).
  Fallback : Built-in DSP transient detector (no model). This only flags
             loud transient energy — it does NOT name the event. It exists so
             the cyber pipeline still runs (and escalates loud transients for
             human review) when TensorFlow is unavailable.

Rules
-----
1. Never assume event classes that the model did not output.
2. Every event carries (start_s, end_s, label, event_type, confidence,
   severity). Timestamps are absolute seconds in the source timeline.
3. Group consecutive positive patches into one event; keep the peak
   confidence of the group.
4. Lazy-load the model on first call only. Never block import.
5. Never raise — on failure return events=[] with an `error` string.
6. If YAMNet is unavailable the fallback backend must be clearly labelled
   `backend="heuristic"` so downstream consumers treat it as low-trust.

Install
-------
  pip install tensorflow tensorflow-hub
  (ffmpeg must be on PATH for audio extraction)

Usage (library)
---------------
  from acoustic_event_detection import detect_acoustic_events

  result = detect_acoustic_events("clip.mp4")
  # result = {
  #   "events": [
  #     {"event_id": 0, "start_s": 12.0, "end_s": 12.96, "label": "Gunshot, gunfire",
  #      "event_type": "gunshot", "confidence": 0.87, "severity": "CRITICAL"},
  #     ...
  #   ],
  #   "summary": {...},
  #   "backend": "yamnet",
  #   "model_used": "yamnet",
  #   "error": null
  # }

Usage (CLI)
-----------
  python acoustic_event_detection.py --video clip.mp4 --pretty
  python acoustic_event_detection.py --video clip.mp4 --threshold 0.25 --pretty
"""

import os
import sys
import csv
import json
import wave
import argparse
import tempfile
import datetime
import subprocess
from typing import Optional

import numpy as np

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

YAMNET_HUB_URL = os.getenv(
    "YAMNET_HUB_URL", "https://tfhub.dev/google/yamnet/1"
)

# YAMNet emits one 521-class prediction per 0.48 s patch.
YAMNET_PATCH_SECONDS = 0.48

# Peak confidence required to report an event.
DETECTION_THRESHOLD = float(os.getenv("ACOUSTIC_THRESHOLD", "0.30"))

# Consecutive positive patches within this gap (in patches) merge into one event.
MAX_GAP_PATCHES = 1

# Audio extraction sample rate (YAMNet is trained on 16 kHz mono).
TARGET_SR = 16000

# Heuristic fallback tuning
HEURISTIC_WINDOW_S = 0.48
HEURISTIC_SIGMA = 4.0

# ─────────────────────────────────────────────────────────────────────────────
# EVENT RULES — map YAMNet AudioSet display names to Chorus event types.
# Tuple: (event_type, severity)
# ─────────────────────────────────────────────────────────────────────────────

ACOUSTIC_EVENT_RULES = {
    "Gunshot, gunfire":                 ("gunshot",   "CRITICAL"),
    "Machine gun":                      ("gunshot",   "CRITICAL"),
    "Fusillade":                        ("gunshot",   "CRITICAL"),
    "Artillery fire":                   ("explosion", "CRITICAL"),
    "Explosion":                        ("explosion", "CRITICAL"),
    "Glass":                            ("glass_break", "HIGH"),
    "Shatter":                          ("glass_break", "HIGH"),
    "Breaking":                         ("glass_break", "HIGH"),
    "Smoke detector, smoke alarm":      ("alarm",     "HIGH"),
    "Fire alarm":                       ("alarm",     "HIGH"),
    "Car alarm":                        ("alarm",     "HIGH"),
    "Alarm":                            ("alarm",     "HIGH"),
    "Buzzer":                           ("alarm",     "MEDIUM"),
    "Siren":                            ("siren",     "HIGH"),
    "Civil defense siren":              ("siren",     "HIGH"),
    "Police car (siren)":               ("siren",     "HIGH"),
    "Ambulance (siren)":                ("siren",     "HIGH"),
    "Fire engine, fire truck (siren)":  ("siren",     "HIGH"),
    "Screaming":                         ("scream",    "HIGH"),
    "Shout":                            ("scream",    "MEDIUM"),
    "Yell":                             ("scream",    "MEDIUM"),
    "Bang":                             ("impact",    "MEDIUM"),
    "Thump, thud":                      ("impact",    "LOW"),
    "Crash":                            ("impact",    "HIGH"),
    "Tire squeal":                      ("vehicle",   "MEDIUM"),
    "Skidding":                         ("vehicle",   "MEDIUM"),
    "Race car, auto racing":            ("vehicle",   "LOW"),
    "Car passing by":                   ("vehicle",   "LOW"),
    "Truck":                            ("vehicle",   "LOW"),
    "Motorcycle":                       ("vehicle",   "LOW"),
    "Helicopter":                       ("aircraft",  "LOW"),
    "Aircraft":                         ("aircraft",  "LOW"),
    "Fire":                             ("fire",      "HIGH"),
    "Crackle":                          ("fire",      "MEDIUM"),
}

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# ─────────────────────────────────────────────────────────────────────────────
# LAZY MODEL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

_yamnet_model = None
_yamnet_available: Optional[bool] = None
_class_index_to_name: dict = {}


def _load_yamnet():
    """
    Lazy-load YAMNet from TensorFlow Hub. Returns the loaded model or None
    if TensorFlow / tensorflow-hub are not installed.
    """
    global _yamnet_model, _yamnet_available, _class_index_to_name
    if _yamnet_available is False:
        return None
    if _yamnet_model is not None:
        return _yamnet_model

    try:
        import tensorflow_hub as hub
    except ImportError:
        _yamnet_available = False
        print(
            "  [Acoustic] ⚠️  TensorFlow Hub not installed — using heuristic backend.\n"
            "  [Acoustic]    Install: pip install tensorflow tensorflow-hub",
            flush=True,
        )
        return None

    try:
        print("  [Acoustic] Loading YAMNet from TensorFlow Hub…", flush=True)
        _yamnet_model = hub.load(YAMNET_HUB_URL)
        _yamnet_available = True

        # Build class index -> display name map from the model's class map CSV
        try:
            class_map_path = _yamnet_model.class_map_path().numpy().decode("utf-8")
            with open(class_map_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    _class_index_to_name[int(row["index"])] = row["display_name"]
            print(
                f"  [Acoustic] ✅ YAMNet loaded — {len(_class_index_to_name)} classes.",
                flush=True,
            )
        except Exception as exc:
            print(f"  [Acoustic] ⚠️  Could not read YAMNet class map: {exc}", flush=True)

        return _yamnet_model
    except Exception as exc:
        _yamnet_available = False
        print(f"  [Acoustic] ⚠️  YAMNet load failed: {exc}", flush=True)
        return None


def unload_acoustic_model():
    """Release the YAMNet model from memory."""
    global _yamnet_model
    if _yamnet_model is not None:
        try:
            del _yamnet_model
        except Exception:
            pass
        _yamnet_model = None
        print("  [Acoustic] YAMNet unloaded.", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO EXTRACTION / LOADING
# ─────────────────────────────────────────────────────────────────────────────

def _extract_audio_16k_mono(video_path: str, out_path: str) -> bool:
    """Extract mono 16 kHz PCM WAV from a video/audio file using ffmpeg."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ar", str(TARGET_SR),
            "-ac", "1",
            "-vn",
            "-f", "wav",
            out_path,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300
        )
        if result.returncode != 0:
            print(
                f"  [Acoustic] ffmpeg error: "
                f"{result.stderr.decode('utf-8', errors='replace')[:300]}",
                flush=True,
            )
            return False
        return True
    except FileNotFoundError:
        print(
            "  [Acoustic] ❌ ffmpeg not found on PATH.\n"
            "  Install: https://ffmpeg.org/download.html  or  winget install ffmpeg",
            flush=True,
        )
        return False
    except Exception as exc:
        print(f"  [Acoustic] ❌ Audio extraction failed: {exc}", flush=True)
        return False


def _read_wav_mono(wav_path: str) -> tuple:
    """
    Read a PCM WAV file into (float32 numpy waveform in [-1, 1], sample_rate).
    Uses the stdlib `wave` module — no extra dependency.
    """
    with wave.open(wav_path, "rb") as wf:
        n_frames = wf.getnframes()
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        samp_width = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    if samp_width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif samp_width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif samp_width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {samp_width} bytes")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    return data, sr


def _resample_linear(waveform: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Simple linear resample. Good enough for event detection."""
    if src_sr == dst_sr or waveform.size == 0:
        return waveform
    duration = waveform.size / float(src_sr)
    n_out = int(round(duration * dst_sr))
    if n_out <= 0:
        return waveform
    src_t = np.linspace(0.0, duration, num=waveform.size, endpoint=False)
    dst_t = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(dst_t, src_t, waveform).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# YAMNET INFERENCE
# ─────────────────────────────────────────────────────────────────────────────

def _group_patch_indices(indices: list, max_gap: int = MAX_GAP_PATCHES) -> list:
    """Group sorted patch indices into [start, end] ranges allowing small gaps."""
    if not indices:
        return []
    groups = [[indices[0], indices[0]]]
    for idx in indices[1:]:
        if idx - groups[-1][1] <= max_gap + 1:
            groups[-1][1] = idx
        else:
            groups.append([idx, idx])
    return groups


def _events_from_yamnet(
    waveform: np.ndarray, threshold: float
) -> tuple:
    """Run YAMNet and return (events, model_used)."""
    model = _load_yamnet()
    if model is None:
        return None, None

    import tensorflow as tf  # noqa: F401  (ensures tf present for score tensor ops)
    scores, _embeddings, _spectrogram = model(waveform.astype(np.float32))
    scores = np.asarray(scores)
    if scores.ndim != 2:
        return [], "yamnet"

    n_patches = scores.shape[0]

    # Gather all (patch, class) positives for classes we care about
    events = []
    event_id = 0
    seen_types = {}  # event_type -> list of (start_s, end_s, conf)

    for class_idx, display_name in _class_index_to_name.items():
        rule = ACOUSTIC_EVENT_RULES.get(display_name)
        if rule is None:
            continue
        if class_idx >= scores.shape[1]:
            continue

        event_type, severity = rule
        class_scores = scores[:, class_idx]
        positive = [i for i in range(n_patches) if class_scores[i] >= threshold]
        if not positive:
            continue

        for start_patch, end_patch in _group_patch_indices(positive):
            peak = float(class_scores[start_patch:end_patch + 1].max())
            start_s = round(start_patch * YAMNET_PATCH_SECONDS, 3)
            end_s = round((end_patch + 1) * YAMNET_PATCH_SECONDS, 3)

            # Suppress weaker overlaps of the same event type
            overlaps = seen_types.setdefault(event_type, [])
            if any(not (end_s <= s or start_s >= e) and peak <= c
                   for s, e, c in overlaps):
                continue
            overlaps.append((start_s, end_s, peak))

            events.append({
                "event_id":   event_id,
                "start_s":    start_s,
                "end_s":      end_s,
                "label":      display_name,
                "event_type": event_type,
                "confidence": round(peak, 4),
                "severity":   severity,
            })
            event_id += 1

    events.sort(key=lambda e: e["start_s"])
    for i, ev in enumerate(events):
        ev["event_id"] = i

    return events, "yamnet"


# ─────────────────────────────────────────────────────────────────────────────
# HEURISTIC FALLBACK — loud transient detector (no model)
# ─────────────────────────────────────────────────────────────────────────────

def _events_from_heuristic(waveform: np.ndarray, sr: int) -> tuple:
    """
    Flag loud transient windows using short-time RMS. Labels them
    generically as transient_noise because the backend cannot classify.
    """
    if waveform.size == 0:
        return [], "heuristic"

    win = max(int(HEURISTIC_WINDOW_S * sr), 1)
    n_windows = waveform.size // win
    if n_windows == 0:
        return [], "heuristic"

    rms = np.array([
        float(np.sqrt(np.mean(np.square(waveform[i * win:(i + 1) * win]))))
        for i in range(n_windows)
    ])
    mean = float(rms.mean())
    std = float(rms.std())
    thresh = mean + HEURISTIC_SIGMA * std
    thresh = max(thresh, 0.15)  # absolute floor so quiet audio doesn't fire

    positives = [i for i in range(n_windows) if rms[i] >= thresh]
    events = []
    for i, (start_w, end_w) in enumerate(_group_patch_indices(positives)):
        peak = float(rms[start_w:end_w + 1].max())
        events.append({
            "event_id":   i,
            "start_s":    round(start_w * HEURISTIC_WINDOW_S, 3),
            "end_s":      round((end_w + 1) * HEURISTIC_WINDOW_S, 3),
            "label":      "Transient loud noise (unclassified)",
            "event_type": "transient_noise",
            "confidence": round(min(peak / max(thresh, 1e-6), 1.0), 4),
            "severity":   "LOW",
        })
    return events, "heuristic"


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def _build_summary(events: list, duration_s: Optional[float]) -> dict:
    by_type: dict = {}
    highest = "LOW"
    for ev in events:
        by_type[ev["event_type"]] = by_type.get(ev["event_type"], 0) + 1
        if _SEVERITY_ORDER.get(ev["severity"], 0) > _SEVERITY_ORDER.get(highest, 0):
            highest = ev["severity"]
    return {
        "total_events":     len(events),
        "by_type":          by_type,
        "highest_severity": highest if events else None,
        "audio_duration_s": duration_s,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_acoustic_events(
    video_path: str,
    threshold: float = DETECTION_THRESHOLD,
    force_backend: Optional[str] = None,   # "yamnet" | "heuristic" | None (auto)
) -> dict:
    """
    Detect non-speech acoustic events in a video/audio file.

    Parameters
    ----------
    video_path    : Absolute path to the source media (video or audio).
    threshold     : Peak confidence required to report a YAMNet event.
    force_backend : Force "yamnet" or "heuristic"; None = auto (prefer YAMNet).

    Returns
    -------
    dict with keys: events, summary, backend, model_used, duration_s, error.
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    empty = {
        "events":      [],
        "summary":     _build_summary([], None),
        "backend":     None,
        "model_used":  None,
        "duration_s":  None,
        "started_at":  started_at,
        "completed_at": None,
        "error":       None,
    }

    if not video_path:
        empty["error"] = "No video_path provided."
        print("  [Acoustic] ❌ No video path — skipping.", flush=True)
        return empty
    if not os.path.exists(video_path):
        empty["error"] = f"File not found: {video_path}"
        print(f"  [Acoustic] ❌ File not found: {video_path}", flush=True)
        return empty

    print(f"  [Acoustic] Analysing audio: {os.path.basename(video_path)}", flush=True)

    tmp_audio = None
    try:
        tmp_fd, tmp_audio = tempfile.mkstemp(suffix=".wav", prefix="chorus_acoustic_")
        os.close(tmp_fd)

        if not _extract_audio_16k_mono(video_path, tmp_audio):
            empty["error"] = "ffmpeg audio extraction failed. Is ffmpeg on PATH?"
            return empty

        waveform, sr = _read_wav_mono(tmp_audio)
        if sr != TARGET_SR:
            waveform = _resample_linear(waveform, sr, TARGET_SR)
        duration_s = round(waveform.size / float(TARGET_SR), 3) if waveform.size else 0.0

        backend = force_backend
        events = None
        if backend != "heuristic":
            events, used = _events_from_yamnet(waveform, threshold)
            if events is not None:
                backend = used

        if events is None:
            events, backend = _events_from_heuristic(waveform, TARGET_SR)
            print(
                "  [Acoustic] ℹ️  Heuristic backend in use — events are "
                "unclassified and should be treated as low-trust.",
                flush=True,
            )

        summary = _build_summary(events, duration_s)
        empty.update({
            "events":       events,
            "summary":      summary,
            "backend":      backend,
            "model_used":   "yamnet" if backend == "yamnet" else "heuristic-dsp",
            "duration_s":   duration_s,
            "completed_at": datetime.datetime.utcnow().isoformat() + "Z",
        })

        print(
            f"  [Acoustic] ✅ {len(events)} event(s) via {backend} "
            f"(highest severity: {summary['highest_severity']}).",
            flush=True,
        )
        return empty

    except Exception as exc:
        import traceback
        empty["error"] = str(exc)
        empty["traceback"] = traceback.format_exc()
        print(f"  [Acoustic] ❌ Detection failed: {exc}", flush=True)
        return empty
    finally:
        if tmp_audio and os.path.exists(tmp_audio):
            try:
                os.remove(tmp_audio)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Acoustic Event Detection — YAMNet non-speech audio events.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python acoustic_event_detection.py --video clip.mp4 --pretty\n"
            "  python acoustic_event_detection.py --video clip.mp4 --threshold 0.25 --pretty\n"
            "  python acoustic_event_detection.py --video clip.mp4 --backend heuristic --pretty\n"
        ),
    )
    p.add_argument("--video", required=True, help="Path to video/audio file.")
    p.add_argument("--threshold", type=float, default=DETECTION_THRESHOLD,
                   help=f"YAMNet peak confidence threshold (default {DETECTION_THRESHOLD}).")
    p.add_argument("--backend", default=None, choices=["yamnet", "heuristic"],
                   help="Force a backend (default: auto — prefer YAMNet).")
    p.add_argument("--output", default=None, help="Save JSON result to this path.")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    result = detect_acoustic_events(
        video_path=args.video,
        threshold=args.threshold,
        force_backend=args.backend,
    )

    out = json.dumps(result, indent=2 if args.pretty else None,
                     ensure_ascii=False, default=str)
    print(out)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"\n  [Acoustic] Saved to: {args.output}", flush=True)

    sys.exit(1 if result["error"] else 0)