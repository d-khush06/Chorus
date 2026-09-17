"""
train_chorus_v2.py
==================
One-shot script that:
  1. Checks / loads the existing Hermes datasets (already downloaded to ./datasets/)
  2. Generates Chorus-specific seed rows for Steps 6, 12, 15, 17
  3. Merges + oversamples seed rows so Chorus knowledge dominates
  4. Runs QLoRA fine-tuning (via Unsloth) on your existing local model
  5. Saves the new adapter to ./orchestrator_lora_v2/

Run:
    python train_chorus_v2.py

Hardware target: RTX A2000 12GB VRAM
Output adapter : ./orchestrator_lora_v2/
"""

# ── Unsloth MUST be the very first import ─────────────────────────────────────
# It patches trl / transformers kernels at import time. If imported after them
# you get a warning and slower / higher-VRAM training.
import unsloth  # noqa: F401  (side-effect import)

import os
import sys
import json
import random
import hashlib
import datetime
import subprocess

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DS1_PATH       = os.path.join(BASE_DIR, "datasets", "hermes_reasoning_tool_use")
DS2_PATH       = os.path.join(BASE_DIR, "datasets", "hermes_function_calling_v1")
EXISTING_DATA  = os.path.join(BASE_DIR, "chorus_negotiations.json")   # 4893 Hermes rows
MERGED_DATA    = os.path.join(BASE_DIR, "chorus_v2.json")             # output of this script
MODEL_PATH     = os.path.join(BASE_DIR, "models", "Qwen2.5-7B-Browser-Agent-Merged")
OUTPUT_DIR     = os.path.join(BASE_DIR, "orchestrator_lora_v2")

OVERSAMPLE_X   = 10    # repeat each Chorus seed row this many times
RANDOM_SEED    = 42
MAX_SEQ_LEN    = 1024  # tokens — keeps VRAM within 12GB


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — DEPENDENCY CHECK
# ─────────────────────────────────────────────────────────────────────────────

def install_deps():
    # unsloth is already imported at the top of this file.
    # Here we only ensure the lightweight runtime deps are present.
    for pkg in ["trl", "datasets", "accelerate", "tqdm"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[setup] Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

install_deps()

from tqdm import tqdm
from datasets import load_from_disk, load_dataset, Dataset, concatenate_datasets


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — CHORUS SEED ROW GENERATORS
# Each function returns a list of dicts in the same negotiation-dialogue
# format as chorus_negotiations.json so the existing training loop handles
# them without any changes.
# ─────────────────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    "source_adapters", "quality_gate", "dedup_check", "manipulation_detection",
    "project_manager", "scene_segmentation", "perception_agent", "asr_agent",
    "diarization_agent", "ocr_agent", "context_enrichment", "fusion_agent",
    "quality_verification", "correlation_agent", "analytics_query_agent",
    "review_queue", "domain_output",
]

CYBER_ONLY  = {"geo_estimation_agent", "face_reid_agent"}
GENERAL_ONLY = {"chapter_highlight_detection", "audio_description_agent"}


def _make_row(scenario, mode, category, called_tools, excluded_tools,
              extra_dialogue=None, escalated=False, escalation_reason=None,
              source="chorus_seed"):
    """Build one training row in the Chorus negotiation format."""
    opening = (
        f"Initiating Chorus pipeline for: {scenario}\n\n"
        f"[Mode: {mode}] Evaluating which tools to call, in order."
    )
    dialogue = [{"speaker": "orchestrator", "turn": "opening", "content": opening}]

    # Agent self-reports
    for tool in (called_tools + excluded_tools):
        is_called = tool in called_tools
        confidence = round(random.uniform(0.80, 0.97), 2) if is_called else round(random.uniform(0.08, 0.25), 2)
        report = (
            f"I am [{tool}]. Ready to handle this stage. Confidence: {confidence}."
            if is_called else
            f"I am [{tool}]. This scenario does not require my capabilities. Confidence: {confidence}."
        )
        dialogue.append({
            "speaker": tool,
            "turn": "self_report",
            "content": report,
            "confidence": confidence,
        })

    # Optional clarification turns
    if extra_dialogue:
        dialogue.extend(extra_dialogue)

    # Final decision
    tool_calls = [
        {"step": i + 1, "tool": t, "tier": "n/a", "arguments": {}}
        for i, t in enumerate(called_tools)
    ]
    decision = json.dumps({
        "mode": mode,
        "tool_calls": tool_calls,
        "excluded": excluded_tools,
        "reasoning_summary": (
            f"Selected: {called_tools}. "
            f"Excluded: {excluded_tools}. "
            "Order follows Chorus dependency chain."
        )
    })
    dialogue.append({"speaker": "orchestrator", "turn": "final_decision", "content": decision})

    return {
        "source_dataset": source,
        "scenario": scenario,
        "mode": mode,
        "category": category,
        "dialogue": dialogue,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
    }


# ── Step 6: Orchestrator Routing Seed Rows ────────────────────────────────────

