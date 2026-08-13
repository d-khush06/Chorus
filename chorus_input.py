"""
chorus_input.py — Unified Input Adapter for Chorus Platform
============================================================
Single entry point that accepts ANY source and routes it to the correct adapter.

Supported sources:
  • YouTube URL         → https://youtube.com/watch?v=...
  • YouTube search      → "python tutorials youtube"
  • Local video file    → C:/path/to/video.mp4  (MP4, AVI, MKV, MOV, WMV, WEBM)
  • Local image file    → C:/path/to/image.jpg  (JPG, PNG, BMP, WEBP)
  • RTSP stream         → rtsp://user:pass@192.168.1.100/stream
  • HTTP stream         → http://camera-ip/stream.mjpg
  • Plain text query    → "what is machine learning?"

Stub hooks (wired, not yet active — team members rewire these):
  • run_orchestrator()      ← Chorus Router model (being trained)
  • run_quality_gate()      ← Quality scoring
  • run_duplicate_check()   ← Perceptual hashing
  • run_deepfake_check()    ← Deepfake detection
  • run_manual_annotation() ← Manual annotation flags

Usage:
    python chorus_input.py
"""

import os
import re
import sys
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  (override via environment variables or .env)
# ─────────────────────────────────────────────────────────────────────────────
LOCAL_VIDEO_FRAMES  = int(os.getenv("LOCAL_VIDEO_FRAMES",  "8"))  # frames sampled from local video
RTSP_FRAMES         = int(os.getenv("RTSP_FRAMES",         "4"))  # frames captured from RTSP
RTSP_FRAME_INTERVAL = int(os.getenv("RTSP_FRAME_INTERVAL", "2"))  # seconds between RTSP captures

TEXT_MODEL_PATH  = os.path.join(".", "models", "Qwen2.5-7B-Browser-Agent-Merged")
TEXT_MODEL_HF_ID = "dkhush06/Qwen2.5-7B-Browser-Agent-Merged"
VL_MODEL_PATH    = os.path.join(".", "models", "Qwen2.5-VL-Agent2-Merged")
VL_MODEL_HF_ID   = "dkhush06/Qwen2.5-VL-Agent2-Merged"

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm", ".flv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".gif"}


