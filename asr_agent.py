"""
asr_agent.py
============
Chorus Pipeline — Step 7a: Automatic Speech Recognition (ASR) Agent

Pipeline position
-----------------
  Runs AFTER : Scene Segmentation (Step 7)
  Runs BEFORE: Fusion Agent
  Depends on : A local video file path being available in the payload.

Purpose
-------
Transcribes all speech from the video audio track using OpenAI Whisper.
Produces a timestamped transcript with speaker-neutral segments that the
Fusion Agent merges onto the shared scene timeline.

Model
-----
  Primary  : openai/whisper-large-v3  (best accuracy, ~3.5 GB VRAM)
  Fallback : openai/whisper-base      (if VRAM < 4 GB, ~1 GB VRAM)

Rules
-----
1. Always detect language first — do not assume English.
2. Return timestamped segments (start_s, end_s, text) — never a flat blob.
3. For RTSP/chunked sources: accept a list of chunk audio paths and offset
   each chunk's timestamps by its stream_offset_seconds.
4. Never block on model load — lazy-load on first call only.
5. If audio extraction fails, return an empty transcript with error detail.
   Never raise — the pipeline continues without audio.

Usage (library)
---------------
  from asr_agent import transcribe_video

  result = transcribe_video("clip.mp4")
  # result = {
  #   "language": "en",
  #   "language_confidence": 0.98,
  #   "segments": [
  #     {"segment_id": 0, "start_s": 0.0, "end_s": 4.2, "text": "Hello world"},
  #     ...
  #   ],
  #   "full_transcript": "Hello world ...",
  #   "word_count": 42,
  #   "duration_s": 120.5,
  #   "model_used": "whisper-large-v3",
  #   "error": null
  # }

Usage (CLI)
-----------
  python asr_agent.py --video clip.mp4 --pretty
  python asr_agent.py --video clip.mp4 --model base --language en
  python asr_agent.py --video clip.mp4 --output transcript.json
"""

import os
import sys
import json
import argparse
import tempfile
import datetime
from typing import Optional

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def _ensure_ffmpeg():
    import shutil
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        d = os.path.dirname(exe)
        t = os.path.join(d, "ffmpeg.exe")
        if not os.path.exists(t):
            shutil.copyfile(exe, t)
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass
    if not shutil.which("ffmpeg"):
        solidworks_ffmpeg = r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS Flow Simulation\binCFW"
        if os.path.exists(os.path.join(solidworks_ffmpeg, "ffmpeg.exe")):
            os.environ["PATH"] = solidworks_ffmpeg + os.pathsep + os.environ.get("PATH", "")

_ensure_ffmpeg()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Model to use. Override via ASR_MODEL env var or --model CLI flag.
# Options: "large-v3", "large-v2", "medium", "small", "base", "tiny"
DEFAULT_MODEL_SIZE = os.getenv("ASR_MODEL", "base")

# VRAM threshold (GB) below which we auto-downgrade to "base"
VRAM_DOWNGRADE_THRESHOLD_GB = 4.0

# Maximum segment text length before splitting (chars)
MAX_SEGMENT_CHARS = 500

# ─────────────────────────────────────────────────────────────────────────────
# LAZY MODEL REGISTRY
# ─────────────────────────────────────────────────────────────────────────────
_whisper_model = None
_model_size_loaded: Optional[str] = None


