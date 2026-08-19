"""Conservative AI-video screening for CCTV, phone, and downloaded web video.

This is a triage tool, not proof of origin.  Re-encoding (including YouTube)
can add camera-like compression, so no codec/noise signal is ever treated as
proof that a clip is real.
"""
from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np


MIN_FRAMES = 4
LIKELY_AI_THRESHOLD = 0.75
REVIEW_THRESHOLD = 0.45


def _sample_frames(video_path: str, num_frames: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video source")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        total = num_frames
    indexes = np.linspace(0, max(0, total - 1), num_frames, dtype=int)
    frames: list[np.ndarray] = []
    for index in indexes:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = cap.read()
        if ok:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cap.release()
    return frames


def analyze_ai_generation(video_path: str, num_frames: int = 12) -> dict[str, Any]:
    """Return a conservative, explainable AI-generation screening report.

    CCTV is deliberately not penalised for blur, low light, low frame rate, or
    compression.  Those conditions make the outcome ``INCONCLUSIVE`` unless
    several independent visual signals point in the same direction.
    """
    started = time.time()
    report: dict[str, Any] = {
        "verdict": "INCONCLUSIVE",
        "ai_confidence": 0.0,
        "review_required": True,
        "is_ai_generated": False,
        "signals": {},
        "limitations": [
            "This is a screening result, not proof of provenance.",
            "YouTube and other platforms re-encode video; codec artifacts cannot prove a video is real.",
            "CCTV blur, low light, compression, and low frame rate are expected and are not AI evidence.",
        ],
        "processing_time_seconds": 0.0,
    }
    try:
        frames = _sample_frames(video_path, num_frames)
        if len(frames) < MIN_FRAMES:
            report["limitations"].append("Too few decodable frames for a reliable assessment.")
            return report

        # Use neighbouring sampled frames only as weak contextual indicators.
        # Large scene motion is separated from pixel-level residual movement.
        residuals, sharpness = [], []
        for previous, current in zip(frames, frames[1:]):
            flow = cv2.calcOpticalFlowFarneback(previous, current, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            warped = cv2.remap(previous, flow[..., 0] + np.arange(previous.shape[1], dtype=np.float32),
                               flow[..., 1] + np.arange(previous.shape[0], dtype=np.float32)[:, None],
                               cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            residuals.append(float(np.mean(cv2.absdiff(current, warped))))
        sharpness = [float(cv2.Laplacian(frame, cv2.CV_64F).var()) for frame in frames]
        residual = float(np.mean(residuals))
        laplacian = float(np.mean(sharpness))
        report["signals"] = {
            "motion_compensated_residual": round(residual, 3),
            "detail_measure": round(laplacian, 3),
            "frames_analysed": len(frames),
        }

        # Very smooth frames plus unusually low motion residual is only a weak
        # indicator.  It must not turn a CCTV recording into a 'real' verdict.
        smoothness_signal = 0.0
        if laplacian < 18:
            smoothness_signal += 0.5
        if residual < 1.0:
            smoothness_signal += 0.5
        report["ai_confidence"] = round(smoothness_signal, 3)

        if smoothness_signal >= LIKELY_AI_THRESHOLD:
            report.update(verdict="LIKELY_AI_GENERATED", is_ai_generated=True, review_required=True)
        elif smoothness_signal >= REVIEW_THRESHOLD:
            report.update(verdict="INCONCLUSIVE", review_required=True)
        else:
            report.update(verdict="NO_STRONG_EVIDENCE_OF_AI", review_required=False)
        return report
    except Exception as exc:
        report["limitations"].append(f"Analysis error: {exc}")
        return report
    finally:
        report["processing_time_seconds"] = round(time.time() - started, 3)


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Conservative AI-video screening")
    parser.add_argument("video_path")
    parser.add_argument("--frames", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps(analyze_ai_generation(args.video_path, args.frames), indent=2))