def generate_step6_routing_rows():
    rows = []

    # ── 1. Standard general pipeline (full happy path) ──────────────────────
    for i in range(8):
        durations = ["2-minute", "5-minute", "10-minute", "30-second"]
        subjects  = ["news broadcast", "documentary clip", "sports highlight",
                      "product demo", "interview", "lecture recording"]
        scenario = (
            f"A {random.choice(durations)} {random.choice(subjects)} is uploaded "
            f"as a local MP4 file. English audio, no known duplicates, quality checks pass."
        )
        called = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent", "asr_agent", "diarization_agent", "ocr_agent",
            "context_enrichment", "fusion_agent", "quality_verification",
            "correlation_agent", "analytics_query_agent", "domain_output",
        ]
        excluded = ["geo_estimation_agent", "face_reid_agent",
                    "chapter_highlight_detection", "review_queue"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded))

    # ── 2. Early halt — duplicate found ──────────────────────────────────────
    for i in range(8):
        scenario = (
            f"A video file is uploaded. Perceptual hash matches an existing "
            f"entry in the archive (duplicate #{i+1}). Pipeline must stop immediately."
        )
        called   = ["source_adapters", "dedup_check"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(
            scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{
                "speaker": "dedup_check",
                "turn": "response",
                "content": "DUPLICATE DETECTED. halt_pipeline=True. All downstream steps must be skipped.",
                "confidence": 0.99,
            }]
        ))

    # ── 3. Quality Gate FAIL — stop before Step 4 ────────────────────────────
    for i in range(7):
        issues = [
            "timestamp integrity violation — frames out of bounds",
            "confidence floor breach — 3 events below 0.55",
            "cross-source contradiction flagged — 2+ exclusive key tokens conflict",
            "coverage gap of 120s detected in VOD timeline",
            "hallucination guard triggered — unrecognised source signal",
            "format completeness failure — missing required fields",
            "speaker consistency check failed — generic placeholder speakers",
        ]
        scenario = (
            f"Uploaded clip passes deduplication but Quality Gate raises FAIL: "
            f"{issues[i]}. Pipeline must stop before manipulation detection."
        )
        called   = ["source_adapters", "dedup_check", "quality_gate"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(
            scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{
                "speaker": "quality_gate",
                "turn": "response",
                "content": f"FAIL: {issues[i]}. halt_pipeline=True.",
                "confidence": 0.99,
            }]
        ))

    # ── 4. Manipulation detection — SEND_TO_REVIEW_QUEUE ─────────────────────
    for i in range(6):
        scenario = (
            f"Video #{i+1} passes quality gate. Manipulation detection flags the video "
            f"(SEND_TO_REVIEW_QUEUE verdict). Project Manager must still open the case "
            f"and Scene Segmentation must still run — flagged status attaches to the case."
        )
        called   = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "review_queue",
        ]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(
            scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{
                "speaker": "manipulation_detection",
                "turn": "response",
                "content": (
                    "Verdict: SEND_TO_REVIEW_QUEUE. Deepfake probability 0.72 exceeds "
                    "VIDEO_FLAG_THRESHOLD=0.30. Project Manager must still open case. "
                    "Scene Segmentation still runs. Flagged verdict stored in case record."
                ),
                "confidence": 0.94,
            }],
        ))

    # ── 5. Cyber mode — geo + face_reid unlocked ─────────────────────────────
    for i in range(6):
        scenario = (
            f"Security camera footage #{i+1} is submitted for forensic analysis "
            f"(mode=cyber, governance_approved=true). Geo-estimation and face "
            f"re-identification are required."
        )
        called   = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent", "asr_agent", "diarization_agent", "ocr_agent",
            "geo_estimation_agent", "face_reid_agent",
            "context_enrichment", "fusion_agent", "quality_verification",
            "correlation_agent", "analytics_query_agent", "domain_output",
        ]
        excluded = ["chapter_highlight_detection", "audio_description_agent"]
        rows.append(_make_row(scenario, "cyber", "mode_gated", called, excluded))

    # ── 6. Cyber mode — face_reid blocked (no governance_approved) ───────────
    for i in range(5):
        scenario = (
            f"Incident footage #{i+1} submitted in cyber mode. "
            f"governance_approved flag is NOT set. face_reid_agent must NOT be called."
        )
        called   = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent", "asr_agent", "geo_estimation_agent",
            "context_enrichment", "fusion_agent", "domain_output",
        ]
        excluded = ["face_reid_agent", "chapter_highlight_detection",
                    "audio_description_agent", "review_queue"]
        rows.append(_make_row(
            scenario, "cyber", "mode_gated", called, excluded,
            extra_dialogue=[{
                "speaker": "face_reid_agent",
                "turn": "self_report",
                "content": (
                    "I am [face_reid_agent]. governance_approved=false detected. "
                    "I MUST NOT run without explicit legal approval. Excluding myself."
                ),
                "confidence": 0.05,
            }]
        ))

    # ── 7. Tier escalation — low confidence → Tier 2 ─────────────────────────
    for i in range(5):
        scenario = (
            f"Video analysis #{i+1}. Perception agent (Tier 1) returns confidence 0.61 "
            f"— below the 0.75 threshold. Must escalate perception_agent to Tier 2 "
            f"(Qwen3-VL-8B) before proceeding to context_enrichment."
        )
        called   = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent",   # Tier 1 first
            "perception_agent",   # Tier 2 escalation (represented twice in training)
            "asr_agent", "diarization_agent", "ocr_agent",
            "context_enrichment", "fusion_agent", "domain_output",
        ]
        excluded = ["geo_estimation_agent", "face_reid_agent", "review_queue"]
        rows.append(_make_row(
            scenario, "general", "multi_step", called, excluded,
            escalated=True, escalation_reason="low_confidence"
        ))

    # ── 8. RTSP live stream routing ───────────────────────────────────────────
    for i in range(5):
        scenario = (
            f"Live RTSP stream #{i+1} from a security camera. "
            f"source_type=live_rtsp. dedup_check must be SKIPPED. "
            f"quality_verification runs on rolling cadence, not once."
        )
        called   = [
            "source_adapters", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent", "asr_agent", "diarization_agent",
            "context_enrichment", "fusion_agent", "quality_verification",
            "domain_output",
        ]
        excluded = ["dedup_check", "geo_estimation_agent", "face_reid_agent",
                    "chapter_highlight_detection"]
        rows.append(_make_row(
            scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{
                "speaker": "dedup_check",
                "turn": "self_report",
                "content": (
                    "I am [dedup_check]. source_type=live_rtsp detected. "
                    "Per Chorus Rule 7, I must be skipped for live RTSP sources. "
                    "Excluding myself."
                ),
                "confidence": 0.02,
            }]
        ))

    # ── 9. Public figure video — mandatory manipulation_detection ─────────────
    for i in range(5):
        subjects = ["politician", "celebrity", "public official",
                    "world leader", "sports star"]
        scenario = (
            f"Video clip features a well-known {subjects[i % len(subjects)]} "
            f"in a widely-shared context. Per Rule 6, manipulation_detection is mandatory "
            f"and an extra quality_verification pass must run after domain_output."
        )
        called   = [
            "source_adapters", "dedup_check", "quality_gate",
            "manipulation_detection", "project_manager", "scene_segmentation",
            "perception_agent", "asr_agent", "diarization_agent", "ocr_agent",
            "context_enrichment", "fusion_agent", "quality_verification",
            "correlation_agent", "analytics_query_agent", "domain_output",
            "quality_verification",  # second pass — Rule 6
        ]
        excluded = ["geo_estimation_agent", "face_reid_agent", "review_queue"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded))

    print(f"  [Step 6 seed] Generated {len(rows)} routing rows.")
    return rows


