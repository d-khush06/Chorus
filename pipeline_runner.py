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

Usage (CLI)
-----------
  python pipeline_runner.py --video clip.mp4 --question "Summarize this" --pretty
  python pipeline_runner.py --video clip.mp4 --mode cyber --pretty
  python pipeline_runner.py --url "https://youtu.be/ID" --question "What is this?"

  # Legacy: dedup-only mode (original pipeline_runner behaviour)
  python pipeline_runner.py --legacy --source-type local_upload --video clip.mp4 \\
      --timeline-input timeline.json --pretty
"""

import json
import sys
import os
import argparse
import datetime
from typing import Optional

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    model, tokenizer = load_orchestrator()

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
            "reasoning_summary": "Rule-based routing (orchestrator model not available).",
            "routing_method": "rule_based",
        }

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

    Returns
    -------
    Full pipeline result dict.
    """
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
    }

    # ── Resolve video path ─────────────────────────────────────────────────
    local_video_path = video_path
    if url and not local_video_path:
        print(f"  [Pipeline] URL source detected — Source: {url}", flush=True)
        print(f"  [Pipeline] ℹ️  URL-based sources: use chorus_input.py to extract frames first.", flush=True)

    # ── Step 3: Duplication Check ──────────────────────────────────────────
    print("\n  [Pipeline] ▶ Step 3 — Duplication Check", flush=True)
    dedup_mod, dedup_ok = _try_import("duplication_check", "Duplication Check")
    if not skip_dedup and dedup_ok and local_video_path and os.path.exists(local_video_path):
        dedup_kwargs = {
            "source_type": source_type,
            "video_path": local_video_path,
        }
        dedup_result = dedup_mod.run_duplication_check(**dedup_kwargs)
        result["duplication_result"] = dedup_result
        if dedup_result.get("halt_pipeline"):
            result["pipeline_halted"] = True
            result["halt_reason"]     = dedup_result.get("halt_reason", "Duplicate detected")
            result["halt_step"]       = "duplication_check"
            result["completed_at"]    = datetime.datetime.utcnow().isoformat() + "Z"
            print(f"  [Pipeline] ⛔ HALT — {result['halt_reason']}", flush=True)
            return result
        print("  [Pipeline] ✅ Step 3 — No duplicates.", flush=True)
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
    )
    result["routing_decision"] = routing
    mode = routing.get("mode", mode)  # Use orchestrator's confirmed mode
    tool_calls = routing.get("tool_calls", [])
    print(f"  [Pipeline] ✅ Step 5 — Mode: {mode.upper()} | Tools: {tool_calls}", flush=True)

    # Release orchestrator VRAM before loading perception models
    unload_orchestrator()

    # ── Step 7: Scene Segmentation ─────────────────────────────────────────
    scenes = []
    if "scene_segmentation" in tool_calls and local_video_path and os.path.exists(local_video_path):
        print("\n  [Pipeline] ▶ Step 7 — Scene Segmentation", flush=True)
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
                print(f"  [Pipeline] ✅ Step 7 — {len(scenes)} scene(s) detected.", flush=True)
            except Exception as exc:
                print(f"  [Pipeline] ⚠️  Step 7 error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 7 skipped.", flush=True)

    # ── Step 6 (VL): Visual Analysis ──────────────────────────────────────
    vl_output_text = None
    if not skip_vl and "perception_agent" in tool_calls and local_video_path:
        print("\n  [Pipeline] ▶ Step 6 — Vision Analysis (VL Brain)", flush=True)
        try:
            from chorus_input import LocalAdapter
            from run_vl_agent import run_vision_analysis

            print("  [Pipeline] Extracting frames…", flush=True)
            adapter = LocalAdapter()
            payload = adapter.process(local_video_path, "local_video")
            frames = payload.frames

            if frames:
                print(f"  [Pipeline] Analyzing {len(frames)} frames…", flush=True)
                meta = {
                    "ai_generated_flag": manipulation_verdict == "FLAGGED",
                    "deepfake_flag": manipulation_verdict == "FLAGGED",
                }
                vl_output_text = run_vision_analysis(frames, user_question, meta)
                result["vl_output"] = vl_output_text
                print("  [Pipeline] ✅ Step 6 — VL analysis complete.", flush=True)
            else:
                print("  [Pipeline] ⚠️  Step 6 — No frames extracted.", flush=True)
        except Exception as exc:
            print(f"  [Pipeline] ⚠️  Step 6 error: {exc}", flush=True)
    else:
        print("  [Pipeline] ⚠️  Step 6 (VL) skipped.", flush=True)

    # Release VL model from VRAM before loading Text Brain later
    try:
        from run_vl_agent import unload_vl_model
        unload_vl_model()
    except ImportError:
        pass

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

    # ── Finalize ────────────────────────────────────────────────────────────
    result["completed_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"\n{'═'*60}", flush=True)
    print(f"  [Pipeline] ✅ Pipeline complete!", flush=True)
    print(f"  [Pipeline] Mode: {mode.upper()} | Halted: {result['pipeline_halted']}", flush=True)
    print(f"{'═'*60}\n", flush=True)
    return result


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
        )

    # Strip large binary-ish fields from CLI output for readability
    if result.get("vl_output") and len(str(result["vl_output"])) > 2000:
        result["vl_output"] = result["vl_output"][:2000] + "... [truncated]"

    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False,
                     default=str))
    sys.exit(1 if result.get("pipeline_halted") else 0)
