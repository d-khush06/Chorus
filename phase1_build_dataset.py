"""
phase1_build_dataset.py
========================
Generates Chorus seed rows for Steps 6, 12, 15, 17 and merges them
with the existing Hermes data (chorus_negotiations.json).

Output: chorus_v2.json   (~5,700 rows, ~15 MB)
Time  : ~30 seconds, CPU only, no GPU needed

Run:
    python phase1_build_dataset.py
"""

import os, sys, json, random, codecs

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
EXISTING_DATA = os.path.join(BASE_DIR, "chorus_negotiations.json")
OUTPUT_FILE   = os.path.join(BASE_DIR, "chorus_v2.json")
OVERSAMPLE_X  = 10
RANDOM_SEED   = 42
random.seed(RANDOM_SEED)

# ─────────────────────────────────────────────────────────────────────────────
ALL_TOOLS = [
    "source_adapters","quality_gate","dedup_check","manipulation_detection",
    "project_manager","scene_segmentation","perception_agent","asr_agent",
    "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
    "quality_verification","correlation_agent","analytics_query_agent",
    "review_queue","domain_output",
]

def _row(scenario, mode, category, called, excluded,
         extra=None, escalated=False, esc_reason=None, sys_prompt=None):
    sys_prompt = sys_prompt or (
        "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
        "Decide which tools to call, in what order. Return only structured JSON."
    )
    dlg = [{"speaker":"orchestrator","turn":"opening",
            "content":f"Initiating Chorus pipeline for: {scenario}"}]
    for t in (called + [x for x in excluded if x not in called]):
        is_c = t in called
        c    = round(random.uniform(0.82,0.97),2) if is_c else round(random.uniform(0.07,0.22),2)
        dlg.append({"speaker":t,"turn":"self_report",
                    "content": f"I am [{t}]. {'Ready to handle this request.' if is_c else 'Not needed for this scenario.'}",
                    "confidence":c})
    if extra:
        dlg.extend(extra)
    tc = [{"step":i+1,"tool":t,"tier":"n/a","arguments":{}} for i,t in enumerate(called)]
    dlg.append({"speaker":"orchestrator","turn":"final_decision",
                "content":json.dumps({"mode":mode,"tool_calls":tc,"excluded":excluded,
                                      "reasoning_summary":f"Selected:{called}. Excluded:{excluded}."})})
    return {"source_dataset":"chorus_seed","scenario":scenario,"mode":mode,
            "category":category,"dialogue":dlg,
            "escalated":escalated,"escalation_reason":esc_reason,
            "_system_prompt":sys_prompt}


# ── Step 6: Orchestrator routing rows ────────────────────────────────────────

