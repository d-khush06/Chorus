"""
domain_output.py
================
Chorus Pipeline — Step 9: Domain Output Agent

Pipeline position
-----------------
  Runs AFTER : Fusion Agent (all timelines merged)
  Final step : Produces the user-facing output

Purpose
-------
Takes the fused timeline from fusion_agent and uses the existing
Qwen2.5-7B Text Brain (run_text_agent.py) with four specialist
system prompts to produce:

  1. CONTEXT ENRICHMENT   — cross-checks, cleans, and corroborates all
                             agent outputs; flags conflicts and low-confidence
                             findings before the final answer is generated.

  2. ANALYTICS SUMMARY    — auto-generates statistics (scene count, word
                             count, duration, detected language, flags) and
                             answers any specific user question about the video.

  3. DOMAIN OUTPUT        — structures the final user-facing response for
                             general mode (video summary, key findings,
                             timeline highlights, recommendations).

  4. INCIDENT REPORT      — cyber mode only: structured forensic incident
                             report format (timeline, anomalies, persons of
                             interest, recommended next steps).

Rules
-----
1. Never load a new model — always reuse the Qwen2.5-7B Text Brain
   already loaded via run_text_agent.py.
2. Run stages 1→2→3 in order (or 1→2→4 in cyber mode). Each stage's
   output feeds the next as additional context.
3. If a stage fails, continue with what is available — never block the
   entire output chain.
4. All structured output must be valid JSON. If the model fails to
   produce valid JSON, fall back to raw text wrapped in {"raw_output": ...}.
5. Never truncate the full_transcript or vl_output before passing to
   the model — pass the full content within the context window limit.

Usage (library)
---------------
  from domain_output import generate_output

  result = generate_output(
      fused=fused_timeline_dict,   # from fusion_agent
      user_question="Summarize what happens in this video.",
      mode="general",              # "general" | "cyber"
  )

  print(result["final_output"]["summary"])
"""

import os
import sys
import json
import datetime
from typing import Optional

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

_CONTEXT_ENRICHMENT_PROMPT = """\
You are the Context Enrichment Agent for the Chorus video intelligence pipeline.
You receive the raw merged output from multiple analysis agents (vision analysis, \
speech transcription, scene segmentation) and your job is to:

1. Cross-check consistency: Does the VL visual description match the speech content?
2. Flag low-confidence findings: Any segment where the speaker says something \
that contradicts what is visible, or where VL output is vague/uncertain.
3. Clean noise: Identify ASR hallucinations (filler words, repeated phrases, \
nonsensical segments) and mark them with [LOW_CONFIDENCE].
4. Extract key entities: List all named persons, locations, organizations, objects, \
and events mentioned across all modalities.
5. Resolve conflicts: If vision and speech contradict each other, note the conflict \
and provide your best reconciled interpretation.

Return ONLY this JSON structure, no other text:
{
  "key_entities": {
    "persons": [...],
    "locations": [...],
    "organizations": [...],
    "objects": [...],
    "events": [...]
  },
  "conflicts": [{"description": "...", "resolution": "..."}],
  "low_confidence_segments": [{"segment_id": N, "reason": "..."}],
  "enriched_summary": "One paragraph clean summary of what the video contains.",
  "quality_assessment": "GOOD | MIXED | POOR",
  "quality_notes": "Brief explanation of quality assessment."
}
"""

_ANALYTICS_PROMPT = """\
You are the Analytics Agent for the Chorus video intelligence pipeline.
You receive a fused video timeline and must generate both automatic statistics \
and a direct answer to the user's specific question.

Your job:
1. Auto-generate statistics from the data provided (do not invent — only report \
what is present in the input).
2. Answer the user's question with specific references to the timeline.
3. Identify the most important moment/scene in the video and explain why.

Return ONLY this JSON structure, no other text:
{
  "statistics": {
    "duration_s": <number or null>,
    "total_scenes": <number>,
    "speech_coverage_pct": <0-100 percentage of video with speech>,
    "total_words_spoken": <number>,
    "detected_language": "<language or null>",
    "scenes_with_persons": <number>,
    "scenes_with_vehicles": <number>,
    "scenes_with_text_on_screen": <number>,
    "deepfake_flagged": <true|false>,
    "ai_generated_flagged": <true|false>
  },
  "most_important_moment": {
    "scene_id": <number>,
    "start_s": <number>,
    "end_s": <number>,
    "reason": "Why this moment is significant."
  },
  "user_question_answer": "Direct answer to the user's question with evidence."
}
"""

