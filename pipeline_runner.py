# -*- coding: utf-8 -*-
"""
pipeline_runner.py
==================
Chorus Pipeline Orchestrator — Full Phase 1 General Mode Pipeline.

Pipeline Steps (General Mode)
------------------------------
 Step 1  Source Adapter        chorus_input.py       [WIRED via chorus_input]
 Step 2  Quality Gate          quality_gate.py       [WIRED]
 Step 3  Duplication Check     duplication_check.py  [WIRED]
 Step 4  Manipulation Detect   manipulation_detection.py [WIRED]
 Step 5  Orchestrator Brain    orchestrator_lora_v2/ [WIRED — routes general/cyber]
 Step 6  Scene Segmentation    scene_segmentation.py [WIRED]
 Step 7  VL Vision Agent       run_vl_agent.py       [WIRED — frames→description]
 Step 7a ASR Agent             asr_agent.py          [WIRED — audio→transcript]
 Step 8  Fusion Agent          fusion_agent.py       [WIRED — merge all outputs]
 Step 9  Domain Output         domain_output.py      [WIRED — final summary]

Pipeline Steps (Cyber Mode additions)
--------------------------------------
 Step C1 Acoustic Event        acoustic_event_detection.py  [WIRED]
 Step C2 Geo Estimation        geo_estimation_agent.py      [WIRED]
 Step C3 Face Re-ID            face_reid_agent.py           [WIRED — governance gated]
 Step C4 Alert System          alert_system.py              [WIRED]

Halt conditions (stop pipeline immediately)
-------------------------------------------
  • duplication_check  → halt_pipeline=True (duplicate detected)
  • quality_gate       → overall_verdict="FAIL"
  • manipulation       → verdict="FLAGGED" AND detector_error=False → review queue
  • No video file path → skip scene segmentation, VL, and ASR

Usage (library)
---------------
  from pipeline_runner import run_full_pipeline

  result = run_full_pipeline(
      video_path="clip.mp4",
      source_type="local_upload",
      user_question="What happens in this video?",
      mode="general",           # "general" | "cyber"
      governance_approved=False,
  )
  print(result["domain_output"]["final_output"]["executive_summary"])

  # Playlist / multi-video batch mode
  from pipeline_runner import run_playlist_pipeline

  batch = run_playlist_pipeline(
      url="https://youtube.com/playlist?list=PL...",
      max_playlist_videos=3,    # 0 (or negative) = ALL videos
      fast_mode=True,
  )
  print(batch["total_playlist_videos"])       # full catalog size (e.g. 94)
  print(len(batch["analyzed_videos"]))         # per-video full analyses
  print(batch["master_summary"]["master_summary"])  # cross-video synthesis

Usage (CLI)
-----------
  python pipeline_runner.py --video clip.mp4 --question "Summarize this" --pretty
  python pipeline_runner.py --video clip.mp4 --mode cyber --pretty
  python pipeline_runner.py --url "https://youtu.be/ID" --question "What is this?"

  # Playlist / multi-video batch mode (auto-detected for playlist URLs)
  python pipeline_runner.py --url "https://youtube.com/playlist?list=PL..." \\
      --max-playlist-videos 2 --fast --pretty
  python pipeline_runner.py --url "https://youtube.com/playlist?list=PL..." \\
      --max-playlist-videos 0 --fast --pretty   # 0 (or negative) = ALL videos

  # Legacy: dedup-only mode (original pipeline_runner behaviour)
  python pipeline_runner.py --legacy --source-type local_upload --video clip.mp4 \\
      --timeline-input timeline.json --pretty

Playlist Batch Mode (run_playlist_pipeline)
-------------------------------------------
  When --url points to a YouTube playlist, the runner switches to batch
  orchestration:

   1. resolve_playlist() catalogs EVERY video in the playlist (no download).
   2. The first --max-playlist-videos entries (default 3; 0 = all) are
      processed one-by-one through the full per-video pipeline:
      Step 3 Dedup → Step 2 Quality Gate → Step 4 Manipulation →
      Step 5 Orchestrator Routing → Step 6 Scene Segmentation →
      Step 7 VL Vision → Step 7a Whisper ASR → Step 8 Fusion.
      (Per-video Step 9 domain output is skipped in batch mode; the Text
      Brain runs once at the end over ALL videos instead.)
   3. A failed/private video marks that entry as status="failed" and the
      batch continues with the next video (error isolation).
   4. A cross-video Master Synthesis (Text/Domain Brain) fuses all ASR
      transcripts + VL visual observations into one master executive
      summary with phase/topic progression and cross-video insights.
"""

import json
import sys
import os
import time
import argparse
import datetime
from typing import Optional, List

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
# OPTIONAL IMPORTS (graceful degradation if not installed)
# ─────────────────────────────────────────────────────────────────────────────

def _try_import(module_name: str, friendly: str):
    try:
        import importlib
        return importlib.import_module(module_name), True
    except ImportError:
        print(f"  [Pipeline] ⚠️  {friendly} not available (import {module_name} failed).", flush=True)
        return None, False


def _probe_has_audio(video_path: str) -> bool:
    """
    Detect whether a video file contains an audio stream.
    Tries cv2 first (fast, no subprocess), falls back to ffprobe, then
    defaults to True (assume audio present) so the pipeline is conservative.
    """
    # Try OpenCV — cap.get with CAP_PROP_FOURCC cannot detect audio, but we
    # can try the lightweight ffprobe path which is reliable.
    try:
        import subprocess
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            video_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # If ffprobe prints an audio stream index, audio is present
        if result.stdout.strip():
            return True
        # Empty output = no audio stream found
        if result.returncode == 0:
            return False
    except FileNotFoundError:
        pass  # ffprobe not on PATH
    except Exception:
        pass

    # Fallback: assume audio present (conservative — avoids missing real audio)
    return True


def _build_auto_timeline_payload(video_path: str) -> dict:
    """
    Build a minimal quality_gate-compatible timeline payload from video
    metadata extracted via OpenCV. Used when no timeline_payload is provided.
    """
    payload = {
        "video_id": os.path.basename(video_path),
        "video_path": video_path,
        "source_type": "local_upload",
        "duration_seconds": 0.0,
        "fps": 0.0,
        "resolution": {"width": 0, "height": 0},
        "file_size_bytes": 0,
        "total_frames": 0,
        "codec": "unknown",
        "has_audio": _probe_has_audio(video_path),
    }
    try:
        payload["file_size_bytes"] = os.path.getsize(video_path)
    except OSError:
        pass

    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            payload["fps"] = cap.get(cv2.CAP_PROP_FPS) or 0.0
            payload["resolution"]["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            payload["resolution"]["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            payload["total_frames"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if payload["fps"] > 0 and payload["total_frames"] > 0:
                payload["duration_seconds"] = payload["total_frames"] / payload["fps"]
            codec_int = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
            if codec_int:
                payload["codec"] = "".join(
                    chr((codec_int >> 8 * i) & 0xFF) for i in range(4)
                )
            cap.release()
    except Exception as exc:
        print(f"  [Pipeline] ⚠️  cv2 probe failed: {exc}", flush=True)

    dur = float(payload.get("duration_seconds") or 1.0)
    payload["video_duration_seconds"] = dur
    payload["current_stream_position_seconds"] = None
    payload["stream_gaps"] = None
    payload["fused_timeline"] = [
        {
            "event_id": "ev_001",
            "timestamp_start": 0.0,
            "timestamp_end": dur,
            "source": "vision",
            "content": f"Video footage ({payload['resolution']['width']}x{payload['resolution']['height']}, {payload['fps']:.1f} fps).",
            "confidence_score": 0.95,
            "speaker_id": None,
        }
    ]

    print(f"  [Pipeline] ℹ️  Auto-built timeline payload: "
          f"{payload['resolution']['width']}x{payload['resolution']['height']}, "
          f"{payload['fps']:.1f} fps, {payload['duration_seconds']:.1f}s",
          flush=True)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR BRAIN — Route using LoRA fine-tuned model
# ─────────────────────────────────────────────────────────────────────────────

ORCHESTRATOR_ADAPTER_PATH = os.path.join(
    os.path.dirname(__file__), "orchestrator_lora_v2"
)

_orch_model     = None
_orch_tokenizer = None


def load_orchestrator():
    """Lazy-load the Chorus orchestrator brain (Qwen2.5-7B + LoRA adapter)."""
    global _orch_model, _orch_tokenizer
    if _orch_model is not None:
        return _orch_model, _orch_tokenizer

    print("  [Orchestrator] Loading LoRA fine-tuned routing brain…", flush=True)
    try:
        from unsloth import FastLanguageModel
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=ORCHESTRATOR_ADAPTER_PATH,
            max_seq_length=1024,
            load_in_4bit=True,
        )
        FastLanguageModel.for_inference(model)
        _orch_model     = model
        _orch_tokenizer = tokenizer
        print("  [Orchestrator] ✅ Routing brain loaded.", flush=True)
        return _orch_model, _orch_tokenizer
    except Exception as exc:
        print(f"  [Orchestrator] ⚠️  Could not load LoRA brain: {exc}", flush=True)
        print("  [Orchestrator] ℹ️  Falling back to rule-based routing.", flush=True)
        return None, None


def unload_orchestrator():
    """Release orchestrator from VRAM."""
    global _orch_model, _orch_tokenizer
    if _orch_model is not None:
        try:
            import torch
            del _orch_model
            torch.cuda.empty_cache()
        except Exception:
            pass
        _orch_model     = None
        _orch_tokenizer = None
        print("  [Orchestrator] Unloaded from VRAM.", flush=True)


def orchestrate(
    source_type: str,
    user_question: str,
    mode_hint: str = "general",
    governance_approved: bool = False,
    manipulation_verdict: str = "CLEAN",
    has_audio: bool = True,
    has_video: bool = True,
    fast_mode: bool = False,
) -> dict:
    """
    Ask the orchestrator brain which agents to call for this request.
    Falls back to a safe rule-based routing decision if the model is unavailable.

    Returns a routing decision dict:
    {
      "mode": "general" | "cyber",
      "tool_calls": ["scene_segmentation", "perception_agent", "asr_agent", ...],
      "excluded": ["face_reid_agent", ...],
      "reasoning_summary": "..."
    }
    """
    # ── Rule-based fallback (always safe to call) ──────────────────────────
    def _rule_based_route() -> dict:
        mode = mode_hint
        # Infer cyber from question keywords if mode_hint is ambiguous
        cyber_keywords = ["cctv", "forensic", "surveillance", "investigation",
                          "security", "cyber", "crime", "incident", "suspect"]
        if any(kw in user_question.lower() for kw in cyber_keywords):
            mode = "cyber"

        tools = ["scene_segmentation", "perception_agent"]
        excluded = []

        if has_audio:
            tools.append("asr_agent")
        if mode == "cyber":
            tools.extend(["acoustic_event_detection", "geo_estimation_agent", "alert_system"])
            if governance_approved:
                tools.append("face_reid_agent")
            else:
                excluded.append("face_reid_agent")
        else:
            excluded.extend(["geo_estimation_agent", "face_reid_agent", "alert_system"])

        if manipulation_verdict == "FLAGGED":
            tools.append("review_queue")

        tools.extend(["fusion_agent", "domain_output"])

        return {
            "mode": mode,
            "tool_calls": tools,
            "excluded": excluded,
            "reasoning_summary": "Rule-based routing (orchestrator model not available or fast mode requested).",
            "routing_method": "rule_based",
        }

    is_fast = fast_mode or os.getenv("CHORUS_FAST_ROUTING", "").lower() in ("1", "true", "yes")
    if is_fast:
        print("  [Orchestrator] ⚡ Fast mode enabled — using rule-based routing.", flush=True)
        return _rule_based_route()

    model, tokenizer = load_orchestrator()
    if model is None:
        return _rule_based_route()

    # ── LLM-based routing ──────────────────────────────────────────────────
    system_prompt = (
        "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
        "Decide which agents to call in what order. "
        "Return ONLY valid JSON: {\"mode\": \"general\"|\"cyber\", "
        "\"tool_calls\": [...], \"excluded\": [...], \"reasoning_summary\": \"...\"}"
    )

    # Build scenario description
    scenario_parts = [
        f"source_type: {source_type}",
        f"user_question: {user_question}",
        f"mode_hint: {mode_hint}",
        f"governance_approved: {governance_approved}",
        f"manipulation_verdict: {manipulation_verdict}",
        f"has_audio: {has_audio}",
        f"has_video: {has_video}",
    ]
    scenario = "SCENARIO: " + " | ".join(scenario_parts)

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": scenario},
        ]
        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        inputs = tokenizer([text], return_tensors="pt").to(device)
        out = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        trimmed = out[0][inputs.input_ids.shape[1]:]
        raw = tokenizer.decode(trimmed, skip_special_tokens=True).strip()

        # Parse JSON from output
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        # Extract JSON object
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            decision = json.loads(m.group(0))
            decision["routing_method"] = "orchestrator_lora"

            # Safety override: never call face_reid_agent without governance
            if not governance_approved and "face_reid_agent" in decision.get("tool_calls", []):
                decision["tool_calls"].remove("face_reid_agent")
                decision.setdefault("excluded", []).append("face_reid_agent")
                decision["reasoning_summary"] += " [face_reid_agent removed: governance not approved]"

            return decision

    except Exception as exc:
        print(f"  [Orchestrator] ⚠️  LLM routing failed: {exc}. Using rule-based fallback.", flush=True)

    return _rule_based_route()


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICATION MCP — Conditional external verification
# ─────────────────────────────────────────────────────────────────────────────

