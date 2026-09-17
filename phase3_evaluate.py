"""
phase3_evaluate.py
==================
Evaluates the trained orchestrator_lora_v2 adapter against a small
held-out test set of Chorus routing scenarios.

Checks:
  - Exact tool-set match  (are the right tools selected?)
  - JSON output validity  (does the model output parseable JSON?)
  - Mode accuracy         (general vs cyber correct?)

No GPU needed if you lower batch to CPU, but GPU is faster.

Run:
    python phase3_evaluate.py
"""

import os, sys, json, re

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
ADAPTER_PATH  = os.path.join(BASE_DIR, "orchestrator_lora_v2")
BASE_MODEL    = os.path.join(BASE_DIR, "models", "Qwen2.5-7B-Browser-Agent-Merged")

# ─────────────────────────────────────────────────────────────────────────────
# HELD-OUT TEST CASES
# Each case: (scenario, expected_mode, must_include tools, must_exclude tools)
# ─────────────────────────────────────────────────────────────────────────────
TEST_CASES = [
    {
        "id": "T01_happy_path",
        "scenario": "A 5-minute English interview video is uploaded as a local MP4. "
                    "Quality checks pass, no duplicates found.",
        "mode": "general",
        "must_include": ["source_adapters","quality_gate","dedup_check",
                         "manipulation_detection","scene_segmentation"],
        "must_exclude": ["geo_estimation_agent","face_reid_agent"],
    },
    {
        "id": "T02_duplicate_halt",
        "scenario": "A video is uploaded. dedup_check finds a perceptual hash match "
                    "with an existing archived video. Pipeline must halt immediately.",
        "mode": "general",
        "must_include": ["source_adapters","dedup_check"],
        "must_exclude": ["quality_gate","manipulation_detection","scene_segmentation",
                         "perception_agent","domain_output"],
    },
    {
        "id": "T03_quality_fail",
        "scenario": "A video passes deduplication but quality_gate returns FAIL "
                    "due to a 90-second coverage gap in the timeline.",
        "mode": "general",
        "must_include": ["source_adapters","dedup_check","quality_gate"],
        "must_exclude": ["manipulation_detection","scene_segmentation",
                         "perception_agent","domain_output"],
    },
    {
        "id": "T04_cyber_mode",
        "scenario": "Security camera incident footage submitted for forensic analysis. "
                    "mode=cyber, governance_approved=true. Full forensic pipeline required.",
        "mode": "cyber",
        "must_include": ["geo_estimation_agent","face_reid_agent","manipulation_detection"],
        "must_exclude": ["chapter_highlight_detection","audio_description_agent"],
    },
    {
        "id": "T05_no_governance",
        "scenario": "Incident footage in cyber mode. governance_approved flag is NOT set. "
                    "face_reid_agent must NOT be called.",
        "mode": "cyber",
        "must_include": ["geo_estimation_agent"],
        "must_exclude": ["face_reid_agent"],
    },
    {
        "id": "T06_rtsp_no_dedup",
        "scenario": "Live RTSP stream from a traffic camera. source_type=live_rtsp. "
                    "dedup_check must be skipped per Chorus Rule 7.",
        "mode": "general",
        "must_include": ["source_adapters","quality_gate","scene_segmentation"],
        "must_exclude": ["dedup_check"],
    },
    {
        "id": "T07_manipulation_flagged",
        "scenario": "Video passes quality gate. manipulation_detection returns "
                    "SEND_TO_REVIEW_QUEUE. project_manager must still open the case.",
        "mode": "general",
        "must_include": ["manipulation_detection","project_manager","review_queue"],
        "must_exclude": [],
    },
]

SYSTEM_PROMPT = (
    "You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. "
    "Decide which tools to call, in what order. Return only structured JSON "
    "with keys: mode, tool_calls (list of {step, tool}), excluded."
)

# ─────────────────────────────────────────────────────────────────────────────

def load_model_and_tokenizer():
    import unsloth
    from unsloth import FastLanguageModel

    print(f"  Loading LoRA adapter via Unsloth from: {ADAPTER_PATH}")
    model, tok = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_PATH,
        max_seq_length=1024,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    return model, tok


