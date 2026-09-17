"""
train_chorus_v3_unsloth.py
===========================
Unsloth-optimised replacement for train_chorus_v2.py.

Why Unsloth?
  * 2x faster training than vanilla transformers+peft
  * ~60 % less VRAM  -> no more hangs on RTX A2000 12 GB
  * Drop-in: same LoRA config, same dataset, same output format
  * Works with trl SFTTrainer

Install Unsloth FIRST (one-time):
    pip install unsloth

Run:
    python train_chorus_v3_unsloth.py

Hardware target : RTX A2000 12 GB VRAM
Output adapter  : ./orchestrator_lora_v3/
"""

import os, sys, json, random, datetime, subprocess

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
EXISTING_DATA = os.path.join(BASE_DIR, "chorus_negotiations.json")
MERGED_DATA   = os.path.join(BASE_DIR, "chorus_v3.json")
MODEL_PATH    = os.path.join(BASE_DIR, "models", "Qwen2.5-7B-Browser-Agent-Merged")
OUTPUT_DIR    = os.path.join(BASE_DIR, "orchestrator_lora_v3")

OVERSAMPLE_X  = 10
RANDOM_SEED   = 42
MAX_SEQ_LEN   = 2048   # safe on 12 GB with Unsloth (was 1024 in v2)


# ──────────────────────────────────────────────────────────────────────────────
# STEP 0 — DEPENDENCY CHECK
# ──────────────────────────────────────────────────────────────────────────────

def install_deps():
    for pkg in ["trl", "datasets", "accelerate", "tqdm"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[setup] Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
    try:
        import unsloth  # noqa: F401
    except ImportError:
        print("\n" + "="*65)
        print("  Unsloth is NOT installed. Run:")
        print("    pip install unsloth")
        print("="*65 + "\n")
        sys.exit(1)

install_deps()

from datasets import load_dataset  # noqa: E402 (after install)


# ──────────────────────────────────────────────────────────────────────────────
# CHORUS SEED-ROW HELPERS  (identical logic to v2)
# ──────────────────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    "source_adapters", "quality_gate", "dedup_check", "manipulation_detection",
    "project_manager", "scene_segmentation", "perception_agent", "asr_agent",
    "diarization_agent", "ocr_agent", "context_enrichment", "fusion_agent",
    "quality_verification", "correlation_agent", "analytics_query_agent",
    "review_queue", "domain_output",
]


def _make_row(scenario, mode, category, called_tools, excluded_tools,
              extra_dialogue=None, escalated=False, escalation_reason=None,
              source="chorus_seed"):
    opening = (
        f"Initiating Chorus pipeline for: {scenario}\n\n"
        f"[Mode: {mode}] Evaluating which tools to call, in order."
    )
    dialogue = [{"speaker": "orchestrator", "turn": "opening", "content": opening}]
    for tool in (called_tools + excluded_tools):
        is_called = tool in called_tools
        conf = round(random.uniform(0.80, 0.97), 2) if is_called else round(random.uniform(0.08, 0.25), 2)
        report = (
            f"I am [{tool}]. Ready to handle this stage. Confidence: {conf}."
            if is_called else
            f"I am [{tool}]. This scenario does not require my capabilities. Confidence: {conf}."
        )
        dialogue.append({"speaker": tool, "turn": "self_report", "content": report, "confidence": conf})
    if extra_dialogue:
        dialogue.extend(extra_dialogue)
    tool_calls = [{"step": i+1, "tool": t, "tier": "n/a", "arguments": {}} for i, t in enumerate(called_tools)]
    decision = json.dumps({
        "mode": mode, "tool_calls": tool_calls, "excluded": excluded_tools,
        "reasoning_summary": f"Selected: {called_tools}. Excluded: {excluded_tools}. Order follows Chorus dependency chain."
    })
    dialogue.append({"speaker": "orchestrator", "turn": "final_decision", "content": decision})
    return {
        "source_dataset": source, "scenario": scenario, "mode": mode,
        "category": category, "dialogue": dialogue,
        "escalated": escalated, "escalation_reason": escalation_reason,
    }


