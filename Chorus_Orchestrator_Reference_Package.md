# Chorus Orchestrator — Complete Reference Package
## For use in Antigravity

This document contains everything needed to build, train, and deploy the
Chorus Orchestrator (Pipeline Step 6) as a standalone project.

---

## 1. Model Decision

**Base model: Qwen3-8B** (Apache 2.0, self-hostable, Hugging Face: `Qwen/Qwen3-8B`)

**Why this model, not alternatives:**
- In independent real-world testing (not just leaderboard benchmarks), Qwen3-8B scored 0.933 — beating GPT-4o (0.857) and Claude 3.5 Sonnet (0.851).
- "Specialist" tool-calling models (xLAM-8B, Hammer-7B/2.0, Watt-Tool-8B) all scored 15-20% when tested through a standard inference server (LM Studio) despite topping the official BFCL leaderboard — they were over-fit to a narrow output format that breaks outside their own eval harness.
- Llama-3-Groq-8B-Tool-Use is the one specialist that reportedly survives real-world serving (89.06% BFCL, clean format) — worth testing as an alternative if Qwen3-8B underperforms in your own evaluation, but not the default.
- GLM-4.5-Air (MIT, open-weight, 12B active/MoE) is a genuinely stronger agentic model on TAU-Bench/BrowseComp, but was ruled out for the primary role due to higher VRAM requirement (24GB) — flagged as a future upgrade path, not implemented.
- Newer Qwen3.5 family exists (released mid-project) but has no real-world tool-calling validation yet — treat as a pilot candidate, not a swap.

**Fine-tuning method:** QLoRA — r=16, lora_alpha=32, lora_dropout=0.05, target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"], 4-bit NF4 quantization, bf16 compute dtype.

---

## 2. Model Tier / Cascade Logic

The Orchestrator itself is a cascading agent (Tier 1 → Tier 2), and it also manages cascades for other stages.

**Mechanism (fixed, not a judgment call):**
1. Tier 1 (SLM) always runs first on every input.
2. Tier 1 outputs its answer plus a confidence score (0.0–1.0).
3. If confidence < 0.75 → automatically escalate to Tier 2.
4. Forced escalation regardless of confidence: cross-source contradiction flagged by Fusion Agent, "contested" flag from agent-negotiation, or an input pattern not matching any trained category.
5. Tier 2's answer always overrides Tier 1's once escalated.
6. Every escalation is logged with a reason: `low_confidence` | `contradiction` | `contested` | `unseen_pattern` — this log feeds future fine-tuning rounds.

**Orchestrator's own tier assignment:** Tier 1 = Qwen3-4B, Tier 2 = Qwen3-8B.

**Tier reference for agents the Orchestrator manages:**

| Agent | Tier 1 | Tier 2 (escalation) |
|---|---|---|
| orchestrator (self) | Qwen3-4B | Qwen3-8B |
| perception_agent | Moondream 2B | Qwen3-VL-8B |
| geo_estimation_agent | GeoCLIP | GLM-4.5V |
| context_enrichment | Qwen3-4B | Qwen3-8B |
| analytics_query_agent | Qwen3-4B | Qwen3-8B |
| domain_output | Qwen3-4B | Qwen3-8B |

All other agents in the tool registry are fixed, single-tier — no escalation path.

**Evidence this pattern works (not theoretical):** NVIDIA + Cisco/Outshift replaced a 70B LLM-judge with a fine-tuned 3B SLM — latency dropped 4-6s → 400ms (10x), accuracy exceeded the 70B baseline. NVIDIA's own internal NVInfo AI replaced Llama 3.1 70B routing with a fine-tuned 8B — 96% accuracy, 10x smaller, 70% faster.

---

## 3. Mode Logic

The Orchestrator's first decision on every video is **mode**, before any other routing:

- **`general`** (default) — consumer/creator use case
- **`cyber`** — security/forensics/OSINT, opt-in and gated

Mode determines which agents are even eligible to be called:
- `geo_estimation_agent`, `face_reid_agent` → **cyber only**. `face_reid_agent` additionally requires `governance_approved: true` in the input — must never be called without this flag (real legal/consent process required behind this flag, not just a prompt instruction — see Section 8).
- `chapter_highlight_detection`, `audio_description_agent` → **general only** (content/accessibility features, not investigation features).
- Everything else is available in both modes.

If mode is ambiguous, default to `general`.

---

## 4. Full Tool Registry (33 tools)