# ─────────────────────────────────────────────────────────────────────────────
# CHORUS PAYLOAD
# Standardized data object produced by every adapter.
# Every downstream system (Orchestrator, Quality Gate, etc.) consumes this.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ChorusPayload:
    source_type:   str   # "youtube" | "local_video" | "local_image" | "rtsp" | "text"
    source_uri:    str   # original user input (URL, file path, or query string)
    frames:        list  # list of PIL Images — empty for text-only sources
    metadata:      dict  # resolution, fps, duration, frame_count, timestamp, ...
    raw_text:      str   # scraped text (YouTube) or user question (text)
    user_question: str = ""

    # ── Hooks for team features (filled in by pipeline stubs below) ──────────
    quality_score:         Optional[float] = None  # 0.0–1.0; Quality Gate fills this
    duplicate_hash:        Optional[str]   = None  # perceptual hash; Duplicate Check fills
    is_deepfake:           Optional[bool]  = None  # True/False; Deepfake detector fills
    annotation_flags:      list            = field(default_factory=list)
    orchestrator_decision: Optional[str]   = None  # "vl_model" | "text_model" | ...

    def summary(self) -> str:
        frame_info = f"{len(self.frames)} frame(s)" if self.frames else "no frames"
        return (
            f"[{self.source_type.upper()}] {self.source_uri[:60]} | "
            f"{frame_info} | quality={self.quality_score} | deepfake={self.is_deepfake}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ████  STUB HOOKS
# These functions are WIRED into the pipeline but are NO-OPS right now.
# Team members replace the body of each function when their feature is ready.
# The call sites in ChorusAgent._run_pipeline() never change.
# ─────────────────────────────────────────────────────────────────────────────

def run_orchestrator(payload: ChorusPayload) -> str:
    """
    STUB — Chorus Router / Orchestrator Model
    ─────────────────────────────────────────
    TODO (team): Replace with Chorus Router model inference.
    The orchestrator receives ChorusPayload and decides which model to run.

    Expected return values:
        "vl_model"    — route to Qwen2.5-VL vision model
        "text_model"  — route to Qwen2.5-7B text model
        "reject"      — block this input (too low quality / duplicate)
        "flag_review" — send to manual review queue
    """
    # Placeholder: visual sources → VL model, everything else → text model
    if payload.source_type in ("local_video", "local_image", "rtsp", "http_stream"):
        return "vl_model"
    return "text_model"


def run_quality_gate(payload: ChorusPayload) -> float:
    """
    STUB — Quality Gate
    ───────────────────
    TODO (team): Implement video quality scoring.
    Inputs: payload.frames (PIL Images), payload.metadata
    Returns float 0.0–1.0. Payloads < 0.2 are rejected.
    """
    return 1.0  # stub: all inputs pass


def run_duplicate_check(payload: ChorusPayload) -> Optional[str]:
    """
    STUB — Duplicate / Perceptual Hash Check
    ─────────────────────────────────────────
    TODO (team): Implement perceptual hashing (pHash for frames, SHA-256 for text).
    Returns a hash string. Caller compares against stored hashes DB.
    Returns None if not applicable.
    """
    if payload.source_uri:
        return hashlib.sha256(payload.source_uri.encode()).hexdigest()
    return None


def run_deepfake_check(payload: ChorusPayload) -> bool:
    """
    STUB — Deepfake / Manipulation Detector
    ────────────────────────────────────────
    TODO (team): Plug in deepfake detection model.
    Inputs: payload.frames (PIL Images), payload.metadata
    Returns True if deepfake detected, False otherwise.
    """
    return False  # stub: no detection active


def run_manual_annotation(payload: ChorusPayload) -> list:
    """
    STUB — Manual Annotation Flags
    ────────────────────────────────
    TODO (team): Implement annotation pipeline.
    Returns list of flag strings, e.g. ["violence", "misleading_title"].
    Empty list = no flags.
    """
    return []  # stub: no annotations


# ─────────────────────────────────────────────────────────────────────────────
# INPUT ROUTER
# Detects the type of input from the user's raw string.
# ─────────────────────────────────────────────────────────────────────────────
class InputRouter:
    _YT          = re.compile(r'(youtube\.com|youtu\.be)', re.IGNORECASE)
    _RTSP        = re.compile(r'^rtsp://', re.IGNORECASE)
    _HTTP_STREAM = re.compile(
        r'https?://.*(/stream|/cam|/video|mjpeg|\.m3u8)', re.IGNORECASE
    )

    @classmethod
    def detect(cls, user_input: str) -> str:
        """
        Returns one of:
          "youtube"        — YouTube watch URL
          "youtube_search" — YouTube search URL or text containing 'youtube'
          "rtsp"           — rtsp:// URL
          "http_stream"    — HTTP camera/stream URL
          "local_video"    — existing local video file
          "local_image"    — existing local image file
          "text"           — plain text query (fallback)
        """
        s = user_input.strip()

        if cls._YT.search(s):
            if "results" in s or "search_query" in s or (
                "youtube.com" in s.lower() and "watch?v=" not in s and "youtu.be" not in s
            ):
                return "youtube_search"
            return "youtube"

        if cls._RTSP.match(s):
            return "rtsp"

        if cls._HTTP_STREAM.search(s):
            return "http_stream"

        if os.path.exists(s):
            ext = os.path.splitext(s)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                return "local_video"
            if ext in IMAGE_EXTENSIONS:
                return "local_image"
            return "text"

        if re.search(r'\byoutube\b', s, re.IGNORECASE):
            return "youtube_search"

        return "text"


# ─────────────────────────────────────────────────────────────────────────────
# YOUTUBE ADAPTER
# ─────────────────────────────────────────────────────────────────────────────
class YouTubeAdapter:
    """
    Scrapes YouTube via Playwright and returns structured text data.
    No frames — text model handles YouTube results.
    """

    def process(self, source_uri: str, source_type: str) -> ChorusPayload:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return self._err(source_uri,
                "Playwright not installed. Run: pip install playwright && playwright install chromium")

        if source_type == "youtube_search":
            query = self._parse_query(source_uri)
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        else:
            url = source_uri

        print(f"  [YouTube] Opening: {url}")
        videos = []

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, slow_mo=150)
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(4)
                page.evaluate("window.scrollBy(0, 600)")
                time.sleep(2)

                videos = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer').forEach(r => {
                        const t = r.querySelector('a#video-title, #video-title');
                        const l = r.querySelector('a#video-title, a#thumbnail');
                        const c = r.querySelector('#channel-name, ytd-channel-name');
                        if (t && l && l.href && l.href.includes('/watch?v=')) {
                            out.push({ title: t.innerText.trim(), url: l.href,
                                       channel: c ? c.innerText.trim() : '' });
                        }
                    });
                    return out.slice(0, 15);
                }""")

                if not videos:
                    videos = page.evaluate("""() => {
                        const out = [];
                        document.querySelectorAll('a[href*="/watch?v="]').forEach(a => {
                            const text = a.innerText.trim() || a.getAttribute('title') || '';
                            if (text && text.length > 5 && !out.find(r => r.url === a.href))
                                out.push({ title: text, url: a.href, channel: '' });
                        });
                        return out.slice(0, 15);
                    }""")

                time.sleep(3)
                browser.close()
        except Exception as e:
            return self._err(source_uri, f"Browser error: {e}")

        raw_text = ""
        for i, v in enumerate(videos, 1):
            raw_text += f"{i}. {v['title']}\n   URL: {v['url']}\n"
            if v.get("channel"):
                raw_text += f"   Channel: {v['channel']}\n"
            raw_text += "\n"

        print(f"  [YouTube] Scraped {len(videos)} video(s). ✓")
        return ChorusPayload(
            source_type="youtube", source_uri=source_uri, frames=[],
            metadata={"video_count": len(videos), "scraped_url": url,
                      "timestamp": datetime.now().isoformat()},
            raw_text=raw_text.strip(),
        )

    def _parse_query(self, s: str) -> str:
        m = re.search(r'search_query=([^&]+)', s)
        if m:
            return m.group(1).replace("+", " ")
        cleaned = re.sub(r'https?://(www\.)?youtube\.com[^\s]*', '', s, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'\byoutube\b', '', cleaned, flags=re.IGNORECASE).strip()
        return cleaned or s

    def _err(self, uri: str, msg: str) -> ChorusPayload:
        print(f"  [YouTubeAdapter ERROR] {msg}")
        return ChorusPayload(source_type="youtube", source_uri=uri,
                             frames=[], metadata={"error": msg}, raw_text=f"[ERROR] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL FILE ADAPTER
# ─────────────────────────────────────────────────────────────────────────────
class LocalAdapter:
    """
    Reads local video or image files.
    Video  → samples N evenly-spaced frames via OpenCV.
    Image  → loads directly as a single PIL Image.
    """

    def process(self, file_path: str, source_type: str) -> ChorusPayload:
        try:
            import cv2
            from PIL import Image as PILImage
        except ImportError as e:
            return self._err(file_path, source_type,
                             f"Missing dependency: {e}. Run: pip install opencv-python Pillow")

        if source_type == "local_image":
            return self._image(file_path, PILImage)
        return self._video(file_path, cv2, PILImage)

    # ── Image ──────────────────────────────────────────────────────────────
    def _image(self, path: str, PILImage) -> ChorusPayload:
        print(f"  [Local] Loading image: {path}")
        try:
            img = PILImage.open(path).convert("RGB")
            w, h = img.size
            return ChorusPayload(
                source_type="local_image", source_uri=path, frames=[img],
                metadata={"width": w, "height": h, "file": os.path.basename(path),
                          "size_bytes": os.path.getsize(path),
                          "timestamp": datetime.now().isoformat()},
                raw_text="",
            )
        except Exception as e:
            return self._err(path, "local_image", str(e))

    # ── Video ──────────────────────────────────────────────────────────────
    def _video(self, path: str, cv2, PILImage) -> ChorusPayload:
        print(f"  [Local] Opening video: {path}")
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return self._err(path, "local_video", "OpenCV could not open file.")

        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dur    = round(total / fps, 2) if fps > 0 else 0

        n = min(LOCAL_VIDEO_FRAMES, max(total, 1))
        indices = [int(i * (total - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]

        print(f"  [Local] Extracting {n} frames from {total} total ({dur}s @ {fps:.1f}fps)...")
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        cap.release()

        print(f"  [Local] Extracted {len(frames)} frame(s). ✓")
        return ChorusPayload(
            source_type="local_video", source_uri=path, frames=frames,
            metadata={"file": os.path.basename(path), "total_frames": total,
                      "fps": fps, "duration_sec": dur, "width": width, "height": height,
                      "frames_sampled": len(frames),
                      "timestamp": datetime.now().isoformat()},
            raw_text="",
        )

    def _err(self, path: str, stype: str, msg: str) -> ChorusPayload:
        print(f"  [LocalAdapter ERROR] {msg}")
        return ChorusPayload(source_type=stype, source_uri=path,
                             frames=[], metadata={"error": msg}, raw_text=f"[ERROR] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# RTSP / HTTP STREAM ADAPTER
# ─────────────────────────────────────────────────────────────────────────────
class RTSPAdapter:
    """
    Connects to a live RTSP or HTTP stream via OpenCV.
    Captures RTSP_FRAMES frames spaced RTSP_FRAME_INTERVAL seconds apart.
    """

    def process(self, stream_url: str, source_type: str) -> ChorusPayload:
        try:
            import cv2
            from PIL import Image as PILImage
        except ImportError as e:
            return self._err(stream_url,
                             f"Missing dependency: {e}. Run: pip install opencv-python Pillow")

        print(f"  [RTSP] Connecting to: {stream_url}")
        cap = cv2.VideoCapture(stream_url)

        if not cap.isOpened():
            return self._err(stream_url,
                "Could not open stream. Check URL, credentials, and network.")

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 0.0
        print(f"  [RTSP] Stream opened — {width}x{height} @ {fps:.1f}fps")
        print(f"  [RTSP] Capturing {RTSP_FRAMES} frames every {RTSP_FRAME_INTERVAL}s...")

        frames = []
        for i in range(RTSP_FRAMES):
            # Flush stale buffer frames
            for _ in range(5):
                cap.grab()
            ret, frame = cap.read()
            if ret:
                from PIL import Image as PILImage
                frames.append(PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                print(f"  [RTSP] Frame {i + 1}/{RTSP_FRAMES} ✓")
            else:
                print(f"  [RTSP] Frame {i + 1}/{RTSP_FRAMES} failed (stream drop?)")
            if i < RTSP_FRAMES - 1:
                time.sleep(RTSP_FRAME_INTERVAL)

        cap.release()
        print(f"  [RTSP] Done — {len(frames)} frame(s) captured.")

        return ChorusPayload(
            source_type="rtsp", source_uri=stream_url, frames=frames,
            metadata={"stream_url": stream_url, "width": width, "height": height,
                      "fps": fps, "frames_captured": len(frames),
                      "capture_interval_sec": RTSP_FRAME_INTERVAL,
                      "timestamp": datetime.now().isoformat()},
            raw_text="",
        )

    def _err(self, uri: str, msg: str) -> ChorusPayload:
        print(f"  [RTSPAdapter ERROR] {msg}")
        return ChorusPayload(source_type="rtsp", source_uri=uri,
                             frames=[], metadata={"error": msg}, raw_text=f"[ERROR] {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# MODEL WRAPPERS  (lazy-loaded — only instantiated on first use)
# ─────────────────────────────────────────────────────────────────────────────
class TextModel:
    """Wraps Qwen2.5-7B for text / YouTube queries."""

    def __init__(self):
        self._model = self._tok = self._device = None

    def _load(self):
        if self._model:
            return
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        src = TEXT_MODEL_PATH if os.path.exists(TEXT_MODEL_PATH) else TEXT_MODEL_HF_ID
        print(f"\n  [TextModel] Loading: {src}")
        self._tok    = AutoTokenizer.from_pretrained(src)
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        if self._device == "cuda":
            bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                     bnb_4bit_use_double_quant=True,
                                     bnb_4bit_compute_dtype=torch.bfloat16)
            self._model = AutoModelForCausalLM.from_pretrained(
                src, quantization_config=bnb, device_map="auto", low_cpu_mem_usage=True)
        else:
            self._model = AutoModelForCausalLM.from_pretrained(
                src, torch_dtype=torch.float32, low_cpu_mem_usage=True)
            self._model.to("cpu")
        print("  [TextModel] Ready ✓")

    def generate(self, system_prompt: str, user_content: str,
                 max_new_tokens: int = 512) -> str:
        import torch
        self._load()
        msgs  = [{"role": "system", "content": system_prompt},
                 {"role": "user",   "content": user_content}]
        text  = self._tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp   = self._tok([text], return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model.generate(**inp, max_new_tokens=max_new_tokens,
                                       do_sample=False, temperature=None, top_p=None)
        new = out[0][inp["input_ids"].shape[1]:]
        return self._tok.decode(new, skip_special_tokens=True).strip()


class VisionModel:
    """Wraps Qwen2.5-VL for video / image / RTSP queries."""

    def __init__(self):
        self._model = self._proc = self._device = None

    def _load(self):
        if self._model:
            return
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        src = VL_MODEL_PATH if os.path.exists(VL_MODEL_PATH) else VL_MODEL_HF_ID
        print(f"\n  [VisionModel] Loading: {src}")
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._proc   = AutoProcessor.from_pretrained(src)
        self._model  = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            src,
            torch_dtype=torch.bfloat16 if self._device == "cuda" else torch.float32,
            device_map="auto" if self._device == "cuda" else None,
            low_cpu_mem_usage=True,
        )
        if self._device == "cpu":
            self._model.to("cpu")
        print("  [VisionModel] Ready ✓")

    def generate(self, frames: list, question: str, max_new_tokens: int = 512) -> str:
        import torch
        self._load()
        if not frames:
            return "[VisionModel] No frames to analyze."
        content = [{"type": "image", "image": f} for f in frames]
        content.append({"type": "text", "text": question})
        msgs = [{"role": "user", "content": content}]
        text = self._proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inp  = self._proc(text=[text], images=frames, return_tensors="pt").to(self._device)
        with torch.no_grad():
            out = self._model.generate(**inp, max_new_tokens=max_new_tokens, do_sample=False)
        new = out[0][inp["input_ids"].shape[1]:]
        return self._proc.decode(new, skip_special_tokens=True).strip()


# ─────────────────────────────────────────────────────────────────────────────
# CHORUS AGENT  — ties everything together
# ─────────────────────────────────────────────────────────────────────────────
class ChorusAgent:
    """
    Main agent class.
      1. Routes input → correct adapter → ChorusPayload
      2. Runs stub pipeline (quality gate, duplicate, deepfake, orchestrator)
      3. Routes payload → correct model
      4. Returns answer string
    """

    def __init__(self):
        self.router        = InputRouter()
        self._yt           = YouTubeAdapter()
        self._local        = LocalAdapter()
        self._rtsp         = RTSPAdapter()
        self._text_model   = TextModel()   # lazy-loaded
        self._vision_model = VisionModel() # lazy-loaded

    # ── 1. Build payload ──────────────────────────────────────────────────────
    def build_payload(self, user_input: str) -> ChorusPayload:
        src_type = self.router.detect(user_input)
        print(f"\n  [Router] Source type: {src_type.upper()}")

        if src_type in ("youtube", "youtube_search"):
            return self._yt.process(user_input, src_type)
        if src_type in ("local_video", "local_image"):
            return self._local.process(user_input, src_type)
        if src_type in ("rtsp", "http_stream"):
            return self._rtsp.process(user_input, src_type)

        # Plain text
        return ChorusPayload(
            source_type="text", source_uri=user_input, frames=[],
            metadata={"timestamp": datetime.now().isoformat()},
            raw_text=user_input,
        )

    # ── 2. Stub pipeline ──────────────────────────────────────────────────────
    def _run_pipeline(self, payload: ChorusPayload) -> ChorusPayload:
        """
        Call order is intentional:
          quality → duplicate → deepfake → annotation → orchestrator
        When team members implement a stub, they only change the stub function body.
        Nothing in this method changes.
        """
        payload.quality_score         = run_quality_gate(payload)
        payload.duplicate_hash        = run_duplicate_check(payload)
        payload.is_deepfake           = run_deepfake_check(payload)
        payload.annotation_flags      = run_manual_annotation(payload)
        payload.orchestrator_decision = run_orchestrator(payload)
        return payload

    # ── 3. Run ────────────────────────────────────────────────────────────────
    def run(self, user_input: str, user_question: str = "") -> str:
        payload = self.build_payload(user_input)

        if "error" in payload.metadata:
            return f"[ERROR] {payload.metadata['error']}"

        payload.user_question = user_question or payload.raw_text or "Describe what you see."

        print("  [Pipeline] Running quality gate → duplicate → deepfake → orchestrator...")
        payload = self._run_pipeline(payload)

        print(f"  [Pipeline] quality={payload.quality_score:.2f}  "
              f"deepfake={payload.is_deepfake}  "
              f"flags={payload.annotation_flags}  "
              f"decision={payload.orchestrator_decision}")

        if payload.quality_score is not None and payload.quality_score < 0.2:
            return f"[REJECTED] Quality gate score too low: {payload.quality_score:.2f}"

        decision = payload.orchestrator_decision or "text_model"

        if decision == "vl_model":
            if not payload.frames:
                return "[ERROR] VL model selected but no frames were extracted."
            print(f"  [Model] → VisionModel ({len(payload.frames)} frames)...")
            return self._vision_model.generate(payload.frames, payload.user_question)

        # text_model (YouTube + plain text)
        print("  [Model] → TextModel...")
        context = payload.raw_text or payload.user_question
        user_content = (
            f"Context:\n{context}\n\nQuestion: {payload.user_question}"
            if payload.user_question and payload.user_question != payload.raw_text
            else context
        )
        return self._text_model.generate(
            system_prompt=(
                "You are Chorus, a universal video intelligence assistant. "
                "Answer the user's question based on the provided context."
            ),
            user_content=user_content,
        )


# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE CLI
# ─────────────────────────────────────────────────────────────────────────────
VISUAL_TYPES = ("local_video", "local_image", "rtsp", "http_stream")

BANNER = """
╔══════════════════════════════════════════════════════════╗
║   🎬  CHORUS — Universal Video Intelligence Platform    ║
╚══════════════════════════════════════════════════════════╝

  Accepted inputs
  ───────────────
  • YouTube URL / search  →  youtube.com/watch?v=...  or  "python tutorial youtube"
  • Local video           →  C:/path/to/video.mp4  (.mp4 .avi .mkv .mov .wmv .webm)
  • Local image           →  C:/path/to/image.jpg  (.jpg .png .bmp .webp)
  • RTSP stream           →  rtsp://user:pass@192.168.1.100/stream
  • HTTP stream           →  http://camera-ip/stream.mjpg
  • Plain text question   →  just type anything

  Type 'exit' or 'quit' to stop.
"""


def main():
    print(BANNER)
    agent = ChorusAgent()

    while True:
        try:
            print("─" * 60)
            user_input = input("📥  Input > ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("\n👋  Goodbye!")
                break

            # Ask follow-up question for visual inputs
            detected = InputRouter.detect(user_input)
            if detected in VISUAL_TYPES:
                user_question = input("❓  Question about this input > ").strip()
                if not user_question:
                    user_question = "Describe what you see in detail."
            else:
                user_question = input("❓  Your question > ").strip() or user_input

            print()
            t0     = time.time()
            answer = agent.run(user_input, user_question)
            took   = time.time() - t0

            print(f"\n{'═' * 60}")
            print("🤖  CHORUS ANSWER:")
            print("═" * 60)
            print(answer)
            print(f"\n  [Done in {took:.1f}s]")
            print("═" * 60)

        except KeyboardInterrupt:
            print("\n\n👋  Interrupted. Goodbye!")
            break
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
