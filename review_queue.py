"""
review_queue.py
===============
Chorus Pipeline — Review Queue (pure code, no model)

Pipeline position
-----------------
  Runs AFTER : Manipulation Detection, Fusion, cyber agents (alerts / face re-id)
  Runs BEFORE: Domain Output (final report) — the queue result is attached to
               the fused timeline and surfaced in the incident report.

Purpose
-------
Collects low-confidence or high-severity findings and flags them for a human
analyst. This is the "human-in-the-loop" safety net: anything the automated
pipeline is not certain about, or anything that carries legal / privacy weight,
lands here instead of being presented as a confirmed fact.

Rules
-----
1. Never block the pipeline — every function returns a dict and never raises.
2. Append-only JSONL storage (one file per UTC day) so the audit trail is
   immutable and easy to tail.
3. PII-safe: review items store a caller-supplied payload, but the queue never
   reads it back into prompts automatically. Human eyes only.
4. Deterministic: same input produces the same review item id.

Usage (library)
---------------
  from review_queue import flag_for_review, build_review_item, write_review_item

  item = build_review_item(
      source_uri="clip.mp4",
      step="manipulation_detection",
      reason="Deepfake detector flagged the footage",
      severity="HIGH",
      confidence=0.42,
      mode="cyber",
  )
  write_review_item(item)

Usage (CLI)
-----------
  python review_queue.py --list --pretty
  python review_queue.py --list --date 2026-09-16 --pretty
  python review_queue.py --add '{"source_uri":"clip.mp4","step":"x","reason":"y"}'
  python review_queue.py --stats --pretty
"""

import os
import sys
import json
import hashlib
import argparse
import datetime
from typing import Optional

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_QUEUE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audit_logs", "review_queue"
)

VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

# A finding at or below this confidence is auto-flagged regardless of severity.
LOW_CONFIDENCE_THRESHOLD = 0.60


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _today_utc() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _queue_path(day: Optional[str] = None) -> str:
    return os.path.join(REVIEW_QUEUE_DIR, f"{day or _today_utc()}.jsonl")


def _make_item_id(source_uri: str, step: str, reason: str) -> str:
    """Deterministic 12-char id from (source, step, reason)."""
    digest = hashlib.sha256(
        f"{source_uri}|{step}|{reason}".encode("utf-8")
    ).hexdigest()
    return digest[:12]


# ─────────────────────────────────────────────────────────────────────────────
# ITEM CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def build_review_item(
    source_uri: str,
    step: str,
    reason: str,
    severity: str = "MEDIUM",
    confidence: Optional[float] = None,
    mode: str = "general",
    payload: Optional[dict] = None,
    recommended_action: str = "Human analyst review required.",
) -> dict:
    """
    Build a standard review-queue item. Never raises.

    Returns a dict with a stable item_id; duplicate builds collapse when
    persisted (write_review_item deduplicates by item_id per day).
    """
    severity = (severity or "MEDIUM").upper()
    if severity not in VALID_SEVERITIES:
        severity = "MEDIUM"

    item = {
        "item_id":            _make_item_id(source_uri or "", step or "", reason or ""),
        "created_at":         datetime.datetime.utcnow().isoformat() + "Z",
        "source_uri":         source_uri or "",
        "mode":               mode or "general",
        "step":               step or "unknown",
        "reason":             reason or "Unspecified finding",
        "severity":           severity,
        "confidence":         confidence,
        "status":             "OPEN",
        "recommended_action": recommended_action,
        "payload":            payload or {},
    }
    return item


def should_flag(
    confidence: Optional[float],
    severity: str,
    detector_error: bool = False,
) -> bool:
    """
    Decide whether a finding should enter the review queue.

    Flag when:
      - the detector errored (an error is a review request, not a finding), OR
      - severity is HIGH / CRITICAL, OR
      - confidence is known and below LOW_CONFIDENCE_THRESHOLD.
    """
    if detector_error:
        return True
    if (severity or "").upper() in ("HIGH", "CRITICAL"):
        return True
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    return False