```python
TOOLS = [
  # Core pipeline (17 steps)
  {"name": "source_adapters", "desc": "yt-dlp/upload handler/RTSP ingestion.", "mode": "both", "model": "none"},
  {"name": "quality_gate", "desc": "Rule-based checks on ingested video.", "mode": "both", "model": "none"},
  {"name": "dedup_check", "desc": "Perceptual hashing, stops pipeline if duplicate found.", "mode": "both", "model": "none"},
  {"name": "manipulation_detection", "desc": "Xception/SBI deepfake detector.", "mode": "both", "model": "Xception+SBI"},
  {"name": "project_manager", "desc": "SHA-256 hashing, audit trail.", "mode": "both", "model": "none"},
  {"name": "scene_segmentation", "desc": "PySceneDetect shot/scene cut detector.", "mode": "both", "model": "none"},
  {"name": "perception_agent", "desc": "Watches video for objects, actions, events, timing.", "mode": "both", "model": "Moondream2B->Qwen3-VL-8B", "cascading": true},
  {"name": "asr_agent", "desc": "Speech-to-text transcription.", "mode": "both", "model": "Whisper-large-v3 / Qwen3-ASR-1.7B"},
  {"name": "diarization_agent", "desc": "Speaker diarization (who spoke when).", "mode": "both", "model": "pyannote.audio 4.0 / NeMo Sortformer"},
  {"name": "ocr_agent", "desc": "On-screen text reader.", "mode": "both", "model": "PaddleOCR-VL"},
  {"name": "context_enrichment", "desc": "Cross-checks, corroborates, cleans raw agent outputs.", "mode": "both", "model": "Qwen3-4B->Qwen3-8B", "cascading": true},
  {"name": "fusion_agent", "desc": "Rule-based merge onto one shared timeline.", "mode": "both", "model": "none"},
  {"name": "quality_verification", "desc": "Fixed 8-rule check against the fused timeline.", "mode": "both", "model": "Qwen3-8B (fixed, no SLM tier)"},
  {"name": "correlation_agent", "desc": "Links objects/speech/text/scenes into relationships.", "mode": "both", "model": "DINOv3"},
  {"name": "analytics_query_agent", "desc": "Auto-stats + on-demand grounded Q&A.", "mode": "both", "model": "rule-based (stats) / Qwen3-4B->Qwen3-8B (Q&A)", "cascading": true},
  {"name": "review_queue", "desc": "Routes low-confidence findings to a human.", "mode": "both", "model": "Human + Qwen3-1.7B assist"},
  {"name": "domain_output", "desc": "Shapes final output to target field/template.", "mode": "both", "model": "Qwen3-4B->Qwen3-8B", "cascading": true},

  # Extended pipeline
  {"name": "object_detection", "desc": "RF-DETR frame-by-frame object detector.", "mode": "both", "model": "RF-DETR"},
  {"name": "zero_shot_detection", "desc": "Grounding DINO open-vocabulary detector fallback.", "mode": "both", "model": "Grounding DINO"},
  {"name": "classification_agent", "desc": "Labels each detected crop.", "mode": "both", "model": "DINOv3"},
  {"name": "voice_clone_agent", "desc": "Clones user voice from reference audio.", "mode": "both", "model": "Chatterbox Multilingual v3"},
  {"name": "avatar_video_agent", "desc": "Narrated summary video generation.", "mode": "both", "model": "HunyuanVideo-Avatar"},

  # Cyber/governance additions
  {"name": "geo_estimation_agent", "desc": "Visual location estimation from scene frames.", "mode": "cyber", "model": "GeoCLIP->GLM-4.5V", "cascading": true},
  {"name": "acoustic_event_detection", "desc": "Non-speech audio event tagging (music/applause general; glass-break/alarm cyber).", "mode": "both", "model": "YAMNet"},
  {"name": "face_reid_agent", "desc": "Persistent identity tracking. REQUIRES governance_approved=true.", "mode": "cyber", "model": "InsightFace (ArcFace/buffalo_l)"},
  {"name": "pii_redaction_gate", "desc": "PII detection and redaction before output.", "mode": "both", "model": "Microsoft Presidio"},
  {"name": "c2pa_signoff", "desc": "Cryptographic provenance signing.", "mode": "both", "model": "c2patool (no model)"},

  # Ultimate add-ons
  {"name": "language_identification", "desc": "Detects spoken language, routes ASR handling.", "mode": "both", "model": "Whisper built-in detector"},
  {"name": "translation_subtitle_agent", "desc": "Multilingual subtitle/translation generation.", "mode": "both", "model": "NLLB-200"},
  {"name": "emotion_sentiment_agent", "desc": "Speech tone + facial expression signal fusion.", "mode": "both", "model": "emotion2vec + vision signal"},
  {"name": "content_moderation_gate", "desc": "Toxicity/hate-speech classifier before output.", "mode": "both", "model": "Detoxify"},
  {"name": "copyright_fingerprint_check", "desc": "Audio fingerprint match for copyright.", "mode": "both", "model": "Chromaprint/AcoustID"},
  {"name": "chapter_highlight_detection", "desc": "Rule-based auto-chaptering.", "mode": "general", "model": "none, reuses correlation_agent output"},
  {"name": "cross_video_search_index", "desc": "Vector index write for cross-video search.", "mode": "both", "model": "Qdrant + existing embeddings"},
  {"name": "audio_description_agent", "desc": "Spoken description track for accessibility.", "mode": "general", "model": "Qwen3-8B + Chatterbox"},
]
```