def generate_step6_routing_rows():
    rows = []
    durations = ["2-minute", "5-minute", "10-minute", "30-second"]
    subjects  = ["news broadcast", "documentary clip", "sports highlight",
                 "product demo", "interview", "lecture recording"]

    # Standard general pipeline
    for i in range(8):
        scenario = f"A {random.choice(durations)} {random.choice(subjects)} uploaded as MP4. English audio, no duplicates, quality checks pass."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","diarization_agent","ocr_agent",
                    "context_enrichment","fusion_agent","quality_verification","correlation_agent",
                    "analytics_query_agent","domain_output"]
        excluded = ["geo_estimation_agent","face_reid_agent","chapter_highlight_detection","review_queue"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded))

    # Early halt — duplicate
    for i in range(8):
        scenario = f"Video uploaded. Perceptual hash matches existing entry (duplicate #{i+1}). Stop immediately."
        called   = ["source_adapters", "dedup_check"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{"speaker":"dedup_check","turn":"response",
                "content":"DUPLICATE DETECTED. halt_pipeline=True. All downstream steps skipped.","confidence":0.99}]))

    # Quality gate fail
    issues = ["timestamp integrity violation","confidence floor breach","cross-source contradiction",
              "coverage gap of 120s","hallucination guard triggered","format completeness failure",
              "speaker consistency check failed"]
    for i in range(7):
        scenario = f"Clip passes dedup but Quality Gate FAIL: {issues[i]}. Stop before manipulation detection."
        called   = ["source_adapters","dedup_check","quality_gate"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{"speaker":"quality_gate","turn":"response",
                "content":f"FAIL: {issues[i]}. halt_pipeline=True.","confidence":0.99}]))

    # Manipulation -> review queue
    for i in range(6):
        scenario = f"Video #{i+1} passes quality gate. Manipulation detection flags it (SEND_TO_REVIEW_QUEUE). PM opens case."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection",
                    "project_manager","scene_segmentation","review_queue"]
        excluded = [t for t in ALL_TOOLS if t not in called]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{"speaker":"manipulation_detection","turn":"response",
                "content":"Verdict: SEND_TO_REVIEW_QUEUE. Deepfake 0.72 > threshold 0.30. PM opens case; scene segmentation runs.","confidence":0.94}]))

    # Cyber mode — full
    for i in range(6):
        scenario = f"Security footage #{i+1} — mode=cyber, governance_approved=true. Geo+face_reid required."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","diarization_agent","ocr_agent",
                    "geo_estimation_agent","face_reid_agent","context_enrichment","fusion_agent",
                    "quality_verification","correlation_agent","analytics_query_agent","domain_output"]
        excluded = ["chapter_highlight_detection","audio_description_agent"]
        rows.append(_make_row(scenario, "cyber", "mode_gated", called, excluded))

    # Cyber mode — no governance
    for i in range(5):
        scenario = f"Incident footage #{i+1} — cyber mode, governance_approved NOT set. face_reid must NOT be called."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","geo_estimation_agent",
                    "context_enrichment","fusion_agent","domain_output"]
        excluded = ["face_reid_agent","chapter_highlight_detection","audio_description_agent","review_queue"]
        rows.append(_make_row(scenario, "cyber", "mode_gated", called, excluded,
            extra_dialogue=[{"speaker":"face_reid_agent","turn":"self_report",
                "content":"governance_approved=false. I MUST NOT run. Excluding myself.","confidence":0.05}]))

    # Tier escalation
    for i in range(5):
        scenario = f"Video #{i+1}: perception_agent Tier1 conf=0.61 < 0.75. Escalate to Tier2 before context_enrichment."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","perception_agent","asr_agent","diarization_agent",
                    "ocr_agent","context_enrichment","fusion_agent","domain_output"]
        excluded = ["geo_estimation_agent","face_reid_agent","review_queue"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded,
                              escalated=True, escalation_reason="low_confidence"))

    # RTSP live stream
    for i in range(5):
        scenario = f"Live RTSP stream #{i+1} — dedup_check SKIPPED. quality_verification on rolling cadence."
        called   = ["source_adapters","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","diarization_agent",
                    "context_enrichment","fusion_agent","quality_verification","domain_output"]
        excluded = ["dedup_check","geo_estimation_agent","face_reid_agent","chapter_highlight_detection"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded,
            extra_dialogue=[{"speaker":"dedup_check","turn":"self_report",
                "content":"source_type=live_rtsp. Chorus Rule 7: skip for live RTSP. Excluding myself.","confidence":0.02}]))

    # Public figure — double quality_verification
    subjects_pf = ["politician","celebrity","public official","world leader","sports star"]
    for i in range(5):
        scenario = f"Video of {subjects_pf[i%5]}. Rule 6: manipulation_detection mandatory + extra quality_verification."
        called   = ["source_adapters","dedup_check","quality_gate","manipulation_detection","project_manager",
                    "scene_segmentation","perception_agent","asr_agent","diarization_agent","ocr_agent",
                    "context_enrichment","fusion_agent","quality_verification","correlation_agent",
                    "analytics_query_agent","domain_output","quality_verification"]
        excluded = ["geo_estimation_agent","face_reid_agent","review_queue"]
        rows.append(_make_row(scenario, "general", "multi_step", called, excluded))

    print(f"  [Step 6 seed] Generated {len(rows)} routing rows.")
    return rows