# ── Step 12: Context Enrichment Seed Rows ─────────────────────────────────────

def generate_step12_enrichment_rows():
    rows = []
    SYSTEM = (
        "You are the CONTEXT ENRICHMENT agent for the Chorus pipeline. "
        "Cross-check the raw outputs from perception_agent, asr_agent, and ocr_agent. "
        "Identify conflicts, resolve or flag them, and return a cleaned unified output. "
        "Return only structured JSON."
    )

    scenarios = [
        # Clean passes
        {
            "scenario": "All three agents (perception, ASR, OCR) agree on scene content. No conflicts detected.",
            "user": '{"perception": {"objects": ["podium", "microphone"]}, "asr": {"transcript": "Good morning."}, "ocr": {"text": "City Hall"}}',
            "assistant": '{"status": "clean", "conflicts": [], "cleaned_output": {"objects": ["podium", "microphone"], "transcript": "Good morning.", "on_screen_text": "City Hall"}, "confidence": 0.96}',
        },
        {
            "scenario": "Perception and ASR agree. OCR finds no text (blank screen). No conflict — blank OCR is valid.",
            "user": '{"perception": {"objects": ["crowd", "banner"]}, "asr": {"transcript": "We demand change."}, "ocr": {"text": ""}}',
            "assistant": '{"status": "clean", "conflicts": [], "cleaned_output": {"objects": ["crowd", "banner"], "transcript": "We demand change.", "on_screen_text": ""}, "confidence": 0.94}',
        },
        {
            "scenario": "All agents report confidently on a documentary scene. Context enrichment passes through unchanged.",
            "user": '{"perception": {"objects": ["wildlife", "river"]}, "asr": {"transcript": "The Amazon basin spans 5.5 million square kilometres."}, "ocr": {"text": "Amazon Rainforest 2024"}}',
            "assistant": '{"status": "clean", "conflicts": [], "cleaned_output": {"objects": ["wildlife", "river"], "transcript": "The Amazon basin spans 5.5 million square kilometres.", "on_screen_text": "Amazon Rainforest 2024"}, "confidence": 0.97}',
        },
        # ASR vs OCR conflicts
        {
            "scenario": "ASR transcribes 'no weapons visible' but OCR reads 'ARMED RESPONSE UNIT'. Direct contradiction on safety-critical content.",
            "user": '{"asr": {"transcript": "no weapons visible"}, "ocr": {"text": "ARMED RESPONSE UNIT"}}',
            "assistant": '{"status": "conflict_detected", "conflicts": [{"source_a": "asr_agent", "source_b": "ocr_agent", "description": "ASR denies weapons; OCR confirms armed unit label", "resolution": "flag_for_review"}], "cleaned_output": null, "confidence": 0.12}',
        },
        {
            "scenario": "ASR says speaker identified themselves as 'John Smith' but OCR shows badge reading 'Mark Davies'.",
            "user": '{"asr": {"transcript": "My name is John Smith"}, "ocr": {"text": "Mark Davies — Senior Officer"}}',
            "assistant": '{"status": "conflict_detected", "conflicts": [{"source_a": "asr_agent", "source_b": "ocr_agent", "description": "Name mismatch: spoken John Smith vs badge Mark Davies", "resolution": "flag_for_review"}], "cleaned_output": null, "confidence": 0.15}',
        },
        {
            "scenario": "ASR transcribes date as '14th March' but on-screen graphic shows '14th May'.",
            "user": '{"asr": {"transcript": "This happened on 14th March"}, "ocr": {"text": "14 May 2026"}}',
            "assistant": '{"status": "conflict_detected", "conflicts": [{"source_a": "asr_agent", "source_b": "ocr_agent", "description": "Date conflict: spoken March vs displayed May", "resolution": "flag_for_review"}], "cleaned_output": null, "confidence": 0.11}',
        },
        # Perception vs ASR conflicts
        {
            "scenario": "Perception agent detects no person in frame. ASR detects a human voice. Physical impossibility — flag.",
            "user": '{"perception": {"objects": ["empty room", "chair"]}, "asr": {"transcript": "Hello, is anyone there?"}}',
            "assistant": '{"status": "conflict_detected", "conflicts": [{"source_a": "perception_agent", "source_b": "asr_agent", "description": "No person detected visually but human speech transcribed", "resolution": "escalate_tier2"}], "cleaned_output": null, "confidence": 0.09}',
        },
        {
            "scenario": "Perception reports outdoor daylight scene. ASR transcript mentions 'late at night' and 'darkness'.",
            "user": '{"perception": {"scene": "outdoor, bright sunlight, daytime"}, "asr": {"transcript": "It was late at night, very dark outside"}}',
            "assistant": '{"status": "conflict_detected", "conflicts": [{"source_a": "perception_agent", "source_b": "asr_agent", "description": "Visual shows daytime; speech describes nighttime", "resolution": "flag_for_review"}], "cleaned_output": null, "confidence": 0.10}',
        },
        # Low confidence → escalate
        {
            "scenario": "Perception agent confidence is 0.58 — below Tier 2 escalation threshold of 0.75. Must escalate.",
            "user": '{"perception": {"objects": ["vehicle?", "person?"], "confidence": 0.58}}',
            "assistant": '{"status": "escalate_tier2", "conflicts": [], "reason": "perception_agent confidence 0.58 below threshold 0.75", "cleaned_output": null}',
        },
        {
            "scenario": "ASR confidence 0.62 on heavily accented speech. Escalate ASR to Whisper-large-v3 Tier 2.",
            "user": '{"asr": {"transcript": "[unclear]", "confidence": 0.62}}',
            "assistant": '{"status": "escalate_tier2", "conflicts": [], "reason": "asr_agent confidence 0.62 below threshold 0.75", "cleaned_output": null}',
        },
        # Hallucination guard
        {
            "scenario": "Perception agent reports detecting 'a flying car in the sky'. This is not physically plausible — hallucination guard triggers.",
            "user": '{"perception": {"objects": ["flying car", "skyscraper"]}}',
            "assistant": '{"status": "hallucination_flagged", "conflicts": [{"source_a": "perception_agent", "description": "Flying car detection implausible — likely hallucination", "resolution": "reject_artifact"}], "cleaned_output": null, "confidence": 0.05}',
        },
    ]

    for s in scenarios:
        dialogue = [
            {
                "speaker": "orchestrator",
                "turn": "opening",
                "content": f"Running context enrichment for: {s['scenario']}",
            },
            {
                "speaker": "user",
                "turn": "input",
                "content": s["user"],
            },
            {
                "speaker": "orchestrator",
                "turn": "final_decision",
                "content": s["assistant"],
            },
        ]
        rows.append({
            "source_dataset": "chorus_seed",
            "scenario": s["scenario"],
            "mode": "general",
            "category": "context_enrichment",
            "dialogue": dialogue,
            "escalated": "escalate" in s["assistant"],
            "escalation_reason": "low_confidence" if "escalate" in s["assistant"] else None,
            # Store system prompt as metadata for the training formatter
            "_system_prompt": SYSTEM,
        })

    print(f"  [Step 12 seed] Generated {len(rows)} enrichment rows.")
    return rows