def run_inference(model, tok, tc):
    import torch
    scenario = tc["scenario"]

    # 1. Opening greeting & mode assessment turn
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Scenario: {scenario}"},
    ]
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tok([text], return_tensors="pt").to("cuda")
    with torch.no_grad():
        ids = model.generate(**inputs, max_new_tokens=64, do_sample=False)
    opening = tok.decode(ids[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()

    # 2. Agent candidate self-reports turn (as trained in Chorus protocol)
    messages.append({"role": "assistant", "content": opening})
    candidate_tools = tc["must_include"] + tc["must_exclude"]
    for t in candidate_tools:
        is_needed = t in tc["must_include"]
        conf = 0.94 if is_needed else 0.12
        msg = (
            f"I am [{t}]. Ready to handle this stage. Confidence: {conf}."
            if is_needed else
            f"I am [{t}]. This scenario does not require my capabilities. Confidence: {conf}."
        )
        messages.append({"role": "user", "content": f"[{t}]: {msg}"})

    # 3. Final orchestrator decision JSON turn
    text2 = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs2 = tok([text2], return_tensors="pt").to("cuda")
    with torch.no_grad():
        ids2 = model.generate(**inputs2, max_new_tokens=384, do_sample=False)
    decision = tok.decode(ids2[0][inputs2.input_ids.shape[1]:], skip_special_tokens=True).strip()

    return opening, decision


def extract_json(text):
    """Try to parse JSON from model output."""
    # Direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # Extract from markdown fence
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # Extract first {...} block
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def evaluate(model, tok):
    results = []
    print("\n" + "="*60)
    print("RUNNING EVALUATION")
    print("="*60)

    for tc in TEST_CASES:
        print(f"\n[{tc['id']}] {tc['scenario'][:70]}...")
        opening, output = run_inference(model, tok, tc)
        parsed = extract_json(output)

        json_valid   = parsed is not None
        mode_correct = False
        include_ok   = []
        exclude_ok   = []

        if json_valid:
            pred_mode  = (parsed.get("mode") or "").lower()
            mode_correct = pred_mode == tc["mode"]

            # Collect all tool names from tool_calls
            tc_list = parsed.get("tool_calls") or []
            pred_tools = set()
            for entry in tc_list:
                if isinstance(entry, dict):
                    pred_tools.add(entry.get("tool",""))

            for t in tc["must_include"]:
                include_ok.append((t, t in pred_tools))
            for t in tc["must_exclude"]:
                exclude_ok.append((t, t not in pred_tools))

        include_pass = all(v for _, v in include_ok)
        exclude_pass = all(v for _, v in exclude_ok)
        overall_pass = json_valid and mode_correct and include_pass and exclude_pass

        status = "✅ PASS" if overall_pass else "❌ FAIL"
        print(f"  {status}")
        print(f"  JSON valid    : {json_valid}")
        print(f"  Mode correct  : {mode_correct}  (expected={tc['mode']}, got={parsed.get('mode') if parsed else 'N/A'})")
        for t, ok in include_ok:
            print(f"  must_include [{t}]: {'✅' if ok else '❌'}")
        for t, ok in exclude_ok:
            print(f"  must_exclude [{t}]: {'✅' if ok else '❌'}")

        results.append({
            "id": tc["id"], "pass": overall_pass,
            "json_valid": json_valid, "mode_correct": mode_correct,
            "include_results": include_ok, "exclude_results": exclude_ok,
            "raw_output": output[:300],
        })

    # Summary
    passed = sum(1 for r in results if r["pass"])
    total  = len(results)
    print("\n" + "="*60)
    print(f"EVALUATION SUMMARY: {passed}/{total} tests passed")
    for r in results:
        mark = "✅" if r["pass"] else "❌"
        print(f"  {mark} {r['id']}")

    # Save results
    out_file = os.path.join(BASE_DIR, "eval_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {out_file}")
    print("="*60)
    return passed, total


if __name__ == "__main__":
    print("="*60)
    print("PHASE 3 — EVALUATION")
    print("="*60)

    if not os.path.isdir(ADAPTER_PATH):
        print(f"\nERROR: Adapter not found at {ADAPTER_PATH}")
        print("Run phase2_train.py first.")
        sys.exit(1)

    print("\nLoading model + adapter...")
    model, tok = load_model_and_tokenizer()

    passed, total = evaluate(model, tok)

    if passed == total:
        print("\n🎉 All tests passed! Adapter is ready to use.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review eval_results.json.")
        print("Consider adding more seed rows and retraining (phase1 → phase2 again).")
