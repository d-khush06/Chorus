"""
video_engine/schema.py
======================
VideoProfile — versioned schema for all engine output.

Stored with every run/case under:
  backend/data/runs/<runId>/engine_profile.json
"""

from __future__ import annotations

import json
import os
import datetime
from typing import Dict, Any, Optional

SCHEMA_VERSION = "1.1.0"


class VideoProfile:
    """
    Versioned container for VideoEngine results.

    Usage
    -----
    profile = VideoProfile(run_id="abc123")
    profile.populate(engine.run())
    profile.save("path/to/engine_profile.json")
    """

    def __init__(self, run_id: str, created_at: Optional[str] = None):
        self.run_id = run_id
        self.data: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "created_at": created_at or datetime.datetime.utcnow().isoformat() + "Z",
            "metadata": {},
            "performance": {},
            "technical": {},
            "shots": {},
            "motion": {},
            "objects": {},
            "faces": {},
            "text_and_codes": {},
            "similarity": {},
            "export": {},
        }

    def populate(self, engine_results: Dict[str, Any]) -> None:
        """Merge engine run() output into this profile."""
        self.data["metadata"] = engine_results.get("metadata", {})
        self.data["performance"] = engine_results.get("performance", {})

        analyzers = engine_results.get("analyzers", {})
        self.data["technical"] = analyzers.get("TechnicalAnalyzer", {})
        self.data["shots"] = analyzers.get("ShotsAnalyzer", {})
        self.data["motion"] = analyzers.get("MotionAnalyzer", {})
        self.data["objects"] = analyzers.get("ObjectAnalyzer", {})
        self.data["faces"] = analyzers.get("FaceAnalyzer", {})
        self.data["text_and_codes"] = analyzers.get("TextAndCodeAnalyzer", {})
        self.data["similarity"] = analyzers.get("SimilarityAnalyzer", {})
        self.data["export"] = analyzers.get("ExportAnalyzer", {})

    # ── serialization ─────────────────────────────────────────────────────────

    def save(self, filepath: str) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._serializable(), f, indent=2)

    def to_dict(self) -> Dict[str, Any]:
        return self._serializable()

    def _serializable(self) -> Dict[str, Any]:
        """Return a JSON-safe copy (drop numpy arrays / cv2 mats)."""
        import copy, numpy as np
        def _clean(obj):
            if isinstance(obj, dict):
                return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_clean(i) for i in obj]
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.integer, np.floating)):
                return obj.item()
            if isinstance(obj, bytes):
                return obj.hex()
            return obj
        return _clean(copy.deepcopy(self.data))

    @classmethod
    def load(cls, filepath: str) -> "VideoProfile":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        p = cls(data.get("run_id", "unknown"), data.get("created_at"))
        p.data = data
        return p

    # ── quick accessors for downstream (fusion, domain_output) ───────────────

    def motion_peaks(self, threshold: float = 0.15) -> list:
        """Return timestamps where activity_level > threshold."""
        timeline = self.data.get("motion", {}).get("activity_timeline", [])
        return [round(ts, 3) for ts, lvl in timeline if lvl > threshold]

    def on_screen_text_sample(self, max_chars: int = 400) -> str:
        texts = self.data.get("text_and_codes", {}).get("detected_texts", [])
        codes = self.data.get("text_and_codes", {}).get("detected_codes", [])
        parts = [t["text"] for t in texts[:5]] + [c["data"] for c in codes[:5]]
        combined = " | ".join(p for p in parts if p)
        return combined[:max_chars]

    def quality_warnings(self) -> list:
        warnings = []
        tech = self.data.get("technical", {})
        if tech.get("avg_blur", 999) < 50:
            warnings.append("video is blurry (avg Laplacian variance < 50)")
        if tech.get("black_frame_count", 0) > 0:
            warnings.append(f"{tech['black_frame_count']} black frames detected")
        if tech.get("frozen_frame_count", 0) > 5:
            warnings.append(f"{tech['frozen_frame_count']} frozen frames detected")
        if tech.get("avg_exposure", 128) < 20:
            warnings.append("video is very dark (avg brightness < 20)")
        if tech.get("avg_exposure", 128) > 235:
            warnings.append("video is overexposed (avg brightness > 235)")
        return warnings

    def face_count_timeline(self) -> list:
        return self.data.get("faces", {}).get("timeline", [])

    def shot_count(self) -> int:
        return len(self.data.get("shots", {}).get("cuts", []))

    def summary_for_llm(self) -> str:
        """Compact text summary injected into VL/text prompts."""
        meta = self.data.get("metadata", {})
        tech = self.data.get("technical", {})
        lines = [
            f"[Engine Profile v{self.data.get('schema_version', SCHEMA_VERSION)}]",
            f"Resolution: {meta.get('width', '?')}x{meta.get('height', '?')} @ {meta.get('fps', '?')} fps",
            f"Duration: {meta.get('duration_seconds', '?')} s  |  Codec: {meta.get('codec', '?')}",
            f"Avg blur (Laplacian var): {round(tech.get('avg_blur', 0), 1)}",
            f"Avg exposure: {round(tech.get('avg_exposure', 0), 1)}  "
            f"Avg contrast: {round(tech.get('avg_contrast', 0), 1)}",
            f"Black frames: {tech.get('black_frame_count', 0)}  "
            f"Frozen frames: {tech.get('frozen_frame_count', 0)}",
            f"Shots detected: {self.shot_count()}",
        ]

        motion = self.data.get("motion", {})
        avg_act = motion.get("avg_activity", 0)
        peaks = self.motion_peaks()
        lines.append(f"Avg activity: {round(avg_act * 100, 1)}%  |  Motion peaks at: {peaks[:8]}")

        text_sample = self.on_screen_text_sample()
        if text_sample:
            lines.append(f"On-screen text/codes: {text_sample}")

        warnings = self.quality_warnings()
        if warnings:
            lines.append(f"Quality warnings: {'; '.join(warnings)}")

        faces = self.data.get("faces", {})
        if faces.get("status") == "ok":
            lines.append(f"Faces detected (total instances): {faces.get('total_detected_instances', 0)}")
        elif faces.get("status") == "unavailable":
            lines.append(f"Face detection: unavailable ({faces.get('reason', '')})")

        objects = self.data.get("objects", {})
        if objects.get("status") == "ok":
            lines.append(f"Objects detected (total instances): {objects.get('total_detected_instances', 0)}")
        elif objects.get("status") == "unavailable":
            lines.append(f"Object detection: unavailable ({objects.get('reason', '')})")

        return "\n".join(lines)
