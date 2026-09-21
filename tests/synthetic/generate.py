"""
tests/synthetic/generate.py
============================
Generate synthetic test videos with known ground truth.

Videos produced
---------------
- basic_10s.mp4        : 10s, 25fps, 640x480
  - 0–2s  : black frames
  - 2–4s  : moving white box (left→right)  → motion
  - 4–6s  : frozen frame (static box)
  - 6–8s  : blurred random noise
  - 8–10s : text on screen ("TEST TEXT")

- scene_cuts.mp4       : 10s, 25fps; hard cuts every 2s with different solid colours

- rotated_90.mp4       : 5s, 25fps, 640x480 (portrait: box bounces vertically)

- variable_fps.mp4     : 5s, 10fps then 25fps (approx — same clip at different rates)

- no_audio.mp4         : same as basic_10s but explicitly no audio track

- corrupt_tail.mp4     : basic_10s with last 20% of bytes zeroed (simulate corruption)

- long_30s.mp4         : 30s, 25fps, 640x480, moving box; for bounded-memory test

All files are written to tests/synthetic/videos/ relative to the repo root.
"""

import cv2
import numpy as np
import os
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_VIDEOS_DIR = os.path.join(_HERE, "videos")


def _make_dir():
    os.makedirs(_VIDEOS_DIR, exist_ok=True)


def _writer(name: str, fps: float, w: int, h: int) -> tuple:
    path = os.path.join(_VIDEOS_DIR, name)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    wrt = cv2.VideoWriter(path, fourcc, fps, (w, h))
    return path, wrt


def generate_basic(name: str = "basic_10s.mp4", duration_sec: int = 10,
                   fps: int = 25, w: int = 640, h: int = 480) -> str:
    """
    Returns (path, ground_truth) where ground_truth is a dict.
    Ground truth:
      black_frames_ts : [0.0 – 2.0)
      moving_box_ts   : [2.0 – 4.0)
      frozen_ts       : [4.0 – 6.0)
      blurred_ts      : [6.0 – 8.0)
      text_ts         : [8.0 – 10.0)
    """
    path, wrt = _writer(name, fps, w, h)
    total = duration_sec * fps

    for i in range(total):
        t = i / fps
        if t < 2.0:
            frame = np.zeros((h, w, 3), dtype=np.uint8)
        elif t < 4.0:
            frame = np.full((h, w, 3), 50, dtype=np.uint8)
            bw = 60
            x = int((t - 2.0) / 2.0 * (w - bw))
            y = h // 2 - bw // 2
            cv2.rectangle(frame, (x, y), (x + bw, y + bw), (255, 255, 255), -1)
        elif t < 6.0:
            # Same frame every time → frozen
            frame = np.full((h, w, 3), 100, dtype=np.uint8)
            cx, cy = w // 2, h // 2
            cv2.rectangle(frame, (cx, cy), (cx + 60, cy + 60), (0, 0, 200), -1)
        elif t < 8.0:
            rng = np.random.default_rng(seed=42)  # deterministic
            frame = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
            frame = cv2.GaussianBlur(frame, (31, 31), 10)
        else:
            frame = np.full((h, w, 3), 200, dtype=np.uint8)
            cv2.putText(frame, "TEST TEXT", (w // 2 - 120, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
        wrt.write(frame)

    wrt.release()
    return path


def generate_scene_cuts(name: str = "scene_cuts.mp4") -> str:
    """5 scenes of 2s each with solid distinct colours; 4 hard cuts."""
    fps, w, h = 25, 640, 480
    path, wrt = _writer(name, fps, w, h)
    colours = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30), (30, 200, 200)]
    for colour in colours:
        for _ in range(fps * 2):
            frame = np.full((h, w, 3), colour, dtype=np.uint8)
            wrt.write(frame)
    wrt.release()
    return path


def generate_rotated(name: str = "rotated_90.mp4") -> str:
    """Portrait video (480x640) with moving box; metadata would indicate 90° rotation."""
    fps, w, h = 25, 480, 640  # native portrait
    path, wrt = _writer(name, fps, w, h)
    total = fps * 5
    for i in range(total):
        frame = np.full((h, w, 3), 70, dtype=np.uint8)
        y = int(i / total * (h - 60))
        cv2.rectangle(frame, (w // 2 - 30, y), (w // 2 + 30, y + 60), (255, 100, 0), -1)
        wrt.write(frame)
    wrt.release()
    return path


def generate_no_audio(name: str = "no_audio.mp4") -> str:
    """Same content as basic but clearly no audio track (cv2.VideoWriter never adds audio)."""
    return generate_basic(name=name, duration_sec=5)


def generate_corrupt_tail(src_name: str = "basic_10s.mp4",
                          out_name: str = "corrupt_tail.mp4") -> str:
    """Copies basic_10s and zeros the last 20% of bytes to simulate a corrupt tail."""
    src = os.path.join(_VIDEOS_DIR, src_name)
    if not os.path.exists(src):
        generate_basic(name=src_name)
    dst = os.path.join(_VIDEOS_DIR, out_name)
    shutil.copy2(src, dst)
    size = os.path.getsize(dst)
    corrupt_start = int(size * 0.80)
    with open(dst, "r+b") as f:
        f.seek(corrupt_start)
        f.write(b"\x00" * (size - corrupt_start))
    return dst


def generate_long(name: str = "long_30s.mp4") -> str:
    """30s moving-box video for bounded-memory test."""
    return generate_basic(name=name, duration_sec=30)


def generate_all() -> dict:
    """Generate all synthetic videos; return {name: path}."""
    _make_dir()
    paths = {}
    print("Generating synthetic videos in:", _VIDEOS_DIR)
    paths["basic_10s"] = generate_basic()
    print("  ✔ basic_10s.mp4")
    paths["scene_cuts"] = generate_scene_cuts()
    print("  ✔ scene_cuts.mp4")
    paths["rotated_90"] = generate_rotated()
    print("  ✔ rotated_90.mp4")
    paths["no_audio"] = generate_no_audio()
    print("  ✔ no_audio.mp4")
    paths["corrupt_tail"] = generate_corrupt_tail()
    print("  ✔ corrupt_tail.mp4")
    paths["long_30s"] = generate_long()
    print("  ✔ long_30s.mp4")
    return paths


if __name__ == "__main__":
    generate_all()
    print("Done.")