def generate_step12_enrichment_rows():
    rows = []
    SYSTEM = ("You are the CONTEXT ENRICHMENT agent for the Chorus pipeline. "
              "Cross-check outputs from perception_agent, asr_agent, and ocr_agent. "
              "Identify conflicts, resolve or flag them, return cleaned unified JSON.")
    scenarios = [
        {"s":"All three agents agree — no conflicts.",
         "u":'{"perception":{"objects":["podium","microphone"]},"asr":{"transcript":"Good morning."},"ocr":{"text":"City Hall"}}',
         "a":'{"status":"clean","conflicts":[],"cleaned_output":{"objects":["podium","microphone"],"transcript":"Good morning.","on_screen_text":"City Hall"},"confidence":0.96}'},
        {"s":"Perception and ASR agree. OCR blank — valid.",
         "u":'{"perception":{"objects":["crowd","banner"]},"asr":{"transcript":"We demand change."},"ocr":{"text":""}}',
         "a":'{"status":"clean","conflicts":[],"cleaned_output":{"objects":["crowd","banner"],"transcript":"We demand change.","on_screen_text":""},"confidence":0.94}'},
        {"s":"All agents confident on documentary scene.",
         "u":'{"perception":{"objects":["wildlife","river"]},"asr":{"transcript":"The Amazon basin spans 5.5M km2."},"ocr":{"text":"Amazon Rainforest 2024"}}',
         "a":'{"status":"clean","conflicts":[],"cleaned_output":{"objects":["wildlife","river"],"transcript":"The Amazon basin spans 5.5M km2.","on_screen_text":"Amazon Rainforest 2024"},"confidence":0.97}'},
        {"s":"ASR no weapons; OCR reads ARMED RESPONSE UNIT — contradiction.",
         "u":'{"asr":{"transcript":"no weapons visible"},"ocr":{"text":"ARMED RESPONSE UNIT"}}',
         "a":'{"status":"conflict_detected","conflicts":[{"source_a":"asr_agent","source_b":"ocr_agent","description":"ASR denies weapons; OCR confirms armed unit label","resolution":"flag_for_review"}],"cleaned_output":null,"confidence":0.12}'},
        {"s":"ASR: John Smith. OCR badge: Mark Davies — name mismatch.",
         "u":'{"asr":{"transcript":"My name is John Smith"},"ocr":{"text":"Mark Davies Senior Officer"}}',
         "a":'{"status":"conflict_detected","conflicts":[{"source_a":"asr_agent","source_b":"ocr_agent","description":"Name mismatch: spoken John Smith vs badge Mark Davies","resolution":"flag_for_review"}],"cleaned_output":null,"confidence":0.15}'},
        {"s":"ASR: 14th March; OCR shows 14 May — date conflict.",
         "u":'{"asr":{"transcript":"This happened on 14th March"},"ocr":{"text":"14 May 2026"}}',
         "a":'{"status":"conflict_detected","conflicts":[{"source_a":"asr_agent","source_b":"ocr_agent","description":"Date conflict: spoken March vs displayed May","resolution":"flag_for_review"}],"cleaned_output":null,"confidence":0.11}'},
        {"s":"Perception: no person in frame. ASR: human voice detected — impossibility.",
         "u":'{"perception":{"objects":["empty room","chair"]},"asr":{"transcript":"Hello, is anyone there?"}}',
         "a":'{"status":"conflict_detected","conflicts":[{"source_a":"perception_agent","source_b":"asr_agent","description":"No person visually but human speech transcribed","resolution":"escalate_tier2"}],"cleaned_output":null,"confidence":0.09}'},
        {"s":"Perception: outdoor daylight. ASR: late at night, very dark.",
         "u":'{"perception":{"scene":"outdoor bright sunlight daytime"},"asr":{"transcript":"It was late at night very dark"}}',
         "a":'{"status":"conflict_detected","conflicts":[{"source_a":"perception_agent","source_b":"asr_agent","description":"Visual: daytime; speech: nighttime","resolution":"flag_for_review"}],"cleaned_output":null,"confidence":0.10}'},
        {"s":"Perception confidence 0.58 — escalate to Tier2.",
         "u":'{"perception":{"objects":["vehicle?","person?"],"confidence":0.58}}',
         "a":'{"status":"escalate_tier2","conflicts":[],"reason":"perception_agent confidence 0.58 below 0.75","cleaned_output":null}'},
        {"s":"ASR confidence 0.62 on accented speech — escalate to Whisper-large-v3.",
         "u":'{"asr":{"transcript":"[unclear]","confidence":0.62}}',
         "a":'{"status":"escalate_tier2","conflicts":[],"reason":"asr_agent confidence 0.62 below 0.75","cleaned_output":null}'},
        {"s":"Perception reports flying car — hallucination guard triggers.",
         "u":'{"perception":{"objects":["flying car","skyscraper"]}}',
         "a":'{"status":"hallucination_flagged","conflicts":[{"source_a":"perception_agent","description":"Flying car implausible — hallucination","resolution":"reject_artifact"}],"cleaned_output":null,"confidence":0.05}'},
    ]
    for s in scenarios:
        dialogue = [
            {"speaker":"orchestrator","turn":"opening","content":f"Running context enrichment for: {s['s']}"},
            {"speaker":"user","turn":"input","content":s["u"]},
            {"speaker":"orchestrator","turn":"final_decision","content":s["a"]},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":s["s"],"mode":"general",
                     "category":"context_enrichment","dialogue":dialogue,
                     "escalated":"escalate" in s["a"],
                     "escalation_reason":"low_confidence" if "escalate" in s["a"] else None,
                     "_system_prompt":SYSTEM})
    print(f"  [Step 12 seed] Generated {len(rows)} enrichment rows.")
    return rows


