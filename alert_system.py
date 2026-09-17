"""
alert_system.py
===============
Chorus Pipeline — Cyber Step C4: Alert System

Pipeline position
-----------------
  Runs AFTER : Acoustic Event Detection, Geo Estimation, Face Re-ID,
               Manipulation Detection, Fusion Agent
  Runs BEFORE: Domain Output (incident report includes alert history)
  Cyber mode only.

Purpose
-------
Evaluates pipeline outputs against a configurable threshold rule set and
fires notifications when severity / confidence thresholds are crossed.
Supported notification channels:
  1. Console  — always on (prints to stdout)
  2. Webhook  — HTTP POST to a configurable URL (Slack, Discord, custom)
  3. File     — appends to a JSONL audit log under audit_logs/alerts/

Rules
-----
1. Never block the pipeline — every function returns a dict and never raises.
2. Every alert carries: alert_id, severity, source_step, description,
   triggered_at, and the raw event that triggered it.
3. Thresholds are overridable via environment variables.
4. Deduplication: identical (source_step, event_type, window_s) alerts are
   suppressed within a configurable cooldown window.
5. The alert history is attached to the fused timeline so the Domain Output
   agent can include it in the incident report.

Usage (library)
---------------
  from alert_system import evaluate_and_alert

  result = evaluate_and_alert(
      acoustic_result=acoustic_result,
      geo_result=geo_result,
      face_reid_result=face_reid_result,
      manipulation_result=manipulation_result,
      source_uri="incident.mp4",
  )
  # result = {
  #   "alerts": [...],
  #   "total_alerts": 3,
  #   "highest_severity": "CRITICAL",
  #   "notifications_sent": 2,
  #   "error": null
  # }

Usage (CLI)
-----------
  python alert_system.py --input pipeline_result.json --pretty
"""

import os
import sys
import json
import hashlib
import datetime
import argparse
from typing import Optional

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Webhook URL for remote notifications. Set via ALERT_WEBHOOK_URL env var.
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

# Cooldown: suppress duplicate alerts within this window (seconds).
ALERT_COOLDOWN_S = int(os.getenv("ALERT_COOLDOWN_S", "60"))

# Audit log directory
ALERT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audit_logs", "alerts"
)

# Severity levels (ordered)
SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLD RULES
# ─────────────────────────────────────────────────────────────────────────────
# Each rule: (source_step, event_type_or_key, min_severity, min_confidence, description_template)
# If an incoming event matches (source_step, event_type) and its severity/confidence
# meet the thresholds, an alert is triggered.