---

## 5. Production System Prompt

```
You are the ORCHESTRATOR for the Chorus video-intelligence pipeline. Your
only job is to decide, for a given ingested video, which agents/tools to
call, in what order, with what arguments, at what model tier, and under
which operating mode. You do not summarize, transcribe, detect objects,
or generate any content yourself — you only route.

## Step 0 — Determine mode
Before any other decision, set `mode` to "general" or "cyber" — either
explicitly given by the caller, or inferred from content signals
(security-camera source, incident footage, explicit investigation
request). This determines which agents are even eligible to be called.
If uncertain, default to "general" — cyber-mode agents (geo_estimation,
face_reid) must never run without explicit mode selection or override.

## Rules you must follow, in order of priority

1. Never call an agent whose precondition is not met by the current
   state (e.g., do not call `translation_subtitle_agent` before
   `asr_agent`, do not call `avatar_video_agent` before
   `voice_clone_agent`, do not call `chapter_highlight_detection` before
   `correlation_agent`).
2. Skip any agent that is genuinely unnecessary for this specific video.
   Justify each call against the scenario, don't call everything by
   default.
3. If `quality_gate` or `dedup_check` fails, stop immediately.
4. Mode-gated agents only run in their permitted mode:
   - `geo_estimation_agent`, `face_reid_agent` → cyber mode only, and
     `face_reid_agent` additionally requires a `governance_approved`
     flag to be true in the input — never call it without this flag.
   - `chapter_highlight_detection`, `audio_description_agent` →
     general mode only (content/accessibility features, not
     investigation features).
   - Everything else is available in both modes.
5. Cascading agents (see tier table) always call Tier 1 first.
   Escalate to Tier 2 only if: confidence < 0.75, OR a cross-source
   contradiction is flagged by `fusion_agent`, OR the case is marked
   "contested" by your own agent-negotiation step, OR the input pattern
   doesn't match any category seen in training. Tier 2's result always
   overrides Tier 1's once escalation happens.
6. If content involves named public figures, political material, or
   anything likely to be widely shared, always include
   `manipulation_detection` and end with an extra `quality_verification`
   pass.
7. For `source_type == "live_rtsp"`, skip `dedup_check`, run
   `quality_verification` on a rolling cadence, and treat
   `acoustic_event_detection` as continuous, not one-shot.
8. `copyright_fingerprint_check` runs immediately after
   `source_adapters`, before any deeper analysis.
9. `content_moderation_gate` and `pii_redaction_gate` both run before
   `domain_output` — never let output reach a user unfiltered.
10. `cross_video_search_index` only runs after `domain_output` succeeds.
11. Before your final tool-call list, write one short internal
    reasoning line per decision. This is for audit logging, not shown
    to the end user.

## Tier reference (cascading agents only)

| Agent | Tier 1 | Tier 2 (escalation) |
|---|---|---|
| orchestrator (self) | Qwen3-4B | Qwen3-8B |
| perception_agent | Moondream 2B | Qwen3-VL-8B |
| geo_estimation_agent | GeoCLIP | GLM-4.5V |
| context_enrichment | Qwen3-4B | Qwen3-8B |
| analytics_query_agent | Qwen3-4B | Qwen3-8B |
| domain_output | Qwen3-4B | Qwen3-8B |

All other agents are fixed, single-tier (no escalation path).

## Available tools
You will receive the full tool list (name, description, mode
eligibility, tier info, input schema) in the user message as
`available_tools`. Only call tools from that list, using their exact
names.

## Output format — return ONLY this JSON, no other text

{
  "mode": "general" | "cyber",
  "reasoning": [
    { "tool": "string", "decision": "call | skip", "tier": "1 | 2 | n/a", "why": "one short sentence" }
  ],
  "tool_calls": [
    { "step": 1, "tool": "string", "tier": "1 | 2", "arguments": { } }
  ]
}

## Do not
- Do not invent a tool name not present in `available_tools`.
- Do not call a cyber-mode-only agent in general mode, or vice versa.
- Do not call `face_reid_agent` without `governance_approved: true`.
- Do not skip `quality_gate` under any circumstances.
```