def generate_step15_analytics_rows():
    rows = []
    SYSTEM = ("You are the ANALYTICS & QUERY agent for the Chorus pipeline. "
              "Answer grounded questions using ONLY the fused_timeline. "
              "Cite evidence. Return JSON with 'answer' and 'evidence' fields.")
    qas = [
        ("How many unique speakers appear in this video?",
         '{"fused_timeline":{"speakers":["SPEAKER_00","SPEAKER_01","SPEAKER_02"],"scenes":[]}}',
         '{"answer":"3 unique speakers: SPEAKER_00, SPEAKER_01, SPEAKER_02.","evidence":[{"source":"diarization_agent"}]}'),
        ("Which speaker had the most screen time?",
         '{"fused_timeline":{"speaker_time":{"SPEAKER_00":142.3,"SPEAKER_01":67.8}}}',
         '{"answer":"SPEAKER_00 had the most screen time at 142.3s.","evidence":[{"source":"diarization_agent","speaker":"SPEAKER_00","total_seconds":142.3}]}'),
        ("How long did SPEAKER_01 speak in total?",
         '{"fused_timeline":{"speaker_time":{"SPEAKER_00":90.0,"SPEAKER_01":45.5}}}',
         '{"answer":"SPEAKER_01 spoke for 45.5 seconds.","evidence":[{"source":"diarization_agent","speaker":"SPEAKER_01","total_seconds":45.5}]}'),
        ("How many scenes were detected?",
         '{"fused_timeline":{"scenes":[{"scene_id":0},{"scene_id":1},{"scene_id":2},{"scene_id":3}]}}',
         '{"answer":"4 scenes detected.","evidence":[{"source":"scene_segmentation","scene_count":4}]}'),
        ("What is the total duration of the video?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"start_seconds":0.0,"end_seconds":45.2},{"scene_id":1,"start_seconds":45.2,"end_seconds":183.7}]}}',
         '{"answer":"Total duration: 183.7 seconds.","evidence":[{"source":"scene_segmentation","last_scene_end":183.7}]}'),
        ("Was a vehicle detected in any scene?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"objects":["person","podium"]},{"scene_id":1,"objects":["vehicle","street"]}]}}',
         '{"answer":"Yes, vehicle detected in scene 1.","evidence":[{"source":"perception_agent","scene_id":1}]}'),
        ("Was a weapon detected at any point?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"objects":["person","table"]},{"scene_id":1,"objects":["crowd","banner"]}]}}',
         '{"answer":"No weapon detected in any scene.","evidence":[{"source":"perception_agent","note":"no weapon in 2 scenes"}]}'),
        ("What text appeared on screen?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"ocr_text":"CITY HALL PRESS CONFERENCE"},{"scene_id":1,"ocr_text":"14 SEPTEMBER 2026"}]}}',
         '{"answer":"Scene 0: CITY HALL PRESS CONFERENCE. Scene 1: 14 SEPTEMBER 2026.","evidence":[{"source":"ocr_agent","scene_id":0},{"source":"ocr_agent","scene_id":1}]}'),
        ("Did the speaker mention climate change?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"transcript":"Good morning. Thank you for coming today."}]}}',
         '{"answer":"Climate change not mentioned in the transcript.","evidence":[{"source":"asr_agent","note":"no mention found"}]}'),
        ("Who is the person in the video?",
         '{"fused_timeline":{"scenes":[{"scene_id":0,"objects":["person"]}],"face_reid":null}}',
         '{"answer":"Identity cannot be determined — face_reid_agent not run.","evidence":[{"source":"face_reid_agent","status":"not_run"}]}'),
        ("Give me a summary of key statistics.",
         '{"fused_timeline":{"total_duration_s":245.0,"scenes":[{"scene_id":0},{"scene_id":1},{"scene_id":2}],"speakers":["SPEAKER_00","SPEAKER_01"],"speaker_time":{"SPEAKER_00":180.0,"SPEAKER_01":65.0}}}',
         '{"answer":"Duration: 245s. Scenes: 3. Speakers: 2 (SPEAKER_00:180s, SPEAKER_01:65s).","evidence":[{"source":"scene_segmentation"},{"source":"diarization_agent"}]}'),
    ]
    for q, u, a in qas:
        dialogue = [
            {"speaker":"orchestrator","turn":"opening","content":f"Analytics Q&A: {q}"},
            {"speaker":"user","turn":"input","content":u},
            {"speaker":"orchestrator","turn":"final_decision","content":a},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":q,"mode":"general",
                     "category":"analytics_query","dialogue":dialogue,
                     "escalated":False,"escalation_reason":None,"_system_prompt":SYSTEM})
    print(f"  [Step 15 seed] Generated {len(rows)} analytics Q&A rows.")
    return rows