# ── Step 15: Analytics & Q&A Seed Rows ───────────────────────────────────────

def generate_step15_analytics_rows():
    rows = []
    SYSTEM = (
        "You are the ANALYTICS & QUERY agent for the Chorus pipeline. "
        "Answer grounded questions using ONLY the fused_timeline as your source. "
        "Cite evidence (scene_id, timestamp). Never invent information not in the timeline. "
        "Return structured JSON with 'answer' and 'evidence' fields."
    )

    qas = [
        # Speaker counts
        ("How many unique speakers appear in this video?",
         '{"fused_timeline": {"speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"], "scenes": []}}',
         '{"answer": "3 unique speakers appear: SPEAKER_00, SPEAKER_01, SPEAKER_02.", "evidence": [{"source": "diarization_agent", "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"]}]}'),
        ("Which speaker had the most screen time?",
         '{"fused_timeline": {"speaker_time": {"SPEAKER_00": 142.3, "SPEAKER_01": 67.8}}}',
         '{"answer": "SPEAKER_00 had the most screen time at 142.3 seconds (approximately 2 minutes 22 seconds).", "evidence": [{"source": "diarization_agent", "speaker": "SPEAKER_00", "total_seconds": 142.3}]}'),
        ("How long did SPEAKER_01 speak in total?",
         '{"fused_timeline": {"speaker_time": {"SPEAKER_00": 90.0, "SPEAKER_01": 45.5, "SPEAKER_02": 30.0}}}',
         '{"answer": "SPEAKER_01 spoke for 45.5 seconds in total.", "evidence": [{"source": "diarization_agent", "speaker": "SPEAKER_01", "total_seconds": 45.5}]}'),
        # Scene queries
        ("How many scenes were detected?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0}, {"scene_id": 1}, {"scene_id": 2}, {"scene_id": 3}]}}',
         '{"answer": "4 scenes were detected by the scene segmentation agent.", "evidence": [{"source": "scene_segmentation", "scene_count": 4}]}'),
        ("What is the total duration of the video?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "start_seconds": 0.0, "end_seconds": 45.2}, {"scene_id": 1, "start_seconds": 45.2, "end_seconds": 183.7}]}}',
         '{"answer": "The total video duration is 183.7 seconds (approximately 3 minutes 4 seconds).", "evidence": [{"source": "scene_segmentation", "last_scene_end": 183.7}]}'),
        # Object queries
        ("Was a vehicle detected in any scene?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "objects": ["person", "podium"]}, {"scene_id": 1, "objects": ["vehicle", "street"]}]}}',
         '{"answer": "Yes. A vehicle was detected in scene 1.", "evidence": [{"source": "perception_agent", "scene_id": 1, "objects": ["vehicle", "street"]}]}'),
        ("Was a weapon detected at any point?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "objects": ["person", "table"]}, {"scene_id": 1, "objects": ["crowd", "banner"]}]}}',
         '{"answer": "No weapon was detected in any scene according to the fused timeline.", "evidence": [{"source": "perception_agent", "note": "no weapon detected in any of 2 scenes"}]}'),
        # OCR queries
        ("What text appeared on screen during this video?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "ocr_text": "CITY HALL PRESS CONFERENCE"}, {"scene_id": 1, "ocr_text": "14 SEPTEMBER 2026"}]}}',
         '{"answer": "On-screen text: Scene 0 — \'CITY HALL PRESS CONFERENCE\'. Scene 1 — \'14 SEPTEMBER 2026\'.", "evidence": [{"source": "ocr_agent", "scene_id": 0, "text": "CITY HALL PRESS CONFERENCE"}, {"source": "ocr_agent", "scene_id": 1, "text": "14 SEPTEMBER 2026"}]}'),
        # Unanswerable / not in timeline
        ("Did the speaker mention climate change?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "transcript": "Good morning. Thank you for coming today."}]}}',
         '{"answer": "Climate change is not mentioned in the available transcript. The fused timeline does not contain this information.", "evidence": [{"source": "asr_agent", "note": "searched all transcript segments — no mention of climate change"}]}'),
        ("Who is the person in the video?",
         '{"fused_timeline": {"scenes": [{"scene_id": 0, "objects": ["person"]}], "face_reid": null}}',
         '{"answer": "Identity cannot be determined. face_reid_agent was not run (either general mode or governance_approved not set). No identity data in the fused timeline.", "evidence": [{"source": "face_reid_agent", "status": "not_run"}]}'),
        # Multi-stat
        ("Give me a summary of the key statistics for this video.",
         '{"fused_timeline": {"total_duration_s": 245.0, "scenes": [{"scene_id": 0}, {"scene_id": 1}, {"scene_id": 2}], "speakers": ["SPEAKER_00", "SPEAKER_01"], "speaker_time": {"SPEAKER_00": 180.0, "SPEAKER_01": 65.0}}}',
         '{"answer": "Duration: 245.0s. Scenes: 3. Speakers: 2 (SPEAKER_00: 180s, SPEAKER_01: 65s).", "evidence": [{"source": "scene_segmentation"}, {"source": "diarization_agent"}]}'),
    ]

    for question, user_input, assistant_output in qas:
        dialogue = [
            {"speaker": "orchestrator", "turn": "opening",
             "content": f"Analytics Q&A request: {question}"},
            {"speaker": "user", "turn": "input", "content": user_input},
            {"speaker": "orchestrator", "turn": "final_decision", "content": assistant_output},
        ]
        rows.append({
            "source_dataset": "chorus_seed",
            "scenario": question,
            "mode": "general",
            "category": "analytics_query",
            "dialogue": dialogue,
            "escalated": False,
            "escalation_reason": None,
            "_system_prompt": SYSTEM,
        })

    print(f"  [Step 15 seed] Generated {len(rows)} analytics Q&A rows.")
    return rows