ALERT_RULES = [
    # ── Acoustic events ──────────────────────────────────────────────────
    {
        "source_step": "acoustic_event_detection",
        "event_type": "gunshot",
        "min_severity": "CRITICAL",
        "min_confidence": 0.30,
        "description": "Gunshot detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "CRITICAL",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "explosion",
        "min_severity": "CRITICAL",
        "min_confidence": 0.30,
        "description": "Explosion detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "CRITICAL",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "scream",
        "min_severity": "HIGH",
        "min_confidence": 0.30,
        "description": "Scream/shout detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "HIGH",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "alarm",
        "min_severity": "HIGH",
        "min_confidence": 0.30,
        "description": "Alarm detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "HIGH",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "siren",
        "min_severity": "HIGH",
        "min_confidence": 0.30,
        "description": "Siren detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "HIGH",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "glass_break",
        "min_severity": "HIGH",
        "min_confidence": 0.30,
        "description": "Glass breaking detected in audio at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "MEDIUM",
    },
    {
        "source_step": "acoustic_event_detection",
        "event_type": "fire",
        "min_severity": "HIGH",
        "min_confidence": 0.30,
        "description": "Fire-related sound detected at {start_s:.1f}s–{end_s:.1f}s (confidence: {confidence:.2f})",
        "alert_severity": "HIGH",
    },
    # ── Manipulation / deepfake ───────────────────────────────────────────
    {
        "source_step": "manipulation_detection",
        "event_type": "deepfake",
        "min_severity": "HIGH",
        "min_confidence": 0.0,
        "description": "Deepfake/manipulation flagged by detector (verdict: {verdict})",
        "alert_severity": "HIGH",
    },
    # ── Face Re-ID ───────────────────────────────────────────────────────
    {
        "source_step": "face_reid",
        "event_type": "identity_detected",
        "min_severity": "MEDIUM",
        "min_confidence": 0.0,
        "description": "Face re-identification detected {identity_count} unique identity/identities across {faces_detected} face(s)",
        "alert_severity": "MEDIUM",
    },
    # ── Geo estimation ───────────────────────────────────────────────────
    {
        "source_step": "geo_estimation",
        "event_type": "location_estimated",
        "min_severity": "LOW",
        "min_confidence": 0.50,
        "description": "Location estimated: ({lat}, {lon}) with confidence {confidence:.2f}",
        "alert_severity": "LOW",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# DEDUP / COOLDOWN
# ─────────────────────────────────────────────────────────────────────────────

_cooldown_cache: dict = {}  # key -> last_fire_utc


def _make_dedup_key(source_step: str, event_type: str) -> str:
    return f"{source_step}|{event_type}"


def _is_cooled_down(key: str) -> bool:
    """Return True if this alert was already fired within the cooldown window."""
    last = _cooldown_cache.get(key)
    if last is None:
        return False
    elapsed = (datetime.datetime.utcnow() - last).total_seconds()
    return elapsed < ALERT_COOLDOWN_S


def _record_fire(key: str) -> None:
    _cooldown_cache[key] = datetime.datetime.utcnow()


# ─────────────────────────────────────────────────────────────────────────────
# ALERT CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def _make_alert_id(source_uri: str, source_step: str, event_type: str, ts: str) -> str:
    digest = hashlib.sha256(
        f"{source_uri}|{source_step}|{event_type}|{ts}".encode("utf-8")
    ).hexdigest()
    return digest[:12]


def _build_alert(
    source_uri: str,
    source_step: str,
    event_type: str,
    severity: str,
    description: str,
    raw_event: dict,
) -> dict:
    now = datetime.datetime.utcnow().isoformat() + "Z"
    return {
        "alert_id":      _make_alert_id(source_uri, source_step, event_type, now),
        "severity":      severity,
        "source_step":   source_step,
        "event_type":    event_type,
        "description":   description,
        "triggered_at":  now,
        "source_uri":    source_uri,
        "raw_event":     raw_event,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION CHANNELS
# ─────────────────────────────────────────────────────────────────────────────

def _send_console(alert: dict) -> bool:
    """Print alert to console. Always succeeds."""
    icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
        alert["severity"], "⚪"
    )
    print(
        f"  [Alert] {icon} {alert['severity']} — {alert['description']}",
        flush=True,
    )
    return True


def _send_webhook(alert: dict) -> bool:
    """POST alert JSON to the configured webhook URL. Returns True on success."""
    url = ALERT_WEBHOOK_URL
    if not url:
        return False
    try:
        import urllib.request
        payload = json.dumps(alert, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except Exception as exc:
        print(f"  [Alert] ⚠️  Webhook failed: {exc}", flush=True)
        return False


def _append_log_file(alert: dict) -> bool:
    """Append alert to the daily JSONL audit log. Returns True on success."""
    try:
        os.makedirs(ALERT_LOG_DIR, exist_ok=True)
        day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        path = os.path.join(ALERT_LOG_DIR, f"{day}.jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(alert, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as exc:
        print(f"  [Alert] ⚠️  Log write failed: {exc}", flush=True)
        return False


def _send_notifications(alert: dict) -> int:
    """Send alert through all configured channels. Returns count of successes."""
    count = 0
    if _send_console(alert):
        count += 1
    if _send_webhook(alert):
        count += 1
    if _append_log_file(alert):
        count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# EVENT EXTRACTION — pull triggerable events from each agent result
# ─────────────────────────────────────────────────────────────────────────────

def _extract_acoustic_events(acoustic_result: Optional[dict]) -> list:
    """Convert acoustic_event_detection output to triggerable event dicts."""
    if not acoustic_result or acoustic_result.get("error"):
        return []
    events = []
    for ev in acoustic_result.get("events", []):
        events.append({
            "source_step": "acoustic_event_detection",
            "event_type": ev["event_type"],
            "severity": ev["severity"],
            "confidence": ev["confidence"],
            "start_s": ev["start_s"],
            "end_s": ev["end_s"],
            "label": ev.get("label", ""),
        })
    return events


def _extract_manipulation_events(manipulation_result: Optional[dict]) -> list:
    if not manipulation_result:
        return []
    verdict = manipulation_result.get("verdict", "CLEAN")
    if verdict == "FLAGGED":
        return [{
            "source_step": "manipulation_detection",
            "event_type": "deepfake",
            "severity": "HIGH",
            "confidence": 1.0,
            "verdict": verdict,
        }]
    return []


def _extract_face_reid_events(face_reid_result: Optional[dict]) -> list:
    if not face_reid_result or face_reid_result.get("error"):
        return []
    identities = face_reid_result.get("identities", [])
    if not identities:
        return []
    return [{
        "source_step": "face_reid",
        "event_type": "identity_detected",
        "severity": "MEDIUM",
        "confidence": 1.0,
        "identity_count": len(identities),
        "faces_detected": face_reid_result.get("faces_detected", 0),
    }]


def _extract_geo_events(geo_result: Optional[dict]) -> list:
    if not geo_result or not geo_result.get("gps"):
        return []
    gps = geo_result["gps"]
    return [{
        "source_step": "geo_estimation",
        "event_type": "location_estimated",
        "severity": "LOW",
        "confidence": gps.get("confidence", 0.0),
        "lat": gps.get("lat"),
        "lon": gps.get("lon"),
    }]


# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_and_alert(
    acoustic_result: Optional[dict] = None,
    geo_result: Optional[dict] = None,
    face_reid_result: Optional[dict] = None,
    manipulation_result: Optional[dict] = None,
    source_uri: str = "",
) -> dict:
    """
    Evaluate all cyber-mode agent outputs against threshold rules and
    fire alerts for any triggered rules.

    Returns
    -------
    dict with keys: alerts, total_alerts, highest_severity,
                    notifications_sent, error
    """
    started_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Collect all triggerable events from every agent
    raw_events = []
    raw_events.extend(_extract_acoustic_events(acoustic_result))
    raw_events.extend(_extract_manipulation_events(manipulation_result))
    raw_events.extend(_extract_face_reid_events(face_reid_result))
    raw_events.extend(_extract_geo_events(geo_result))

    # Match events against rules
    alerts = []
    total_notifications = 0
    highest = "LOW"

    for evt in raw_events:
        for rule in ALERT_RULES:
            if rule["source_step"] != evt["source_step"]:
                continue
            if rule["event_type"] != evt["event_type"]:
                continue
            if SEVERITY_ORDER.get(evt["severity"], 0) < SEVERITY_ORDER.get(rule["min_severity"], 0):
                continue
            if evt.get("confidence", 0.0) < rule["min_confidence"]:
                continue

            # Rule matched — build description
            try:
                desc = rule["description"].format(**evt)
            except (KeyError, ValueError):
                desc = f"{rule['event_type']} event from {rule['source_step']}"

            dedup_key = _make_dedup_key(evt["source_step"], evt["event_type"])
            if _is_cooled_down(dedup_key):
                continue

            alert = _build_alert(
                source_uri=source_uri,
                source_step=evt["source_step"],
                event_type=evt["event_type"],
                severity=rule["alert_severity"],
                description=desc,
                raw_event=evt,
            )
            alerts.append(alert)
            _record_fire(dedup_key)

            if SEVERITY_ORDER.get(rule["alert_severity"], 0) > SEVERITY_ORDER.get(highest, 0):
                highest = rule["alert_severity"]

            total_notifications += _send_notifications(alert)

    print(
        f"  [Alert] ✅ Evaluated {len(raw_events)} event(s) → "
        f"{len(alerts)} alert(s) fired, "
        f"{total_notifications} notification(s) sent.",
        flush=True,
    )

    return {
        "alerts":               alerts,
        "total_alerts":         len(alerts),
        "highest_severity":     highest if alerts else None,
        "notifications_sent":   total_notifications,
        "events_evaluated":     len(raw_events),
        "started_at":           started_at,
        "completed_at":         datetime.datetime.utcnow().isoformat() + "Z",
        "error":                None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser():
    p = argparse.ArgumentParser(
        description="Chorus Alert System — threshold-based cyber alerts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python alert_system.py --input pipeline_result.json --pretty\n"
            "  python alert_system.py --acoustic acoustic.json --pretty\n"
        ),
    )
    p.add_argument("--input", default=None,
                   help="Full pipeline result JSON (extracts agent outputs automatically).")
    p.add_argument("--acoustic", default=None,
                   help="Path to acoustic_event_detection JSON output.")
    p.add_argument("--geo", default=None,
                   help="Path to geo_estimation_agent JSON output.")
    p.add_argument("--face-reid", default=None, dest="face_reid",
                   help="Path to face_reid_agent JSON output.")
    p.add_argument("--manipulation", default=None,
                   help="Path to manipulation_detection result JSON (needs 'verdict' key).")
    p.add_argument("--source-uri", default="unknown",
                   help="Source URI for audit trail.")
    p.add_argument("--output", default=None,
                   help="Save alert result JSON to this path.")
    p.add_argument("--pretty", action="store_true")
    return p


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    acoustic = geo = face_reid = manipulation = None

    if args.input:
        with open(args.input, encoding="utf-8") as f:
            pipeline = json.load(f)
        acoustic = pipeline.get("acoustic_result") or pipeline.get("acoustic_event_detection")
        geo = pipeline.get("geo_result") or pipeline.get("geo_estimation")
        face_reid = pipeline.get("face_reid_result") or pipeline.get("face_reid")
        manipulation = pipeline.get("manipulation_result")
        if not args.source_uri or args.source_uri == "unknown":
            args.source_uri = pipeline.get("source_uri", "unknown")
    else:
        if args.acoustic:
            with open(args.acoustic, encoding="utf-8") as f:
                acoustic = json.load(f)
        if args.geo:
            with open(args.geo, encoding="utf-8") as f:
                geo = json.load(f)
        if args.face_reid:
            with open(args.face_reid, encoding="utf-8") as f:
                face_reid = json.load(f)
        if args.manipulation:
            with open(args.manipulation, encoding="utf-8") as f:
                manipulation = json.load(f)

    result = evaluate_and_alert(
        acoustic_result=acoustic,
        geo_result=geo,
        face_reid_result=face_reid,
        manipulation_result=manipulation,
        source_uri=args.source_uri,
    )

    out = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False, default=str)
    print(out)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"\n  [Alert] Saved to: {args.output}", flush=True)