_DOMAIN_OUTPUT_PROMPT_GENERAL = """\
You are the Domain Output Agent for the Chorus video intelligence platform.
You have received enriched video analysis data from multiple AI agents. \
Your job is to produce the final structured summary that will be shown to the user.

Rules:
- Be specific — do not write generic summaries. Reference actual content.
- Use the timeline data to structure your answer chronologically.
- Highlight anything unusual, interesting, or important.
- Keep the executive summary to 2-3 sentences maximum.
- The detailed_analysis should be thorough — at least 5 bullet points.

Return ONLY this JSON structure, no other text:
{
  "executive_summary": "2-3 sentence top-level summary of the video.",
  "detailed_analysis": [
    "Bullet point 1 describing a key finding or event...",
    "Bullet point 2...",
    ...
  ],
  "timeline_highlights": [
    {"time": "0:00-0:12", "event": "Description of what happens in this scene"},
    ...
  ],
  "content_flags": {
    "contains_sensitive_content": <true|false>,
    "contains_faces": <true|false>,
    "contains_audio": <true|false>,
    "manipulation_detected": <true|false>
  },
  "recommendations": ["Any recommended follow-up actions or caveats for the user."]
}
"""

_DOMAIN_OUTPUT_PROMPT_CYBER = """\
You are the Cyber Forensics Domain Output Agent for the Chorus video intelligence platform.
This is a SECURITY / FORENSIC incident analysis. You have received enriched analysis data \
from multiple specialist AI agents. Your job is to produce a structured forensic incident report.

IMPORTANT: The input data includes ALL of the following cyber intelligence sources:
- Visual Analysis (VL Brain): Frame-by-frame descriptions, OCR, object detection.
- Speech Transcript (ASR): Full transcript with timestamps.
- Geo Estimation: GPS coordinates, confidence, and top candidate locations.
- Acoustic Events: Gunshots, explosions, screams, alarms, sirens with timestamps and severity.
- Face Re-ID: Unique identities tracked across frames with first/last seen times and match scores.
- Triggered Alerts: Security alerts with severity, source step, and descriptions.
- Scene Segmentation: Timeline with scene tags (gunshot_detected, explosion_detected, etc.).

You MUST incorporate ALL available cyber intelligence into your report. Do NOT report data as \
"not available" or "not provided" if it is present in the input. Use precise, factual language — \
this report may be used by security professionals.
- Reference specific timestamps for every finding.
- Clearly distinguish CONFIRMED findings from SUSPECTED findings.
- Never speculate without labeling it as [SUSPECTED].
- Flag any evidence that may require human expert review.

Return ONLY this JSON structure, no other text:
{
  "incident_summary": "2-3 sentence factual summary of what the footage shows.",
  "timeline_of_events": [
    {"time_range": "0:00-0:12", "event": "...", "confidence": "HIGH|MEDIUM|LOW"},
    ...
  ],
  "persons_of_interest": [
    {"description": "...", "first_seen_s": <number>, "last_seen_s": <number>, "notes": "..."}
  ],
  "anomalies_detected": [
    {"type": "...", "time_s": <number>, "description": "...", "severity": "HIGH|MEDIUM|LOW"}
  ],
  "geo_intelligence": {
    "estimated_location": {"lat": <number>, "lon": <number>, "confidence": <number>},
    "top_candidates": [{"lat": <number>, "lon": <number>, "probability": <number>}, ...],
    "assessment": "Brief assessment of location estimate reliability."
  },
  "acoustic_summary": {
    "total_events": <number>,
    "critical_events": ["List of CRITICAL severity events"],
    "assessment": "Brief assessment of audio threat landscape."
  },
  "identity_summary": {
    "unique_identities": <number>,
    "identities": [{"label": "...", "first_seen_s": <number>, "last_seen_s": <number>}],
    "assessment": "Brief note on identity tracking."
  },
  "evidence_quality": "GOOD | DEGRADED | POOR",
  "manipulation_assessment": {
    "deepfake_detected": <true|false>,
    "ai_generated": <true|false>,
    "notes": "..."
  },
  "recommended_next_steps": ["..."],
  "requires_human_review": <true|false>,
  "human_review_reason": "<null or reason string>"
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fused_to_text(fused: dict, max_chars: int = 8000, mode: str = "general") -> str:
    """
    Convert a fused timeline dict to a compact text representation
    for passing to the LLM within context limits.
    When mode="cyber" or cyber_summary is present, appends all cyber
    intelligence data (geo, acoustic, face re-id, alerts).
    """
    lines = []

    summary = fused.get("summary", {})
    lines.append(f"=== VIDEO METADATA ===")
    lines.append(f"Source: {fused.get('source_type', 'unknown')} | {fused.get('source_uri', '')}")
    lines.append(f"Duration: {summary.get('duration_s', 'unknown')}s")
    lines.append(f"Language: {summary.get('language', 'unknown')}")
    lines.append(f"Deepfake Flag: {fused.get('deepfake_flag', False)}")
    lines.append(f"AI Generated Flag: {fused.get('ai_generated_flag', False)}")
    lines.append(f"Total Scenes: {summary.get('total_scenes', 0)}")
    lines.append(f"Total Words Spoken: {summary.get('total_words', 0)}")
    lines.append("")

    # Full VL output
    if fused.get("full_vl_output"):
        lines.append("=== VISUAL ANALYSIS (Vision AI) ===")
        lines.append(fused["full_vl_output"][:2000])
        lines.append("")

    # Full transcript
    if fused.get("full_transcript"):
        lines.append("=== SPEECH TRANSCRIPT (ASR) ===")
        lines.append(fused["full_transcript"][:2000])
        lines.append("")

    # Scene-by-scene breakdown
    lines.append("=== SCENE-BY-SCENE TIMELINE ===")
    for scene in fused.get("fused_timeline", []):
        sid = scene.get("scene_id", 0)
        start = float(scene.get("start_s", scene.get("start_seconds", 0.0)))
        end = float(scene.get("end_s", scene.get("end_seconds", 0.0)))
        t = f"{start:.1f}s–{end:.1f}s"
        tags = ", ".join(scene.get("scene_tags", [])) or "none"
        lines.append(f"[Scene {sid}] {t} | Tags: {tags}")
        vl_desc = scene.get("vl_description") or (scene.get("content") if scene.get("event_type") == "object" else None)
        if vl_desc and vl_desc != "[See scene 0 for full analysis]":
            lines.append(f"  Visual: {vl_desc[:300]}")
        asr_txt = scene.get("asr_text") or (scene.get("content") if scene.get("event_type") == "speech" else None)
        if asr_txt:
            lines.append(f"  Speech: {asr_txt[:300]}")
        lines.append("")

    # ── Cyber Intelligence Data (cyber mode only) ─────────────────────────
    is_cyber = (mode == "cyber") or fused.get("cyber_summary") is not None
    if is_cyber:
        # Geo Estimation
        geo_result = fused.get("geo_result") or fused.get("cyber_summary", {}).get("geo")
        if geo_result and geo_result.get("gps"):
            gps = geo_result["gps"]
            lines.append("=== GEO ESTIMATION (GeoCLIP) ===")
            lines.append(f"Estimated Coordinates: ({gps.get('lat', 'N/A')}, {gps.get('lon', 'N/A')})")
            lines.append(f"Confidence: {gps.get('confidence', 'N/A')}")
            # Top candidate locations
            top_preds = geo_result.get("top_predictions", [])
            if top_preds:
                lines.append("Top Candidate Locations:")
                for i, pred in enumerate(top_preds[:5], 1):
                    lines.append(
                        f"  {i}. ({pred.get('lat', 'N/A')}, {pred.get('lon', 'N/A')}) "
                        f"probability={pred.get('probability', 'N/A')}"
                    )
            lines.append("")

        # Acoustic Events
        acoustic_result = fused.get("acoustic_result") or fused.get("cyber_summary", {}).get("acoustic")
        if acoustic_result and acoustic_result.get("events"):
            lines.append("=== ACOUSTIC EVENT DETECTION ===")
            lines.append(f"Backend: {acoustic_result.get('backend', 'unknown')}")
            lines.append(f"Total Events Detected: {len(acoustic_result['events'])}")
            for ev in acoustic_result["events"]:
                lines.append(
                    f"  [{ev.get('severity', 'UNKNOWN')}] {ev.get('event_type', 'unknown')} "
                    f"({ev.get('label', 'N/A')}): "
                    f"{ev.get('start_s', 'N/A')}s–{ev.get('end_s', 'N/A')}s "
                    f"confidence={ev.get('confidence', 'N/A')}"
                )
            lines.append("")

        # Face Re-ID & Identities
        face_reid_result = fused.get("face_reid_result") or fused.get("cyber_summary", {}).get("face_reid")
        if face_reid_result and face_reid_result.get("identities"):
            lines.append("=== FACE RE-IDENTIFICATION (InsightFace) ===")
            lines.append(f"Total Faces Detected: {face_reid_result.get('faces_detected', 0)}")
            lines.append(f"Unique Identities: {len(face_reid_result['identities'])}")
            for ident in face_reid_result["identities"]:
                label = ident.get("label", "Unknown")
                match_score = ident.get("match_score", "N/A")
                lines.append(
                    f"  Identity: {label} | "
                    f"First Seen: {ident.get('first_seen_s', 'N/A')}s | "
                    f"Last Seen: {ident.get('last_seen_s', 'N/A')}s | "
                    f"Match Score: {match_score}"
                )
            lines.append("")
        elif face_reid_result and face_reid_result.get("status") == "blocked":
            lines.append("=== FACE RE-IDENTIFICATION ===")
            lines.append(f"Status: BLOCKED — {face_reid_result.get('error', 'Governance not approved.')}")
            lines.append("")

        # Triggered Alerts
        alert_result = fused.get("alert_result")
        if alert_result and alert_result.get("alerts"):
            lines.append("=== TRIGGERED ALERTS ===")
            lines.append(f"Total Alerts: {alert_result['total_alerts']}")
            lines.append(f"Highest Severity: {alert_result.get('highest_severity', 'N/A')}")
            for alert in alert_result["alerts"]:
                lines.append(
                    f"  [{alert.get('severity', 'UNKNOWN')}] "
                    f"Source: {alert.get('source_step', 'N/A')} | "
                    f"Description: {alert.get('description', 'N/A')}"
                )
            lines.append("")

    result = "\n".join(lines)
    # Truncate to max_chars to stay within context window
    if len(result) > max_chars:
        result = result[:max_chars] + "\n[...truncated to fit context window...]"
    return result


def _call_text_brain(system_prompt: str, user_content: str) -> dict:
    """
    Call the Qwen2.5-7B Text Brain with a given system prompt and content.
    Returns parsed JSON dict, or raw text fallback.
    """
    try:
        from run_text_agent import load_text_model
        import torch

        model, tokenizer = load_text_model()
        device = "cuda" if torch.cuda.is_available() else "cpu"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ]

        text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer([text], return_tensors="pt").to(device)

        generated = model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        trimmed = [
            out[len(inp):] for inp, out in zip(inputs.input_ids, generated)
        ]
        output_text = tokenizer.batch_decode(trimmed, skip_special_tokens=True)[0]

        # Parse JSON
        raw = output_text.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw_output": output_text}

    except ImportError as e:
        return {"error": f"Text Brain not available: {e}"}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


# ─────────────────────────────────────────────────────────────────────────────
# CORE PIPELINE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def generate_output(
    fused: dict,
    user_question: str = "Summarize what happens in this video.",
    mode: str = "general",
) -> dict:
    """
    Run all three domain output stages on a fused timeline.

    Parameters
    ----------
    fused         : Output dict from fusion_agent.fuse_pipeline_outputs()
    user_question : The user's original question about the video.
    mode          : "general" | "cyber"

    Returns
    -------
    dict with keys:
      enrichment      - Stage 1 output (entities, conflicts, quality)
      analytics       - Stage 2 output (stats, user Q answer)
      final_output    - Stage 3 output (summary, highlights, recommendations)
      mode            - "general" | "cyber"
      generated_at    - ISO timestamp
      error           - null or error string
    """
    generated_at = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"  [Domain Output] Starting {mode.upper()} mode output generation…", flush=True)

    # Build the shared context block
    fused_text = _fused_to_text(fused, mode=mode)

    # ── Stage 1: Context Enrichment ────────────────────────────────────────
    print("  [Domain Output] Stage 1/3 — Context enrichment…", flush=True)
    enrichment = _call_text_brain(
        _CONTEXT_ENRICHMENT_PROMPT,
        f"=== FUSED VIDEO DATA ===\n{fused_text}\n\n"
        f"User question: {user_question}"
    )
    if "error" in enrichment and enrichment["error"]:
        print(f"  [Domain Output] ⚠️  Stage 1 error: {enrichment['error']}", flush=True)
    else:
        print("  [Domain Output] ✅ Stage 1 complete.", flush=True)

    # Add enrichment to context for next stage
    enrichment_text = json.dumps(enrichment, ensure_ascii=False)

    # ── Stage 2: Analytics ─────────────────────────────────────────────────
    print("  [Domain Output] Stage 2/3 — Analytics & Q&A…", flush=True)
    analytics = _call_text_brain(
        _ANALYTICS_PROMPT,
        f"=== FUSED VIDEO DATA ===\n{fused_text}\n\n"
        f"=== ENRICHMENT FINDINGS ===\n{enrichment_text[:1000]}\n\n"
        f"User question: {user_question}"
    )
    if "error" in analytics and analytics["error"]:
        print(f"  [Domain Output] ⚠️  Stage 2 error: {analytics['error']}", flush=True)
    else:
        print("  [Domain Output] ✅ Stage 2 complete.", flush=True)

    analytics_text = json.dumps(analytics, ensure_ascii=False)

    # ── Stage 3: Final Structured Output ──────────────────────────────────
    print("  [Domain Output] Stage 3/3 — Final output generation…", flush=True)
    output_prompt = (
        _DOMAIN_OUTPUT_PROMPT_CYBER if mode == "cyber"
        else _DOMAIN_OUTPUT_PROMPT_GENERAL
    )
    final_output = _call_text_brain(
        output_prompt,
        f"=== FUSED VIDEO DATA ===\n{fused_text}\n\n"
        f"=== ENRICHMENT FINDINGS ===\n{enrichment_text[:800]}\n\n"
        f"=== ANALYTICS ===\n{analytics_text[:800]}\n\n"
        f"User question: {user_question}"
    )
    if "error" in final_output and final_output["error"]:
        print(f"  [Domain Output] ⚠️  Stage 3 error: {final_output['error']}", flush=True)
    else:
        print("  [Domain Output] ✅ Stage 3 complete.", flush=True)

    print("  [Domain Output] ✅ All stages done.", flush=True)

    return {
        "enrichment":   enrichment,
        "analytics":    analytics,
        "final_output": final_output,
        "mode":         mode,
        "user_question": user_question,
        "generated_at": generated_at,
        "error":        None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Chorus Domain Output Agent — Generate final video summary."
    )
    p.add_argument("--fused",    required=True, help="Path to fused timeline JSON (from fusion_agent).")
    p.add_argument("--question", default="Summarize what happens in this video.",
                   help="User question to answer.")
    p.add_argument("--mode",     default="general", choices=["general", "cyber"])
    p.add_argument("--output",   default=None, help="Save output JSON to this path.")
    p.add_argument("--pretty",   action="store_true")
    args = p.parse_args()

    with open(args.fused, encoding="utf-8") as f:
        fused_data = json.load(f)

    result = generate_output(
        fused=fused_data,
        user_question=args.question,
        mode=args.mode,
    )

    out = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)
    print(out)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"\n  [Domain Output] Saved to: {args.output}", flush=True)