def _get_available_vram_gb() -> float:
    """Returns available VRAM in GB, or 0.0 if CUDA is not available."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free, total = torch.cuda.mem_get_info(0)
        return free / (1024 ** 3)
    except Exception:
        return 0.0


def _select_model_size(requested: str) -> str:
    """Auto-downgrade model if VRAM is insufficient."""
    if requested in ("large-v3", "large-v2", "large"):
        vram = _get_available_vram_gb()
        if vram > 0 and vram < VRAM_DOWNGRADE_THRESHOLD_GB:
            print(
                f"  [ASR Agent] ⚠️  Only {vram:.1f} GB VRAM free. "
                f"Downgrading from {requested} → base to avoid OOM."
            )
            return "base"
    return requested


def load_whisper(model_size: Optional[str] = None) -> tuple:
    """
    Lazy-load Whisper model. Returns (model, model_size_used).
    Caches the model globally so subsequent calls are instant.
    """
    global _whisper_model, _model_size_loaded

    size = _select_model_size(model_size or DEFAULT_MODEL_SIZE)

    if _whisper_model is not None and _model_size_loaded == size:
        return _whisper_model, size

    try:
        import whisper
    except ImportError:
        raise ImportError(
            "[ASR Agent] Whisper not installed.\n"
            "Run: pip install openai-whisper\n"
            "Also needed: pip install ffmpeg-python  (and ffmpeg on PATH)"
        )

    print(f"  [ASR Agent] Loading whisper-{size}…", flush=True)

    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"

    _whisper_model = whisper.load_model(size, device=device)
    _model_size_loaded = size
    print(f"  [ASR Agent] ✅ Loaded whisper-{size} on {device.upper()}", flush=True)
    return _whisper_model, size


def unload_whisper():
    """Release Whisper from VRAM. Call before loading another large model."""
    global _whisper_model, _model_size_loaded
    if _whisper_model is not None:
        try:
            import torch
            del _whisper_model
            torch.cuda.empty_cache()
        except Exception:
            pass
        _whisper_model = None
        _model_size_loaded = None
        print("  [ASR Agent] Model unloaded from VRAM.", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# AUDIO EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _extract_audio(video_path: str, out_path: str) -> bool:
    """
    Extract audio from video to a 16kHz mono WAV file using ffmpeg.
    Returns True on success, False on failure.
    """
    try:
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ar", "16000",    # Whisper expects 16kHz
            "-ac", "1",        # Mono
            "-vn",             # No video
            "-f", "wav",
            out_path
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=300
        )
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[:500]
            print(f"  [ASR Agent] ffmpeg error: {err}", flush=True)
            return False
        return True
    except FileNotFoundError:
        print(
            "  [ASR Agent] ❌ ffmpeg not found on PATH.\n"
            "  Install: https://ffmpeg.org/download.html  or  winget install ffmpeg",
            flush=True
        )
        return False
    except subprocess.TimeoutExpired:
        print("  [ASR Agent] ❌ ffmpeg timed out during audio extraction.", flush=True)
        return False
    except Exception as exc:
        print(f"  [ASR Agent] ❌ Audio extraction failed: {exc}", flush=True)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIPT POST-PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _build_segments(raw_segments: list, stream_offset_s: float = 0.0) -> list:
    """
    Convert Whisper raw segment dicts to Chorus-standard format.
    Applies stream_offset for chunked RTSP transcription.
    """
    out = []
    for i, seg in enumerate(raw_segments):
        text = seg.get("text", "").strip()
        if not text:
            continue
        out.append({
            "segment_id": i,
            "start_s": round(seg.get("start", 0.0) + stream_offset_s, 3),
            "end_s":   round(seg.get("end",   0.0) + stream_offset_s, 3),
            "text":    text,
            "avg_logprob": round(seg.get("avg_logprob", 0.0), 4),
            "no_speech_prob": round(seg.get("no_speech_prob", 0.0), 4),
        })
    return out


def _full_transcript(segments: list) -> str:
    """Join segment texts into one clean string."""
    return " ".join(s["text"] for s in segments).strip()


# ─────────────────────────────────────────────────────────────────────────────
# CORE TRANSCRIPTION FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_video(
    video_path: str,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
    stream_offset_s: float = 0.0,
    task: str = "transcribe",   # "transcribe" | "translate" (translate → English)
) -> dict:
    """
    Transcribe a video file and return a Chorus-standard ASR result dict.

    Parameters
    ----------
    video_path      : Absolute path to the video (mp4, avi, mkv, etc.)
    model_size      : Whisper model size override ("large-v3", "base", etc.)
    language        : ISO 639-1 language code ("en", "hi", "fr"…).
                      If None, Whisper auto-detects.
    stream_offset_s : For chunked RTSP — offset all segment timestamps.
    task            : "transcribe" (default) or "translate" (output in English).

    Returns
    -------
    dict with keys: language, language_confidence, segments, full_transcript,
                    word_count, duration_s, model_used, error
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    _empty = {
        "language": None,
        "language_confidence": None,
        "segments": [],
        "full_transcript": "",
        "word_count": 0,
        "duration_s": None,
        "model_used": model_size or DEFAULT_MODEL_SIZE,
        "started_at": started_at,
        "completed_at": None,
        "error": None,
    }

    # ── Validate input ─────────────────────────────────────────────────────
    if not video_path:
        _empty["error"] = "No video_path provided."
        print("  [ASR Agent] ❌ No video path — skipping.", flush=True)
        return _empty

    if not os.path.exists(video_path):
        _empty["error"] = f"File not found: {video_path}"
        print(f"  [ASR Agent] ❌ File not found: {video_path}", flush=True)
        return _empty

    print(f"  [ASR Agent] Transcribing: {os.path.basename(video_path)}", flush=True)

    # ── Extract audio to temp WAV ──────────────────────────────────────────
    tmp_audio = None
    try:
        tmp_fd, tmp_audio = tempfile.mkstemp(suffix=".wav", prefix="chorus_asr_")
        os.close(tmp_fd)

        print("  [ASR Agent] Extracting audio track (16kHz mono)…", flush=True)
        ok = _extract_audio(video_path, tmp_audio)
        if not ok:
            _empty["error"] = "ffmpeg audio extraction failed. Is ffmpeg on PATH?"
            return _empty

        # ── Load model ────────────────────────────────────────────────────
        try:
            model, size_used = load_whisper(model_size)
        except ImportError as e:
            _empty["error"] = str(e)
            return _empty

        # ── Run transcription ──────────────────────────────────────────────
        decode_options = {
            "task": task,
            "verbose": False,
        }
        if language:
            decode_options["language"] = language

        print(f"  [ASR Agent] Running whisper-{size_used} transcription…", flush=True)
        result = model.transcribe(tmp_audio, **decode_options)

        # ── Parse results ─────────────────────────────────────────────────
        lang = result.get("language", "unknown")
        # Whisper stores language probability in the first segment's compression ratio
        lang_prob = None
        if result.get("segments"):
            # Heuristic: use avg compression ratio of first segment as confidence proxy
            first_seg = result["segments"][0]
            lang_prob = round(1.0 - min(first_seg.get("compression_ratio", 1.0) / 3.0, 1.0), 2)

        segments = _build_segments(result.get("segments", []), stream_offset_s)
        transcript = _full_transcript(segments)
        word_count = len(transcript.split())

        # Duration from last segment end
        duration_s = segments[-1]["end_s"] if segments else None

        completed_at = datetime.datetime.utcnow().isoformat() + "Z"
        print(
            f"  [ASR Agent] ✅ Done — {len(segments)} segments, "
            f"{word_count} words, lang={lang}",
            flush=True
        )

        return {
            "language": lang,
            "language_confidence": lang_prob,
            "segments": segments,
            "full_transcript": transcript,
            "word_count": word_count,
            "duration_s": duration_s,
            "model_used": f"whisper-{size_used}",
            "started_at": started_at,
            "completed_at": completed_at,
            "error": None,
        }

    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print(f"  [ASR Agent] ❌ Transcription failed: {exc}", flush=True)
        _empty["error"] = str(exc)
        _empty["traceback"] = tb
        return _empty

    finally:
        # Always clean up the temp audio file
        if tmp_audio and os.path.exists(tmp_audio):
            try:
                os.remove(tmp_audio)
            except OSError:
                pass