def gen_step6():
    rows = []
    FULL_PIPELINE = [
        "source_adapters","dedup_check","quality_gate","manipulation_detection",
        "project_manager","scene_segmentation","perception_agent","asr_agent",
        "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
        "quality_verification","correlation_agent","analytics_query_agent","domain_output",
    ]
    NO_CYBER = ["geo_estimation_agent","face_reid_agent","chapter_highlight_detection","review_queue"]

    # 1. Happy path — general full pipeline
    subjects = ["news broadcast","documentary","sports highlight","product demo",
                "interview","lecture","podcast video","corporate presentation"]
    for i, subj in enumerate(subjects):
        rows.append(_row(
            f"A local MP4 {subj} is uploaded. English audio, no known duplicates, quality passes.",
            "general","multi_step", FULL_PIPELINE, NO_CYBER))

    # 2. Early halt — duplicate found
    for i in range(8):
        called   = ["source_adapters","dedup_check"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_row(
            f"Uploaded video #{i+1}: perceptual hash matches existing archive entry. Stop immediately.",
            "general","multi_step", called, excluded,
            extra=[{"speaker":"dedup_check","turn":"response",
                    "content":"DUPLICATE DETECTED. halt_pipeline=True. No downstream steps run.",
                    "confidence":0.99}]))

    # 3. Quality Gate FAIL — stop before Step 4
    fails = [
        "timestamp integrity violation — frames out of video bounds",
        "confidence floor breach — events below 0.55 threshold",
        "cross-source contradiction — 2+ exclusive tokens conflict",
        "45-second coverage gap detected in VOD timeline",
        "hallucination guard triggered — unrecognised source signal",
        "format completeness failure — missing required fields",
        "speaker consistency fail — generic placeholder speakers detected",
    ]
    for fail in fails:
        called   = ["source_adapters","dedup_check","quality_gate"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_row(
            f"Clip passes dedup but Quality Gate raises FAIL: {fail}",
            "general","multi_step", called, excluded,
            extra=[{"speaker":"quality_gate","turn":"response",
                    "content":f"FAIL: {fail}. halt_pipeline=True.","confidence":0.99}]))

    # 4. Manipulation flagged — still run Step 5 and 7
    for i in range(6):
        called   = ["source_adapters","dedup_check","quality_gate",
                    "manipulation_detection","project_manager","scene_segmentation","review_queue"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_row(
            f"Video #{i+1} passes quality gate. Manipulation detection verdict: SEND_TO_REVIEW_QUEUE. "
            "project_manager still opens case. scene_segmentation still runs.",
            "general","multi_step", called, excluded,
            extra=[{"speaker":"manipulation_detection","turn":"response",
                    "content":"SEND_TO_REVIEW_QUEUE. Score 0.72 > threshold 0.30. "
                    "project_manager must open case. scene_segmentation still runs.",
                    "confidence":0.94}]))

    # 5. Cyber mode — geo + face_reid unlocked
    for i in range(6):
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection",
                    "project_manager","scene_segmentation","perception_agent","asr_agent",
                    "diarization_agent","ocr_agent","geo_estimation_agent","face_reid_agent",
                    "context_enrichment","fusion_agent","quality_verification",
                    "correlation_agent","analytics_query_agent","domain_output"]
        excluded = ["chapter_highlight_detection","audio_description_agent"]
        rows.append(_row(
            f"Security footage #{i+1} submitted for forensic analysis. mode=cyber, governance_approved=true.",
            "cyber","mode_gated", called, excluded))

    # 6. Cyber — face_reid blocked (no governance)
    for i in range(5):
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection",
                    "project_manager","scene_segmentation","perception_agent","asr_agent",
                    "geo_estimation_agent","context_enrichment","fusion_agent","domain_output"]
        excluded = ["face_reid_agent","chapter_highlight_detection","audio_description_agent","review_queue"]
        rows.append(_row(
            f"Incident clip #{i+1}: mode=cyber, governance_approved NOT set. face_reid_agent must NOT run.",
            "cyber","mode_gated", called, excluded,
            extra=[{"speaker":"face_reid_agent","turn":"self_report",
                    "content":"governance_approved=false detected. I must NOT run without legal approval. Excluding.",
                    "confidence":0.04}]))

    # 7. Tier escalation
    for i in range(5):
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection",
                    "project_manager","scene_segmentation","perception_agent","perception_agent",
                    "asr_agent","diarization_agent","ocr_agent","context_enrichment",
                    "fusion_agent","domain_output"]
        excluded = ["geo_estimation_agent","face_reid_agent","review_queue"]
        rows.append(_row(
            f"Video #{i+1}: perception_agent Tier 1 returns confidence 0.61 < 0.75 threshold. "
            "Must escalate to Tier 2 before context_enrichment.",
            "general","multi_step", called, excluded,
            escalated=True, esc_reason="low_confidence"))

    # 8. RTSP live stream (skip dedup)
    for i in range(5):
        called   = ["source_adapters","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","diarization_agent",
                    "context_enrichment","fusion_agent","quality_verification","domain_output"]
        excluded = ["dedup_check","geo_estimation_agent","face_reid_agent","chapter_highlight_detection"]
        rows.append(_row(
            f"Live RTSP stream #{i+1}: source_type=live_rtsp. dedup_check MUST be skipped. "
            "quality_verification runs on rolling cadence.",
            "general","multi_step", called, excluded,
            extra=[{"speaker":"dedup_check","turn":"self_report",
                    "content":"source_type=live_rtsp. Chorus Rule 7: I must be skipped for live streams.",
                    "confidence":0.02}]))

    # 9. Public figure — mandatory manipulation + extra quality_verification pass
    figures = ["politician","celebrity","public official","world leader","sports star"]
    for fig in figures:
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection",
                    "project_manager","scene_segmentation","perception_agent","asr_agent",
                    "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
                    "quality_verification","correlation_agent","analytics_query_agent",
                    "domain_output","quality_verification"]
        excluded = ["geo_estimation_agent","face_reid_agent","review_queue"]
        rows.append(_row(
            f"Widely-shared clip of a well-known {fig}. "
            "Rule 6: manipulation_detection mandatory. Extra quality_verification pass after domain_output.",
            "general","multi_step", called, excluded))

    print(f"  Step 6  routing    : {len(rows)} rows")
    return rows