def flag_for_review(
    source_uri: str,
    step: str,
    reason: str,
    severity: str = "MEDIUM",
    confidence: Optional[float] = None,
    mode: str = "general",
    payload: Optional[dict] = None,
    detector_error: bool = False,
    recommended_action: str = "Human analyst review required.",
) -> dict:
    """
    Build AND persist a review item in one call. Never raises.

    Always returns {"flagged": bool, "item": dict|None, "path": str|None,
    "error": str|None}. `flagged` is False when should_flag() says the finding
    does not need human review.
    """
    try:
        if not should_flag(confidence, severity, detector_error=detector_error):
            return {"flagged": False, "item": None, "path": None, "error": None}

        item = build_review_item(
            source_uri=source_uri,
            step=step,
            reason=reason,
            severity=severity,
            confidence=confidence,
            mode=mode,
            payload=payload,
            recommended_action=recommended_action,
        )
        path = write_review_item(item)
        return {"flagged": True, "item": item, "path": path, "error": None}
    except Exception as exc:
        return {"flagged": False, "item": None, "path": None, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────

def write_review_item(item: dict, day: Optional[str] = None) -> Optional[str]:
    """
    Append a review item to today's JSONL queue. Skips exact duplicates
    (same item_id already present that day). Returns the path written, or
    the existing path if skipped. Never raises.
    """
    try:
        os.makedirs(REVIEW_QUEUE_DIR, exist_ok=True)
        path = _queue_path(day)

        # Deduplicate within the same day file
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        existing = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if existing.get("item_id") == item.get("item_id"):
                        return path

        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        return path
    except Exception as exc:
        print(f"  [Review Queue] ⚠️  Could not persist item: {exc}", flush=True)
        return None


def list_review_items(day: Optional[str] = None) -> list:
    """Return all review items for a given UTC day (default: today). Never raises."""
    path = _queue_path(day)
    items = []
    if not os.path.exists(path):
        return items
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        print(f"  [Review Queue] ⚠️  Could not read queue: {exc}", flush=True)
    return items


def queue_stats(day: Optional[str] = None) -> dict:
    """Summarise the queue by status and severity. Never raises."""
    items = list_review_items(day)
    by_severity: dict = {}
    by_status: dict = {}
    for it in items:
        by_severity[it.get("severity", "MEDIUM")] = (
            by_severity.get(it.get("severity", "MEDIUM"), 0) + 1
        )
        by_status[it.get("status", "OPEN")] = (
            by_status.get(it.get("status", "OPEN"), 0) + 1
        )
    return {
        "date":        day or _today_utc(),
        "total":       len(items),
        "by_severity": by_severity,
        "by_status":   by_status,
        "error":       None,
    }


def collect_review_flags(
    manipulation_result: Optional[dict] = None,
    alert_result: Optional[dict] = None,
    face_reid_result: Optional[dict] = None,
    geo_result: Optional[dict] = None,
    acoustic_result: Optional[dict] = None,
    source_uri: str = "",
    mode: str = "cyber",
) -> dict:
    """
    Inspect every agent result and gather all findings that need human review.
    Returns {"items": [...], "count": N, "error": None}. Never raises.
    """
    candidates: list = []

    try:
        if manipulation_result:
            verdict = manipulation_result.get("verdict")
            if verdict == "FLAGGED":
                candidates.append({
                    "step": "manipulation_detection",
                    "reason": "Manipulation/deepfake detector flagged the footage.",
                    "severity": "HIGH",
                    "confidence": None,
                    "payload": manipulation_result,
                })
            if manipulation_result.get("detector_error"):
                candidates.append({
                    "step": "manipulation_detection",
                    "reason": "Manipulation detector errored — verdict is unreliable.",
                    "severity": "HIGH",
                    "confidence": None,
                    "payload": manipulation_result,
                    "detector_error": True,
                })

        if acoustic_result and not acoustic_result.get("error"):
            for ev in acoustic_result.get("events", []):
                if ev.get("severity") in ("HIGH", "CRITICAL"):
                    candidates.append({
                        "step": "acoustic_event_detection",
                        "reason": f"High-severity acoustic event detected: {ev.get('label')}.",
                        "severity": ev.get("severity", "HIGH"),
                        "confidence": ev.get("confidence"),
                        "payload": ev,
                    })

        if face_reid_result:
            if face_reid_result.get("status") == "blocked":
                candidates.append({
                    "step": "face_reid_agent",
                    "reason": "Face re-identification requested without governance approval.",
                    "severity": "CRITICAL",
                    "confidence": None,
                    "payload": {"status": "blocked"},
                })
            elif face_reid_result.get("identities"):
                candidates.append({
                    "step": "face_reid_agent",
                    "reason": (
                        f"{len(face_reid_result['identities'])} face identit(ies) "
                        "established — biometric data, confirm lawful basis."
                    ),
                    "severity": "HIGH",
                    "confidence": None,
                    "payload": {"identity_count": len(face_reid_result["identities"])},
                })

        if geo_result and geo_result.get("confidence") is not None:
            if geo_result.get("confidence", 1.0) < 0.5 and geo_result.get("top_predictions"):
                candidates.append({
                    "step": "geo_estimation_agent",
                    "reason": "Geo-location estimate is low confidence.",
                    "severity": "MEDIUM",
                    "confidence": geo_result.get("confidence"),
                    "payload": {"gps": geo_result.get("gps")},
                })

        if alert_result and alert_result.get("alerts"):
            high = [a for a in alert_result["alerts"]
                    if a.get("severity") in ("HIGH", "CRITICAL")]
            if high:
                candidates.append({
                    "step": "alert_system",
                    "reason": f"{len(high)} high-severity alert(s) fired.",
                    "severity": "HIGH",
                    "confidence": None,
                    "payload": {"alert_ids": [a.get("alert_id") for a in high]},
                })

        items = []
        for c in candidates:
            built = build_review_item(
                source_uri=source_uri,
                step=c["step"],
                reason=c["reason"],
                severity=c["severity"],
                confidence=c.get("confidence"),
                mode=mode,
                payload=c.get("payload"),
            )
            if write_review_item(built):
                items.append(built)

        if items:
            print(f"  [Review Queue] ⚠️  {len(items)} finding(s) flagged for human review.", flush=True)
        else:
            print("  [Review Queue] ✅ No findings require human review.", flush=True)

        return {"items": items, "count": len(items), "path": _queue_path(), "error": None}

    except Exception as exc:
        return {"items": [], "count": 0, "path": None, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Review Queue — human-in-the-loop findings store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python review_queue.py --list --pretty\n"
            "  python review_queue.py --list --date 2026-09-16 --pretty\n"
            "  python review_queue.py --stats --pretty\n"
            "  python review_queue.py --add '{\"source_uri\":\"clip.mp4\","
            "\"step\":\"manipulation_detection\",\"reason\":\"flagged\"}'\n"
        ),
    )
    p.add_argument("--list",  action="store_true", dest="do_list",
                   help="List review items for a day.")
    p.add_argument("--stats", action="store_true", dest="do_stats",
                   help="Show queue statistics.")
    p.add_argument("--add",   metavar="JSON", default=None,
                   help="Add a review item from a JSON string.")
    p.add_argument("--date",  default=None, help="UTC date YYYY-MM-DD (default: today).")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.add:
        try:
            data = json.loads(args.add)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON: {exc}", file=sys.stderr)
            sys.exit(2)
        result = flag_for_review(
            source_uri=data.get("source_uri", ""),
            step=data.get("step", "manual"),
            reason=data.get("reason", "Manually queued"),
            severity=data.get("severity", "MEDIUM"),
            confidence=data.get("confidence"),
            mode=data.get("mode", "general"),
            payload=data.get("payload"),
        )
    elif args.do_stats:
        result = queue_stats(args.date)
    else:
        result = list_review_items(args.date)

    print(json.dumps(result, indent=2 if args.pretty else None,
                     ensure_ascii=False, default=str))
    sys.exit(0)