# ── Step 17: Domain Output / Narration Seed Rows ──────────────────────────────

def generate_step17_narration_rows():
    rows = []
    SYSTEM = (
        "You are the DOMAIN OUTPUT agent for the Chorus pipeline. "
        "Write a concise, factual narrated summary of the video "
        "based ONLY on the provided fused_timeline. "
        "If manipulation was detected, include a clear warning. "
        "Return JSON with 'output_format', 'narration', and 'confidence' fields."
    )

    narrations = [
        # Clean general
        {
            "scenario": "3-minute English news broadcast, 2 speakers, no flags.",
            "input": '{"total_duration_s": 183.0, "scenes": 4, "speakers": ["SPEAKER_00", "SPEAKER_01"], "transcript_summary": "City council announces new infrastructure plan.", "ocr_summary": "City Hall, 14 Sep 2026", "manipulation": "CLEAN"}',
            "output": '{"output_format": "narrative_summary", "narration": "This 3-minute news broadcast (183 seconds, 4 scenes) covers a city council announcement regarding a new infrastructure plan. Two speakers are present (SPEAKER_00 and SPEAKER_01). On-screen text confirms the location as City Hall on 14 September 2026. No manipulation or deepfake signals were detected.", "confidence": 0.95}',
        },
        # Flagged — manipulation
        {
            "scenario": "Video flagged by manipulation detection (SEND_TO_REVIEW_QUEUE).",
            "input": '{"total_duration_s": 120.0, "scenes": 2, "speakers": ["SPEAKER_00"], "transcript_summary": "Public statement by official.", "manipulation": "FLAGGED", "manipulation_score": 0.74}',
            "output": '{"output_format": "narrative_summary", "narration": "⚠️ MANIPULATION WARNING: This 2-minute video has been flagged by the deepfake detection system (confidence score 0.74, threshold 0.30). The content shows a public statement. This case has been routed to the review queue and requires human verification before any further use.", "confidence": 0.41}',
        },
        # Cyber mode
        {
            "scenario": "Security camera clip (cyber mode), geo-estimated location, no faces identified without governance.",
            "input": '{"total_duration_s": 90.0, "scenes": 3, "mode": "cyber", "geo_estimate": "central London, 85% confidence", "face_reid": "not_run", "manipulation": "CLEAN", "transcript_summary": "No speech detected."}',
            "output": '{"output_format": "forensic_summary", "narration": "This 90-second security camera clip (3 scenes) was processed in cyber mode. Geo-estimation places the location in central London (confidence: 85%). No speech was detected. Face re-identification was not performed (governance not approved). No manipulation signals detected.", "confidence": 0.88}',
        },
        # Multi-speaker interview
        {
            "scenario": "10-minute interview, 3 speakers, prominent on-screen captions.",
            "input": '{"total_duration_s": 600.0, "scenes": 8, "speakers": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"], "speaker_time": {"SPEAKER_00": 320.0, "SPEAKER_01": 180.0, "SPEAKER_02": 100.0}, "ocr_summary": "Interview: Future of AI — Panel Discussion", "manipulation": "CLEAN"}',
            "output": '{"output_format": "narrative_summary", "narration": "This 10-minute panel interview (600 seconds, 8 scenes) on the topic of \'Future of AI\' features 3 speakers. SPEAKER_00 dominated with 320 seconds of speech, followed by SPEAKER_01 (180s) and SPEAKER_02 (100s). On-screen captions confirm the topic. No manipulation signals were detected.", "confidence": 0.93}',
        },
        # RTSP live stream
        {
            "scenario": "Rolling 30-second RTSP chunk from a live traffic camera.",
            "input": '{"chunk_start_s": 3600.0, "chunk_end_s": 3630.0, "scenes": 2, "source_type": "live_rtsp", "objects": ["vehicles", "road"], "manipulation": "CLEAN"}',
            "output": '{"output_format": "live_stream_chunk_summary", "narration": "Live stream chunk (stream position 3600–3630s). 2 scenes detected. Objects: vehicles and road visible. No speech or OCR text detected in this chunk. No manipulation signals. Processing continues on rolling cadence.", "confidence": 0.91}',
        },
        # No speech / silent
        {
            "scenario": "Silent documentary b-roll, no ASR output, rich visual content.",
            "input": '{"total_duration_s": 240.0, "scenes": 6, "speakers": [], "transcript": "", "objects_summary": "wildlife, forest, river, aerial shots", "ocr_summary": "", "manipulation": "CLEAN"}',
            "output": '{"output_format": "narrative_summary", "narration": "This 4-minute silent documentary b-roll (6 scenes) contains no spoken audio. Visual content features wildlife, forest, a river, and aerial photography. No on-screen text detected. No manipulation signals were detected.", "confidence": 0.94}',
        },
        # Short clip — 30 seconds
        {
            "scenario": "30-second social media clip, single speaker, product demo.",
            "input": '{"total_duration_s": 30.0, "scenes": 1, "speakers": ["SPEAKER_00"], "transcript_summary": "Quick demo of the new Chorus analytics dashboard.", "manipulation": "CLEAN"}',
            "output": '{"output_format": "narrative_summary", "narration": "This 30-second clip (1 scene) features a single speaker demonstrating the Chorus analytics dashboard. No manipulation signals detected.", "confidence": 0.97}',
        },
        # No faces detected
        {
            "scenario": "Video with no human faces — manipulation detection returns NO_FACES_DETECTED.",
            "input": '{"total_duration_s": 180.0, "scenes": 3, "manipulation": "NO_FACES_DETECTED", "objects_summary": "landscape, buildings, text overlays"}',
            "output": '{"output_format": "narrative_summary", "narration": "This 3-minute video (3 scenes) contains no human faces. Deepfake detection returned NO_FACES_DETECTED — not applicable. Content shows landscape, buildings, and text overlays. No manipulation concerns raised.", "confidence": 0.96}',
        },
    ]

    for n in narrations:
        dialogue = [
            {"speaker": "orchestrator", "turn": "opening",
             "content": f"Domain output narration request: {n['scenario']}"},
            {"speaker": "user", "turn": "input", "content": n["input"]},
            {"speaker": "orchestrator", "turn": "final_decision", "content": n["output"]},
        ]
        rows.append({
            "source_dataset": "chorus_seed",
            "scenario": n["scenario"],
            "mode": "general",
            "category": "domain_output",
            "dialogue": dialogue,
            "escalated": False,
            "escalation_reason": None,
            "_system_prompt": SYSTEM,
        })

    print(f"  [Step 17 seed] Generated {len(rows)} narration rows.")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — MERGE + OVERSAMPLE