---

## 6. Training Dataset

### Sources
- **APIGen / Salesforce xLAM Function-Calling 60k** (`Salesforce/xlam-function-calling-60k`, Hugging Face) — gated, requires HF account + accepting terms on the dataset page + HF token with **Read** permission.
- **ToolACE** was originally planned but dropped for this build (runtime too long on free-tier compute — would have taken 31-63 hours). Available at `Team-ACE/ToolACE` if revisited later with more compute budget.
- **Chorus's own seed dataset** — hand-built scenarios covering the 17-step pipeline decision points (multi-step sequencing, early-stop cases, mode-gating, escalation). Smallest by volume, highest value — should be oversampled 5-10x when merged with the larger APIGen-derived set so it isn't drowned out.

### Dialogue format (multi-agent negotiation)
No existing public dataset teaches "agents debate which tool to call" — this was custom-designed. Each candidate agent self-reports relevance with a confidence score; the Orchestrator resolves conflicts.

```json
{
  "source_dataset": "apigen" | "chorus_seed",
  "original_id": "string or null",
  "scenario": "one paragraph describing the video/request",
  "mode": "general" | "cyber",
  "dialogue": [
    { "speaker": "orchestrator", "turn": "opening", "content": "..." },
    { "speaker": "<agent_name>", "turn": "self_report", "content": "...", "confidence": 0.0, "depends_on": ["..."] },
    { "speaker": "orchestrator", "turn": "clarification", "content": "..." },
    { "speaker": "<agent_name>", "turn": "response", "content": "..." },
    { "speaker": "orchestrator", "turn": "final_decision", "content": "{\"tool_calls\": [...], \"excluded\": [...], \"reasoning_summary\": \"...\"}" }
  ],
  "escalated": true,
  "escalation_reason": "low_confidence" | "contradiction" | "contested" | "unseen_pattern" | null,
  "category": "call_tool" | "skip_tool" | "multi_step" | "irrelevance" | "contested" | "mode_gated"
}
```

### Filter/reformat prompt (KEEP/REJECT + reformat raw APIGen examples)
```
You are a DATASET PROCESSOR preparing third-party function-calling data
to train the Chorus orchestrator (Qwen3-8B). You will be given ONE
example at a time from APIGen, in its native format. Your job is to
decide whether to KEEP or REJECT it, and if kept, reformat it into the
Chorus training schema below.

KEEP the example only if ALL of these are true:
1. It demonstrates a genuine ROUTING decision - which function(s) to
   call, in what order, given a natural-language request - not just a
   single isolated API call with no decision-making involved.
2. The function-call structure is syntactically valid.
3. It does NOT depend on domain knowledge that conflicts with Chorus's
   actual domain (video ingestion, analysis, fusion, narration).
4. It includes at least one case of correct RESTRAINT (declining to
   call an unnecessary function) OR is being kept to balance that ratio.

REJECT if: malformed calls, hallucinated parameters, single-obvious-tool
examples with no real decision, or near-duplicate structure.

Return ONLY this JSON, no other text:
{
  "verdict": "KEEP" | "REJECT",
  "reject_reason": "<one sentence, only if REJECT>",
  "processed_example": { ...Chorus schema... }
}

CRITICAL: Your entire response must be a single valid JSON object and
nothing else. No explanation, no markdown fences, no text before or
after. Begin your response with { and end with }.
```

