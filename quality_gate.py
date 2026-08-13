"""
quality_gate.py
===============
Chorus Quality Verification Agent - Rule-Based Quality Gate.

Apply this module against fused timeline data produced by the Chorus
video-intelligence pipeline.  It evaluates Rules 1-8 exactly as defined
in the SYSTEM PROMPT and returns a structured JSON verdict.

Usage (standalone):
    python quality_gate.py --input sample_input.json

Usage (as a library):
    from quality_gate import run_quality_gate
    verdict = run_quality_gate(payload)      # payload is a dict
    print(verdict)                           # returns a dict ready for json.dumps
"""

import json
import argparse
import re
from typing import Any

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Payload = dict
Event   = dict

# ---------------------------------------------------------------------------
# Required fields every fused_timeline event must contain (Rule 7)
# ---------------------------------------------------------------------------
REQUIRED_EVENT_FIELDS = {
    "event_id",
    "timestamp_start",
    "timestamp_end",
    "source",
    "content",
    "confidence_score",
    "speaker_id",
}

VALID_SOURCES = {"vision", "asr", "ocr", "diarization"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(rule_name, status, failed_ids, notes):
    return {
        "rule": rule_name,
        "status": status,
        "failed_event_ids": failed_ids,
        "notes": notes,
    }


def _overlaps(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------

def rule1_timestamp_integrity(events, source_type, payload):
    failed_ids = []
    duration        = payload.get("video_duration_seconds")
    stream_position = payload.get("current_stream_position_seconds")

    for ev in events:
        eid = ev["event_id"]
        ts  = ev["timestamp_start"]
        te  = ev["timestamp_end"]

        if te < ts:
            failed_ids.append(eid)
            continue

        if source_type in ("youtube", "local_upload"):
            if duration is not None and (ts > duration or te > duration):
                failed_ids.append(eid)
        elif source_type == "live_rtsp":
            if stream_position is not None and (ts > stream_position or te > stream_position):
                failed_ids.append(eid)

    if failed_ids:
        return _make_rule("1_timestamp_integrity", "FAIL", failed_ids,
                          "One or more events have invalid or out-of-bounds timestamps.")
    return _make_rule("1_timestamp_integrity", "PASS", [],
                      "All event timestamps are within valid bounds.")


def rule2_confidence_floor(events):
    fail_ids = []
    warn_ids = []
    for ev in events:
        score = ev["confidence_score"]
        if score < 0.55:
            fail_ids.append(ev["event_id"])
        elif score < 0.70:
            warn_ids.append(ev["event_id"])

    if fail_ids:
        return _make_rule("2_confidence_floor", "FAIL", fail_ids,
                          f"{len(fail_ids)} event(s) have confidence_score below 0.55.")
    if warn_ids:
        return _make_rule("2_confidence_floor", "WARN", warn_ids,
                          f"{len(warn_ids)} event(s) have confidence_score between 0.55 and 0.70.")
    return _make_rule("2_confidence_floor", "PASS", [],
                      "All events meet the confidence floor threshold.")


def rule3_cross_source_contradiction(events):
    def key_tokens(text):
        numbers   = set(re.findall(r"\b\d[\d.,]*\b", text))
        cap_words = set(re.findall(r"\b[A-Z][a-z]+\b", text))
        return numbers | cap_words

    failed_ids = []
    for i, ev_a in enumerate(events):
        for ev_b in events[i + 1:]:
            if ev_a["source"] == ev_b["source"]:
                continue
            if not _overlaps(ev_a["timestamp_start"], ev_a["timestamp_end"],
                             ev_b["timestamp_start"], ev_b["timestamp_end"]):
                continue
            tokens_a = key_tokens(ev_a["content"])
            tokens_b = key_tokens(ev_b["content"])
            if (tokens_a - tokens_b) or (tokens_b - tokens_a):
                if ev_a["confidence_score"] >= 0.85 or ev_b["confidence_score"] >= 0.85:
                    continue
                for eid in (ev_a["event_id"], ev_b["event_id"]):
                    if eid not in failed_ids:
                        failed_ids.append(eid)

    if failed_ids:
        return _make_rule("3_cross_source_contradiction", "FAIL", failed_ids,
                          "Overlapping events from different sources have contradictory content "
                          "with no high-confidence source to resolve the conflict.")
    return _make_rule("3_cross_source_contradiction", "PASS", [],
                      "No unresolved cross-source contradictions detected.")


def rule4_speaker_consistency(events):
    speaker_names     = {}
    speaker_event_ids = {}

    for ev in events:
        spk = ev.get("speaker_id")
        if not spk:
            continue
        names = set(re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", ev["content"]))
        if spk not in speaker_names:
            speaker_names[spk]     = set()
            speaker_event_ids[spk] = []
        speaker_names[spk] |= names
        speaker_event_ids[spk].append(ev["event_id"])

    warn_ids = []
    for spk, names in speaker_names.items():
        if len(names) > 1:
            warn_ids.extend(speaker_event_ids[spk])

    if warn_ids:
        return _make_rule("4_speaker_consistency", "WARN", warn_ids,
                          "One or more speaker_ids have conflicting inferred name identities "
                          "across different timestamps.")
    return _make_rule("4_speaker_consistency", "PASS", [],
                      "No speaker identity conflicts detected.")


def rule5_coverage_gaps(events, source_type, payload):
    GAP_THRESHOLD = 45.0

    if source_type in ("youtube", "local_upload"):
        duration = payload.get("video_duration_seconds")
        if duration is None:
            return _make_rule("5_coverage_gaps", "insufficient_data", [],
                              "video_duration_seconds is null; cannot evaluate coverage gaps.")

        intervals = sorted(
            [(ev["timestamp_start"], ev["timestamp_end"]) for ev in events],
            key=lambda x: x[0],
        )
        gaps_found = []

        if intervals and intervals[0][0] > GAP_THRESHOLD:
            gaps_found.append(f"0.0 - {intervals[0][0]:.1f}s")

        for k in range(len(intervals) - 1):
            gap_start = intervals[k][1]
            gap_end   = intervals[k + 1][0]
            if gap_end - gap_start > GAP_THRESHOLD:
                gaps_found.append(f"{gap_start:.1f} - {gap_end:.1f}s")

        if intervals and (duration - intervals[-1][1]) > GAP_THRESHOLD:
            gaps_found.append(f"{intervals[-1][1]:.1f} - {duration:.1f}s")

        if not intervals and duration > GAP_THRESHOLD:
            gaps_found.append(f"0.0 - {duration:.1f}s")

        if gaps_found:
            return _make_rule("5_coverage_gaps", "WARN", [],
                              f"Coverage gap(s) exceeding 45 s detected: {'; '.join(gaps_found)}.")
        return _make_rule("5_coverage_gaps", "PASS", [],
                          "No coverage gaps exceeding 45 s detected.")

    elif source_type == "live_rtsp":
        pos = payload.get("current_stream_position_seconds")
        if pos is None:
            return _make_rule("5_coverage_gaps", "insufficient_data", [],
                              "current_stream_position_seconds is null; cannot evaluate live coverage gap.")
        window_start  = pos - GAP_THRESHOLD
        recent_events = [
            ev for ev in events
            if ev["timestamp_end"] >= window_start and ev["timestamp_start"] <= pos
        ]
        if not recent_events:
            return _make_rule("5_coverage_gaps", "WARN", [],
                              f"No events in the most recent 45 s window ({window_start:.1f} - {pos:.1f}s).")
        return _make_rule("5_coverage_gaps", "PASS", [],
                          "Events are present within the most recent 45 s window.")

    return _make_rule("5_coverage_gaps", "insufficient_data", [],
                      "Unknown source_type; cannot evaluate coverage gaps.")


def rule6_hallucination_guard(events):
    failed_ids = [ev["event_id"] for ev in events if ev["source"] not in VALID_SOURCES]
    if failed_ids:
        return _make_rule("6_hallucination_guard", "FAIL", failed_ids,
                          "One or more events have a source field that is not a recognised "
                          "signal type, indicating potentially generated content.")
    return _make_rule("6_hallucination_guard", "PASS", [],
                      "All events are attributed to a recognised source signal.")


def rule7_format_completeness(events):
    failed_ids = []
    for ev in events:
        missing = REQUIRED_EVENT_FIELDS - set(ev.keys())
        if missing:
            failed_ids.append(ev.get("event_id", "<unknown>"))
    if failed_ids:
        return _make_rule("7_format_completeness", "FAIL", failed_ids,
                          "One or more events are missing required fields.")
    return _make_rule("7_format_completeness", "PASS", [],
                      "All events contain all required fields.")


def rule8_stream_continuity(source_type, payload):
    if source_type in ("youtube", "local_upload"):
        return _make_rule("8_stream_continuity", "not_applicable", [],
                          "Rule 8 applies only to live_rtsp sources.")

    stream_gaps = payload.get("stream_gaps")
    if stream_gaps is None:
        return _make_rule("8_stream_continuity", "insufficient_data", [],
                          "stream_gaps field is null; cannot evaluate stream continuity.")

    failed_gaps = [g for g in stream_gaps if (g["gap_end"] - g["gap_start"]) > 10]
    if failed_gaps:
        details = "; ".join(f"{g['gap_start']}-{g['gap_end']}s" for g in failed_gaps)
        return _make_rule("8_stream_continuity", "FAIL", [],
                          f"Stream gap(s) exceeding 10 s detected: {details}.")
    return _make_rule("8_stream_continuity", "PASS", [],
                      "No stream gaps exceeding 10 s detected.")


# ---------------------------------------------------------------------------
# Verdict derivation
# ---------------------------------------------------------------------------

def _derive_verdict(rule_results):
    statuses = [r["status"] for r in rule_results]
    if "FAIL" in statuses:
        return "FAIL", True
    if "WARN" in statuses:
        return "FLAG_FOR_REVIEW", True
    return "PASS", False


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_quality_gate(payload):
    source_type = payload.get("source_type", "")
    events      = payload.get("fused_timeline", [])

    rule_results = [
        rule1_timestamp_integrity(events, source_type, payload),
        rule2_confidence_floor(events),
        rule3_cross_source_contradiction(events),
        rule4_speaker_consistency(events),
        rule5_coverage_gaps(events, source_type, payload),
        rule6_hallucination_guard(events),
        rule7_format_completeness(events),
        rule8_stream_continuity(source_type, payload),
    ]

    overall_verdict, route_to_human_review = _derive_verdict(rule_results)
    return {
        "overall_verdict": overall_verdict,
        "rule_results": rule_results,
        "route_to_human_review": route_to_human_review,
    }


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Chorus Quality Gate - Rule-based fused timeline verification."
    )
    parser.add_argument("--input",  required=True,
                        help="Path to a JSON file containing the fused timeline payload.")
    parser.add_argument("--pretty", action="store_true",
                        help="Pretty-print the output JSON.")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)

    verdict = run_quality_gate(payload)
    print(json.dumps(verdict, indent=2 if args.pretty else None))