# ── Step 12: Context enrichment rows ─────────────────────────────────────────

def gen_step12():
    SYS = ("You are the CONTEXT ENRICHMENT agent for the Chorus pipeline. "
           "Cross-check perception, ASR, and OCR outputs. Find conflicts. "
           "Return structured JSON: {status, conflicts, cleaned_output, confidence}.")
    rows = []
    cases = [
        # (scenario, status, conflict_desc_or_None)
        ("All three agents agree on scene content. No conflicts.",
         "clean", None),
        ("OCR finds blank text (blank screen). No conflict — blank OCR is valid.",
         "clean", None),
        ("Documentary — all agents report consistently on wildlife scene.",
         "clean", None),
        ("ASR says 'no weapons visible'. OCR reads 'ARMED RESPONSE UNIT'. Safety-critical contradiction.",
         "conflict_detected", "ASR denies weapons; OCR confirms armed unit label"),
        ("ASR: speaker said 'John Smith'. OCR badge reads 'Mark Davies — Senior Officer'. Name mismatch.",
         "conflict_detected", "Name mismatch: spoken John Smith vs badge Mark Davies"),
        ("ASR: 'this happened on 14th March'. OCR graphic: '14 May 2026'. Date conflict.",
         "conflict_detected", "Date conflict: spoken March vs displayed May"),
        ("Perception: empty room. ASR: human voice transcribed. Physical impossibility.",
         "conflict_detected", "No person detected visually but human speech transcribed"),
        ("Perception: bright outdoor daytime. ASR: 'it was late at night, very dark'.",
         "conflict_detected", "Visual shows daytime; speech describes nighttime"),
        ("Perception confidence 0.58 — below Tier 2 threshold 0.75. Must escalate.",
         "escalate_tier2", None),
        ("ASR confidence 0.62 on heavily accented speech. Escalate to Whisper Tier 2.",
         "escalate_tier2", None),
        ("Perception reports 'a flying car in the sky'. Physically implausible — hallucination.",
         "hallucination_flagged", "Flying car detection implausible — likely hallucination"),
    ]
    for scenario, status, conflict_desc in cases:
        conflict_list = [{"description": conflict_desc}] if conflict_desc else []
        dlg = [
            {"speaker":"orchestrator","turn":"opening",
             "content":f"Context enrichment for: {scenario}"},
            {"speaker":"user","turn":"input",
             "content":json.dumps({"scenario":scenario})},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({
                 "status": status,
                 "conflicts": conflict_list,
                 "cleaned_output": {} if status == "clean" else None,
                 "confidence": 0.95 if status == "clean" else 0.11
             })},
        ]
        rows.append({
            "source_dataset":"chorus_seed","scenario":scenario,
            "mode":"general","category":"context_enrichment","dialogue":dlg,
            "escalated":"escalate" in status,
            "escalation_reason":"low_confidence" if "escalate" in status else None,
            "_system_prompt": SYS,
        })
    print(f"  Step 12 enrichment : {len(rows)} rows")
    return rows


# ── Step 15: Analytics Q&A rows ───────────────────────────────────────────────

def gen_step15():
    SYS = ("You are the ANALYTICS & QUERY agent for Chorus. "
           "Answer grounded questions using ONLY the fused_timeline. "
           "Cite evidence (scene_id, timestamp). Never invent data. "
           "Return JSON: {answer, evidence}.")
    rows = []
    qas = [
        ("How many unique speakers appear in this video?",
         '{"speakers":["SPEAKER_00","SPEAKER_01","SPEAKER_02"]}',
         "3 unique speakers: SPEAKER_00, SPEAKER_01, SPEAKER_02."),
        ("Which speaker had the most screen time?",
         '{"speaker_time":{"SPEAKER_00":142.3,"SPEAKER_01":67.8}}',
         "SPEAKER_00 with 142.3 seconds (≈2 min 22 s)."),
        ("How long did SPEAKER_01 speak in total?",
         '{"speaker_time":{"SPEAKER_00":90.0,"SPEAKER_01":45.5}}',
         "SPEAKER_01 spoke for 45.5 seconds in total."),
        ("How many scenes were detected?",
         '{"scenes":[{"scene_id":0},{"scene_id":1},{"scene_id":2},{"scene_id":3}]}',
         "4 scenes were detected by scene_segmentation."),
        ("What is the total video duration?",
         '{"scenes":[{"scene_id":0,"start_seconds":0.0,"end_seconds":183.7}]}',
         "Total duration is 183.7 seconds (≈3 min 4 s)."),
        ("Was a vehicle detected in any scene?",
         '{"scenes":[{"scene_id":0,"objects":["person"]},{"scene_id":1,"objects":["vehicle","street"]}]}',
         "Yes. A vehicle was detected in scene 1."),
        ("Was a weapon detected at any point?",
         '{"scenes":[{"scene_id":0,"objects":["person","table"]}]}',
         "No weapon was detected in any scene according to the fused timeline."),
        ("What text appeared on screen?",
         '{"scenes":[{"scene_id":0,"ocr_text":"CITY HALL"},{"scene_id":1,"ocr_text":"14 SEP 2026"}]}',
         "Scene 0: 'CITY HALL'. Scene 1: '14 SEP 2026'."),
        ("Did the speaker mention climate change?",
         '{"scenes":[{"scene_id":0,"transcript":"Good morning. Thank you for coming today."}]}',
         "Climate change is not mentioned in the available transcript."),
        ("Who is the person in the video?",
         '{"face_reid":null}',
         "Identity cannot be determined. face_reid_agent was not run."),
        ("Give me a summary of key statistics.",
         '{"total_duration_s":245.0,"scenes":[{},{},{}],"speaker_time":{"SPEAKER_00":180.0,"SPEAKER_01":65.0}}',
         "Duration: 245s. Scenes: 3. Speakers: SPEAKER_00 (180s), SPEAKER_01 (65s)."),
    ]
    for question, timeline, answer in qas:
        dlg = [
            {"speaker":"orchestrator","turn":"opening","content":f"Analytics Q&A: {question}"},
            {"speaker":"user","turn":"input","content":json.dumps({"fused_timeline":json.loads(timeline),"question":question})},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({"answer":answer,"evidence":[{"source":"fused_timeline"}]})},
        ]
        rows.append({
            "source_dataset":"chorus_seed","scenario":question,
            "mode":"general","category":"analytics_query","dialogue":dlg,
            "escalated":False,"escalation_reason":None,"_system_prompt":SYS,
        })
    print(f"  Step 15 analytics  : {len(rows)} rows")
    return rows


# ── Step 17: Domain output / narration rows ───────────────────────────────────

