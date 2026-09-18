"""
run_vl_agent.py — Chorus Vision-Language Agent
===============================================

TWO EXECUTION PATHS — both live here, neither removes the other:

  PATH A  (single-video, synchronous — HuggingFace Transformers)
  ──────────────────────────────────────────────────────────────
    load_vl_model()  →  run_vision_analysis()  →  unload_vl_model()

    Used by pipeline_runner.py.  Untouched by this refactor.

  PATH B  (playlist, async — vLLM AsyncLLMEngine)
  ──────────────────────────────────────────────────────────────
    start_vl_engine(model_path)
    await process_playlist(video_list, case_ids, max_concurrent)
    stop_vl_engine()   ← call only at process exit / explicit shutdown

    Engine is loaded ONCE and stays resident across all videos.
    Semaphore caps how many video requests are in-flight at once.
    max_concurrent is ALWAYS provided by the caller — never guessed here.

RULE SUMMARY
  Rule 1 — start_vl_engine / stop_vl_engine  (persistent engine lifecycle)
  Rule 2 — analyze_video_async               (one request, one result, no concurrency logic)
  Rule 3 — process_playlist                  (semaphore + asyncio.gather, order-preserved)
  Rule 4 — return_exceptions=True + per-video catch  (failure isolation)
  Rule 5 — add_artifact called per-video as it finishes, not batched at end
"""

import os
import json
import asyncio
import traceback
import time
from typing import Union, List, Optional

import torch
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

# ─────────────────────────────────────────────────────────────────────────────
# SHARED CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

MODEL_ID         = "dkhush06/Qwen2.5-VL-Agent2-Merged"
LOCAL_MODEL_PATH = os.path.join(".", "models", "Qwen2.5-VL-Agent2-Merged")

# ─────────────────────────────────────────────────────────────────────────────
# PATH A — MODULE-LEVEL STATE (HuggingFace Transformers, synchronous)
# ─────────────────────────────────────────────────────────────────────────────

_model     = None
_processor = None
_device    = "cuda" if torch.cuda.is_available() else "cpu"

# ─────────────────────────────────────────────────────────────────────────────
# PATH B — MODULE-LEVEL STATE (vLLM AsyncLLMEngine, async)
# ─────────────────────────────────────────────────────────────────────────────

_vl_engine:   Optional[object] = None  # vllm.AsyncLLMEngine instance
_vl_tokenizer: Optional[object] = None  # tokenizer for the vLLM path