def _run_verification(
    case_id: str,
    manipulation_verdict: str,
    source_type: str,
    source_uri: str,
    asr_result: Optional[dict],
    local_video_path: Optional[str],
) -> dict:
    """
    Run conditional external verification via chorus_verification_mcp tools.

    Trigger conditions (from INTEGRATION.md -- do NOT call all four on every video):
      * reverse_search_frame  -- manipulation_verdict == 'FLAGGED'
      * web_search_fetch      -- manipulation_verdict == 'FLAGGED' (context search)
      * check_upload_history  -- source_type == 'youtube'
      * fact_check_claim      -- ASR transcript contains a verifiable claim
      * web_search_fetch      -- fact_check returns 'unverified' (fallback)

    All calls are non-halting: errors are stored but never abort the pipeline.
    Tools are imported directly (same Python process, no subprocess MCP server).
    """
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _mcp_dir = os.path.join(_HERE, "chorus_verification_mcp")
    if _mcp_dir not in sys.path:
        sys.path.insert(0, _mcp_dir)

    # Load chorus_verification_mcp/.env so API keys reach os.getenv() calls
    # inside the tool modules (root .env has only GITHUB_TOKEN — separate file).
    _mcp_env = os.path.join(_mcp_dir, ".env")
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(_mcp_env, override=False)  # override=False: shell env wins
    except ImportError:
        pass  # python-dotenv not installed — keys must be set in shell env

    vr: dict = {
        "reverse_search": None,
        "upload_history": None,
        "fact_check":     None,
        "web_search":     None,
    }

    # Helper: extract YouTube video ID from URL
    def _extract_yt_id(url: str) -> Optional[str]:
        import re
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        return None

    # ── Tools 1 & 2: reverse_search_frame + web_search_fetch ─────────────────
    # Triggered when manipulation detection flags the video.
    if manipulation_verdict == "FLAGGED":
        print("  [Verification] ▶ Manipulation flagged — reverse_search_frame …", flush=True)

        # For YouTube: use thumbnail URL instead of local frame
        yt_id = None
        if source_type == "youtube" and source_uri:
            yt_id = _extract_yt_id(source_uri)

        frame_b64 = None
        thumbnail_url = None
        if yt_id:
            thumbnail_url = f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg"
            print(f"  [Verification] 🔗 Using YouTube thumbnail: {thumbnail_url}", flush=True)
        elif local_video_path and os.path.exists(local_video_path):
            try:
                import cv2 as _cv2
                import base64 as _b64
                cap = _cv2.VideoCapture(local_video_path)
                ok, frame = cap.read()
                cap.release()
                if ok and frame is not None:
                    _, buf = _cv2.imencode(".jpg", frame)
                    frame_b64 = _b64.b64encode(buf.tobytes()).decode("utf-8")
            except Exception as exc:
                print(f"  [Verification] ⚠️  Frame extraction failed: {exc}", flush=True)

        if thumbnail_url or frame_b64:
            try:
                from tools import reverse_search as _rs
                # Pass either thumbnail URL or base64 frame
                image_input = thumbnail_url if thumbnail_url else frame_b64
                rs_result = _rs.run({"image": image_input, "case_id": case_id})
                vr["reverse_search"] = rs_result
                if rs_result.get("error"):
                    print(f"  [Verification] ⚠️  reverse_search_frame: {rs_result.get('reason')}", flush=True)
                else:
                    earliest = rs_result.get("earliest_known_source", "unknown")
                    print(f"  [Verification] ✅ reverse_search_frame — earliest: {earliest}", flush=True)
            except Exception as exc:
                print(f"  [Verification] ⚠️  reverse_search_frame exception: {exc}", flush=True)
        else:
            print("  [Verification] ⚠️  reverse_search_frame skipped — no frame/thumbnail available.", flush=True)

        # web_search_fetch for manipulation context
        try:
            from tools import web_search_fetch as _wsf
            ws_result = _wsf.run({
                "mode":    "search",
                "query":   f"deepfake manipulated video {os.path.basename(source_uri or '')}" ,
                "case_id": case_id,
            })
            vr["web_search"] = ws_result
            if ws_result.get("error"):
                print(f"  [Verification] ⚠️  web_search_fetch: {ws_result.get('reason')}", flush=True)
            else:
                print(f"  [Verification] ✅ web_search_fetch — {len(ws_result.get('results', []))} result(s).", flush=True)
        except Exception as exc:
            print(f"  [Verification] ⚠️  web_search_fetch exception: {exc}", flush=True)

    # ── Tool 3: check_upload_history ─────────────────────────────────────────
    # Triggered when source is YouTube — verify upload date and re-uploads.
    if source_type == "youtube" and source_uri:
        print("  [Verification] ▶ YouTube source — check_upload_history …", flush=True)
        try:
            from tools import upload_history as _uh
            uh_result = _uh.run({"video_url_or_id": source_uri, "case_id": case_id})
            vr["upload_history"] = uh_result
            if uh_result.get("error"):
                print(f"  [Verification] ⚠️  check_upload_history: {uh_result.get('reason')}", flush=True)
            else:
                published = uh_result.get("published_at", "unknown")
                channel   = uh_result.get("channel_title", "unknown")
                print(f"  [Verification] ✅ check_upload_history — published: {published} by {channel}", flush=True)
        except Exception as exc:
            print(f"  [Verification] ⚠️  check_upload_history exception: {exc}", flush=True)

    # ── Tool 4: fact_check_claim (+ web_search_fetch fallback) ───────────────
    # Triggered when ASR transcript contains a verifiable claim.
    asr_text = ""
    if asr_result and not asr_result.get("error"):
        asr_text = (
            asr_result.get("transcript", "")
            or asr_result.get("text", "")
            or ""
        )

    if asr_text.strip():
        import re as _re
        sentences = _re.split(r'(?<=[.!?])\s+', asr_text.strip())
        claim = next((s for s in sentences if len(s) > 20), None)
        if claim:
            print("  [Verification] ▶ ASR claim detected — fact_check_claim …", flush=True)
            try:
                from tools import fact_check as _fc
                fc_result = _fc.run({"claim_text": claim[:1000], "case_id": case_id})
                vr["fact_check"] = fc_result
                if fc_result.get("error"):
                    print(f"  [Verification] ⚠️  fact_check_claim: {fc_result.get('reason')}", flush=True)
                else:
                    verdict = fc_result.get("verdict", "unknown")
                    print(f"  [Verification] ✅ fact_check_claim — verdict: {verdict}", flush=True)
                    # Fallback: web_search_fetch when fact-check cannot verify the claim
                    if verdict == "unverified" and vr["web_search"] is None:
                        print("  [Verification] ▶ Claim unverified — web_search_fetch fallback …", flush=True)
                        try:
                            from tools import web_search_fetch as _wsf2
                            ws_fb = _wsf2.run({
                                "mode":    "search",
                                "query":   claim[:200],
                                "case_id": case_id,
                            })
                            vr["web_search"] = ws_fb
                            if ws_fb.get("error"):
                                print(f"  [Verification] ⚠️  web_search_fetch fallback: {ws_fb.get('reason')}", flush=True)
                            else:
                                print(f"  [Verification] ✅ web_search_fetch fallback — {len(ws_fb.get('results', []))} result(s).", flush=True)
                        except Exception as exc:
                            print(f"  [Verification] ⚠️  web_search_fetch fallback exception: {exc}", flush=True)
            except Exception as exc:
                print(f"  [Verification] ⚠️  fact_check_claim exception: {exc}", flush=True)

    return vr


# ─────────────────────────────────────────────────────────────────────────────
# WORKER KEY FEATURE EXTRACTION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def extract_video_key_features(
    video_path: Optional[str],
    scenes: Optional[List[dict]] = None,
    asr_result: Optional[dict] = None,
    manipulation_result: Optional[dict] = None,
    video_title: Optional[str] = None,
    video_id: Optional[str] = None,
    playlist_context: Optional[str] = None,
    max_keyframes: int = 12,
) -> dict:
    """
    Extract structured key features and scene-aligned keyframes from a video.
    Packages high-density multimodal evidence (scenes, timestamps, audio transcript,
    and metadata) directly for the VL Agent.
    Guaranteed not to raise unhandled exceptions.
    """
    try:
        import cv2
        from PIL import Image as PILImage
    except ImportError:
        cv2 = None
        PILImage = None

    result = {
        "video_title": video_title or (os.path.basename(video_path) if video_path else "Unknown Video"),
        "video_id": video_id or "",
        "playlist_context": playlist_context or "",
        "duration_seconds": 0.0,
        "fps": 25.0,
        "resolution": "unknown",
        "total_frames": 0,
        "scenes": scenes or [],
        "scene_count": len(scenes) if scenes else 0,
        "keyframe_timestamps": [],
        "keyframes": [],
        "audio_transcript": "",
        "audio_language": "unknown",
        "audio_word_count": 0,
        "ai_generated_flag": False,
        "deepfake_flag": False,
        "manipulation_verdict": "CLEAN",
        "key_features_summary": [],
    }

    # 1. Video Probe & Scene-Aligned Keyframe Extraction
    if video_path and os.path.exists(video_path) and cv2 and PILImage:
        try:
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                dur = round(total / fps, 2) if fps > 0 else 0.0

                result["duration_seconds"] = dur
                result["fps"] = fps
                result["resolution"] = f"{width}x{height}"
                result["total_frames"] = total

                # Determine target timestamps for keyframes based on detected scenes
                target_timestamps = []  # List[Tuple[float, str]]
                if scenes and len(scenes) >= 4:
                    for s in scenes:
                        s_id = s.get("scene_id", 0)
                        start = s.get("start_seconds", 0.0)
                        end = s.get("end_seconds", 0.0)
                        mid = round((start + end) / 2.0, 2)
                        target_timestamps.append((mid, f"Scene {s_id}"))

                    # If more than max_keyframes, sample evenly across scenes
                    if len(target_timestamps) > max_keyframes:
                        step = len(target_timestamps) / float(max_keyframes)
                        target_timestamps = [target_timestamps[int(i * step)] for i in range(max_keyframes)]
                else:
                    # Uniform sampling across duration (at least 6-8 keyframes so VL model perceives full visual progression)
                    n_k = max(6, min(max_keyframes, int(dur / 2.5) if dur > 0 else 6))
                    for i in range(n_k):
                        t_sec = round((i / max(n_k - 1, 1)) * max(dur - 0.5, 0.0), 2)
                        target_timestamps.append((t_sec, f"Point {i+1}"))

                # Read frames at target timestamps
                extracted_frames = []
                kf_labels = []
                for t_sec, label in target_timestamps:
                    frame_idx = min(int(t_sec * fps), max(total - 1, 0))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                    ret, frame = cap.read()
                    if ret:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        extracted_frames.append(PILImage.fromarray(rgb))
                        mm = int(t_sec // 60)
                        ss = int(t_sec % 60)
                        kf_labels.append(f"{mm:02d}:{ss:02d} ({label})")

                cap.release()
                result["keyframes"] = extracted_frames
                result["keyframe_timestamps"] = kf_labels
        except Exception as probe_err:
            print(f"  [KeyFeatures] Probe warning: {probe_err}", flush=True)

    # 2. Audio Transcript & Linguistic Highlights
    if asr_result and isinstance(asr_result, dict):
        transcript = (
            asr_result.get("full_transcript")
            or asr_result.get("transcript")
            or asr_result.get("text")
            or ""
        ).strip()
        result["audio_transcript"] = transcript
        result["audio_language"] = asr_result.get("language", "unknown")
        result["audio_word_count"] = asr_result.get("word_count", len(transcript.split()))

    # 3. Manipulation & Forensic Indicators
    if manipulation_result and isinstance(manipulation_result, dict):
        verdict = manipulation_result.get("verdict", "CLEAN")
        result["manipulation_verdict"] = verdict
        result["ai_generated_flag"] = verdict == "FLAGGED"
        result["deepfake_flag"] = verdict == "FLAGGED"

    # 4. Synthesize Summary Bullets
    summary = [
        f"Title: {result['video_title']}",
        f"Technical: {result['duration_seconds']}s | {result['resolution']} @ {result['fps']:.1f}fps",
        f"Structure: {result['scene_count']} distinct scenes detected",
    ]
    if result["keyframe_timestamps"]:
        summary.append(f"Sampled Timestamps: {', '.join(result['keyframe_timestamps'][:8])}")
    if result["audio_transcript"]:
        summary.append(f"Audio Speech: {result['audio_word_count']} words in {result['audio_language']}")
    if result["manipulation_verdict"] == "FLAGGED":
        summary.append("Forensics: Synthetic/Deepfake anomaly flagged")
    result["key_features_summary"] = summary

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CORE PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_full_pipeline(
    video_path: Optional[str] = None,
    url: Optional[str] = None,
    source_type: str = "local_upload",
    user_question: str = "Summarize what happens in this video.",
    mode: str = "general",
    governance_approved: bool = False,
    timeline_payload: Optional[dict] = None,
    skip_vl: bool = False,
    skip_asr: bool = False,
    skip_domain_output: bool = False,
    skip_dedup: bool = False,
    fast_mode: bool = False,
    max_playlist_videos: Optional[int] = 0,
    max_concurrent: int = 2,
    batch_size: Optional[int] = None,
    output_file: str = "playlist_analysis_results.json",
    is_playlist_item: bool = False,
    video_title: Optional[str] = None,
    video_id: Optional[str] = None,
    playlist_index: Optional[int] = None,
    playlist_total: Optional[int] = None,
) -> dict:
    """
    Run the complete Chorus Phase 1 general-mode pipeline.

    Parameters
    ----------
    video_path       : Absolute path to a local video file.
    url              : YouTube or RTSP URL (alternative to video_path).
    source_type      : "local_upload" | "youtube" | "live_rtsp"
    user_question    : User's analysis request.
    mode             : "general" | "cyber"
    governance_approved : Required for face_reid_agent in cyber mode.
    timeline_payload : Pre-built quality gate payload (skips dedup if None).
    skip_vl          : Skip VL vision analysis (faster, no visual description).
    skip_asr         : Skip ASR transcription (no audio analysis).
    skip_domain_output: Skip final LLM summarization (returns raw fusion only).
    max_playlist_videos : For playlist URLs, max number of videos to analyze (0 or None = ALL videos).
    max_concurrent   : Worker pool concurrency cap for playlist batch mode (default 2).
    batch_size       : Chunk size for batch-wise playlist processing (default: 2).
    output_file      : File to save individual video summaries and master results (default: playlist_analysis_results.json).
    is_playlist_item : Internal flag when processing an individual video item from a playlist batch.

    Returns
    -------
    Full pipeline result dict.
    """
    # ── Playlist / Multi-Video Batch Auto-Delegation ────────────────────────
    if url and not video_path and not is_playlist_item:
        try:
            from chorus_input import is_playlist_url
            if is_playlist_url(url):
                print(f"  [Pipeline] 📺 Playlist URL detected — delegating to batch orchestrator...", flush=True)
                return run_playlist_pipeline(
                    url                 = url,
                    max_playlist_videos = max_playlist_videos,
                    max_concurrent      = max_concurrent,
                    batch_size          = batch_size,
                    output_file         = output_file,
                    user_question       = user_question,
                    mode                = mode,
                    governance_approved = governance_approved,
                    skip_vl             = skip_vl,
                    skip_asr            = skip_asr,
                    skip_dedup          = skip_dedup,
                    fast_mode           = fast_mode,
                )
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Playlist check failed ({exc}) — proceeding with single video flow.", flush=True)

    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"\n{'═'*60}", flush=True)
    print(f"  [Pipeline] 🎬 Starting Chorus Pipeline", flush=True)
    print(f"  [Pipeline] Mode: {mode.upper()} | Source: {source_type}", flush=True)
    print(f"{'═'*60}\n", flush=True)

    result = {
        "pipeline_halted":   False,
        "halt_reason":       None,
        "halt_step":         None,
        "mode":              mode,
        "source_type":       source_type,
        "source_uri":        video_path or url or "",
        "user_question":     user_question,
        "routing_decision":  None,
        "started_at":        started_at,
        "completed_at":      None,
        # Step results
        "duplication_result":    None,
        "quality_gate_result":   None,
        "manipulation_result":   None,
        "scene_result":          None,
        "key_features":          None,
        "vl_output":             None,
        "asr_result":            None,
        "fusion_result":         None,
        "domain_output":         None,
        # Cyber mode results
        "acoustic_result":       None,
        "geo_result":            None,
        "face_reid_result":      None,
        "alert_result":          None,
        "review_queue_result":   None,
        "verification_result":   None,
        "playlist_manifest":     None,
        "analyzed_video_info":   None,
    }

    # ── Resolve video path (Universal Ingestion) ───────────────────────────
    local_video_path = video_path

    if url and not local_video_path:
        print(f"  [Pipeline] URL source detected — Source: {url}", flush=True)
        try:
            from chorus_input import download_youtube_video
            if "youtube.com" in url or "youtu.be" in url:
                print(f"  [Pipeline] 📥 Auto-ingesting YouTube video...", flush=True)
                local_video_path = download_youtube_video(url)
                print(f"  [Pipeline] ✅ Ingest complete: {local_video_path}", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️ URL auto-ingest warning: {exc}. Proceeding with stream metadata.", flush=True)

    # ── Step 3: Duplication Check ──────────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 3 — Duplication Check", flush=True)
    dedup_mod, dedup_ok = _try_import("duplication_check", "Duplication Check")
    if not skip_dedup and dedup_ok and local_video_path and os.path.exists(local_video_path):
        dedup_kwargs = {
            "source_type": source_type,
            "video_path": local_video_path,
        }
        # When the video was auto-downloaded (YouTube / playlist ingest) the
        # local file is already on disk — hash it directly instead of
        # re-streaming from the network. run_duplication_check dispatches on
        # source_type, so normalize to local_upload whenever a local file
        # exists; pass the URL only as a remote fallback.
        if local_video_path and os.path.exists(local_video_path):
            dedup_kwargs["source_type"] = "local_upload"
        elif source_type == "youtube" and url:
            dedup_kwargs["url"] = url
        dedup_result = dedup_mod.run_duplication_check(**dedup_kwargs)
        result["duplication_result"] = dedup_result
        if dedup_result.get("halt_pipeline"):
            # Soft-halt for remote/ingested sources: static-camera lecture
            # content (whiteboard, slides) legitimately produces hundreds of
            # "duplicate" consecutive-frame pairs, so a hard halt here would
            # wrongly reject real content. Record the flag and CONTINUE; only
            # local uploads keep the original hard-halt behavior.
            if source_type != "local_upload":
                print(f"  [Pipeline] ⚠️  Step 3 — duplicates flagged on remote "
                      f"source (soft-halt, continuing): "
                      f"{dedup_result.get('halt_reason')}", flush=True)
            else:
                result["pipeline_halted"] = True
                result["halt_reason"]     = dedup_result.get("halt_reason", "Duplicate detected")
                result["halt_step"]       = "duplication_check"
                result["completed_at"]    = datetime.datetime.utcnow().isoformat() + "Z"
                print(f"  [Pipeline] ⛔ HALT — {result['halt_reason']}", flush=True)
                return result
        if not dedup_result.get("halt_pipeline"):
            print("  [Pipeline] ✅ Step 3 — No duplicates.", flush=True)
        else:
            print("  [Pipeline] ✅ Step 3 — Duplicate flags recorded (soft-halt); continuing.", flush=True)
    elif skip_dedup:
        print("  [Pipeline] ⏭️  Step 3 skipped (--skip-dedup enabled).", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 3 skipped (no video file or module unavailable).", flush=True)

    # ── Step 2: Quality Gate ───────────────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 2 — Quality Gate", flush=True)
    if not timeline_payload and local_video_path and os.path.exists(local_video_path):
        # Auto-build a basic timeline payload from video metadata
        print("  [Pipeline] ℹ️  No timeline payload — auto-building from video metadata.", flush=True)
        timeline_payload = _build_auto_timeline_payload(local_video_path)
    if timeline_payload:
        qg_mod, qg_ok = _try_import("quality_gate", "Quality Gate")
        if qg_ok:
            qg_result = qg_mod.run_quality_gate(timeline_payload)
            result["quality_gate_result"] = qg_result
            verdict = qg_result.get("overall_verdict", "UNKNOWN")
            print(f"  [Pipeline] Quality Gate verdict: {verdict}", flush=True)
            if verdict == "FAIL":
                result["pipeline_halted"] = True
                result["halt_reason"]     = "Quality gate FAIL"
                result["halt_step"]       = "quality_gate"
                result["completed_at"]    = datetime.datetime.utcnow().isoformat() + "Z"
                print(f"  [Pipeline] ⛔ HALT — Quality gate failed.", flush=True)
                return result
    else:
        print("  [Pipeline] ⚠️  Step 2 skipped (no timeline payload provided).", flush=True)

    # ── Step 4: Manipulation Detection ────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 4 — Manipulation Detection", flush=True)
    manipulation_verdict = "CLEAN"
    if local_video_path and os.path.exists(local_video_path):
        manip_mod, manip_ok = _try_import("manipulation_detection", "Manipulation Detection")
        if manip_ok:
            try:
                import hashlib
                manip_payload = {
                    "video_id": hashlib.sha256((local_video_path or "").encode()).hexdigest()[:12],
                    "video_path": local_video_path,
                    "source_type": "local_upload",
                    "duration_seconds": 0.0,
                    "dedup_status": "unique",
                    "dedup_hash": "none",
                    "upstream_metadata": {},
                }
                step3_in = manip_mod.parse_step3_input(manip_payload)
                manip_res = manip_mod.detect_manipulation(step3_in)
                manipulation_verdict = manip_res.manipulation_check.verdict
                result["manipulation_result"] = {
                    "verdict": manipulation_verdict,
                    "frames_analyzed": manip_res.manipulation_check.frames_analyzed,
                    "faces_detected": manip_res.manipulation_check.faces_detected,
                    "detector_error": manip_res.manipulation_check.detector_error,
                }
                print(f"  [Pipeline] ✅ Step 4 — Manipulation verdict: {manipulation_verdict}", flush=True)
                if manipulation_verdict == "FLAGGED" and not manip_res.manipulation_check.detector_error:
                    print("  [Pipeline] ⚠️  Deepfake/manipulation flagged — routing to review queue.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step 4 error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 4 skipped (no video file).", flush=True)

    # ── Step 5: Orchestrator Routing ───────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 5 — Orchestrator Brain (Routing Decision)", flush=True)

    # Detect audio presence via ffprobe (not just file existence)
    has_audio = False
    if local_video_path and os.path.exists(local_video_path):
        has_audio = _probe_has_audio(local_video_path)
        print(f"  [Pipeline] ℹ️  Audio stream {'detected' if has_audio else 'NOT detected'}.", flush=True)

    routing = orchestrate(
        source_type=source_type,
        user_question=user_question,
        mode_hint=mode,
        governance_approved=governance_approved,
        manipulation_verdict=manipulation_verdict,
        has_audio=has_audio,
        has_video=bool(local_video_path),
        fast_mode=fast_mode,
    )
    result["routing_decision"] = routing
    mode = routing.get("mode", mode)  # Use orchestrator's confirmed mode
    tool_calls = routing.get("tool_calls", [])
    print(f"  [Pipeline] ✅ Step 5 — Mode: {mode.upper()} | Tools: {tool_calls}", flush=True)

    # Release orchestrator VRAM before loading perception models
    unload_orchestrator()

    # ── Step 6: Scene Segmentation ─────────────────────────────────────────
    scenes = []
    if "scene_segmentation" in tool_calls and local_video_path and os.path.exists(local_video_path):
        print("\n  [Pipeline] ▶ Step 6 — Scene Segmentation", flush=True)
        seg_mod, seg_ok = _try_import("scene_segmentation", "Scene Segmentation")
        if seg_ok:
            try:
                seg_result = seg_mod.detect_scenes({
                    "video_path": local_video_path,
                    "source_type": source_type,
                    "mode": mode,
                })
                scenes = seg_result.get("scenes", [])
                result["scene_result"] = seg_result
                print(f"  [Pipeline] ✅ Step 6 — {len(scenes)} scene(s) detected.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step 6 error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 6 (Scene Segmentation) skipped.", flush=True)

    # ── Step 7a: ASR Transcription ────────────────────────────────────────
    asr_result = None
    if not skip_asr and "asr_agent" in tool_calls and local_video_path:
        print("\n  [Pipeline] ▶ Step 7a — ASR Transcription (Whisper)", flush=True)
        try:
            from asr_agent import transcribe_video
            asr_result = transcribe_video(local_video_path)
            result["asr_result"] = asr_result
            if asr_result.get("error"):
                print(f"  [Pipeline] ⚠️  Step 7a — ASR error: {asr_result['error']}", flush=True)
            else:
                print(
                    f"  [Pipeline] ✅ Step 7a — {asr_result.get('word_count', 0)} words, "
                    f"lang={asr_result.get('language', 'unknown')}",
                    flush=True
                )
        except ImportError:
            print("  [Pipeline] ⚠️  Step 7a skipped — asr_agent not available.", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Step 7a error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 7a (ASR) skipped.", flush=True)

    # ── Step 7b: Worker Key Feature Extraction & Smart Keyframing ────────
    key_features = {}
    extracted_frames = []
    if local_video_path and os.path.exists(local_video_path):
        print("\n  [Pipeline] ▶ Step 7b — Worker Key Feature Extraction & Smart Keyframing", flush=True)
        try:
            resolved_title = video_title or (result.get("analyzed_video_info") or {}).get("title") or os.path.basename(local_video_path)
            resolved_vid   = video_id or (result.get("analyzed_video_info") or {}).get("video_id") or ""
            p_context      = f"Video {playlist_index} of {playlist_total}" if (playlist_index and playlist_total) else None

            key_features = extract_video_key_features(
                video_path=local_video_path,
                scenes=scenes,
                asr_result=asr_result,
                manipulation_result=result.get("manipulation_result"),
                video_title=resolved_title,
                video_id=resolved_vid,
                playlist_context=p_context,
                max_keyframes=12,
            )
            extracted_frames = key_features.pop("keyframes", [])
            result["key_features"] = key_features
            print(
                f"  [Pipeline] ✅ Step 7b — Key features extracted: "
                f"{key_features.get('scene_count', 0)} scenes, "
                f"{key_features.get('duration_seconds', 0)}s duration, "
                f"{len(extracted_frames)} keyframes, "
                f"{key_features.get('audio_word_count', 0)} spoken words.",
                flush=True,
            )
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Step 7b error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 7b skipped (no video file).", flush=True)

    # ── Step 7c (VL): Vision Analysis (VL Brain) ──────────────────────────
    vl_output_text = None
    if not skip_vl and "perception_agent" in tool_calls and local_video_path:
        print("\n  [Pipeline] ▶ Step 7c — Vision Analysis (VL Brain)", flush=True)
        try:
            from run_vl_agent import run_vision_analysis

            # Use smart scene-aligned keyframes if available, else fallback to LocalAdapter
            frames = extracted_frames
            if not frames:
                print("  [Pipeline] Fallback frame extraction via LocalAdapter…", flush=True)
                from chorus_input import LocalAdapter
                adapter = LocalAdapter()
                payload = adapter.process(local_video_path, "local_video")
                frames = payload.frames

            if frames:
                print(f"  [Pipeline] Delivering {len(frames)} keyframes + structured key features to VL Brain…", flush=True)
                vl_meta = dict(key_features) if key_features else {}
                vl_meta.update({
                    "ai_generated_flag": manipulation_verdict == "FLAGGED",
                    "deepfake_flag": manipulation_verdict == "FLAGGED",
                })
                vl_output_text = run_vision_analysis(frames, user_question, vl_meta)
                result["vl_output"] = vl_output_text
                print("  [Pipeline] ✅ Step 7c — VL analysis complete.", flush=True)
            else:
                print("  [Pipeline] ⚠️  Step 7c — No frames extracted.", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Step 7c error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 7c (VL) skipped.", flush=True)

    # Release VL model from VRAM before loading Text Brain later
    try:
        from run_vl_agent import unload_vl_model
        unload_vl_model()
    except ImportError:
        pass

    # ── Cyber Mode Steps (C1–C4) ──────────────────────────────────────────
    acoustic_result = None
    geo_result = None
    face_reid_result = None
    alert_result = None

    if mode == "cyber":
        # ── Step C1: Acoustic Event Detection ─────────────────────────────
        if "acoustic_event_detection" in tool_calls and local_video_path and os.path.exists(local_video_path):
            print("\n  [Pipeline] ▶ Step C1 — Acoustic Event Detection (YAMNet)", flush=True)
            try:
                from acoustic_event_detection import detect_acoustic_events
                acoustic_result = detect_acoustic_events(local_video_path)
                result["acoustic_result"] = acoustic_result
                n_events = len(acoustic_result.get("events", []))
                backend = acoustic_result.get("backend", "unknown")
                print(f"  [Pipeline] ✅ Step C1 — {n_events} event(s) via {backend}.", flush=True)
            except ImportError:
                print("  [Pipeline] ⚠️  Step C1 skipped — acoustic_event_detection not available.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step C1 error: {exc}", flush=True)
        else:
            print("  [Pipeline] ⚠️  Step C1 (Acoustic) skipped.", flush=True)

        # ── Step C2: Geo Estimation ───────────────────────────────────────
        if "geo_estimation_agent" in tool_calls and local_video_path and os.path.exists(local_video_path):
            print("\n  [Pipeline] ▶ Step C2 — Geo Estimation (GeoCLIP)", flush=True)
            try:
                from geo_estimation_agent import estimate_geo
                geo_result = estimate_geo(video_path=local_video_path)
                result["geo_result"] = geo_result
                gps = geo_result.get("gps")
                if gps:
                    print(f"  [Pipeline] ✅ Step C2 — ({gps['lat']}, {gps['lon']}) conf={gps['confidence']}", flush=True)
                else:
                    print(f"  [Pipeline] ⚠️  Step C2 — no GPS estimate: {geo_result.get('error', 'unknown')}", flush=True)
            except ImportError:
                print("  [Pipeline] ⚠️  Step C2 skipped — geo_estimation_agent not available.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step C2 error: {exc}", flush=True)
        else:
            print("  [Pipeline] ⚠️  Step C2 (Geo) skipped.", flush=True)

        # ── Step C3: Face Re-ID (governance gated) ────────────────────────
        if "face_reid_agent" in tool_calls and local_video_path and os.path.exists(local_video_path):
            print("\n  [Pipeline] ▶ Step C3 — Face Re-ID (InsightFace)", flush=True)
            if governance_approved:
                try:
                    from face_reid_agent import run_face_reid
                    face_reid_result = run_face_reid(
                        video_path=local_video_path,
                        governance_approved=True,
                    )
                    result["face_reid_result"] = face_reid_result
                    n_identities = len(face_reid_result.get("identities", []))
                    n_faces = face_reid_result.get("faces_detected", 0)
                    print(f"  [Pipeline] ✅ Step C3 — {n_faces} face(s) → {n_identities} identity/identities.", flush=True)
                except ImportError:
                    print("  [Pipeline] ⚠️  Step C3 skipped — face_reid_agent not available.", flush=True)
                except Exception as exc:
                    print(f"  [Pipeline] ⚠️  Step C3 error: {exc}", flush=True)
            else:
                print("  [Pipeline] ⏭️  Step C3 skipped — governance not approved.", flush=True)
                face_reid_result = {
                    "status": "blocked",
                    "governance_approved": False,
                    "identities": [],
                    "faces_detected": 0,
                    "error": "Governance not approved.",
                }
                result["face_reid_result"] = face_reid_result
        else:
            print("  [Pipeline] ⚠️  Step C3 (Face Re-ID) skipped.", flush=True)

        # ── Step C4: Alert System ─────────────────────────────────────────
        if "alert_system" in tool_calls or mode == "cyber":
            print("\n  [Pipeline] ▶ Step C4 — Alert System", flush=True)
            try:
                from alert_system import evaluate_and_alert
                alert_result = evaluate_and_alert(
                    acoustic_result=acoustic_result,
                    geo_result=geo_result,
                    face_reid_result=face_reid_result,
                    manipulation_result=result.get("manipulation_result"),
                    source_uri=local_video_path or url or "",
                )
                result["alert_result"] = alert_result
                n_alerts = alert_result.get("total_alerts", 0)
                highest = alert_result.get("highest_severity", "NONE")
                print(f"  [Pipeline] ✅ Step C4 — {n_alerts} alert(s), highest: {highest}.", flush=True)
            except ImportError:
                print("  [Pipeline] ⚠️  Step C4 skipped — alert_system not available.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step C4 error: {exc}", flush=True)

    # ── Review Queue (manipulation flagged or cyber critical) ──────────────
    if manipulation_verdict == "FLAGGED" or (alert_result and alert_result.get("highest_severity") == "CRITICAL"):
        print("\n  [Pipeline] ▶ Review Queue — Flagging for human analyst", flush=True)
        try:
            from review_queue import build_review_item, write_review_item
            reason_parts = []
            if manipulation_verdict == "FLAGGED":
                reason_parts.append("Deepfake/manipulation flagged")
            if alert_result and alert_result.get("highest_severity") == "CRITICAL":
                reason_parts.append(f"Critical alert(s): {alert_result.get('total_alerts', 0)} triggered")

            item = build_review_item(
                source_uri=local_video_path or url or "",
                step="pipeline_review",
                reason="; ".join(reason_parts) if reason_parts else "Flagged for review",
                severity="CRITICAL" if alert_result and alert_result.get("highest_severity") == "CRITICAL" else "HIGH",
                confidence=0.5,
                mode=mode,
            )
            write_review_item(item)
            result["review_queue_result"] = item
            print(f"  [Pipeline] ✅ Review item created: {item.get('item_id', 'unknown')}", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Review queue error: {exc}", flush=True)

    # ── Step 4b: Verification MCP ─────────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 4b — Verification MCP (conditional)", flush=True)
    import hashlib as _hashlib
    _case_id = _hashlib.sha256((local_video_path or url or "").encode()).hexdigest()[:16]
    verification_result = _run_verification(
        case_id=_case_id,
        manipulation_verdict=manipulation_verdict,
        source_type=source_type,
        source_uri=url or local_video_path or "",
        asr_result=asr_result,
        local_video_path=local_video_path,
    )
    result["verification_result"] = verification_result
    _active_tools = [k for k, v in verification_result.items() if v is not None and not (isinstance(v, dict) and v.get("error"))]
    print(f"  [Pipeline] ✅ Step 4b — Verification tools run: {_active_tools or ['none (no triggers fired)']}", flush=True)

    # ── Step 8: Fusion ────────────────────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 8 — Fusion Agent", flush=True)
    fused = None
    try:
        from fusion_agent import fuse_pipeline_outputs
        deepfake_flag = manipulation_verdict == "FLAGGED"
        meta = {
            "video_duration_seconds": (
                result.get("scene_result", {}) or {}
            ).get("duration_s"),
        }
        if result.get("manipulation_result"):
            meta.update(result["manipulation_result"])

        fused = fuse_pipeline_outputs(
            scenes=scenes,
            asr_result=asr_result,
            vl_output=vl_output_text,
            metadata=meta,
            source_type=source_type,
            source_uri=local_video_path or url or "",
            deepfake_flag=deepfake_flag,
            ai_generated_flag=deepfake_flag,
            mode=mode,
            acoustic_result=acoustic_result,
            geo_result=geo_result,
            face_reid_result=face_reid_result,
            alert_result=alert_result,
            verification_result=verification_result,
        )
        result["fusion_result"] = fused
        print("  [Pipeline] ✅ Step 8 — Fusion complete.", flush=True)
    except Exception as exc:
        print(f"  [Pipeline] ⚠️  Step 8 error: {exc}", flush=True)
        import traceback; traceback.print_exc()

    # ── Step 9: Domain Output ──────────────────────────────────────────────
    if not skip_domain_output and fused and "domain_output" in tool_calls:
        print("\n  [Pipeline] ▶ Step 9 — Domain Output (Final Summary)", flush=True)
        try:
            from domain_output import generate_output
            domain_result = generate_output(
                fused=fused,
                user_question=user_question,
                mode=mode,
            )
            result["domain_output"] = domain_result
            print("  [Pipeline] ✅ Step 9 — Domain output complete.", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Step 9 error: {exc}", flush=True)
            import traceback; traceback.print_exc()
    else:
        print("  [Pipeline] ⚠️  Step 9 (Domain Output) skipped.", flush=True)

    # ── Finalize & Disk Space Cleanup ───────────────────────────────────────
    # Clean up temporary downloaded video if it was an ingested playlist item to preserve disk space
    if is_playlist_item and local_video_path and os.path.exists(local_video_path):
        if "chorus_yt_" in os.path.basename(local_video_path):
            try:
                os.remove(local_video_path)
                print(f"  [Pipeline] 🧹 Cleaned up temporary video file: {os.path.basename(local_video_path)}", flush=True)
            except Exception:
                pass

    result["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"\n{'═'*60}", flush=True)
    print(f"  [Pipeline] ✅ Pipeline complete!", flush=True)
    print(f"  [Pipeline] Mode: {mode.upper()} | Halted: {result['pipeline_halted']}", flush=True)
    print(f"{'═'*60}\n", flush=True)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PLAYLIST / MULTI-VIDEO BATCH ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

def _collect_multimodal_evidence(analyzed_videos: List[dict]) -> str:
    """
    Combine ASR transcripts + VL visual observations across all successfully
    analyzed videos into one compact text block for the Text/Domain Brain.
    Each video gets a bounded budget so a huge batch still fits the context
    window.
    """
    parts: List[str] = []
    for i, v in enumerate(analyzed_videos, 1):
        info   = v.get("playlist_entry") or {}
        title  = info.get("title") or v.get("source_uri") or f"Video {i}"
        vid    = info.get("video_id") or ""
        header = f"### VIDEO {i}: {title}" + (f" (id={vid})" if vid else "")

        asr = v.get("asr_result") or {}
        transcript = (
            asr.get("full_transcript")
            or asr.get("transcript")
            or asr.get("text")
            or ""
        ).strip()

        vl = v.get("vl_output") or ""
        if isinstance(vl, str):
            vl_text = vl.strip()
        else:
            vl_text = json.dumps(vl, ensure_ascii=False, default=str)

        scenes = (v.get("scene_result") or {}).get("scenes") or []
        seg_line = f"[{len(scenes)} scene(s) detected]" if scenes else ""

        block = header + "\n"
        if seg_line:
            block += f"Scene segmentation: {seg_line}\n"
        kf = v.get("key_features") or {}
        if kf.get("key_features_summary"):
            block += "KEY FEATURES (Worker pre-extracted):\n" + "\n".join(f"- {s}" for s in kf["key_features_summary"]) + "\n"
        block += f"VISUAL OBSERVATIONS (VL agent):\n{vl_text[:1500] if vl_text else '(no visual analysis available)'}\n"
        block += f"TRANSCRIPT (Whisper ASR):\n{transcript[:3000] if transcript else '(no transcript available)'}\n"
        parts.append(block)

    return "\n".join(parts)


def _heuristic_master_summary(analyzed_videos: List[dict], playlist_url: str) -> dict:
    """
    Deterministic fallback synthesis used when the Text Brain is unavailable
    (model not installed / fast mode without GPU). Aggregates raw statistics
    and first-line topic hints per video — never calls any model.
    """
    per_video = []
    all_topics: List[str] = []
    for i, v in enumerate(analyzed_videos, 1):
        info = v.get("playlist_entry") or {}
        asr  = v.get("asr_result") or {}
        transcript = (asr.get("full_transcript") or "").strip()
        first_line = transcript.split("\n")[0][:200] if transcript else ""
        if first_line:
            all_topics.append(first_line)
        per_video.append({
            "index": i,
            "video_id": info.get("video_id"),
            "title": info.get("title"),
            "words": asr.get("word_count", 0),
            "language": asr.get("language"),
            "topic_hint": first_line or (v.get("vl_output") or "")[:200] or info.get("title") or "(no signal)",
        })

    return {
        "master_summary": (
            f"Batch analysis of {len(analyzed_videos)} video(s) from playlist "
            f"{playlist_url}. Heuristic synthesis: "
            + " | ".join(f"#{p['index']} ({p['title']}): {p['topic_hint']}" for p in per_video)
        ),
        "per_video_topics": per_video,
        "aggregate_stats": {
            "videos_analyzed": len(analyzed_videos),
            "total_transcript_words": sum(p["words"] for p in per_video),
            "languages": sorted({p["language"] for p in per_video if p["language"]}),
        },
        "cross_video_insights": (
            f"Analyzed {len(analyzed_videos)} video(s) from playlist. Titles and scene cuts cataloged."
        ),
        "synthesis_method": "heuristic_fallback",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _run_master_synthesis(
    analyzed_videos: List[dict],
    playlist_url: str,
    user_question: str,
    mode: str,
    use_text_brain: bool = True,
) -> dict:
    """
    Multi-video master synthesis: feed the combined ASR transcripts + VL
    visual observations of ALL analyzed videos to the Text/Domain Brain
    (domain_output._call_text_brain → Qwen2.5-7B) and produce an aggregated
    executive summary, phase/topic progression, and cross-video insights.
    Falls back to a deterministic heuristic summary on any failure.
    """
    evidence = _collect_multimodal_evidence(analyzed_videos)
    if not evidence.strip():
        return _heuristic_master_summary(analyzed_videos, playlist_url)

    if not use_text_brain:
        return _heuristic_master_summary(analyzed_videos, playlist_url)

    system_prompt = (
        "You are the Master Synthesis Agent for the Chorus multi-video "
        "intelligence pipeline. You receive per-video visual observations "
        "(VL agent) and speech transcripts (Whisper ASR) for several videos "
        "from the SAME playlist. Synthesize ACROSS videos. Return ONLY valid "
        "JSON with exactly these keys:\n"
        '''{"master_summary": "aggregated executive summary of the whole "
        "playlist batch (one dense paragraph)", "
        "phase_topic_progression": ["phase/topic 1", "phase/topic 2", ...], "
        "cross_video_insights": ["insight 1", "insight 2", ...], "
        "content_type": "short classification e.g. educational course, "
        "vlog series, news compilation", "
        "recommended_next_steps": ["action 1", ...]}'''
    )
    user_content = (
        f"=== PLAYLIST ===\n{playlist_url}\n\n"
        f"=== VIDEOS ANALYZED: {len(analyzed_videos)} ===\n\n"
        f"=== COMBINED MULTIMODAL EVIDENCE ===\n{evidence[:24000]}\n\n"
        f"User question: {user_question}"
    )

    try:
        from domain_output import _call_text_brain
        synthesis = _call_text_brain(system_prompt, user_content)
        if not isinstance(synthesis, dict) or synthesis.get("error") or synthesis.get("status") == "failure":
            raise RuntimeError(
                synthesis.get("message") or synthesis.get("error", "empty synthesis") if isinstance(synthesis, dict)
                else "empty synthesis"
            )
        synthesis.setdefault("synthesis_method", "text_brain")
        synthesis.setdefault("generated_at", datetime.datetime.utcnow().isoformat() + "Z")
        # Guarantee the required keys exist so downstream consumers can rely on them
        synthesis.setdefault("master_summary", synthesis.get("raw_output", ""))
        synthesis.setdefault("phase_topic_progression", [])
        synthesis.setdefault("cross_video_insights", [])
        return synthesis
    except Exception as exc:
        print(f"  [MasterSynthesis] ⚠️  Text Brain synthesis failed: {exc}", flush=True)
        print("  [MasterSynthesis] ℹ️  Falling back to heuristic summary.", flush=True)
        fallback = _heuristic_master_summary(analyzed_videos, playlist_url)
        fallback["synthesis_error"] = str(exc)
        return fallback


def _build_per_video_summary(video_result: dict, user_question: str) -> dict:
    """
    Build a comprehensive individual summary and answer for a single video in a playlist.
    Extracts key features, ASR transcript, and VL visual observations.
    """
    entry = video_result.get("playlist_entry") or {}
    idx = entry.get("index", 1)
    vid = entry.get("video_id") or ""
    title = entry.get("title") or video_result.get("source_uri") or f"Video {idx}"
    url = entry.get("url") or video_result.get("source_uri") or ""

    if video_result.get("status") == "failed" or video_result.get("pipeline_halted"):
        err = video_result.get("error") or video_result.get("halt_reason") or "Video processing failed"
        return {
            "index": idx,
            "video_id": vid,
            "title": title,
            "url": url,
            "status": "failed",
            "error": err,
            "summary": f"Video #{idx} ('{title}') processing halted/failed: {err}",
            "detailed_answer": f"Unable to analyze Video #{idx} due to error: {err}",
            "key_features_summary": [],
            "topics_covered": [],
        }

    # Extract key features
    kf = video_result.get("key_features") or {}
    scene_res = video_result.get("scene_result") or {}
    duration_s = kf.get("duration_s") or scene_res.get("duration_s") or 0.0
    scene_count = kf.get("scene_count") or scene_res.get("scene_count") or len(scene_res.get("scenes", []))
    kf_summary = kf.get("key_features_summary") or []
    kf_timestamps = kf.get("keyframe_timestamps") or []

    # Extract ASR
    asr = video_result.get("asr_result") or {}
    transcript = (asr.get("full_transcript") or asr.get("transcript") or asr.get("text") or "").strip()
    word_count = asr.get("word_count") or (len(transcript.split()) if transcript else 0)
    language = asr.get("language") or "en"

    # Extract VL output
    vl = video_result.get("vl_output") or ""
    if isinstance(vl, dict):
        vl_desc = vl.get("description") or vl.get("analysis") or json.dumps(vl, ensure_ascii=False)
    else:
        vl_desc = str(vl).strip()

    # Build per-video deep summary
    summary_parts = []
    summary_parts.append(f"Title: {title}")
    summary_parts.append(f"Duration: {round(duration_s, 1)}s | Scenes: {scene_count} | Language: {language}")

    if kf_summary:
        summary_parts.append("Key Multimodal Characteristics:")
        for feat in kf_summary:
            summary_parts.append(f"  • {feat}")

    if vl_desc and vl_desc != "(no visual analysis available)":
        summary_parts.append(f"Visual Analysis (VL Brain):\n{vl_desc[:1200]}")

    if transcript:
        preview = transcript[:800].replace("\n", " ")
        summary_parts.append(f"Spoken Content ({word_count} words):\n{preview}...")

    video_summary = "\n\n".join(summary_parts)

    # Detailed answer answering user question for this video
    answer_parts = []
    answer_parts.append(f"Analysis for Video #{idx} ('{title}'):")
    if transcript:
        first_lines = " ".join([l.strip() for l in transcript.split("\n") if len(l.strip()) > 10][:4])
        answer_parts.append(f"Key Concepts & Spoken Explanation: {first_lines}")
    if vl_desc and vl_desc != "(no visual analysis available)":
        answer_parts.append(f"Visual Presentation & Demonstrations: {vl_desc[:500]}")
    if not transcript and (not vl_desc or vl_desc == "(no visual analysis available)"):
        answer_parts.append(f"Cataloged {scene_count} scene transitions across {round(duration_s, 1)}s of video.")
    detailed_answer = "\n".join(answer_parts)

    # Topic extraction
    topics = []
    if title and title != "Untitled":
        topics.append(title)
    if transcript:
        for line in transcript.split("\n"):
            line = line.strip()
            if 15 < len(line) < 100 and not any(line in t for t in topics):
                topics.append(line)
            if len(topics) >= 5:
                break

    return {
        "index": idx,
        "video_id": vid,
        "title": title,
        "url": url,
        "duration_seconds": round(duration_s, 2),
        "scene_count": scene_count,
        "keyframe_timestamps": kf_timestamps,
        "key_features_summary": kf_summary,
        "word_count": word_count,
        "language": language,
        "summary": video_summary,
        "detailed_answer": detailed_answer,
        "topics_covered": topics,
        "status": "completed",
    }


def run_playlist_pipeline(
    url: str,
    max_playlist_videos: Optional[int] = 0,
    max_concurrent: int = 2,
    batch_size: Optional[int] = None,
    output_file: str = "playlist_analysis_results.json",
    user_question: str = "Summarize the topics covered across these videos.",
    mode: str = "general",
    governance_approved: bool = False,
    skip_vl: bool = False,
    skip_asr: bool = False,
    skip_dedup: bool = False,
    fast_mode: bool = False,
) -> dict:
    """
    Generalized Playlist & Multi-Video Batch Orchestrator.

    Resolves the FULL playlist catalog (e.g. all 94 videos), then processes
    all videos batch-by-batch using concurrent worker pools. For every video,
    pre-extracts key features (scenes, keyframes, audio density, video composition),
    invokes the VL Vision Agent and ASR transcription, generates individual
    summaries and answers one-by-one, cleans up temporary downloads, and saves
    progressive checkpoints. Finally, runs a cross-video master synthesis across
    all analyzed videos.

    Parameters
    ----------
    url                 : Playlist URL (youtube.com/playlist?list=...).
    max_playlist_videos : Max number of videos to analyze (default: 0 = ALL videos in playlist).
    max_concurrent      : Worker pool concurrency cap (default: 2).
    batch_size          : Videos per batch chunk (default: 2).
    output_file         : Checkpoint and final results file (default: playlist_analysis_results.json).
    user_question       : User's query/prompt for each video and the master summary.
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"
    t0 = time.time()

    print(f"\n{'█'*60}", flush=True)
    print("  [PlaylistBatch] 📺 Chorus Generalized Playlist Batch Pipeline", flush=True)
    print(f"{'█'*60}\n", flush=True)

    # ── Step 1: Resolve FULL playlist catalog (metadata only) ─────────────
    print("  [PlaylistBatch] ▶ Resolving full playlist catalog…", flush=True)
    from chorus_input import resolve_playlist

    resolved = resolve_playlist(url)
    if not resolved:
        return {
            "batch_type":            "playlist_batch",
            "playlist_url":          url,
            "total_playlist_videos": 0,
            "playlist_manifest":     None,
            "max_playlist_videos":   max_playlist_videos,
            "max_concurrent":        max_concurrent,
            "analyzed_videos":       [],
            "per_video_summaries":   [],
            "failed_videos": [{
                "index": 0, "url": url, "title": None,
                "error": "Playlist resolution returned no videos "
                         "(yt-dlp failure, private playlist, or yt-dlp missing).",
            }],
            "master_summary":        None,
            "started_at":            started_at,
            "completed_at":          datetime.datetime.utcnow().isoformat() + "Z",
            "elapsed_seconds":       round(time.time() - t0, 2),
        }

    total_playlist_videos = len(resolved)
    print(f"  [PlaylistBatch] ✅ Catalog: {total_playlist_videos} video(s) detected in playlist.", flush=True)

    # ── Step 2: Select video scope (Default: ALL videos) ───────────────────
    if max_playlist_videos is None or max_playlist_videos <= 0:
        selected = list(resolved)
        print(f"  [PlaylistBatch] 🎯 Target Scope: Processing ALL {len(selected)} video(s) in playlist.", flush=True)
    else:
        selected = resolved[:max_playlist_videos]
        print(f"  [PlaylistBatch] 🎯 Target Scope: Processing first {len(selected)} of "
              f"{total_playlist_videos} video(s) (capped by --max-playlist-videos).", flush=True)

    # ── Step 3: Batch-Wise Concurrent Worker Pool ─────────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed

    effective_batch_size = max(1, batch_size or max_concurrent or 2)
    effective_workers = max(1, max_concurrent or 2)
    total_batches = (len(selected) + effective_batch_size - 1) // effective_batch_size

    print(f"  [PlaylistBatch] 🚀 Batch Architecture: {len(selected)} video(s) across {total_batches} batch(es) "
          f"(Batch Size: {effective_batch_size}, Concurrency: {effective_workers} worker(s)).", flush=True)

    def _worker_task(idx: int, entry: dict) -> dict:
        v_url   = entry.get("url") or ""
        v_title = entry.get("title") or "Untitled"
        v_id    = entry.get("video_id") or ""

        print(f"\n{'═'*60}", flush=True)
        print(f"  [PlaylistWorker] ▶ [Worker] Starting Video {idx}/{len(selected)}: {v_title}", flush=True)
        print(f"  [PlaylistWorker]   URL: {v_url}", flush=True)
        print(f"{'═'*60}\n", flush=True)

        try:
            clean_url = f"https://www.youtube.com/watch?v={v_id}" if (v_id and len(v_id) == 11) else v_url
            video_result = run_full_pipeline(
                url=clean_url,
                source_type="youtube",
                user_question=user_question,
                mode=mode,
                governance_approved=governance_approved,
                skip_vl=skip_vl,
                skip_asr=skip_asr,
                skip_domain_output=True,   # Text Brain runs master synthesis across batch
                skip_dedup=skip_dedup,
                fast_mode=fast_mode,
                is_playlist_item=True,
                video_title=v_title,
                video_id=v_id,
                playlist_index=idx,
                playlist_total=len(selected),
            )
            video_result["playlist_entry"] = {
                "index": idx,
                "url":   v_url,
                "title": v_title,
                "video_id": v_id,
            }
            video_result["status"] = "failed" if video_result.get("pipeline_halted") else "ok"
            if video_result["status"] == "failed":
                video_result["error"] = video_result.get("halt_reason") or "pipeline_halted"
                print(f"  [PlaylistWorker] ⛔ Video {idx} halted: {video_result['error']}", flush=True)
            else:
                print(f"  [PlaylistWorker] ✅ Video {idx} complete.", flush=True)
            return video_result

        except Exception as exc:
            print(f"  [PlaylistWorker] ⚠️  Video {idx} FAILED: {exc}", flush=True)
            import traceback; traceback.print_exc()
            return {
                "status": "failed",
                "error": str(exc),
                "source_uri": v_url,
                "playlist_entry": {
                    "index": idx, "url": v_url, "title": v_title, "video_id": v_id,
                },
            }

    all_analyzed_videos: List[dict] = []
    per_video_summaries: List[dict] = []
    failed_videos: List[dict] = []

    # Execute Batch-by-Batch
    for batch_num in range(1, total_batches + 1):
        start_idx = (batch_num - 1) * effective_batch_size
        end_idx = min(start_idx + effective_batch_size, len(selected))
        batch_slice = selected[start_idx:end_idx]

        print(f"\n{'═'*60}", flush=True)
        print(f"  [PlaylistBatch] 📦 BATCH {batch_num}/{total_batches}: Processing Videos {start_idx + 1} to {end_idx} (of {len(selected)})", flush=True)
        print(f"{'═'*60}\n", flush=True)

        batch_results_by_idx = {}
        workers_for_batch = min(effective_workers, len(batch_slice))

        with ThreadPoolExecutor(max_workers=workers_for_batch) as executor:
            future_to_idx = {
                executor.submit(_worker_task, start_idx + offset + 1, entry): start_idx + offset + 1
                for offset, entry in enumerate(batch_slice)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res = future.result()
                    batch_results_by_idx[idx] = res
                except Exception as pool_exc:
                    entry = selected[idx - 1]
                    batch_results_by_idx[idx] = {
                        "status": "failed",
                        "error": str(pool_exc),
                        "source_uri": entry.get("url"),
                        "playlist_entry": {
                            "index": idx, "url": entry.get("url"), "title": entry.get("title"), "video_id": entry.get("video_id"),
                        },
                    }

        # Order preservation & individual summary recording for this batch
        for idx in range(start_idx + 1, end_idx + 1):
            res = batch_results_by_idx.get(idx)
            if not res:
                continue
            all_analyzed_videos.append(res)
            summary_entry = _build_per_video_summary(res, user_question)
            res["video_summary"] = summary_entry
            per_video_summaries.append(summary_entry)

            if res.get("status") == "failed":
                entry = selected[idx - 1]
                failed_videos.append({
                    "index": idx,
                    "url": entry.get("url"),
                    "title": entry.get("title"),
                    "error": res.get("error", "unknown error"),
                })
                print(f"  [PlaylistBatch] ❌ Video {idx}/{len(selected)} ({entry.get('title')}) recorded as failed.", flush=True)
            else:
                print(f"  [PlaylistBatch] ✅ Video {idx}/{len(selected)} ({summary_entry.get('title')}): Summary & answers saved.", flush=True)

        # Progressive Checkpoint Saving after each batch
        if output_file:
            try:
                checkpoint_payload = {
                    "batch_type": "playlist_batch_checkpoint",
                    "playlist_url": url,
                    "total_playlist_videos": total_playlist_videos,
                    "total_selected": len(selected),
                    "batch_size": effective_batch_size,
                    "completed_batches": batch_num,
                    "total_batches": total_batches,
                    "videos_processed_so_far": len(all_analyzed_videos),
                    "successful_so_far": len([v for v in all_analyzed_videos if v.get("status") != "failed"]),
                    "failed_so_far": len(failed_videos),
                    "per_video_summaries": per_video_summaries,
                    "failed_videos": failed_videos,
                    "checkpoint_saved_at": datetime.datetime.utcnow().isoformat() + "Z",
                }
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(checkpoint_payload, f, indent=2, ensure_ascii=False, default=str)
                print(f"  [PlaylistBatch] 💾 Checkpoint updated ({len(all_analyzed_videos)}/{len(selected)} videos saved to {output_file})", flush=True)
            except Exception as chk_exc:
                print(f"  [PlaylistBatch] ⚠️ Checkpoint save warning: {chk_exc}", flush=True)

    # ── Step 4: Multi-Video Master Synthesis (Across All Videos) ──────────
    successful = [
        v for v in all_analyzed_videos if v.get("status") != "failed"
    ]
    print(f"\n{'─'*60}", flush=True)
    print(f"  [PlaylistBatch] ▶ Master Synthesis across {len(successful)} "
          f"successfully analyzed video(s)…", flush=True)

    master = _run_master_synthesis(
        analyzed_videos=successful,
        playlist_url=url,
        user_question=user_question,
        mode=mode,
        use_text_brain=True,
    )

    completed_at = datetime.datetime.utcnow().isoformat() + "Z"
    elapsed = round(time.time() - t0, 2)

    # Formatted Console Presentation: One-by-One video summaries
    print(f"\n{'█'*60}", flush=True)
    print(f"  [PlaylistBatch] 📋 PER-VIDEO SUMMARIES & ANSWERS ({len(per_video_summaries)} videos)", flush=True)
    print(f"{'█'*60}", flush=True)
    for pvs in per_video_summaries:
        print(f"\n--- [Video #{pvs['index']}] {pvs.get('title')} ---", flush=True)
        print(f"  URL: {pvs.get('url')}", flush=True)
        print(f"  Duration: {pvs.get('duration_seconds')}s | Scenes: {pvs.get('scene_count')} | Words: {pvs.get('word_count')}", flush=True)
        if pvs.get('key_features_summary'):
            print(f"  Key Features: {'; '.join(pvs['key_features_summary'][:2])}", flush=True)
        if pvs.get('topics_covered'):
            print(f"  Topics: {', '.join(pvs['topics_covered'][:3])}", flush=True)
        first_sum_line = pvs.get('summary', '').split('\n')[0] if pvs.get('summary') else ""
        print(f"  Summary: {first_sum_line}", flush=True)
        print(f"  Answer: {pvs.get('detailed_answer', '')[:250]}...", flush=True)

    exec_summary = (
        master.get("master_summary")
        if isinstance(master, dict)
        else str(master)
    )

    final_result = {
        "batch_type":            "playlist_batch",
        "playlist_url":          url,
        "total_playlist_videos": total_playlist_videos,
        "playlist_manifest": {
            "playlist_url": url,
            "total_videos": total_playlist_videos,
            "videos": resolved[:100],   # full catalog preserved (display cap)
        },
        "max_playlist_videos":   max_playlist_videos if max_playlist_videos and max_playlist_videos > 0 else "all",
        "batch_size":            effective_batch_size,
        "total_batches":         total_batches,
        "analyzed_videos":       all_analyzed_videos,
        "per_video_summaries":   per_video_summaries,
        "failed_videos":         failed_videos,
        "master_summary":        master,
        "domain_output": {
            "status": "success",
            "final_output": {
                "executive_summary": exec_summary,
                "phase_topic_progression": master.get("phase_topic_progression", []) if isinstance(master, dict) else [],
                "cross_video_insights": master.get("cross_video_insights", []) if isinstance(master, dict) else [],
                "total_playlist_videos": total_playlist_videos,
                "analyzed_count": len(successful),
                "per_video_summaries": per_video_summaries,
            }
        },
        "started_at":            started_at,
        "completed_at":          completed_at,
        "elapsed_seconds":       elapsed,
    }

    # Save final complete results
    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(final_result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n  [PlaylistBatch] 💾 Final complete results saved to {output_file}", flush=True)
        except Exception as save_exc:
            print(f"\n  [PlaylistBatch] ⚠️ Failed saving final results to {output_file}: {save_exc}", flush=True)

    print(f"\n{'█'*60}", flush=True)
    print("  [PlaylistBatch] ✅ Playlist processing complete!", flush=True)
    print(f"  [PlaylistBatch] Catalog: {total_playlist_videos} | Analyzed: "
          f"{len(successful)} ok / {len(failed_videos)} failed | "
          f"Elapsed: {elapsed}s", flush=True)
    print(f"{'█'*60}\n", flush=True)

    return final_result


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY: original dedup-only pipeline (backward compatible)
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    dedup_kwargs: dict,
    quality_gate_payload: Optional[dict] = None,
) -> dict:
    """
    Original pipeline: Duplication Check → Quality Gate only.
    Kept for backward compatibility with existing tests and scripts.
    """
    from duplication_check import run_duplication_check
    from quality_gate      import run_quality_gate

    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    print("[pipeline_runner] Step 3 — Running duplication check …", flush=True)
    dedup_result = run_duplication_check(**dedup_kwargs)

    if dedup_result["halt_pipeline"]:
        print(f"[pipeline_runner] ⛔ Pipeline HALTED — {dedup_result['halt_reason']}", flush=True)
        return {
            "pipeline_halted":     True,
            "halt_reason":         dedup_result["halt_reason"],
            "halt_step":           "duplication_check",
            "started_at":          started_at,
            "completed_at":        datetime.datetime.utcnow().isoformat() + "Z",
            "duplication_result":  dedup_result,
            "quality_gate_result": None,
        }

    print("[pipeline_runner] ✅ Duplication check passed — no duplicates found.", flush=True)

    quality_gate_result = None
    if quality_gate_payload is not None:
        print("[pipeline_runner] Step 2 — Running quality gate …", flush=True)
        quality_gate_result = run_quality_gate(quality_gate_payload)
        verdict = quality_gate_result.get("overall_verdict", "UNKNOWN")
        print(f"[pipeline_runner] Quality gate verdict: {verdict}", flush=True)
    else:
        print("[pipeline_runner] Step 2 — No timeline payload; quality gate skipped.", flush=True)

    return {
        "pipeline_halted":     False,
        "halt_reason":         None,
        "halt_step":           None,
        "started_at":          started_at,
        "completed_at":        datetime.datetime.utcnow().isoformat() + "Z",
        "duplication_result":  dedup_result,
        "quality_gate_result": quality_gate_result,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser():
    p = argparse.ArgumentParser(
        description="Chorus Pipeline Runner — Full Phase 1 General Mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pipeline_runner.py --video clip.mp4 --pretty\n"
            "  python pipeline_runner.py --video clip.mp4 --question \"What happens?\" --pretty\n"
            "  python pipeline_runner.py --video clip.mp4 --mode cyber --pretty\n"
            "  python pipeline_runner.py --video clip.mp4 --skip-asr --pretty\n"
            "  # Legacy dedup-only mode:\n"
            "  python pipeline_runner.py --legacy --source-type local_upload "
            "--video clip.mp4 --timeline-input timeline.json --pretty\n"
        ),
    )
    # Full pipeline args
    p.add_argument("--video",            metavar="PATH", default=None,
                   help="Path to local video file.")
    p.add_argument("--url",              metavar="URL",  default=None,
                   help="YouTube or RTSP URL.")
    p.add_argument("--question",         default="Summarize what happens in this video.",
                   help="User question/prompt for the analysis.")
    p.add_argument("--mode",             default="general", choices=["general", "cyber"],
                   help="Pipeline mode (default: general).")
    p.add_argument("--governance",       action="store_true", dest="governance_approved",
                   help="Mark governance as approved (enables face_reid in cyber mode).")
    p.add_argument("--skip-vl",          action="store_true", dest="skip_vl",
                   help="Skip VL vision analysis.")
    p.add_argument("--skip-asr",         action="store_true", dest="skip_asr",
                   help="Skip ASR transcription.")
    p.add_argument("--skip-output",      action="store_true", dest="skip_domain_output",
                   help="Skip final domain output (return raw fusion only).")
    p.add_argument("--skip-dedup",       action="store_true", dest="skip_dedup",
                   help="Skip duplication check gate.")
    p.add_argument("--fast",             action="store_true", dest="fast_mode",
                   help="Fast routing: skip heavy 7B LoRA loading, use rule-based orchestrator.")
    p.add_argument("--max-playlist-videos", type=int, default=0,
                   dest="max_playlist_videos", metavar="N",
                   help="Playlist mode: maximum number of videos to analyze from the playlist "
                        "(default: 0 = ALL videos in playlist, e.g. all 94). Set a number > 0 "
                        "only if you want to cap the processing.")
    p.add_argument("--batch-size", type=int, default=2,
                   dest="batch_size", metavar="N",
                   help="Batch size for playlist processing (default: 2). Videos are processed "
                        "batch-by-batch to optimize memory and disk space.")
    p.add_argument("--max-concurrent", "--workers", type=int, default=2,
                   dest="max_concurrent", metavar="N",
                   help="Worker pool concurrency cap: maximum number of videos processed "
                        "concurrently in playlist batch mode (default: 2).")
    p.add_argument("--save-output", "--output-file", default="playlist_analysis_results.json",
                   dest="output_file", metavar="PATH",
                   help="File path to save progressive checkpoints and final analysis results (default: playlist_analysis_results.json).")

    # Legacy mode
    p.add_argument("--legacy",           action="store_true",
                   help="Run original dedup+quality-gate only pipeline.")
    p.add_argument("--source-type",      default="local_upload",
                   choices=("youtube", "local_upload", "live_rtsp"),
                   dest="source_type",
                   help="[Legacy] Source type for dedup check.")
    p.add_argument("--timeline-input",   metavar="PATH", dest="timeline_input",
                   help="[Legacy] Path to fused timeline JSON for quality gate.")

    # Legacy dedup options
    p.add_argument("--algo",             default="phash",
                   choices=("phash", "dhash", "ahash", "whash"))
    p.add_argument("--threshold",        type=int, default=None)
    p.add_argument("--dedup-mode",       default="consecutive",
                   choices=("consecutive", "global"), dest="dedup_mode")
    p.add_argument("--sample-rate",      type=float, default=1.0, dest="sample_rate")
    p.add_argument("--scene-threshold",  type=int, default=15, dest="scene_threshold")
    p.add_argument("--max-seconds",      type=float, default=300.0, dest="max_seconds")
    p.add_argument("--window-seconds",   type=float, default=10.0,  dest="window_seconds")
    p.add_argument("--rtsp-retries",     type=int,   default=10, dest="rtsp_retries")
    p.add_argument("--video-id",         default=None, dest="video_id")
    p.add_argument("--no-hashes",        action="store_true", dest="no_hashes")
    p.add_argument("--pretty",           action="store_true")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()

    if args.legacy:
        # ── Legacy mode ────────────────────────────────────────────────────
        dedup_kwargs: dict = {
            "source_type":            args.source_type,
            "algo":                   args.algo,
            "threshold":              args.threshold,
            "dedup_mode":             args.dedup_mode,
            "sample_rate":            args.sample_rate,
            "scene_change_threshold": args.scene_threshold,
            "max_seconds":            args.max_seconds,
            "window_seconds":         args.window_seconds,
            "rtsp_max_retries":       args.rtsp_retries,
            "video_id":               args.video_id,
        }
        if args.source_type == "local_upload":
            if not args.video:
                parser.error("--video is required for --source-type=local_upload")
            dedup_kwargs["video_path"] = args.video
        else:
            if not args.url:
                parser.error("--url is required for youtube / live_rtsp")
            dedup_kwargs["url"] = args.url

        quality_gate_payload = None
        if args.timeline_input:
            with open(args.timeline_input, "r", encoding="utf-8-sig") as f:
                quality_gate_payload = json.load(f)

        result = run_pipeline(
            dedup_kwargs         = dedup_kwargs,
            quality_gate_payload = quality_gate_payload,
        )
        if args.no_hashes and result.get("duplication_result"):
            result["duplication_result"].pop("hashes", None)
    else:
        # ── Full Phase 1 pipeline ──────────────────────────────────────────
        if not args.video and not args.url:
            parser.error("Provide --video (local file) or --url (YouTube/RTSP).")

        # ── Playlist / multi-video batch mode auto-detection ──────────────
        from chorus_input import is_playlist_url

        if args.url and not args.video and is_playlist_url(args.url):
            result = run_playlist_pipeline(
                url                 = args.url,
                max_playlist_videos = args.max_playlist_videos,
                max_concurrent      = args.max_concurrent,
                batch_size          = args.batch_size,
                output_file         = args.output_file,
                user_question       = args.question,
                mode                = args.mode,
                governance_approved = args.governance_approved,
                skip_vl             = args.skip_vl,
                skip_asr            = args.skip_asr,
                skip_dedup          = args.skip_dedup,
                fast_mode           = args.fast_mode,
            )
        else:
            result = run_full_pipeline(
                video_path          = args.video,
                url                 = args.url,
                source_type         = args.source_type,
                user_question       = args.question,
                mode                = args.mode,
                governance_approved = args.governance_approved,
                skip_vl             = args.skip_vl,
                skip_asr            = args.skip_asr,
                skip_domain_output  = args.skip_domain_output,
                skip_dedup          = args.skip_dedup,
                fast_mode           = args.fast_mode,
                max_playlist_videos = args.max_playlist_videos,
                max_concurrent      = args.max_concurrent,
                batch_size          = args.batch_size,
                output_file         = args.output_file,
            )
            if args.output_file and not result.get("batch_type"):
                try:
                    with open(args.output_file, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2 if args.pretty else None, ensure_ascii=False, default=str)
                    print(f"  [Pipeline] 💾 Single video analysis saved to {args.output_file}", flush=True)
                except Exception as save_exc:
                    print(f"  [Pipeline] ⚠️ Failed saving single video output to {args.output_file}: {save_exc}", flush=True)

    # Strip large binary-ish fields from CLI output for readability
    if result.get("vl_output") and len(str(result["vl_output"])) > 2000:
        result["vl_output"] = result["vl_output"][:2000] + "... [truncated]"

    # Playlist batch: truncate bulky per-video fields for readable final JSON
    if result.get("batch_type") == "playlist_batch":
        for _v in result.get("analyzed_videos") or []:
            if isinstance(_v, dict) and _v.get("vl_output") and len(str(_v["vl_output"])) > 2000:
                _v["vl_output"] = str(_v["vl_output"])[:2000] + "... [truncated]"

    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False,
                     default=str))
    sys.exit(1 if result.get("pipeline_halted") else 0)