# ─────────────────────────────────────────────────────────────────────────────

def build_merged_dataset(oversample_x=OVERSAMPLE_X):
    print("\n" + "="*65)
    print("PHASE 1 — BUILDING chorus_v2.json")
    print("="*65)

    # Load existing Hermes-converted data
    print(f"\n[1/3] Loading existing Hermes data from: {EXISTING_DATA}")
    if not os.path.isfile(EXISTING_DATA):
        print("  ERROR: chorus_negotiations.json not found!")
        print("  Run: python prepare_negotiation_dataset.py  first.")
        sys.exit(1)

    with open(EXISTING_DATA, "r", encoding="utf-8") as f:
        hermes_rows = json.load(f)
    print(f"  Loaded {len(hermes_rows)} Hermes rows.")

    # Generate all Chorus seed rows
    print("\n[2/3] Generating Chorus seed rows...")
    seed_routing    = generate_step6_routing_rows()
    seed_enrichment = generate_step12_enrichment_rows()
    seed_analytics  = generate_step15_analytics_rows()
    seed_narration  = generate_step17_narration_rows()

    all_seed = seed_routing + seed_enrichment + seed_analytics + seed_narration
    print(f"\n  Total seed rows before oversample : {len(all_seed)}")

    # Oversample seed rows
    oversampled = all_seed * oversample_x
    # Shuffle oversampled rows to mix step types
    random.seed(RANDOM_SEED)
    random.shuffle(oversampled)
    print(f"  Total seed rows after ×{oversample_x} oversample : {len(oversampled)}")

    # Deduplicate within seed by hashing scenario text
    seen_hashes = set()
    deduped_oversampled = []
    for row in oversampled:
        h = hashlib.md5(row["scenario"].encode()).hexdigest()
        # Allow duplicates from oversample but track unique scenarios
        deduped_oversampled.append(row)
    # (We keep all oversampled rows — the ×10 repetition IS intentional for training signal)

    # Merge
    merged = hermes_rows + deduped_oversampled
    random.shuffle(merged)

    print(f"\n[3/3] Saving merged dataset...")
    print(f"  Hermes rows       : {len(hermes_rows)}")
    print(f"  Chorus seed (raw) : {len(all_seed)}")
    print(f"  Chorus oversampled: {len(deduped_oversampled)}")
    print(f"  Grand total       : {len(merged)}")

    with open(MERGED_DATA, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    size_mb = round(os.path.getsize(MERGED_DATA) / 1024 / 1024, 1)
    print(f"  Saved to: {MERGED_DATA}  ({size_mb} MB)")
    return MERGED_DATA


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — QLoRA FINE-TUNING
# ─────────────────────────────────────────────────────────────────────────────

def map_to_messages(example):
    """
    Convert Chorus negotiation dialogue (or messages format) to chat messages.
    Handles both Step 6 routing format and Steps 12/15/17 system-prompt format.
    """
    messages = []

    if "dialogue" in example and example["dialogue"] is not None:
        # Pick system prompt: step-specific or default orchestrator prompt
        sys_prompt = example.get("_system_prompt") or (
            "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
            "Decide which tools to call, in what order, return only structured JSON."
        )
        scenario = example.get("scenario", "Process request")

        messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": f"Scenario: {scenario}"})

        for turn in example["dialogue"]:
            speaker = turn.get("speaker", "orchestrator")
            content = turn.get("content", "")
            if speaker == "orchestrator":
                messages.append({"role": "assistant", "content": content})
            elif speaker == "user":
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": f"[{speaker}]: {content}"})

    elif "messages" in example and example["messages"] is not None:
        for msg in example["messages"]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    elif "conversations" in example and example["conversations"] is not None:
        for msg in example["conversations"]:
            role = msg.get("from", "user")
            role = {"human": "user", "gpt": "assistant"}.get(role, role)
            if role not in ("system", "user", "assistant"):
                role = "user"
            messages.append({"role": role, "content": msg.get("value", "")})

    return {"messages": messages}


def run_training(dataset_path: str):
    """
    QLoRA fine-tuning powered by Unsloth.
    Replaces the old transformers+peft+bitsandbytes stack with
    FastLanguageModel + SFTTrainer for ~2x speed and ~60% less VRAM.
    All hyperparameters are identical to the previous working run.
    """
    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig

    print("\n" + "="*65)
    print("PHASE 2 — UNSLOTH QLoRA FINE-TUNING")
    print("="*65)

    # ── Validate model path ──────────────────────────────────────────────────
    if not os.path.isdir(MODEL_PATH):
        print(f"\n  ERROR: Model not found at {MODEL_PATH}")
        print("  Make sure the model folder exists locally.")
        sys.exit(1)
    print(f"\n  Base model : {MODEL_PATH}")
    print(f"  Dataset    : {dataset_path}")
    print(f"  Output dir : {OUTPUT_DIR}")
    if torch.cuda.is_available():
        print(f"  GPU        : {torch.cuda.get_device_name(0)}")
        print(f"  VRAM       : {round(torch.cuda.get_device_properties(0).total_memory/1e9, 1)} GB")

    # ── 1. Load model + tokenizer via Unsloth ────────────────────────────────
    # Replaces: AutoModelForCausalLM + BitsAndBytesConfig + prepare_model_for_kbit_training
    print("\n[1/4] Loading model with Unsloth (4-bit NF4)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_PATH,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,           # auto-detect: bfloat16 on Ampere (A2000), float16 otherwise
        load_in_4bit=True,    # NF4 quant — same as the old bnb_config
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ── 2. Attach LoRA via Unsloth ────────────────────────────────────────────
    # Replaces: peft LoraConfig + get_peft_model  (same r/alpha/targets as before)
    print("[2/4] Attaching LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",   # Unsloth optimised — saves extra VRAM
        random_state=RANDOM_SEED,
        use_rslora=False,
    )
    model.print_trainable_parameters()

    # ── 3. Dataset ────────────────────────────────────────────────────────────
    print("\n[3/4] Loading and preparing dataset...")
    raw = load_dataset("json", data_files=dataset_path, split="train")
    print(f"  Loaded {len(raw)} rows from {dataset_path}")

    raw = raw.map(map_to_messages, remove_columns=raw.column_names)

    def format_prompts(batch):
        texts = []
        for msgs in batch["messages"]:
            try:
                texts.append(
                    tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
                )
            except Exception:
                texts.append("")
        return {"text": texts}

    raw = raw.map(format_prompts, batched=True)
    raw = raw.filter(lambda x: len(x["text"]) > 50)  # drop empty/broken rows
    print(f"  Final dataset size after filtering: {len(raw)} rows")

    # ── Checkpoint resume ────────────────────────────────────────────────────
    checkpoint = None
    if os.path.isdir(OUTPUT_DIR):
        ckpts = sorted(
            [os.path.join(OUTPUT_DIR, d) for d in os.listdir(OUTPUT_DIR)
             if d.startswith("checkpoint-")],
            key=os.path.getmtime,
        )
        if ckpts:
            cand = ckpts[-1]
            if os.path.isfile(os.path.join(cand, "trainer_state.json")):
                checkpoint = cand
                print(f"\n  Resuming from checkpoint: {checkpoint}")
            else:
                print(f"\n  Found {cand} but trainer_state.json is missing; starting fresh.")

    # ── 4. Train with SFTTrainer (Unsloth-aware) ─────────────────────────────
    print("\n[4/4] Configuring and starting Unsloth SFT training...")
    sft_config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,    # effective batch = 8  (unchanged)
        warmup_steps=50,
        num_train_epochs=1,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=5,
        save_strategy="steps",
        save_steps=50,                    # checkpoint every 50 steps
        save_total_limit=5,
        optim="adamw_8bit",               # Unsloth fused 8-bit AdamW
        max_seq_length=MAX_SEQ_LEN,
        dataset_text_field="text",
        report_to="none",
        dataset_num_proc=1,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=raw,
        args=sft_config,
    )

    # ── Train ─────────────────────────────────────────────────────────────────
    start = datetime.datetime.now()
    try:
        trainer.train(resume_from_checkpoint=checkpoint)
    except Exception as e:
        print(f"\n  Training interrupted: {e}")
        print("  Saving partial adapter...")
        model.save_pretrained(OUTPUT_DIR)
        tokenizer.save_pretrained(OUTPUT_DIR)
        raise

    elapsed = datetime.datetime.now() - start
    print(f"\n  Training finished in {str(elapsed).split('.')[0]}")

    # ── Save ──────────────────────────────────────────────────────────────────
    print(f"\n  Saving final adapter to: {OUTPUT_DIR}")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("  Done! Adapter saved.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("CHORUS v2 TRAINING PIPELINE")
    print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # Phase 1: Build merged dataset
    merged_path = build_merged_dataset(oversample_x=OVERSAMPLE_X)

    # Phase 2: Train
    run_training(merged_path)

    print("\n" + "=" * 65)
    print("ALL DONE")
    print(f"  New adapter saved to : {OUTPUT_DIR}")
    print(f"  Merged dataset saved : {MERGED_DATA}")
    print("  Next steps:")
    print("    1. Evaluate on held-out split")
    print("    2. Wire orchestrator_lora_v2 into pipeline_runner.py")
    print("    3. Build Steps 8-11, 13, 14, 16 (no training needed)")
    print("=" * 65)
