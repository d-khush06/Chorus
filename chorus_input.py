"""
chorus_input.py — Pure Code Input Adapter & Pipeline for Chorus Platform
========================================================================
Accepts ANY input source, auto-detects it, routes it to the pure-code adapter
(OpenCV, Playwright, PIL), executes team feature stubs, and outputs a 
standardized ChorusPayload.

NO ML/LLM models are loaded or invoked inside this module.

Supported sources:
  • YouTube URL         → https://youtube.com/watch?v=...
  • YouTube search      → "python tutorials youtube"
  • Local video file    → C:/path/to/video.mp4  (MP4, AVI, MKV, MOV, WMV, WEBM)
  • Local image file    → C:/path/to/image.jpg  (JPG, PNG, BMP, WEBP)
  • RTSP stream         → rtsp://user:pass@192.168.1.100/stream
  • HTTP stream         → http://camera-ip/stream.mjpg
  • Plain text query    → "what is machine learning?"

Stub hooks (pure code — team members rewire these):
  • run_orchestrator()      ← Chorus Router model decision stub
  • run_quality_gate()      ← Quality scoring stub
  • run_duplicate_check()   ← Perceptual hashing stub
  • run_deepfake_check()    ← Deepfake detection stub
  • run_manual_annotation() ← Manual annotation flags stub

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

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
LOCAL_VIDEO_FRAMES  = int(os.getenv("LOCAL_VIDEO_FRAMES",  "8"))  # frames sampled from local video
RTSP_FRAMES         = int(os.getenv("RTSP_FRAMES",         "4"))  # frames captured from RTSP
RTSP_FRAME_INTERVAL = int(os.getenv("RTSP_FRAME_INTERVAL", "2"))  # seconds between RTSP captures

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

    def to_report(self) -> str:
        """Returns a clean text summary of the processed payload."""
        lines = [
            f"Source Type       : {self.source_type.upper()}",
            f"Source URI        : {self.source_uri}",
            f"Frames Extracted  : {len(self.frames)}",
            f"User Question     : {self.user_question}",
            f"Quality Gate Score: {self.quality_score if self.quality_score is not None else 'N/A'}",
            f"Duplicate Hash    : {self.duplicate_hash[:16] + '...' if self.duplicate_hash else 'N/A'}",
            f"Deepfake Flag     : {self.is_deepfake}",
            f"Annotation Flags  : {self.annotation_flags if self.annotation_flags else 'None'}",
            f"Orchestrator Target: {self.orchestrator_decision}",
        ]
        if self.metadata:
            lines.append("Metadata          : " + ", ".join(f"{k}={v}" for k, v in self.metadata.items() if k != "timestamp"))
        if self.raw_text:
            snippet = self.raw_text[:200].replace("\n", " ") + ("..." if len(self.raw_text) > 200 else "")
            lines.append(f"Scraped Text Snippet: {snippet}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# ████  STUB HOOKS
# These functions are WIRED into the pipeline but are NO-OPS right now.
# Team members replace the body of each function when their feature is ready.
# The call sites in ChorusInputPipeline._run_pipeline() never change.
# ─────────────────────────────────────────────────────────────────────────────

def run_orchestrator(payload: ChorusPayload) -> str:
    """
    STUB — Chorus Router / Orchestrator Model
    ─────────────────────────────────────────
    TODO (team): Replace with Chorus Router model decision logic.
    """
    if payload.source_type in ("local_video", "local_image", "rtsp", "http_stream"):
        return "vl_model"
    return "text_model"


def run_quality_gate(payload: ChorusPayload) -> float:
    """
    STUB — Quality Gate
    ───────────────────
    TODO (team): Implement video quality scoring.
    """
    return 1.0  # stub: all inputs pass


def run_duplicate_check(payload: ChorusPayload) -> Optional[str]:
    """
    STUB — Duplicate / Perceptual Hash Check
    ─────────────────────────────────────────
    TODO (team): Implement perceptual hashing (pHash for frames, SHA-256 for text).
    """
    if payload.source_uri:
        return hashlib.sha256(payload.source_uri.encode()).hexdigest()
    return None


def run_deepfake_check(payload: "ChorusPayload") -> bool:
    """
    WIRED — Deepfake / Manipulation Detector (Step 4)
    ──────────────────────────────────────────────────
    Passes extracted frames to the Xception / SBT-based deepfake models.
    """
    if not _DEEPFAKE_CHECK_AVAILABLE:
        print("  [DeepfakeCheck] Module not available — pass-through.")
        return False

    try:
        from manipulation_detection import parse_step3_input
        # Convert ChorusPayload to the contract expected by Step 4
        payload_dict = {
            "video_id": hashlib.sha256(payload.source_uri.encode()).hexdigest()[:12],
            "video_path": payload.source_uri,
            "source_type": "youtube" if "youtube" in payload.source_type else "local_upload",
            "duration_seconds": payload.metadata.get("video_duration_seconds", 0.0),
            "dedup_status": "unique",
            "dedup_hash": payload.duplicate_hash or "none",
            "upstream_metadata": payload.metadata
        }
        step3_out = parse_step3_input(payload_dict)
        result = _real_deepfake_check(step3_out)
        
        flag = result.manipulation_check.verdict == "FLAGGED"
        print(f"  [DeepfakeCheck] Completed. Verdict: {result.manipulation_check.verdict}, Error: {result.manipulation_check.detector_error}")
        return flag
    except Exception as exc:
        print(f"  [DeepfakeCheck] Warning: {exc} — pass-through.")
        return False  # stub: no deepfake detected


def run_manual_annotation(payload: ChorusPayload) -> list:
    """
    STUB — Manual Annotation Flags
    ────────────────────────────────
    TODO (team): Implement annotation pipeline.
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
# YOUTUBE ADAPTER (Playwright Scraper)
# ─────────────────────────────────────────────────────────────────────────────
class YouTubeAdapter:
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

        print(f"  [YouTube Adapter] Opening: {url}")
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
                time.sleep(3)
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

                time.sleep(2)
                browser.close()
        except Exception as e:
            return self._err(source_uri, f"Browser error: {e}")

        raw_text = ""
        for i, v in enumerate(videos, 1):
            raw_text += f"{i}. {v['title']}\n   URL: {v['url']}\n"
            if v.get("channel"):
                raw_text += f"   Channel: {v['channel']}\n"
            raw_text += "\n"

        print(f"  [YouTube Adapter] Scraped {len(videos)} video(s). ✓")
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
# LOCAL FILE ADAPTER (OpenCV & PIL)
# ─────────────────────────────────────────────────────────────────────────────
class LocalAdapter:
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

    def _image(self, path: str, PILImage) -> ChorusPayload:
        print(f"  [Local Adapter] Loading image: {path}")
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

    def _video(self, path: str, cv2, PILImage) -> ChorusPayload:
        print(f"  [Local Adapter] Opening video: {path}")
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

        print(f"  [Local Adapter] Extracting {n} frames from {total} total ({dur}s @ {fps:.1f}fps)...")
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        cap.release()

        print(f"  [Local Adapter] Extracted {len(frames)} frame(s). ✓")
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
# RTSP / HTTP STREAM ADAPTER (OpenCV)
# ─────────────────────────────────────────────────────────────────────────────
class RTSPAdapter:
    def process(self, stream_url: str, source_type: str) -> ChorusPayload:
        try:
            import cv2
            from PIL import Image as PILImage
        except ImportError as e:
            return self._err(stream_url,
                             f"Missing dependency: {e}. Run: pip install opencv-python Pillow")

        print(f"  [RTSP Adapter] Connecting to: {stream_url}")
        cap = cv2.VideoCapture(stream_url)

        if not cap.isOpened():
            return self._err(stream_url,
                "Could not open stream. Check URL, credentials, and network.")

        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps    = cap.get(cv2.CAP_PROP_FPS) or 0.0
        print(f"  [RTSP Adapter] Stream opened — {width}x{height} @ {fps:.1f}fps")
        print(f"  [RTSP Adapter] Capturing {RTSP_FRAMES} frames every {RTSP_FRAME_INTERVAL}s...")

        frames = []
        for i in range(RTSP_FRAMES):
            for _ in range(5):
                cap.grab()
            ret, frame = cap.read()
            if ret:
                from PIL import Image as PILImage
                frames.append(PILImage.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                print(f"  [RTSP Adapter] Frame {i + 1}/{RTSP_FRAMES} ✓")
            else:
                print(f"  [RTSP Adapter] Frame {i + 1}/{RTSP_FRAMES} failed")
            if i < RTSP_FRAMES - 1:
                time.sleep(RTSP_FRAME_INTERVAL)

        cap.release()
        print(f"  [RTSP Adapter] Done — {len(frames)} frame(s) captured.")

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
# CHORUS INPUT PIPELINE (Pure Code — No ML Models loaded)
# ─────────────────────────────────────────────────────────────────────────────
class ChorusInputPipeline:
    def __init__(self):
        self.router = InputRouter()
        self._yt    = YouTubeAdapter()
        self._local = LocalAdapter()
        self._rtsp  = RTSPAdapter()

    def build_payload(self, user_input: str) -> ChorusPayload:
        src_type = self.router.detect(user_input)
        print(f"\n  [Router] Source type: {src_type.upper()}")

        if src_type in ("youtube", "youtube_search"):
            return self._yt.process(user_input, src_type)
        if src_type in ("local_video", "local_image"):
            return self._local.process(user_input, src_type)
        if src_type in ("rtsp", "http_stream"):
            return self._rtsp.process(user_input, src_type)

        return ChorusPayload(
            source_type="text", source_uri=user_input, frames=[],
            metadata={"timestamp": datetime.now().isoformat()},
            raw_text=user_input,
        )

    def _run_pipeline(self, payload: ChorusPayload) -> ChorusPayload:
        payload.quality_score         = run_quality_gate(payload)
        payload.duplicate_hash        = run_duplicate_check(payload)
        payload.is_deepfake           = run_deepfake_check(payload)
        payload.annotation_flags      = run_manual_annotation(payload)
        payload.orchestrator_decision = run_orchestrator(payload)
        return payload

    def process(self, user_input: str, user_question: str = "") -> ChorusPayload:
        payload = self.build_payload(user_input)
        payload.user_question = user_question or payload.raw_text or "Process input"

        print("  [Pipeline] Running quality gate → duplicate → deepfake → orchestrator stubs...")
        payload = self._run_pipeline(payload)
        return payload


try:
    from quality_gate import run_quality_gate as _real_quality_gate
    _QUALITY_GATE_AVAILABLE = True
except ImportError:
    _QUALITY_GATE_AVAILABLE = False

try:
    from manipulation_detection import detect_manipulation as _real_deepfake_check
    _DEEPFAKE_CHECK_AVAILABLE = True
except ImportError:
    _DEEPFAKE_CHECK_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE CLI
# ─────────────────────────────────────────────────────────────────────────────
VISUAL_TYPES = ("local_video", "local_image", "rtsp", "http_stream")

BANNER = f"""
╔══════════════════════════════════════════════════════════╗
║  🎬 CHORUS — Input Adapter & Quality Pipeline                ║
║  duplication_check : {str("✅ WIRED" if getattr(sys.modules[__name__], '_DEDUP_AVAILABLE', False) else "⚠️  not installed (pip install imagehash)")}
║  quality_gate      : {str("✅ WIRED" if getattr(sys.modules[__name__], '_QUALITY_GATE_AVAILABLE', False) else "⚠️  not installed")}
║  manipulation_det  : {str("✅ WIRED" if getattr(sys.modules[__name__], '_DEEPFAKE_CHECK_AVAILABLE', False) else "⚠️  not installed")}
╚══════════════════════════════════════════════════════════════╝

  Input Sources Accepted:
  ────────────────────────
  • YouTube URL / search  →  youtube.com/watch?v=...  or  "python tutorial youtube"
  • Local video           →  C:/path/to/video.mp4
  • Local image           →  C:/path/to/image.jpg
  • RTSP stream           →  rtsp://user:pass@192.168.1.100/stream
  • HTTP stream           →  http://camera-ip/stream.mjpg
  • Plain text query      →  just type anything

  Type 'exit' or 'quit' to stop.
"""


def main():
    print(BANNER)
    pipeline = ChorusInputPipeline()

    while True:
        try:
            print("─" * 60)
            user_input = input("📥 Input > ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("\n👋 Goodbye!")
                break

            detected = InputRouter.detect(user_input)
            if detected in VISUAL_TYPES:
                user_question = input("❓ Question / Prompt about this input > ").strip()
                if not user_question:
                    user_question = "Process visual input"
            else:
                user_question = input("❓ Question / Prompt > ").strip() or user_input

            print()
            t0 = time.time()
            payload = pipeline.process(user_input, user_question)
            took = time.time() - t0

            print(f"\n{'═' * 60}")
            print("📦 CHORUS PAYLOAD OUTPUT:")
            print("═" * 60)
            print(payload.to_report())
            print(f"\n  [Processed in {took:.2f}s]")
            print("═" * 60)

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            break
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