### Dialogue-generation prompt (converts filtered examples into negotiation format)
```
You are converting a function-calling example into a MULTI-AGENT
NEGOTIATION dialogue for training the Chorus orchestrator. Candidate
agents self-report whether they should be called, then the orchestrator
resolves the decision.

Given one example (with its tools and correct answer):
1. List every tool offered as a candidate agent.
2. For each, write one self_report turn: first-person justification for
   why it is or isn't relevant here, with a confidence score (>=0.7 if
   it should be called, <=0.4 if not).
3. If two agents genuinely conflict, add one orchestrator "clarification"
   turn and that agent's "response" turn. Only if a real conflict exists.
4. Close with one orchestrator "final_decision" turn: valid JSON with
   tool_calls (correct order), excluded agents, and a one-sentence
   reasoning_summary.

Return ONLY this JSON, no other text:
{
  "verdict": "KEEP" | "REJECT",
  "reject_reason": "<one sentence, only if REJECT>",
  "processed_example": { ...dialogue schema above... }
}

CRITICAL: Your entire response must be a single valid JSON object and
nothing else. Begin with { and end with }.
```

---

## 7. Training Pipeline (Free, No Paid API)

1. Download APIGen (requires HF authentication + gate acceptance on the dataset page).
2. Filter/reformat via a **local judge model** (`Qwen/Qwen2.5-7B-Instruct`, 4-bit) using the filter prompt above — no paid API key needed.
3. Convert kept examples into multi-agent negotiation dialogues using the same local judge model.
4. Merge with Chorus's own seed dataset (oversampled 5-10x relative to its raw count).
5. Deduplicate (hash on normalized scenario text).
6. Train/eval split (90/10, fixed random seed for reproducibility across runs).
7. QLoRA fine-tune Qwen3-8B on the merged, cleaned dataset.
8. Evaluate: exact tool-set match (order-agnostic) + exact ordered-sequence match, on the held-out eval split. Also run the standard Berkeley Function-Calling Leaderboard (BFCL) suite as an external reference point.

**Evaluation script logic:** load the base model + LoRA adapter, generate against each eval example's message history (excluding the gold final answer), extract tool names from both the gold and predicted `tool_calls`, compare as sets (exact-set accuracy) and as ordered lists (exact-sequence accuracy).

---

## 8. Known Issues / Not Yet Resolved

- **Legal/compliance review required before `face_reid_agent` ships.** The `governance_approved` flag in the prompt is not itself a legal safeguard — it must be backed by a real consent/legal-basis process (BIPA, GDPR biometric provisions apply regardless of prompt design). Do not treat the flag as sufficient on its own.
- **Seed dataset volume is still small** (~10-15 hand-built rows at last count). Needs expansion covering: every agent skipped/called at least a few times, contested cases, mode-gated cases, explicit Tier 1→2 escalation examples, and live-RTSP-specific routing — before training produces reliable results.
- **Qwen3.5 family** — released mid-project, not yet evaluated against the real-world reliability bar (the same test that eliminated xLAM/Hammer/Watt-Tool) — don't swap the base model without running that evaluation first.
- **GLM-4.5-Air** — confirmed genuinely open-weight (MIT, `zai-org` on Hugging Face) and stronger on agentic benchmarks, but not adopted due to 24GB VRAM requirement vs. Qwen3-8B's lighter footprint. Revisit if hardware constraints change.

---

## 9. Practical Environment Lessons (carry into Antigravity)

These were hard-won during Kaggle/Colab builds for this same project — worth applying wherever this runs next:

- **Pin to a single GPU explicitly** if multi-GPU is available (e.g. `device_map={"": 0}`) — letting a model auto-shard across multiple GPUs it doesn't need can cause a ~5x slowdown from communication overhead, for a model this size.
- **Every execution unit should be self-contained with its own imports** — don't rely on state persisting from an earlier cell/step run in a different session.
- **Benchmark on one example before committing to a full batch run** — confirms output format validity and gives a real time estimate instead of a guess.
- **Batch inference calls where possible** — roughly halves total runtime versus one-at-a-time processing for the filter/dialogue-generation steps.
- **Checkpoint and resume** for any long-running data processing job — write progress incrementally (`open(file, "a")`, flush after each batch) rather than only at the end, so an interruption doesn't cost the whole run.
- **Verify dataset repo names, configs, and splits before writing conversion logic** — several datasets used in this project had non-obvious structures (config-gated splits, typo'd repo names, script-based loaders no longer supported, video content packaged in `.tar.gz` shards rather than individually downloadable files). Always run a small diagnostic/inspection step before building the full pipeline around assumed field names.