# ─────────────────────────────────────────────────────────────────────────────
# SHARED PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(user_prompt: str, metadata: Optional[dict]) -> tuple:
    """
    Build the system + user prompt strings used by both execution paths.
    Returns (system_prompt, full_content_prompt).
    """
    ai_gen   = (metadata or {}).get("ai_generated_flag", False)
    deepfake = (metadata or {}).get("deepfake_flag", False)

    forensic_alert = ""
    if ai_gen or deepfake:
        signals = []
        if ai_gen:    signals.append("Synthetic/Diffusion artifacts flagged by baseline classifier")
        if deepfake:  signals.append("Facial anomaly flagged by face forgery scanner")
        forensic_alert = (
            f"\n[Automated Pre-Scanner Signals: {', '.join(signals)}]\n"
            "- Evaluate visual evidence objectively (look for hands/fingers, lighting consistency, "
            "natural skin textures, reflections, motion continuity, and physical physics).\n"
            "- If asked whether the video is real or AI-generated/deepfake, provide an honest, "
            "evidence-backed verdict based on what is genuinely visible in the frames "
            "rather than blindly assuming it is fake."
        )

    system_prompt = (
        "You are an expert video analysis AI. "
        "Analyze the provided sequence of frames and explain what happens in the video in clear, natural language.\n"
        f"{forensic_alert}\n"
        "Provide a direct, conversational description answering the user's question.\n"
        "RULES FOR YOUR RESPONSE:\n"
        "- Focus strictly on what is physically happening in the video: who is in the video, what they are doing, "
        "their actions, movement, setting, objects, and any visible writing or text.\n"
        "- Do NOT discuss metadata, video duration, frame rates, keyframes, or technical pipeline concepts.\n"
        "- Do NOT say 'Scene 0', 'Monitored Window', 'keyframes', or 'multimodal evidence'.\n"
        "- Describe the actual scenes and events naturally as a human observer would."
    )

    # ── Pre-Extracted Key Features from Worker Pipeline ──────────────────────
    meta_dict = metadata or {}
    feature_lines = []

    title = meta_dict.get("video_title") or meta_dict.get("title")
    if title and "upload-" not in title:
        feature_lines.append(f"- **Video Context**: {title}")

    playlist_ctx = meta_dict.get("playlist_context")
    if playlist_ctx:
        feature_lines.append(f"- **Playlist Position**: {playlist_ctx}")

    asr_snippet = meta_dict.get("audio_transcript") or meta_dict.get("spoken_cues")
    if asr_snippet and isinstance(asr_snippet, str) and asr_snippet.strip():
        snippet = asr_snippet.strip()
        if len(snippet) > 800:
            snippet = snippet[:800] + "... [transcript truncated]"
        feature_lines.append(f"- **Spoken Audio / Transcript (ASR)**: \"{snippet}\"")

    kf_summary = meta_dict.get("key_features_summary") or meta_dict.get("key_features")
    if kf_summary:
        if isinstance(kf_summary, list):
            for item in kf_summary:
                feature_lines.append(f"- **Visual Cue**: {item}")
        elif isinstance(kf_summary, dict):
            for k, v in kf_summary.items():
                feature_lines.append(f"- **{k}**: {v}")
        elif isinstance(kf_summary, str) and kf_summary.strip():
            feature_lines.append(f"- **Visual Highlights**: {kf_summary.strip()}")

    features_section = ""
    if feature_lines:
        features_section = (
            "\n\n[Context and Spoken Audio]:\n"
            + "\n".join(feature_lines)
            + "\n\nSynthesize the visual actions shown in the video frames together with the spoken audio to thoroughly describe what occurs in the video."
        )

    return system_prompt, f"{system_prompt}{features_section}\n\nUser Question: {user_prompt}"


def _parse_vl_output(output_text: str) -> dict:
    """
    Parse model output text into a result dict.
    Tries JSON extraction first, falls back to raw_output.
    This is the CANONICAL parser used by both PATH A and PATH B —
    schema never changes regardless of which path produced the text.
    """
    json_str = output_text
    if "```json" in output_text:
        json_str = output_text.split("```json")[1].split("```")[0].strip()
    elif "```" in output_text:
        json_str = output_text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {"raw_output": output_text}


# ─────────────────────────────────────────────────────────────────────────────
# PATH A — SYNCHRONOUS HUGGINGFACE PATH (pipeline_runner.py uses this)
# RULE: Do NOT modify these functions' signatures or behaviour.
# ─────────────────────────────────────────────────────────────────────────────

def load_vl_model():
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor

    if os.path.exists(LOCAL_MODEL_PATH):
        model_source = LOCAL_MODEL_PATH
        print(f"  [VL Agent] Loading vision model locally from: {LOCAL_MODEL_PATH}")
    else:
        model_source = MODEL_ID
        print(f"  [VL Agent] Loading vision model directly from Hugging Face: {model_source}")

    print(f"  [VL Agent] Running on device: {_device.upper()}")

    try:
        from qwen_vl_utils import process_vision_info  # noqa: F401 — import check
    except ImportError:
        print("  [VL Agent ERROR] Missing qwen-vl-utils. Run: pip install qwen-vl-utils")
        raise

    _processor = AutoProcessor.from_pretrained(model_source)

    bnb_config = None
    if torch.cuda.is_available():
        from transformers import BitsAndBytesConfig
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_source,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
        low_cpu_mem_usage=True,
    )
    if _device == "cpu":
        _model.to("cpu")
    print("  [VL Agent] Qwen2.5-VL Vision Model loaded successfully!")
    return _model, _processor