def gen_step17():
    SYS = ("You are the DOMAIN OUTPUT agent for Chorus. "
           "Write a factual narrated summary from the fused_timeline ONLY. "
           "Include a warning if manipulation was detected. "
           "Return JSON: {output_format, narration, confidence}.")
    rows = []
    cases = [
        ("3-minute English news broadcast, 2 speakers, no flags.",
         "narrative_summary",
         "This 3-minute news broadcast (4 scenes, 2 speakers) covers a city council announcement. "
         "No manipulation signals detected.", 0.95),
        ("Video flagged by manipulation detection (SEND_TO_REVIEW_QUEUE, score 0.74).",
         "narrative_summary",
         "⚠️ MANIPULATION WARNING: This video was flagged (deepfake score 0.74). "
         "Content has been routed to the review queue. Human verification required.", 0.41),
        ("Security camera clip, cyber mode, geo-estimated central London, no face-reid.",
         "forensic_summary",
         "90-second security clip (cyber mode). Geo-estimate: central London (85% confidence). "
         "No speech detected. Face re-identification not performed (governance not approved). "
         "No manipulation detected.", 0.88),
        ("10-minute interview, 3 speakers, topic: Future of AI.",
         "narrative_summary",
         "This 10-minute panel interview on 'Future of AI' (8 scenes, 3 speakers): "
         "SPEAKER_00 (320s), SPEAKER_01 (180s), SPEAKER_02 (100s). No manipulation detected.", 0.93),
        ("Live RTSP 30-second chunk from traffic camera, stream position 3600-3630s.",
         "live_stream_chunk_summary",
         "Live stream chunk (3600–3630s). 2 scenes. Objects: vehicles, road. "
         "No speech. No manipulation signals. Processing continues on rolling cadence.", 0.91),
        ("Silent documentary b-roll, no audio, wildlife and forest footage.",
         "narrative_summary",
         "4-minute silent documentary b-roll (6 scenes). Content: wildlife, forest, river, aerial shots. "
         "No spoken audio or on-screen text detected. No manipulation signals.", 0.94),
        ("30-second social media product demo, single speaker.",
         "narrative_summary",
         "30-second product demo (1 scene, 1 speaker). No manipulation detected.", 0.97),
        ("Video with NO_FACES_DETECTED from manipulation scanner.",
         "narrative_summary",
         "3-minute video (3 scenes). No human faces detected — deepfake check not applicable. "
         "Content: landscape, buildings, text overlays. No manipulation concerns.", 0.96),
    ]
    for scenario, fmt, narration, conf in cases:
        dlg = [
            {"speaker":"orchestrator","turn":"opening","content":f"Domain output for: {scenario}"},
            {"speaker":"user","turn":"input","content":json.dumps({"fused_timeline":{},"scenario":scenario})},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({"output_format":fmt,"narration":narration,"confidence":conf})},
        ]
        rows.append({
            "source_dataset":"chorus_seed","scenario":scenario,
            "mode":"general","category":"domain_output","dialogue":dlg,
            "escalated":False,"escalation_reason":None,"_system_prompt":SYS,
        })
    print(f"  Step 17 narration  : {len(rows)} rows")
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("PHASE 1 — BUILD chorus_v2.json")
    print("="*60)

    # Load existing Hermes data
    print(f"\n[1/3] Loading {EXISTING_DATA} ...")
    if not os.path.isfile(EXISTING_DATA):
        print("ERROR: chorus_negotiations.json not found.")
        print("Run: python prepare_negotiation_dataset.py  first.")
        sys.exit(1)
    with codecs.open(EXISTING_DATA, "r", encoding="utf-8") as f:
        hermes = json.load(f)
    print(f"      Loaded {len(hermes)} Hermes rows.")

    # Generate all Chorus seed rows
    print("\n[2/3] Generating Chorus seed rows ...")
    seed = gen_step6() + gen_step12() + gen_step15() + gen_step17()
    print(f"\n      Raw seed rows      : {len(seed)}")

    # Oversample + merge
    oversampled = seed * OVERSAMPLE_X
    random.shuffle(oversampled)
    merged = hermes + oversampled
    random.shuffle(merged)
    print(f"      Oversampled (×{OVERSAMPLE_X})  : {len(oversampled)}")
    print(f"      + Hermes           : {len(hermes)}")
    print(f"      Grand total        : {len(merged)}")

    # Save
    print(f"\n[3/3] Saving to {OUTPUT_FILE} ...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    size_mb = round(os.path.getsize(OUTPUT_FILE) / 1024 / 1024, 1)
    print(f"      Saved! ({size_mb} MB)")

    print("\n" + "="*60)
    print("PHASE 1 DONE.")
    print(f"Output: {OUTPUT_FILE}")
    print("Next  : python phase2_train.py")
    print("="*60)