def transcribe_chunks(
    chunk_paths: list,
    stream_offsets_s: list,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe multiple RTSP chunks and merge into one unified result.
    chunk_paths      : list of video/audio file paths (one per chunk)
    stream_offsets_s : matching list of absolute stream start times (seconds)
    """
    all_segments = []
    detected_lang = None
    total_words = 0
    errors = []

    for i, (path, offset) in enumerate(zip(chunk_paths, stream_offsets_s)):
        print(f"  [ASR Agent] Chunk {i + 1}/{len(chunk_paths)}: {os.path.basename(path)}", flush=True)
        res = transcribe_video(path, model_size=model_size, language=language, stream_offset_s=offset)
        if res["error"]:
            errors.append(f"Chunk {i}: {res['error']}")
        else:
            all_segments.extend(res["segments"])
            total_words += res["word_count"]
            if detected_lang is None:
                detected_lang = res["language"]

    # Re-number segment IDs after merge
    for idx, seg in enumerate(all_segments):
        seg["segment_id"] = idx

    transcript = _full_transcript(all_segments)
    duration_s = all_segments[-1]["end_s"] if all_segments else None

    return {
        "language": detected_lang,
        "language_confidence": None,
        "segments": all_segments,
        "full_transcript": transcript,
        "word_count": total_words,
        "duration_s": duration_s,
        "model_used": f"whisper-{model_size or DEFAULT_MODEL_SIZE}",
        "chunks_processed": len(chunk_paths),
        "errors": errors if errors else None,
        "error": "; ".join(errors) if errors else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser():
    p = argparse.ArgumentParser(
        description="Chorus ASR Agent — Transcribe video audio using Whisper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python asr_agent.py --video clip.mp4 --pretty\n"
            "  python asr_agent.py --video clip.mp4 --model base\n"
            "  python asr_agent.py --video clip.mp4 --language hi --pretty\n"
            "  python asr_agent.py --video clip.mp4 --task translate --pretty\n"
        ),
    )
    p.add_argument("--video",    required=True,  help="Path to video file.")
    p.add_argument("--model",    default=None,   help="Whisper model size (large-v3, medium, base, tiny).")
    p.add_argument("--language", default=None,   help="Force language (ISO 639-1 code, e.g. en, hi, fr).")
    p.add_argument("--task",     default="transcribe", choices=["transcribe", "translate"],
                   help="transcribe = keep original language; translate = output English.")
    p.add_argument("--output",   default=None,   help="Save JSON result to this file path.")
    p.add_argument("--pretty",   action="store_true", help="Pretty-print JSON output.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    result = transcribe_video(
        video_path=args.video,
        model_size=args.model,
        language=args.language,
        task=args.task,
    )

    indent = 2 if args.pretty else None
    out = json.dumps(result, indent=indent, ensure_ascii=False)
    print(out)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\n  [ASR Agent] Saved to: {args.output}", flush=True)

    sys.exit(1 if result["error"] else 0)