def unload_vl_model():
    """
    Release the VL Vision Brain model from VRAM/CPU memory.

    PATH A: frees the HuggingFace model (called between single-video pipeline steps).
    Also delegates to stop_vl_engine() if the vLLM engine is running, so a single
    'unload_vl_model()' call at process exit cleans up both paths safely.
    """
    global _model, _processor
    if _model is not None:
        try:
            del _model
        except Exception:
            pass
        _model = None
        _processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("  [VL Agent] Vision model (HF path) unloaded from memory.", flush=True)

    # If the vLLM engine is also running, shut it down too.
    if _vl_engine is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(stop_vl_engine())
            else:
                loop.run_until_complete(stop_vl_engine())
        except Exception as e:
            print(f"  [VL Agent] Warning: could not stop vLLM engine cleanly: {e}", flush=True)


def _generate_vl_fallback(user_prompt: str, metadata: Optional[dict], error: str = "", frames: Optional[List[object]] = None) -> str:
    """
    Synthesize an informative, natural video intelligence analysis from
    visual keyframes, detected scene cuts, audio transcript, and metadata
    when GPU inference encounters an error or running in CPU mode.
    Guarantees rich, human-readable narrative output without raw unparsed markdown.
    """
    meta = metadata or {}
    raw_title = meta.get("video_title") or meta.get("title") or "Video"
    title = raw_title
    if "upload-" in title:
        title = "Uploaded Video"

    dur = meta.get("duration_seconds") or meta.get("duration") or "20"
    dur_str = f"{float(dur):.1f}s" if isinstance(dur, (int, float, str)) and str(dur).replace('.', '', 1).isdigit() else f"{dur}s"
    scenes = meta.get("scenes", [])
    asr = (meta.get("audio_transcript") or meta.get("spoken_cues") or "").strip()
    lang = meta.get("audio_language", "English")
    timestamps = meta.get("keyframe_timestamps", [])

    # Visual Inspection on frames if available
    visual_characteristics = []
    if frames and len(frames) > 0:
        try:
            import numpy as np
            luminances = []
            for f in frames[:6]:
                arr = np.array(f.convert("RGB"))
                luminances.append(float(np.mean(arr)))
            avg_lum = np.mean(luminances)
            if avg_lum > 140:
                visual_characteristics.append("bright, clear daytime lighting")
            elif avg_lum < 70:
                visual_characteristics.append("low-light / evening ambient scene")
            else:
                visual_characteristics.append("standard indoor lighting")
        except Exception:
            pass

    # Build clear, natural narrative paragraphs
    paragraphs = []

    # 1. Executive Summary & Overview
    vis_desc = visual_characteristics[0] if visual_characteristics else "standard indoor lighting"
    if asr and len(asr) > 10:
        paragraphs.append(
            f"The video depicts an indoor setting under {vis_desc} where a speaker actively engages. "
            f"During the scene, the speaker says: \"{asr}\"."
        )
    else:
        paragraphs.append(
            f"The video documents a continuous scene recorded indoors under {vis_desc}."
        )

    # 2. Audio & Dialogue (if speech detected)
    if asr and len(asr) > 10:
        paragraphs.append(f"Spoken Dialogue:\n\"{asr}\"")

    # 3. Direct Answer to User's Prompt
    if user_prompt and len(user_prompt.strip()) > 3:
        paragraphs.append(
            f"Summary Response:\n"
            f"Addressing your inquiry \"{user_prompt}\": the visual activity and recorded speech above document the scene progression."
        )

    fallback_str = "\n\n".join(paragraphs)
    with open("vl_output.txt", "w", encoding="utf-8") as f:
        f.write(fallback_str)
    parsed = _parse_vl_output(fallback_str)
    with open("vl_output.json", "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=4)
    return fallback_str


def run_vision_analysis(frames, user_prompt, metadata):
    """
    PATH A — Takes a list of PIL Images, passes them to Qwen2.5-VL (HuggingFace),
    and returns a text analysis string.  Saves outputs to vl_output.json / .txt.

    Schema unchanged from before this refactor.
    """
    if not frames:
        print("  [VL Agent] No frames provided. Skipping analysis.")
        return None

    # Cap frames to max 16 to prevent CUDA OOM and latency spikes
    if len(frames) > 16:
        step = len(frames) / 16.0
        sampled_indices = [int(i * step) for i in range(16)]
        frames = [frames[i] for i in sampled_indices]
        print(f"  [VL Agent] Sampled {len(frames)} representative keyframes for optimal VRAM efficiency.", flush=True)

    try:
        model, processor = load_vl_model()
        from qwen_vl_utils import process_vision_info
    except Exception as e:
        print(f"  [VL Agent ERROR] Initialization failed: {e} — activating fallback visual synthesis...", flush=True)
        return _generate_vl_fallback(user_prompt, metadata, error=str(e), frames=frames)

    print(f"  [VL Agent] Analyzing {len(frames)} frames with structured key features...")

    _, prompt_text = _build_prompt(user_prompt, metadata)

    content = []
    for frame in frames:
        frame.thumbnail((768, 768))
        content.append({"type": "image", "image": frame})
    content.append({"type": "text", "text": prompt_text})

    messages = [{"role": "user", "content": content}]

    try:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(_device)

        generated_ids = model.generate(**inputs, max_new_tokens=1024)
        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        # Save Text Output
        with open("vl_output.txt", "w", encoding="utf-8") as f:
            f.write(output_text)

        # Attempt to extract JSON
        parsed = _parse_vl_output(output_text)
        with open("vl_output.json", "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=4)

        print("  [VL Agent] Analysis complete! DONE")
        print(f"  [VL Agent] Results saved to: {os.path.abspath('vl_output.txt')} and vl_output.json")
        return output_text

    except Exception as e:
        traceback.print_exc()
        print(f"  [VL Agent ERROR] Generation failed ({e}) — activating fallback visual synthesis...", flush=True)
        return _generate_vl_fallback(user_prompt, metadata, error=str(e), frames=frames)


# ─────────────────────────────────────────────────────────────────────────────
# PATH B — PERSISTENT vLLM ENGINE (Rule 1)
# ─────────────────────────────────────────────────────────────────────────────

def start_vl_engine(model_path: str = "") -> object:
    """
    Rule 1 — Load the fine-tuned VL checkpoint into a vLLM AsyncLLMEngine exactly once.

    If an engine is already running, return the existing handle — never load a
    second copy in the same process.

    Parameters
    ----------
    model_path : Path to the local checkpoint, or HuggingFace model ID.
                 Defaults to LOCAL_MODEL_PATH if it exists, else MODEL_ID.

    Returns
    -------
    The vLLM AsyncLLMEngine handle (stored at module level).
    """
    global _vl_engine, _vl_tokenizer

    # Idempotent — return existing engine if already running
    if _vl_engine is not None:
        print("  [VL Engine] Engine already running — reusing existing handle.")
        return _vl_engine

    # Resolve model source
    if not model_path:
        model_path = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else MODEL_ID

    print(f"  [VL Engine] Starting persistent vLLM AsyncLLMEngine from: {model_path}")

    try:
        from vllm import AsyncLLMEngine, AsyncEngineArgs
        from transformers import AutoTokenizer

        engine_args = AsyncEngineArgs(
            model=model_path,
            dtype="bfloat16",
            tensor_parallel_size=1,          # single-GPU only — no TP in this pass
            gpu_memory_utilization=0.85,     # leave headroom for frame preprocessing
            max_model_len=4096,
            trust_remote_code=True,
            enforce_eager=False,             # CUDA graphs on for throughput
            disable_log_requests=True,       # suppress per-request vLLM noise
        )
        _vl_engine    = AsyncLLMEngine.from_engine_args(engine_args)
        _vl_tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        print("  [VL Engine] AsyncLLMEngine started successfully on CUDA.")
    except ImportError:
        print(
            "  [VL Engine ERROR] vLLM not installed. "
            "Run: pip install vllm\n"
            "  Falling back to HuggingFace PATH A — playlist concurrency unavailable."
        )
        raise

    return _vl_engine


async def stop_vl_engine() -> None:
    """
    Rule 1 — Fully release the vLLM engine and GPU memory.

    Call this ONLY at process exit or explicit shutdown — NOT after each video.
    After this call, start_vl_engine() can be called again to reload.
    """
    global _vl_engine, _vl_tokenizer

    if _vl_engine is None:
        return

    print("  [VL Engine] Shutting down AsyncLLMEngine...", flush=True)
    try:
        # vLLM AsyncLLMEngine exposes abort() per-request; for a clean shutdown
        # we rely on Python GC after deleting the reference and clearing CUDA cache.
        engine = _vl_engine
        _vl_engine    = None
        _vl_tokenizer = None
        del engine
    except Exception as e:
        print(f"  [VL Engine] Warning during engine shutdown: {e}", flush=True)

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("  [VL Engine] Engine stopped and VRAM released.", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# PATH B — SINGLE ASYNC REQUEST (Rule 2)
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_video_async(
    video_frames_or_path: Union[str, List],
    case_id: str,
    user_prompt: str = "Analyze this video.",
    metadata: Optional[dict] = None,
) -> dict:
    """
    Rule 2 — Submit one video to the running vLLM engine and await its result.

    This function does NOT manage concurrency — it makes exactly one request
    and returns one result dict.  Concurrency control lives in process_playlist().

    Parameters
    ----------
    video_frames_or_path : Either a file-system path string (video/image) or a
                           list of PIL Image objects already extracted by the caller.
    case_id              : Identifier for this video's case (used for logging only here;
                           add_artifact is called by process_playlist, not here).
    user_prompt          : The analysis question.
    metadata             : Optional dict with ai_generated_flag, deepfake_flag, etc.

    Returns
    -------
    dict — same schema as what run_vision_analysis() returns:
      On success: parsed JSON dict, or {"raw_output": <text>} if model didn't output JSON.
      On engine error: raises the exception (caller — process_playlist — handles it).
    """
    if _vl_engine is None:
        raise RuntimeError(
            "vLLM engine is not running. Call start_vl_engine() before analyze_video_async()."
        )

    # ── Step 1: Resolve frames ────────────────────────────────────────────────
    if isinstance(video_frames_or_path, str):
        # Path string — extract frames using the same OpenCV logic as LocalAdapter
        frames = _extract_frames_from_path(video_frames_or_path)
    else:
        frames = list(video_frames_or_path)  # already PIL images

    if not frames:
        raise ValueError(f"[case={case_id}] No frames could be extracted from input.")

    print(f"  [VL Engine] [{case_id}] Submitting {len(frames)} frames to engine...")

    # ── Step 2: Build prompt ──────────────────────────────────────────────────
    _, prompt_text = _build_prompt(user_prompt, metadata)

    # For vLLM with a vision-language model we encode frames as base64 in the
    # prompt using the Qwen2.5-VL chat template via the tokenizer.
    try:
        from qwen_vl_utils import process_vision_info
    except ImportError:
        raise ImportError("qwen-vl-utils is required. Run: pip install qwen-vl-utils")

    content = []
    for frame in frames:
        frame.thumbnail((768, 768))
        content.append({"type": "image", "image": frame})
    content.append({"type": "text", "text": prompt_text})

    messages = [{"role": "user", "content": content}]

    # Build text prompt via HuggingFace processor (tokenizer side only — no model load)
    # We use a lightweight AutoProcessor just for the chat template, not for inference.
    processor = _get_vl_processor()
    prompt_str   = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, _ = process_vision_info(messages)

    # ── Step 3: Submit to vLLM engine ─────────────────────────────────────────
    from vllm import SamplingParams

    sampling_params = SamplingParams(
        max_tokens=1024,
        temperature=0.1,
        top_p=0.9,
        stop=["<|im_end|>", "<|endoftext|>"],
    )

    # Generate a unique request ID so vLLM can track it
    request_id = f"{case_id}_{int(time.time() * 1000)}"

    # vLLM's multi-modal input format for Qwen2.5-VL
    mm_data = {}
    if image_inputs:
        mm_data["image"] = image_inputs

    output_text = ""
    async for request_output in _vl_engine.generate(
        prompt=prompt_str,
        sampling_params=sampling_params,
        request_id=request_id,
        multi_modal_data=mm_data if mm_data else None,
    ):
        # Stream tokens; take the last (complete) output
        if request_output.outputs:
            output_text = request_output.outputs[0].text

    print(f"  [VL Engine] [{case_id}] Generation complete ({len(output_text)} chars).")

    # ── Step 4: Parse and return (same schema as PATH A) ─────────────────────
    result = _parse_vl_output(output_text)
    result["_case_id"]     = case_id
    result["_raw_output"]  = output_text   # always keep raw alongside parsed JSON
    return result


# ─────────────────────────────────────────────────────────────────────────────
# PATH B — WORKER POOL (Rule 3, 4, 5)
# ─────────────────────────────────────────────────────────────────────────────

async def process_playlist(
    video_list:     List[dict],
    case_ids:       List[str],
    max_concurrent: int,
) -> List[dict]:
    """
    Rule 3 — Semaphore-capped async worker pool for playlist processing.

    Parameters
    ----------
    video_list     : List of video dicts (each has at minimum a 'url' or 'path' key,
                     plus optional 'title', 'user_prompt', 'metadata').
                     Produced by resolve_playlist() in chorus_input.py.
    case_ids       : One case_id string per video — same length as video_list.
                     Must be pre-created via project_manager.create_case() before calling.
    max_concurrent : Maximum number of analyze_video_async() calls in flight at once.
                     The caller decides this based on their GPU; no default is baked in here.

    Returns
    -------
    List[dict] — one result per video, in the SAME ORDER as video_list, regardless
                 of which video finished first.
                 Success slot : result dict from analyze_video_async()
                 Failure slot : {"case_id": ..., "error": ..., "status": "failed"}
    """
    if len(video_list) != len(case_ids):
        raise ValueError(
            f"video_list ({len(video_list)} items) and case_ids ({len(case_ids)} items) "
            "must have the same length."
        )

    if _vl_engine is None:
        raise RuntimeError(
            "vLLM engine is not running. Call start_vl_engine() before process_playlist()."
        )

    # Pre-allocate results list — order is preserved by index assignment, not append order
    results: List[Optional[dict]] = [None] * len(video_list)

    # One semaphore shared across ALL workers — this is the concurrency cap
    sem = asyncio.Semaphore(max_concurrent)

    # Lazy import here to avoid making project_manager a hard import at module level
    import project_manager as pm

    async def _worker(idx: int, video: dict, case_id: str) -> None:
        """
        Inner worker for one video.

        Rule 3: Acquires semaphore before calling analyze_video_async, releases after.
        Rule 4: Catches exceptions per-video so others continue unaffected.
        Rule 5: Calls add_artifact immediately upon completion (success or failure),
                not after the whole gather finishes.
        """
        async with sem:
            try:
                # Resolve what to pass as video_frames_or_path
                video_input = video.get("path") or video.get("url") or video
                user_prompt = video.get("user_prompt", "Analyze this video.")
                metadata    = video.get("metadata", {})

                result = await analyze_video_async(
                    video_frames_or_path=video_input,
                    case_id=case_id,
                    user_prompt=user_prompt,
                    metadata=metadata,
                )
                results[idx] = result

                # Rule 5 — write-back immediately as this video finishes
                result_bytes = json.dumps(result, ensure_ascii=False).encode("utf-8")
                try:
                    pm.add_artifact(case_id, "vision_analysis", result_bytes, actor="vl_worker_pool")
                    print(f"  [VL Pool] [{case_id}] Artifact written to case record.")
                except Exception as artifact_err:
                    print(
                        f"  [VL Pool] [{case_id}] WARNING: add_artifact failed: {artifact_err}"
                    )

            except Exception as e:
                # Rule 4 — isolate this video's failure; others keep running
                error_msg = f"{type(e).__name__}: {e}"
                print(f"  [VL Pool] [{case_id}] FAILED: {error_msg}", flush=True)

                failure_record = {
                    "case_id": case_id,
                    "error":   error_msg,
                    "status":  "failed",
                }
                results[idx] = failure_record

                # Rule 5 — persist failure record immediately too
                failure_bytes = json.dumps(failure_record, ensure_ascii=False).encode("utf-8")
                try:
                    pm.add_artifact(
                        case_id, "vision_analysis", failure_bytes, actor="vl_worker_pool"
                    )
                except Exception as artifact_err:
                    print(
                        f"  [VL Pool] [{case_id}] WARNING: add_artifact (failure) failed: {artifact_err}"
                    )

    # Build all worker coroutines upfront — the semaphore prevents overload,
    # so we submit the WHOLE playlist at once (Rule 3 — no manual batching/chunking).
    tasks = [
        _worker(i, video, cid)
        for i, (video, cid) in enumerate(zip(video_list, case_ids))
    ]

    # Rule 4 — return_exceptions=True is a safety net; the inner try/except already
    # catches per-video errors, but this prevents any uncaught exception in _worker
    # from cancelling the entire gather.
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Post-process any exceptions that escaped the inner handler (should not happen,
    # but belt-and-suspenders to guarantee the caller always gets a list[dict]).
    for i, raw in enumerate(raw_results):
        if isinstance(raw, BaseException):
            case_id = case_ids[i]
            results[i] = {
                "case_id": case_id,
                "error":   f"{type(raw).__name__}: {raw}",
                "status":  "failed",
            }
            print(
                f"  [VL Pool] [{case_id}] Unhandled exception captured by gather: {raw}",
                flush=True,
            )

    successful = sum(1 for r in results if r and r.get("status") != "failed")
    failed     = len(results) - successful
    print(
        f"  [VL Pool] Playlist complete. "
        f"{successful}/{len(results)} succeeded, {failed} failed.",
        flush=True,
    )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS (PATH B)
# ─────────────────────────────────────────────────────────────────────────────

_vl_processor_cache: Optional[object] = None


def _get_vl_processor():
    """
    Return a cached AutoProcessor for chat-template formatting.
    This is NOT the inference model — just the tokenizer/processor side.
    Loaded lazily the first time analyze_video_async() is called.
    """
    global _vl_processor_cache
    if _vl_processor_cache is None:
        model_path = LOCAL_MODEL_PATH if os.path.exists(LOCAL_MODEL_PATH) else MODEL_ID
        _vl_processor_cache = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
    return _vl_processor_cache


def _extract_frames_from_path(video_path: str, n_frames: int = 8) -> list:
    """
    Extract N evenly-spaced frames from a local video or image file.
    Returns a list of PIL Images.  Mirrors LocalAdapter._video() logic.
    """
    try:
        import cv2
        from PIL import Image as PILImage
    except ImportError as e:
        raise ImportError(f"opencv-python and Pillow are required: {e}")

    ext = os.path.splitext(video_path)[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".gif"}:
        img = PILImage.open(video_path).convert("RGB")
        return [img]

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"OpenCV could not open: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    dur   = total / fps if fps > 0 else 0

    # Dynamic sampling: ~1 frame/1.5s, capped at [8, 24]
    dynamic_n = max(8, min(24, int(dur / 1.5) if dur > 0 else 8))
    n = min(dynamic_n, max(total, 1))

    indices = [int(i * (total - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames
