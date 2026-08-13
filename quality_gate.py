"""
quality_gate.py
===============
Chorus Quality Verification Agent — Rule-Based Quality Gate.

Pipeline position: Step 3 (runs after duplication_check passes, before AI analysis).

Applies 8 deterministic rules to fused timeline data and returns a structured
JSON verdict.  Rules are applied in order; no rule is skipped.

Supported source types
----------------------
  youtube       — Finite video from YouTube.
  local_upload  — Locally uploaded video file.
  live_rtsp     — Live RTSP stream; some rules are live-specific.

Usage (standalone)
------------------
  python quality_gate.py --input sample_input.json --pretty

Usage (library)
---------------
  from quality_gate import run_quality_gate
  verdict = run_quality_gate(payload)   # payload is a dict
  import json; print(json.dumps(verdict, indent=2))
"""

import json
import argparse
import re


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SOURCE_TYPES = {"youtube", "local_upload", "live_rtsp"}
VALID_SOURCES      = {"vision", "asr", "ocr", "diarization"}

REQUIRED_EVENT_FIELDS = {
    "event_id",
    "timestamp_start",
    "timestamp_end",
    "source",
    "content",
    "confidence_score",
    "speaker_id",
}

# Words that look like proper nouns but are generic in this domain.
# Filtered out before Rule 3 and Rule 4 comparisons.
GENERIC_TOKENS = {
    "Speaker", "Scene", "Frame", "Video", "Transcript",
    "The", "This", "That", "Here", "There", "In", "On",
    "Male", "Female", "Unknown", "Person", "Human", "Voice",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_rule(rule_name: str, status: str, failed_ids: list, notes: str,
               extra: dict = None) -> dict:
    r = {
        "rule":             rule_name,
        "status":           status,
        "failed_event_ids": failed_ids,
        "notes":            notes,
    }
    if extra:
        r.update(extra)
    return r


def _overlaps(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


# ---------------------------------------------------------------------------
# Entry-point validation helpers
# ---------------------------------------------------------------------------

def _validate_payload(payload: dict) -> list:
    """
    Run structural validation on the top-level payload before rule evaluation.
    Returns a list of human-readable error strings (empty = valid).
    """
    errors = []

    source_type = payload.get("source_type")
    if source_type not in VALID_SOURCE_TYPES:
        errors.append(
            f"source_type '{source_type}' is not valid. "
            f"Must be one of {sorted(VALID_SOURCE_TYPES)}."
        )

    if "fused_timeline" not in payload:
        errors.append("Missing required field: fused_timeline.")

    if source_type == "live_rtsp":
        stream_gaps = payload.get("stream_gaps")
        if stream_gaps is not None:
            for i, gap in enumerate(stream_gaps):
                if not isinstance(gap, dict):
                    errors.append(f"stream_gaps[{i}] is not a dict.")
                elif "gap_start" not in gap or "gap_end" not in gap:
                    errors.append(
                        f"stream_gaps[{i}] is missing 'gap_start' or 'gap_end'."
                    )

    return errors


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule1_timestamp_integrity(events: list, source_type: str, payload: dict) -> dict:
    """
    RULE 1 — Timestamp integrity

    Flag FAIL if any event has timestamp_end < timestamp_start.
    For youtube/local_upload: also flag FAIL if any timestamp exceeds video_duration_seconds.
    For live_rtsp: also flag FAIL if any timestamp is later than current_stream_position_seconds.
    """
    failed_ids     = []
    detail_notes   = []
    duration       = payload.get("video_duration_seconds")
    stream_pos     = payload.get("current_stream_position_seconds")

    for ev in events:
        eid = ev["event_id"]
        ts  = ev["timestamp_start"]
        te  = ev["timestamp_end"]

        # Basic integrity check
        if te < ts:
            failed_ids.append(eid)
            detail_notes.append(f"{eid}: timestamp_end ({te}) < timestamp_start ({ts})")
            continue

        # Source-specific upper-bound check
        if source_type in ("youtube", "local_upload") and duration is not None:
            if ts > duration:
                failed_ids.append(eid)
                detail_notes.append(
                    f"{eid}: timestamp_start ({ts}) exceeds video_duration_seconds ({duration})"
                )
            elif te > duration:
                failed_ids.append(eid)
                detail_notes.append(
                    f"{eid}: timestamp_end ({te}) exceeds video_duration_seconds ({duration})"
                )
        elif source_type == "live_rtsp" and stream_pos is not None:
            if ts > stream_pos:
                failed_ids.append(eid)
                detail_notes.append(
                    f"{eid}: timestamp_start ({ts}) exceeds "
                    f"current_stream_position_seconds ({stream_pos})"
                )
            elif te > stream_pos:
                failed_ids.append(eid)
                detail_notes.append(
                    f"{eid}: timestamp_end ({te}) exceeds "
                    f"current_stream_position_seconds ({stream_pos})"
                )

    if failed_ids:
        return _make_rule(
            "1_timestamp_integrity", "FAIL", failed_ids,
            f"{len(failed_ids)} event(s) have invalid timestamps.",
            {"violation_details": detail_notes},
        )
    return _make_rule(
        "1_timestamp_integrity", "PASS", [],
        "All event timestamps are within valid bounds.",
    )


def rule2_confidence_floor(events: list) -> dict:
    """
    RULE 2 — Confidence floor

    FAIL if confidence_score < 0.55.
    WARN if confidence_score is in [0.55, 0.70).
    """
    fail_ids = []
    warn_ids = []

    for ev in events:
        score = ev["confidence_score"]
        if score < 0.55:
            fail_ids.append(ev["event_id"])
        elif score < 0.70:
            warn_ids.append(ev["event_id"])

    if fail_ids:
        return _make_rule(
            "2_confidence_floor", "FAIL", fail_ids,
            f"{len(fail_ids)} event(s) have confidence_score below 0.55.",
        )
    if warn_ids:
        return _make_rule(
            "2_confidence_floor", "WARN", warn_ids,
            f"{len(warn_ids)} event(s) have confidence_score between 0.55 and 0.70.",
        )
    return _make_rule(
        "2_confidence_floor", "PASS", [],
        "All events meet the minimum confidence threshold.",
    )


def rule3_cross_source_contradiction(events: list) -> dict:
    """
    RULE 3 — Cross-source contradiction

    Flag FAIL if two sources overlap the same time window with materially
    different content AND neither source has confidence_score >= 0.85.

    'Materially different' requires AT LEAST 2 exclusive key tokens (numbers
    or non-generic proper-noun-style words) in one event that are absent in
    the other.  This threshold reduces false positives from trivial linguistic
    differences.
    """
    def key_tokens(text: str) -> set:
        numbers   = set(re.findall(r"\b\d[\d.,]*\b", text))
        cap_words = {
            w for w in re.findall(r"\b[A-Z][a-z]+\b", text)
            if w not in GENERIC_TOKENS
        }
        return numbers | cap_words

    failed_ids = []

    for i, ev_a in enumerate(events):
        for ev_b in events[i + 1:]:
            if ev_a["source"] == ev_b["source"]:
                continue
            if not _overlaps(
                ev_a["timestamp_start"], ev_a["timestamp_end"],
                ev_b["timestamp_start"], ev_b["timestamp_end"],
            ):
                continue

            tokens_a   = key_tokens(ev_a["content"])
            tokens_b   = key_tokens(ev_b["content"])
            exclusive_a = tokens_a - tokens_b
            exclusive_b = tokens_b - tokens_a

            # Require at least 2 exclusive tokens before flagging
            if len(exclusive_a) < 2 and len(exclusive_b) < 2:
                continue

            # High-confidence source breaks the tie
            if ev_a["confidence_score"] >= 0.85 or ev_b["confidence_score"] >= 0.85:
                continue

            for eid in (ev_a["event_id"], ev_b["event_id"]):
                if eid not in failed_ids:
                    failed_ids.append(eid)

    if failed_ids:
        return _make_rule(
            "3_cross_source_contradiction", "FAIL", failed_ids,
            "Overlapping events from different sources contain materially contradictory "
            "content (2+ exclusive key tokens) with no high-confidence source to resolve the conflict.",
        )
    return _make_rule(
        "3_cross_source_contradiction", "PASS", [],
        "No unresolved cross-source contradictions detected.",
    )


def rule4_speaker_consistency(events: list) -> dict:
    """
    RULE 4 — Speaker consistency

    Flag WARN if the same speaker_id appears with conflicting non-generic
    inferred name identities at different timestamps.

    Generic terms (Speaker, Male, Female, Unknown, etc.) are excluded from
    the name-conflict check to avoid false positives from ambiguous content.
    """
    speaker_names:     dict = {}
    speaker_event_ids: dict = {}

    for ev in events:
        spk = ev.get("speaker_id")
        if not spk:
            continue

        # Extract non-generic name candidates
        raw_names = set(
            re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", ev["content"])
        )
        names = raw_names - GENERIC_TOKENS

        if spk not in speaker_names:
            speaker_names[spk]     = set()
            speaker_event_ids[spk] = []

        speaker_names[spk]    |= names
        speaker_event_ids[spk].append(ev["event_id"])

    warn_ids = []
    for spk, names in speaker_names.items():
        if len(names) > 1:
            warn_ids.extend(speaker_event_ids[spk])

    if warn_ids:
        return _make_rule(
            "4_speaker_consistency", "WARN", warn_ids,
            "One or more speaker_ids have conflicting non-generic inferred "
            "name identities across different timestamps.",
        )
    return _make_rule(
        "4_speaker_consistency", "PASS", [],
        "No speaker identity conflicts detected.",
    )


def rule5_coverage_gaps(events: list, source_type: str, payload: dict) -> dict:
    """
    RULE 5 — Coverage gaps

    youtube/local_upload: WARN if any continuous span > 45 s has zero events.
    live_rtsp: WARN if the most recent 45 s window has zero events.
    """
    GAP_THRESHOLD = 45.0

    if source_type in ("youtube", "local_upload"):
        duration = payload.get("video_duration_seconds")
        if duration is None:
            return _make_rule(
                "5_coverage_gaps", "insufficient_data", [],
                "video_duration_seconds is null; cannot evaluate coverage gaps.",
            )

        # Sort covered intervals
        intervals = sorted(
            [(ev["timestamp_start"], ev["timestamp_end"]) for ev in events],
            key=lambda x: x[0],
        )
        gaps_found = []

        # Leading gap
        if intervals and intervals[0][0] > GAP_THRESHOLD:
            gaps_found.append(f"0.0 – {intervals[0][0]:.1f}s")

        # Inter-event gaps
        for k in range(len(intervals) - 1):
            gap_s = intervals[k][1]
            gap_e = intervals[k + 1][0]
            if gap_e - gap_s > GAP_THRESHOLD:
                gaps_found.append(f"{gap_s:.1f} – {gap_e:.1f}s")

        # Trailing gap
        if intervals and (duration - intervals[-1][1]) > GAP_THRESHOLD:
            gaps_found.append(f"{intervals[-1][1]:.1f} – {duration:.1f}s")

        # Entire video uncovered
        if not intervals and duration > GAP_THRESHOLD:
            gaps_found.append(f"0.0 – {duration:.1f}s (entire video uncovered)")

        if gaps_found:
            return _make_rule(
                "5_coverage_gaps", "WARN", [],
                f"Coverage gap(s) exceeding 45 s detected: {'; '.join(gaps_found)}.",
            )
        return _make_rule(
            "5_coverage_gaps", "PASS", [],
            "No coverage gaps exceeding 45 s detected in the full timeline.",
        )

    elif source_type == "live_rtsp":
        pos = payload.get("current_stream_position_seconds")
        if pos is None:
            return _make_rule(
                "5_coverage_gaps", "insufficient_data", [],
                "current_stream_position_seconds is null; cannot evaluate live coverage.",
            )
        window_start  = max(0.0, pos - GAP_THRESHOLD)
        recent_events = [
            ev for ev in events
            if ev["timestamp_end"] >= window_start and ev["timestamp_start"] <= pos
        ]
        if not recent_events:
            return _make_rule(
                "5_coverage_gaps", "WARN", [],
                f"No events found in the most recent 45 s window "
                f"({window_start:.1f} – {pos:.1f}s).",
            )
        return _make_rule(
            "5_coverage_gaps", "PASS", [],
            f"Events present within the most recent 45 s window ({window_start:.1f} – {pos:.1f}s).",
        )

    return _make_rule(
        "5_coverage_gaps", "insufficient_data", [],
        "Unknown source_type; cannot evaluate coverage gaps.",
    )


def rule6_hallucination_guard(events: list) -> dict:
    """
    RULE 6 — Hallucination guard

    FAIL if any event's source field is not one of the recognised signal types
    (vision, asr, ocr, diarization).  Content from an unrecognised source
    cannot be attributed to a real signal and is treated as potentially generated.
    """
    failed_ids = [ev["event_id"] for ev in events if ev.get("source") not in VALID_SOURCES]

    if failed_ids:
        return _make_rule(
            "6_hallucination_guard", "FAIL", failed_ids,
            "One or more events have a source field that is not a recognised signal type "
            "(vision | asr | ocr | diarization), indicating potentially generated content.",
        )
    return _make_rule(
        "6_hallucination_guard", "PASS", [],
        "All events are attributed to a recognised source signal.",
    )


def rule7_format_completeness(events: list) -> dict:
    """
    RULE 7 — Format and completeness

    FAIL if any event is missing any required field.
    The result includes the specific missing fields per event.
    """
    failed_ids    = []
    missing_detail: dict = {}

    for ev in events:
        missing = sorted(REQUIRED_EVENT_FIELDS - set(ev.keys()))
        if missing:
            eid = ev.get("event_id", "<unknown>")
            failed_ids.append(eid)
            missing_detail[eid] = missing

    if failed_ids:
        return _make_rule(
            "7_format_completeness", "FAIL", failed_ids,
            f"{len(failed_ids)} event(s) are missing required fields.",
            {"missing_fields_per_event": missing_detail},
        )
    return _make_rule(
        "7_format_completeness", "PASS", [],
        "All events contain all required fields.",
    )


def rule8_stream_continuity(source_type: str, payload: dict) -> dict:
    """
    RULE 8 — Stream continuity (live_rtsp only)

    FAIL if any stream_gap has duration > 10 seconds.
    not_applicable for youtube / local_upload.
    """
    if source_type in ("youtube", "local_upload"):
        return _make_rule(
            "8_stream_continuity", "not_applicable", [],
            "Rule 8 applies only to live_rtsp sources.",
        )

    stream_gaps = payload.get("stream_gaps")
    if stream_gaps is None:
        return _make_rule(
            "8_stream_continuity", "insufficient_data", [],
            "stream_gaps is null; cannot evaluate stream continuity.",
        )

    # Guard against malformed gap entries
    malformed = []
    for i, gap in enumerate(stream_gaps):
        if not isinstance(gap, dict) or "gap_start" not in gap or "gap_end" not in gap:
            malformed.append(i)

    if malformed:
        return _make_rule(
            "8_stream_continuity", "insufficient_data", [],
            f"stream_gaps entries at index(es) {malformed} are malformed "
            f"(missing gap_start or gap_end); cannot evaluate stream continuity.",
        )

    failed_gaps = [g for g in stream_gaps if (g["gap_end"] - g["gap_start"]) > 10]

    if failed_gaps:
        details = "; ".join(
            f"{g['gap_start']}s – {g['gap_end']}s "
            f"({g['gap_end'] - g['gap_start']:.1f}s)"
            for g in failed_gaps
        )
        return _make_rule(
            "8_stream_continuity", "FAIL", [],
            f"{len(failed_gaps)} stream gap(s) exceeding 10 s detected: {details}.",
        )
    return _make_rule(
        "8_stream_continuity", "PASS", [],
        "No stream gaps exceeding 10 s detected.",
    )


# ---------------------------------------------------------------------------
# Verdict derivation
# ---------------------------------------------------------------------------

def _derive_verdict(rule_results: list) -> tuple:
    statuses = [r["status"] for r in rule_results]
    if "FAIL" in statuses:
        return "FAIL", True
    if "WARN" in statuses:
        return "FLAG_FOR_REVIEW", True
    return "PASS", False


# ---------------------------------------------------------------------------
# Insufficient-data fallback (used when payload is structurally invalid)
# ---------------------------------------------------------------------------

def _all_insufficient(reason: str) -> dict:
    rule_names = [
        "1_timestamp_integrity",
        "2_confidence_floor",
        "3_cross_source_contradiction",
        "4_speaker_consistency",
        "5_coverage_gaps",
        "6_hallucination_guard",
        "7_format_completeness",
        "8_stream_continuity",
    ]
    return {
        "overall_verdict":      "FAIL",
        "rule_results": [
            _make_rule(name, "insufficient_data", [], reason)
            for name in rule_names
        ],
        "route_to_human_review": True,
        "payload_validation_errors": [reason],
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_quality_gate(payload: dict) -> dict:
    """
    Apply all 8 quality rules to the fused timeline payload.

    Parameters
    ----------
    payload : dict
        The full input dict as described in the system prompt, containing:
        video_id, source_type, video_duration_seconds,
        current_stream_position_seconds, stream_gaps, fused_timeline.

    Returns
    -------
    dict — JSON-serialisable verdict with overall_verdict, rule_results,
           route_to_human_review, and optionally payload_validation_errors.
    """
    # ── Structural validation ──────────────────────────────────────────────
    errors = _validate_payload(payload)
    if errors:
        return {
            "overall_verdict":          "FAIL",
            "rule_results":             [],
            "route_to_human_review":    True,
            "payload_validation_errors": errors,
        }

    source_type: str  = payload.get("source_type", "")
    events:      list = payload.get("fused_timeline", [])

    # ── Empty timeline guard ───────────────────────────────────────────────
    if not events:
        return _all_insufficient(
            "fused_timeline is empty; no events to evaluate."
        )

    # ── Run all rules ──────────────────────────────────────────────────────
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

    overall_verdict, route = _derive_verdict(rule_results)

    return {
        "overall_verdict":      overall_verdict,
        "rule_results":         rule_results,
        "route_to_human_review": route,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Chorus Quality Gate — Rule-based fused timeline verification.",
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a JSON file containing the fused timeline payload.",
    )
    parser.add_argument(
        "--pretty", action="store_true",
        help="Pretty-print the output JSON.",
    )
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)

    verdict = run_quality_gate(payload)
    print(json.dumps(verdict, indent=2 if args.pretty else None))