def generate_step17_narration_rows():
    rows = []
    SYSTEM = ("You are the DOMAIN OUTPUT agent for the Chorus pipeline. "
              "Write a concise factual narrated summary based ONLY on the fused_timeline. "
              "If manipulation detected, include a clear warning. "
              "Return JSON with 'output_format', 'narration', and 'confidence' fields.")
    narrations = [
        {"s":"3-minute news broadcast, 2 speakers, no flags.",
         "i":'{"total_duration_s":183.0,"scenes":4,"speakers":["SPEAKER_00","SPEAKER_01"],"transcript_summary":"City council infrastructure plan.","ocr_summary":"City Hall 14 Sep 2026","manipulation":"CLEAN"}',
         "o":'{"output_format":"narrative_summary","narration":"3-minute news broadcast (183s, 4 scenes). City council infrastructure announcement. 2 speakers. Location: City Hall, 14 Sep 2026. No manipulation detected.","confidence":0.95}'},
        {"s":"Video flagged by manipulation detection (SEND_TO_REVIEW_QUEUE).",
         "i":'{"total_duration_s":120.0,"scenes":2,"speakers":["SPEAKER_00"],"transcript_summary":"Public statement.","manipulation":"FLAGGED","manipulation_score":0.74}',
         "o":'{"output_format":"narrative_summary","narration":"WARNING: Video flagged by deepfake detection (score 0.74, threshold 0.30). Routed to review queue. Human verification required before any further use.","confidence":0.41}'},
        {"s":"Security camera clip (cyber mode), geo-estimated, no faces without governance.",
         "i":'{"total_duration_s":90.0,"scenes":3,"mode":"cyber","geo_estimate":"central London 85%","face_reid":"not_run","manipulation":"CLEAN","transcript_summary":"No speech."}',
         "o":'{"output_format":"forensic_summary","narration":"90s security clip (3 scenes, cyber mode). Geo: central London (85% confidence). No speech detected. Face re-ID not run (governance not approved). No manipulation.","confidence":0.88}'},
        {"s":"10-minute interview, 3 speakers.",
         "i":'{"total_duration_s":600.0,"scenes":8,"speakers":["SPEAKER_00","SPEAKER_01","SPEAKER_02"],"speaker_time":{"SPEAKER_00":320.0,"SPEAKER_01":180.0,"SPEAKER_02":100.0},"ocr_summary":"Future of AI Panel Discussion","manipulation":"CLEAN"}',
         "o":'{"output_format":"narrative_summary","narration":"10-minute panel interview on Future of AI (600s, 8 scenes). SPEAKER_00: 320s, SPEAKER_01: 180s, SPEAKER_02: 100s. No manipulation detected.","confidence":0.93}'},
        {"s":"Rolling 30-second RTSP chunk from live traffic camera.",
         "i":'{"chunk_start_s":3600.0,"chunk_end_s":3630.0,"scenes":2,"source_type":"live_rtsp","objects":["vehicles","road"],"manipulation":"CLEAN"}',
         "o":'{"output_format":"live_stream_chunk_summary","narration":"Live stream chunk (3600-3630s). 2 scenes. Objects: vehicles, road. No speech or OCR. No manipulation. Rolling cadence continues.","confidence":0.91}'},
        {"s":"Silent documentary b-roll, no ASR output.",
         "i":'{"total_duration_s":240.0,"scenes":6,"speakers":[],"transcript":"","objects_summary":"wildlife forest river aerial shots","ocr_summary":"","manipulation":"CLEAN"}',
         "o":'{"output_format":"narrative_summary","narration":"4-minute silent documentary b-roll (6 scenes). Content: wildlife, forest, river, aerial. No speech or OCR. No manipulation.","confidence":0.94}'},
        {"s":"30-second social media clip, single speaker, product demo.",
         "i":'{"total_duration_s":30.0,"scenes":1,"speakers":["SPEAKER_00"],"transcript_summary":"Demo of Chorus analytics dashboard.","manipulation":"CLEAN"}',
         "o":'{"output_format":"narrative_summary","narration":"30-second product demo (1 scene). Single speaker demos Chorus analytics dashboard. No manipulation detected.","confidence":0.97}'},
        {"s":"Video with no human faces — NO_FACES_DETECTED.",
         "i":'{"total_duration_s":180.0,"scenes":3,"manipulation":"NO_FACES_DETECTED","objects_summary":"landscape buildings text overlays"}',
         "o":'{"output_format":"narrative_summary","narration":"3-minute video (3 scenes), no human faces. Deepfake detection: NO_FACES_DETECTED (N/A). Content: landscape, buildings, text overlays. No manipulation concerns.","confidence":0.96}'},
    ]
    for n in narrations:
        dialogue = [
            {"speaker":"orchestrator","turn":"opening","content":f"Domain output narration: {n['s']}"},
            {"speaker":"user","turn":"input","content":n["i"]},
            {"speaker":"orchestrator","turn":"final_decision","content":n["o"]},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":n["s"],"mode":"general",
                     "category":"domain_output","dialogue":dialogue,
                     "escalated":False,"escalation_reason":None,"_system_prompt":SYSTEM})
    print(f"  [Step 17 seed] Generated {len(rows)} narration rows.")
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# BUILD MERGED DATASET
# ──────────────────────────────────────────────────────────────────────────────

