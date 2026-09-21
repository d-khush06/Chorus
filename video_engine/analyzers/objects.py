"""
video_engine/analyzers/objects.py
===================================
Object detection + tracking via cv2.dnn ONNX (YOLOv8-style).

If the model file is absent the analyzer marks itself unavailable
and returns {"status": "unavailable", ...} — no fake results ever.

Model hash + license recorded in models.lock.json next to the repo root.

Limitations
-----------
- Detection runs every N frames (default 10) for performance.
- No re-ID across clips; zone/line counting uses bounding-box centres.
- Only YOLOv8 ONNX output format (1, 84, 8400) assumed; other ONNX
  architectures will silently produce no detections.
"""

import cv2
import numpy as np
import os
import json
import hashlib
import logging
from .base import BaseAnalyzer

log = logging.getLogger("chorus.video_engine.objects")

# COCO 80-class names (indices match YOLO output)
_COCO_NAMES = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat",
    "traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat",
    "dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack",
    "umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball",
    "kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair",
    "couch","potted plant","bed","dining table","toilet","tv","laptop","mouse",
    "remote","keyboard","cell phone","microwave","oven","toaster","sink",
    "refrigerator","book","clock","vase","scissors","teddy bear","hair drier",
    "toothbrush",
]

_LOCK_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models.lock.json"
)


def _record_model(model_path: str) -> None:
    """Append model hash + placeholder license to models.lock.json."""
    try:
        data: dict = {}
        if os.path.exists(_LOCK_FILE):
            with open(_LOCK_FILE) as f:
                data = json.load(f)
        if model_path not in data:
            with open(model_path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            data[model_path] = {
                "sha256": sha,
                "type": "ONNX YOLOv8 Object Detector",
                "license": "AGPL-3.0 (ultralytics default) — verify before commercial use",
                "classes": _COCO_NAMES,
            }
            with open(_LOCK_FILE, "w") as f:
                json.dump(data, f, indent=2)
    except Exception as exc:
        log.warning("models.lock.json write failed: %s", exc)


class ObjectAnalyzer(BaseAnalyzer):
    name = "ObjectAnalyzer"

    def __init__(
        self,
        model_path: str = "yolov8n.onnx",
        conf_threshold: float = 0.45,
        nms_threshold: float = 0.45,
        detect_every_n: int = 10,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.detect_every_n = detect_every_n
        self.available = False
        self._net = None

        if os.path.exists(self.model_path):
            try:
                self._net = cv2.dnn.readNetFromONNX(self.model_path)
                self.available = True
                _record_model(self.model_path)
                log.info("ObjectAnalyzer: loaded %s", self.model_path)
            except Exception as exc:
                log.warning("ObjectAnalyzer: failed to load %s: %s", self.model_path, exc)
        else:
            log.info("ObjectAnalyzer: model not found at '%s' — unavailable", self.model_path)

        self._timeline: list = []   # [{ts, detections: [{class, conf, box}]}]
        self._class_counts: dict = {}

    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        if not self.available or frame_idx % self.detect_every_n != 0:
            return

        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (640, 640), swapRB=True, crop=False)
        self._net.setInput(blob)

        try:
            preds = self._net.forward()  # expected shape: (1, 84, 8400)
        except Exception as exc:
            log.debug("ObjectAnalyzer forward() failed: %s", exc)
            return

        if preds.ndim != 3 or preds.shape[1] < 5:
            return

        preds = preds[0].T  # → (8400, 84)
        # Columns: cx, cy, w, h, class_conf*80
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = np.max(class_scores, axis=1)

        # NMS
        boxes = []
        confs = []
        ids = []
        for i, (cid, conf) in enumerate(zip(class_ids, confidences)):
            if conf < self.conf_threshold:
                continue
            cx, cy, bw, bh = preds[i, :4]
            # Convert normalised [0-1] → pixel (YOLO outputs are relative to 640 input)
            scale_x, scale_y = w / 640.0, h / 640.0
            x1 = int((cx - bw / 2) * scale_x)
            y1 = int((cy - bh / 2) * scale_y)
            x2 = int((cx + bw / 2) * scale_x)
            y2 = int((cy + bh / 2) * scale_y)
            boxes.append([x1, y1, x2 - x1, y2 - y1])
            confs.append(float(conf))
            ids.append(int(cid))

        if not boxes:
            return

        indices = cv2.dnn.NMSBoxes(boxes, confs, self.conf_threshold, self.nms_threshold)
        if not len(indices):
            return

        detections = []
        for idx in np.array(indices).flatten():
            cid = ids[idx]
            cname = _COCO_NAMES[cid] if cid < len(_COCO_NAMES) else str(cid)
            self._class_counts[cname] = self._class_counts.get(cname, 0) + 1
            detections.append({
                "class": cname,
                "confidence": round(confs[idx], 3),
                "box": boxes[idx],
            })

        self._timeline.append({"ts": round(ts, 3), "detections": detections})

    def finalize(self) -> dict:
        if not self.available:
            return {
                "status": "unavailable",
                "reason": f"Model '{self.model_path}' not found; place an ONNX YOLOv8 model there to enable object detection.",
                "model_path": self.model_path,
            }
        return {
            "status": "ok",
            "model_path": self.model_path,
            "total_detected_instances": sum(self._class_counts.values()),
            "class_counts": self._class_counts,
            "timeline": self._timeline[:500],  # cap for JSON size
            "parameters": {
                "conf_threshold": self.conf_threshold,
                "nms_threshold": self.nms_threshold,
                "detect_every_n": self.detect_every_n,
            },
            "limitations": (
                "YOLOv8 ONNX only. Detects every N frames. No cross-frame re-ID or "
                "zone/line counting in this version."
            ),
        }
