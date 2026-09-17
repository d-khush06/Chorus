"""Quick test: generate all seed rows and print counts. No GPU needed."""
import sys, os, json, random, codecs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
random.seed(42)

# ---- paste only the seed generators ----
ALL_TOOLS = [
    "source_adapters","quality_gate","dedup_check","manipulation_detection",
    "project_manager","scene_segmentation","perception_agent","asr_agent",
    "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
    "quality_verification","correlation_agent","analytics_query_agent",
    "review_queue","domain_output",
]

def _make_row(scenario, mode, category, called_tools, excluded_tools,
              extra_dialogue=None, escalated=False, escalation_reason=None):
    dialogue = [{"speaker":"orchestrator","turn":"opening",
                 "content":f"Initiating Chorus pipeline for: {scenario}"}]
    for t in (called_tools + excluded_tools):
        is_called = t in called_tools
        c = round(random.uniform(0.82,0.97),2) if is_called else round(random.uniform(0.08,0.22),2)
        dialogue.append({"speaker":t,"turn":"self_report",
                         "content":f"I am [{t}]. {'Ready.' if is_called else 'Not needed.'}",
                         "confidence":c})
    if extra_dialogue:
        dialogue.extend(extra_dialogue)
    tc = [{"step":i+1,"tool":t,"tier":"n/a","arguments":{}} for i,t in enumerate(called_tools)]
    dialogue.append({"speaker":"orchestrator","turn":"final_decision",
                     "content":json.dumps({"tool_calls":tc,"excluded":excluded_tools})})
    return {"source_dataset":"chorus_seed","scenario":scenario,"mode":mode,
            "category":category,"dialogue":dialogue,
            "escalated":escalated,"escalation_reason":escalation_reason}

def gen_routing():
    rows=[]
    # happy path
    for i in range(8):
        rows.append(_make_row(f"Standard news clip #{i+1}","general","multi_step",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","perception_agent","asr_agent",
             "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
             "quality_verification","correlation_agent","analytics_query_agent","domain_output"],
            ["geo_estimation_agent","face_reid_agent","chapter_highlight_detection","review_queue"]))
    # early halt duplicate
    for i in range(8):
        rows.append(_make_row(f"Duplicate video #{i+1}","general","multi_step",
            ["source_adapters","dedup_check"],
            [t for t in ALL_TOOLS if t not in ["source_adapters","dedup_check"]],
            extra_dialogue=[{"speaker":"dedup_check","turn":"response",
                             "content":"DUPLICATE. halt_pipeline=True.","confidence":0.99}]))
    # quality gate fail
    for i in range(7):
        rows.append(_make_row(f"Quality gate fail #{i+1}","general","multi_step",
            ["source_adapters","dedup_check","quality_gate"],
            [t for t in ALL_TOOLS if t not in ["source_adapters","dedup_check","quality_gate"]]))
    # manipulation flagged
    for i in range(6):
        rows.append(_make_row(f"Flagged video #{i+1}","general","multi_step",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","review_queue"],
            [t for t in ALL_TOOLS if t not in ["source_adapters","dedup_check","quality_gate",
             "manipulation_detection","project_manager","scene_segmentation","review_queue"]]))
    # cyber mode
    for i in range(6):
        rows.append(_make_row(f"Cyber security clip #{i+1}","cyber","mode_gated",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","perception_agent","asr_agent",
             "diarization_agent","ocr_agent","geo_estimation_agent","face_reid_agent",
             "context_enrichment","fusion_agent","quality_verification",
             "correlation_agent","analytics_query_agent","domain_output"],
            ["chapter_highlight_detection","audio_description_agent"]))
    # cyber no governance
    for i in range(5):
        rows.append(_make_row(f"Cyber no-governance #{i+1}","cyber","mode_gated",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","perception_agent","asr_agent",
             "geo_estimation_agent","context_enrichment","fusion_agent","domain_output"],
            ["face_reid_agent","chapter_highlight_detection","audio_description_agent","review_queue"]))
    # tier escalation
    for i in range(5):
        rows.append(_make_row(f"Tier escalation #{i+1}","general","multi_step",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","perception_agent","perception_agent",
             "asr_agent","diarization_agent","ocr_agent","context_enrichment",
             "fusion_agent","domain_output"],
            ["geo_estimation_agent","face_reid_agent","review_queue"],
            escalated=True,escalation_reason="low_confidence"))
    # rtsp
    for i in range(5):
        rows.append(_make_row(f"RTSP live stream #{i+1}","general","multi_step",
            ["source_adapters","quality_gate","manipulation_detection","project_manager",
             "scene_segmentation","perception_agent","asr_agent","diarization_agent",
             "context_enrichment","fusion_agent","quality_verification","domain_output"],
            ["dedup_check","geo_estimation_agent","face_reid_agent","chapter_highlight_detection"]))
    # public figure
    for i in range(5):
        rows.append(_make_row(f"Public figure video #{i+1}","general","multi_step",
            ["source_adapters","dedup_check","quality_gate","manipulation_detection",
             "project_manager","scene_segmentation","perception_agent","asr_agent",
             "diarization_agent","ocr_agent","context_enrichment","fusion_agent",
             "quality_verification","correlation_agent","analytics_query_agent",
             "domain_output","quality_verification"],
            ["geo_estimation_agent","face_reid_agent","review_queue"]))
    return rows

def gen_enrichment():
    rows=[]
    cases=[
        ("Clean: all agents agree","general","clean"),
        ("ASR vs OCR date conflict","conflict","conflict_detected"),
        ("ASR vs OCR name mismatch","conflict","conflict_detected"),
        ("Perception vs ASR: no person but voice detected","conflict","conflict_detected"),
        ("Low perception confidence 0.58","escalate","escalate_tier2"),
        ("Low ASR confidence 0.62","escalate","escalate_tier2"),
        ("Hallucination: flying car","hallucination","hallucination_flagged"),
        ("Clean: blank OCR valid","general","clean"),
        ("Clean: documentary facts match","general","clean"),
        ("Perception vs ASR: day vs night mismatch","conflict","conflict_detected"),
        ("Hallucination: impossible object","hallucination","hallucination_flagged"),
    ]
    sys_prompt="You are CONTEXT ENRICHMENT for Chorus. Cross-check agent outputs, detect conflicts, return cleaned JSON."
    for scenario, category, status in cases:
        dialogue=[
            {"speaker":"orchestrator","turn":"opening","content":f"Context enrichment for: {scenario}"},
            {"speaker":"user","turn":"input","content":f'{{"scenario":"{scenario}"}}'},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({"status":status,"conflicts":[]if status=="clean" else
                                   [{"description":scenario}],"confidence":0.95 if status=="clean" else 0.12})},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":scenario,"mode":"general",
                     "category":"context_enrichment","dialogue":dialogue,
                     "escalated":"escalate" in status,"escalation_reason":"low_confidence" if "escalate" in status else None,
                     "_system_prompt":sys_prompt})
    return rows

def gen_analytics():
    rows=[]
    sys_prompt="You are ANALYTICS & QUERY for Chorus. Answer from fused_timeline only. Return JSON with answer and evidence."
    qas=[
        "How many unique speakers appear?",
        "Which speaker had the most screen time?",
        "How long did SPEAKER_01 speak in total?",
        "How many scenes were detected?",
        "What is the total duration of the video?",
        "Was a vehicle detected in any scene?",
        "Was a weapon detected at any point?",
        "What text appeared on screen?",
        "Did the speaker mention climate change?",
        "Who is the person in the video?",
        "Give me a summary of key statistics.",
    ]
    for q in qas:
        dialogue=[
            {"speaker":"orchestrator","turn":"opening","content":f"Analytics Q&A: {q}"},
            {"speaker":"user","turn":"input","content":'{"fused_timeline":{}}'},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({"answer":f"Answer to: {q}","evidence":[]})},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":q,"mode":"general",
                     "category":"analytics_query","dialogue":dialogue,
                     "escalated":False,"escalation_reason":None,"_system_prompt":sys_prompt})
    return rows

def gen_narration():
    rows=[]
    sys_prompt="You are DOMAIN OUTPUT for Chorus. Write a narrated summary from fused_timeline. Return JSON."
    cases=[
        "3-minute news broadcast, 2 speakers, no flags",
        "Video flagged by manipulation detection",
        "Cyber mode security clip with geo-estimate",
        "10-minute interview, 3 speakers",
        "RTSP live stream 30-second chunk",
        "Silent documentary b-roll",
        "30-second social media product demo",
        "Video with NO_FACES_DETECTED",
    ]
    for c in cases:
        dialogue=[
            {"speaker":"orchestrator","turn":"opening","content":f"Domain output for: {c}"},
            {"speaker":"user","turn":"input","content":'{"fused_timeline":{}}'},
            {"speaker":"orchestrator","turn":"final_decision",
             "content":json.dumps({"output_format":"narrative_summary",
                                   "narration":f"Summary for: {c}","confidence":0.92})},
        ]
        rows.append({"source_dataset":"chorus_seed","scenario":c,"mode":"general",
                     "category":"domain_output","dialogue":dialogue,
                     "escalated":False,"escalation_reason":None,"_system_prompt":sys_prompt})
    return rows

# --- Run counts ---
r6  = gen_routing();   print(f"Step 6  routing    : {len(r6)} rows")
r12 = gen_enrichment();print(f"Step 12 enrichment : {len(r12)} rows")
r15 = gen_analytics(); print(f"Step 15 analytics  : {len(r15)} rows")
r17 = gen_narration(); print(f"Step 17 narration  : {len(r17)} rows")

total_seed = r6+r12+r15+r17
hermes_count = 4893
oversampled  = len(total_seed)*10
grand_total  = hermes_count + oversampled

print(f"\nSeed total           : {len(total_seed)}")
print(f"After x10 oversample : {oversampled}")
print(f"+ Hermes rows        : {hermes_count}")
print(f"Grand total          : {grand_total}")
print("\nDRY RUN PASSED - all seed generators OK")