def build_merged_dataset(oversample_x=OVERSAMPLE_X):
    print("\n" + "="*65)
    print("PHASE 1 — BUILDING chorus_v3.json")
    print("="*65)

    if not os.path.isfile(EXISTING_DATA):
        print(f"ERROR: {EXISTING_DATA} not found. Run prepare_negotiation_dataset.py first.")
        sys.exit(1)

    with open(EXISTING_DATA, "r", encoding="utf-8") as f:
        hermes_rows = json.load(f)
    print(f"  Loaded {len(hermes_rows)} Hermes rows.")

    print("\n[2/3] Generating Chorus seed rows...")
    all_seed = (generate_step6_routing_rows() + generate_step12_enrichment_rows() +
                generate_step15_analytics_rows() + generate_step17_narration_rows())
    print(f"  Total seed rows (before oversample): {len(all_seed)}")

    oversampled = all_seed * oversample_x
    random.seed(RANDOM_SEED)
    random.shuffle(oversampled)
    print(f"  Oversampled x{oversample_x}: {len(oversampled)}")

    merged = hermes_rows + oversampled
    random.shuffle(merged)
    print(f"  Grand total: {len(merged)} rows")

    with open(MERGED_DATA, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    size_mb = round(os.path.getsize(MERGED_DATA) / 1e6, 1)
    print(f"  Saved: {MERGED_DATA} ({size_mb} MB)")
    return MERGED_DATA


# ──────────────────────────────────────────────────────────────────────────────
# CHAT FORMATTER  (same as v2)
# ──────────────────────────────────────────────────────────────────────────────

def map_to_messages(example):
    messages = []
    if "dialogue" in example and example["dialogue"] is not None:
        sys_prompt = example.get("_system_prompt") or (
            "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
            "Decide which tools to call, in what order, return only structured JSON."
        )
        messages.append({"role": "system",    "content": sys_prompt})
        messages.append({"role": "user",      "content": f"Scenario: {example.get('scenario','Process request')}"})
        for turn in example["dialogue"]:
            sp = turn.get("speaker", "orchestrator")
            ct = turn.get("content", "")
            if sp == "orchestrator":
                messages.append({"role": "assistant", "content": ct})
            elif sp == "user":
                messages.append({"role": "user",      "content": ct})
            else:
                messages.append({"role": "user",      "content": f"[{sp}]: {ct}"})
    elif "messages" in example and example["messages"] is not None:
        for msg in example["messages"]:
            messages.append({"role": msg.get("role","user"), "content": msg.get("content","")})
    elif "conversations" in example and example["conversations"] is not None:
        for msg in example["conversations"]:
            role = {"human":"user","gpt":"assistant"}.get(msg.get("from","user"),"user")
            messages.append({"role": role, "content": msg.get("value","")})
    return {"messages": messages}


# ──────────────────────────────────────────────────────────────────────────────
# UNSLOTH QLoRA TRAINING
# ──────────────────────────────────────────────────────────────────────────────

def run_training(dataset_path: str):
    import torch
    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig

    print("\n" + "="*65)
    print("PHASE 2 — UNSLOTH QLoRA FINE-TUNING")
    print("="*65)

    if not os.path.isdir(MODEL_PATH):
        print(f"ERROR: Model not found at {MODEL_PATH}")
        sys.exit(1)

    if torch.cuda.is_available():
        print(f"  GPU  : {torch.cuda.get_device_name(0)}")
        print(f"  VRAM : {round(torch.cuda.get_device_properties(0).total_memory/1e9, 1)} GB")

    # ── 1. Load model + tokenizer via Unsloth ─────────────────────────────
    # Replaces: AutoModelForCausalLM + BitsAndBytesConfig + prepare_model_for_kbit_training
    print("\n[1/4] Loading model with Unsloth (4-bit NF4)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_PATH,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,           # auto: bfloat16 on Ampere (RTX A2000), float16 otherwise
        load_in_4bit=True,    # NF4 quant — same as v2 bnb_config
        trust_remote_code=True,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # ── 2. Attach LoRA via Unsloth ─────────────────────────────────────────
    # Replaces: peft LoraConfig + get_peft_model
    print("[2/4] Attaching LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=["q_proj","k_proj","v_proj","o_proj",
                        "gate_proj","up_proj","down_proj"],
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",   # Unsloth optimised checkpointing (saves VRAM)
        random_state=RANDOM_SEED,
        use_rslora=False,
    )
    model.print_trainable_parameters()

    # ── 3. Dataset ────────────────────────────────────────────────────────
    print("\n[3/4] Preparing dataset...")
    raw = load_dataset("json", data_files=dataset_path, split="train")
    print(f"  Loaded {len(raw)} rows from {dataset_path}")
    raw = raw.map(map_to_messages, remove_columns=raw.column_names)

    def format_prompts(batch):
        texts = []
        for msgs in batch["messages"]:
            try:
                texts.append(tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False))
            except Exception:
                texts.append("")
        return {"text": texts}

    raw = raw.map(format_prompts, batched=True)
    raw = raw.filter(lambda x: len(x["text"]) > 50)
    print(f"  Final dataset size: {len(raw)} rows")

    # Checkpoint resume
    checkpoint = None
    if os.path.isdir(OUTPUT_DIR):
        ckpts = sorted(
            [os.path.join(OUTPUT_DIR, d) for d in os.listdir(OUTPUT_DIR)
             if d.startswith("checkpoint-")],
            key=os.path.getmtime,
        )
        if ckpts:
            checkpoint = ckpts[-1]
            print(f"  Resuming from checkpoint: {checkpoint}")

    # ── 4. Train ──────────────────────────────────────────────────────────
    print("\n[4/4] Starting training with SFTTrainer...")
    start = datetime.datetime.now()

    sft_config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,     # effective batch = 8 (same as v2)
        warmup_steps=50,
        num_train_epochs=1,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=5,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=5,
        optim="adamw_8bit",                # Unsloth fused 8-bit AdamW
        max_seq_length=MAX_SEQ_LEN,
        dataset_text_field="text",
        report_to="none",
        dataset_num_proc=2,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=raw,
        args=sft_config,
    )

    try:
        trainer.train(resume_from_checkpoint=checkpoint)
    except Exception as e:
        print(f"\nTraining interrupted: {e}")
        print("Saving partial adapter...")
        model.save_pretrained(OUTPUT_DIR)
        tokenizer.save_pretrained(OUTPUT_DIR)
        raise

    elapsed = datetime.datetime.now() - start
    print(f"\n  Training done in {str(elapsed).split('.')[0]}")

    # ── Save ──────────────────────────────────────────────────────────────
    print(f"\n  Saving adapter to: {OUTPUT_DIR}")
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("  Done! Adapter saved.")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("CHORUS v3 TRAINING PIPELINE  (Unsloth edition)")
    print(f"Started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)
    merged_path = build_merged_dataset(oversample_x=OVERSAMPLE_X)
    run_training(merged_path)
    print("\n" + "=" * 65)
    print("ALL DONE")
    print(f"  Adapter  : {OUTPUT_DIR}")
    print(f"  Dataset  : {MERGED_DATA}")
    print("  Next: wire orchestrator_lora_v3 into pipeline_runner.py")
    print("=" * 65)
