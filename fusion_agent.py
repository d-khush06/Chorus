"""
fusion_agent.py
===============
Chorus -- Step 13: Fusion Agent

Pipeline position:
  Step 12 (Context / Enrichment) -> [THIS MODULE] -> Step 14 (Correlation)

Purpose
-------
Merges the independent outputs of Perception (Step 8), ASR (Step 9),
Diarization (Step 10), and OCR (Step 11) into one single, time-aligned
fused timeline, and explicitly flags disagreements between sources
rather than silently resolving them.

Six enforced rules
------------------
  Rule 1 -- Timeline construction:
            Merge all four sources into one sorted list of events keyed by
            start_seconds, each tied back to a canonical scene_id from
            Step 7's scene list.

  Rule 2 -- Speaker-transcript alignment:
            Match each ASR segment to the diarization speaker whose window
            overlaps it by the most.  Split ASR segments that straddle a
            speaker-change boundary at the boundary point.

  Rule 3 -- Conflict detection (most important):
            Two events from different source agents that overlap >50% in time
            AND carry contradictory content (presence / content / timing) are
            emitted into a separate `conflicts` list -- never silently merged.
            conflict_type in {"presence_contradiction",
                               "content_mismatch", "timing_mismatch"}.

  Rule 4 -- Confidence propagation:
            Per-event confidence = min(source confidences) when combining;
            never average or invent.  Single-source events keep their
            original confidence unchanged.

  Rule 5 -- Gap handling:
            Every scene that has zero events from every source gets one
            placeholder entry with event_type="no_signal", source_agent=null.

  Rule 6 -- Determinism:
            Same four inputs always produce identical output.  All sorting
            is explicit; no dict-ordering or set-ordering is relied upon.

Input schema (per source)
-------------------------
Each of the four source lists contains dicts with at least:
  {
    "start_seconds": float,
    "end_seconds":   float,
    "type":          str,      # e.g. "speech", "object", "word", "text"
    "content":       str,
    "confidence":    float,
    "source":        str       # "perception" | "asr" | "diarization" | "ocr"
  }

Output schema
-------------
{
  "fused_timeline": [
    {
      "scene_id":      int,
      "start_seconds": float,
      "end_seconds":   float,
      "event_type":    str,
      "content":       str,
      "source_agent":  str | null,
      "confidence":    float | null
    }
  ],
  "conflicts": [
    {
      "scene_id":     int,
      "time_range":   [float, float],
      "source_a":     str,
      "content_a":    str,
      "source_b":     str,
      "content_b":    str,
      "conflict_type": str
    }
  ],
  "scenes_with_no_signal": [int, ...]
}

Usage (library)
---------------
  from fusion_agent import fuse_timeline

  result = fuse_timeline(
      scenes         = step7_output["scenes"],       # list of {scene_id, start_seconds, end_seconds}
      perception     = step8_output,                 # list of events
      asr            = step9_output,
      diarization    = step10_output,
      ocr            = step11_output,
  )

Usage (CLI)
-----------
  python fusion_agent.py --scenes scenes.json --perception p.json
                         --asr a.json --diarization d.json --ocr o.json --pretty
"""

import os
import json
import logging
import argparse
import datetime
import sys
from typing import List, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.fusion_agent")
logging.basicConfig(
    level=logging.INFO,
    format="[fusion_agent] %(levelname)s -- %(message)s",
)

# ---------------------------------------------------------------------------
# Named constants -- change only here
# ---------------------------------------------------------------------------

# Conflict detection: fraction of the shorter event's duration that must be
# covered by the overlap to trigger conflict analysis.
CONFLICT_OVERLAP_THRESHOLD: float = 0.50

# Diarization alignment: minimum fractional overlap needed to assign a
# transcript segment to a diarization speaker window.
SPEAKER_MIN_OVERLAP_FRAC: float = 0.01

# Audit log directory
AUDIT_LOG_DIR: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audit_logs", "step13"
)

# Canonical source agent names
SOURCE_PERCEPTION  = "perception"
SOURCE_ASR         = "asr"
SOURCE_DIARIZATION = "diarization"
SOURCE_OCR         = "ocr"

ALL_SOURCES = (SOURCE_PERCEPTION, SOURCE_ASR, SOURCE_DIARIZATION, SOURCE_OCR)

# Conflict type constants
CT_PRESENCE    = "presence_contradiction"
CT_CONTENT     = "content_mismatch"
CT_TIMING      = "timing_mismatch"


# ---------------------------------------------------------------------------
# Internal helpers -- geometry
# ---------------------------------------------------------------------------

def _overlap_seconds(a_start: float, a_end: float,
                     b_start: float, b_end: float) -> float:
    """Return the duration (seconds) of overlap between two intervals."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _overlap_fraction(a_start: float, a_end: float,
                      b_start: float, b_end: float) -> float:
    """
    Return overlap / min(duration_a, duration_b).

    This is the fraction used for conflict detection (Rule 3):
    a >50% overlap means more than half of the *shorter* event is covered.
    Using the shorter event prevents a tiny blip from being considered
    to highly overlap a long event just because the absolute overlap is large.
    """
    overlap   = _overlap_seconds(a_start, a_end, b_start, b_end)
    dur_a     = max(a_end - a_start, 1e-9)
    dur_b     = max(b_end - b_start, 1e-9)
    min_dur   = min(dur_a, dur_b)
    return overlap / min_dur


# ---------------------------------------------------------------------------
# Internal helpers -- scene assignment
# ---------------------------------------------------------------------------

def _find_scene_id(start_s: float, scenes: List[dict]) -> int:
    """
    Return the scene_id of the scene whose window contains start_s.

    If start_s falls in a gap between scenes (shouldn't happen with valid
    Step 7 output, but we handle it), we assign the nearest scene by
    distance to its midpoint.  The scenes list must be sorted by
    start_seconds (guaranteed by _sort_scenes()).
    """
    if not scenes:
        return 0

    best_id   = scenes[0]["scene_id"]
    best_dist = float("inf")

    for scene in scenes:
        s = scene["start_seconds"]
        e = scene["end_seconds"]
        if s <= start_s < e:
            return scene["scene_id"]
        # Fallback: nearest by distance to start of scene
        dist = abs(start_s - s)
        if dist < best_dist:
            best_dist = dist
            best_id   = scene["scene_id"]

    return best_id


def _sort_scenes(scenes: List[dict]) -> List[dict]:
    """Return scenes sorted by start_seconds, then scene_id (Rule 6)."""
    return sorted(scenes, key=lambda s: (s["start_seconds"], s["scene_id"]))


# ---------------------------------------------------------------------------
# Rule 2: Speaker-transcript alignment
# ---------------------------------------------------------------------------

def _align_asr_to_diarization(
    asr_events:          List[dict],
    diarization_events:  List[dict],
) -> List[dict]:
    """
    Assign each ASR event to the diarization speaker whose window overlaps
    it most.  If an ASR event straddles a speaker boundary, split it at
    the boundary and assign each piece separately.

    Returns a new list of ASR event dicts with an added "speaker" field
    (the content value of the winning diarization event, or None if no
    diarization event overlaps at all).

    The original asr_events list is not mutated.
    """
    # Sort diarization by start for determinism (Rule 6)
    diar_sorted = sorted(
        diarization_events,
        key=lambda e: (e["start_seconds"], e.get("content", "")),
    )

    aligned: List[dict] = []

    for asr in sorted(asr_events, key=lambda e: (e["start_seconds"], e.get("content", ""))):
        a_start = asr["start_seconds"]
        a_end   = asr["end_seconds"]

        # Collect all diarization windows that overlap this ASR segment
        overlapping = [
            d for d in diar_sorted
            if _overlap_seconds(a_start, a_end,
                                d["start_seconds"], d["end_seconds"]) > 0
        ]

        if not overlapping:
            # No diarization coverage: emit as-is with speaker=None
            aligned.append({**asr, "speaker": None})
            continue

        if len(overlapping) == 1:
            # Simple case: exactly one speaker covers this segment
            aligned.append({**asr, "speaker": overlapping[0].get("content")})
            continue

        # Multiple speakers: split the ASR segment at each speaker boundary
        # The split points are the end of each diarization window (except last)
        split_points = sorted({d["end_seconds"] for d in overlapping[:-1]})
        boundaries   = [a_start] + [p for p in split_points if a_start < p < a_end] + [a_end]

        for i in range(len(boundaries) - 1):
            seg_start = boundaries[i]
            seg_end   = boundaries[i + 1]
            if seg_end <= seg_start:
                continue

            # Assign to the speaker with the most overlap in this sub-segment
            best_speaker = None
            best_overlap = -1.0
            for d in overlapping:
                ov = _overlap_seconds(seg_start, seg_end,
                                      d["start_seconds"], d["end_seconds"])
                if ov > best_overlap:
                    best_overlap = ov
                    best_speaker = d.get("content")

            piece = dict(asr)
            piece["start_seconds"] = seg_start
            piece["end_seconds"]   = seg_end
            piece["speaker"]       = best_speaker
            aligned.append(piece)

    # Sort for determinism (Rule 6)
    return sorted(aligned, key=lambda e: (e["start_seconds"], e.get("content", "")))


# ---------------------------------------------------------------------------
# Rule 3: Conflict detection
# ---------------------------------------------------------------------------

def _classify_conflict_type(ev_a: dict, ev_b: dict) -> str:
    """
    Classify the conflict type between two overlapping events from different
    source agents.

    Rules applied (in order):
      1. presence_contradiction -- one source has "no" / "empty" / "silence"
         content while the other has a positive detection.
      2. timing_mismatch       -- same broad event type but significantly
         different start/end boundaries in the overlap window.
      3. content_mismatch      -- catch-all for overlapping events with
         materially different textual content.
    """
    content_a = str(ev_a.get("content", "")).lower().strip()
    content_b = str(ev_b.get("content", "")).lower().strip()

    # Presence keywords: one side says "nothing here"
    absence_terms = {
        "empty", "no signal", "silent", "silence", "no speech", "no text",
        "no_signal", "blank", "none", "nothing", "no audio",
    }

    def _is_absence(text: str) -> bool:
        return any(term in text for term in absence_terms)

    if _is_absence(content_a) != _is_absence(content_b):
        return CT_PRESENCE

    # Timing mismatch: same source type but the events disagree substantially
    # on where within the overlap window they begin/end.
    type_a = str(ev_a.get("type", ev_a.get("event_type", ""))).lower()
    type_b = str(ev_b.get("type", ev_b.get("event_type", ""))).lower()
    if type_a and type_b and type_a == type_b:
        # Same event type, different agents -- compare boundary offsets
        start_diff = abs(ev_a["start_seconds"] - ev_b["start_seconds"])
        end_diff   = abs(ev_a["end_seconds"]   - ev_b["end_seconds"])
        dur_a      = max(ev_a["end_seconds"] - ev_a["start_seconds"], 1e-9)
        dur_b      = max(ev_b["end_seconds"] - ev_b["start_seconds"], 1e-9)
        if (start_diff / min(dur_a, dur_b)) > 0.25 or \
           (end_diff   / min(dur_a, dur_b)) > 0.25:
            return CT_TIMING

    return CT_CONTENT


def _detect_conflicts(
    all_events:  List[dict],
    scenes:      List[dict],
) -> List[dict]:
    """
    Rule 3: Scan all pairs of events from *different* source agents.
    If a pair overlaps by >CONFLICT_OVERLAP_THRESHOLD of the shorter
    event's duration, classify and record the conflict.

    Events that conflict are still kept in the fused timeline (we never
    silently drop them), but their presence is additionally recorded in
    the returned conflicts list.

    Returns a list of conflict dicts.
    """
    # Sort for determinism (Rule 6)
    evs = sorted(
        all_events,
        key=lambda e: (e["start_seconds"], e.get("source_agent", ""), e.get("content", "")),
    )

    conflicts: List[dict] = []
    seen_pairs = set()

    for i, ev_a in enumerate(evs):
        for j, ev_b in enumerate(evs):
            if j <= i:
                continue
            # Only compare events from different source agents
            src_a = ev_a.get("source_agent")
            src_b = ev_b.get("source_agent")
            if src_a == src_b:
                continue
            if src_a is None or src_b is None:
                continue  # no_signal placeholders don't conflict

            frac = _overlap_fraction(
                ev_a["start_seconds"], ev_a["end_seconds"],
                ev_b["start_seconds"], ev_b["end_seconds"],
            )
            if frac <= CONFLICT_OVERLAP_THRESHOLD:
                continue

            # Deduplicate: don't emit the same (i, j) pair twice
            pair_key = (i, j) if i < j else (j, i)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            ctype = _classify_conflict_type(ev_a, ev_b)

            # Overlap time range: intersection of the two events
            ov_start = max(ev_a["start_seconds"], ev_b["start_seconds"])
            ov_end   = min(ev_a["end_seconds"],   ev_b["end_seconds"])

            scene_id = _find_scene_id(ov_start, scenes)

            conflicts.append({
                "scene_id":     scene_id,
                "time_range":   [round(ov_start, 6), round(ov_end, 6)],
                "source_a":     src_a,
                "content_a":    str(ev_a.get("content", "")),
                "source_b":     src_b,
                "content_b":    str(ev_b.get("content", "")),
                "conflict_type": ctype,
            })

    # Sort conflicts for determinism (Rule 6)
    return sorted(
        conflicts,
        key=lambda c: (c["scene_id"], c["time_range"][0], c["source_a"], c["source_b"]),
    )


# ---------------------------------------------------------------------------
# Rule 1: Build fused timeline
# ---------------------------------------------------------------------------

def _build_fused_event(raw: dict, scene_id: int) -> dict:
    """
    Convert a raw source-agent event dict into the canonical fused event
    schema.  Works for all four source types.
    """
    event_type = raw.get("type") or raw.get("event_type") or "unknown"
    confidence = raw.get("confidence")
    speaker    = raw.get("speaker")  # populated by Rule 2 alignment for ASR
    content    = str(raw.get("content", ""))

    # If the ASR event was split and has a speaker, annotate content
    if speaker and raw.get("source") == SOURCE_ASR:
        content = f"[{speaker}] {content}"

    return {
        "scene_id":      scene_id,
        "start_seconds": round(raw["start_seconds"], 6),
        "end_seconds":   round(raw["end_seconds"],   6),
        "event_type":    event_type,
        "content":       content,
        "source_agent":  raw.get("source") or raw.get("source_agent"),
        "confidence":    confidence,
    }


def _build_timeline(
    all_source_events: List[dict],
    scenes:            List[dict],
) -> List[dict]:
    """
    Rule 1: Sort all events by (start_seconds, source_agent, content)
    and assign each a scene_id.

    The sort key is deterministic and does not rely on dict ordering.
    """
    fused: List[dict] = []
    for raw in all_source_events:
        scene_id = _find_scene_id(raw["start_seconds"], scenes)
        fused.append(_build_fused_event(raw, scene_id))

    return sorted(
        fused,
        key=lambda e: (
            e["start_seconds"],
            e.get("source_agent") or "",
            e.get("content") or "",
        ),
    )


# ---------------------------------------------------------------------------
# Rule 5: Gap handling
# ---------------------------------------------------------------------------

def _inject_no_signal_placeholders(
    fused_timeline: List[dict],
    scenes:         List[dict],
) -> tuple:
    """
    Rule 5: For every scene that has zero events in the fused timeline,
    inject a no_signal placeholder and record the scene_id.

    Returns (augmented_timeline, scenes_with_no_signal).
    """
    covered_scenes = {ev["scene_id"] for ev in fused_timeline}
    no_signal_ids  = []
    extra_events   = []

    for scene in _sort_scenes(scenes):
        sid = scene["scene_id"]
        if sid not in covered_scenes:
            no_signal_ids.append(sid)
            extra_events.append({
                "scene_id":      sid,
                "start_seconds": round(scene["start_seconds"], 6),
                "end_seconds":   round(scene["end_seconds"],   6),
                "event_type":    "no_signal",
                "content":       "",
                "source_agent":  None,
                "confidence":    None,
            })

    augmented = fused_timeline + extra_events
    # Re-sort for determinism (Rule 6)
    augmented = sorted(
        augmented,
        key=lambda e: (
            e["start_seconds"],
            e.get("source_agent") or "",
            e.get("content") or "",
        ),
    )

    return augmented, sorted(no_signal_ids)


# ---------------------------------------------------------------------------
# Rule 4: Confidence propagation (applied at merge time, documented here)
# ---------------------------------------------------------------------------

def _merge_confidence(confidences: List[Optional[float]]) -> Optional[float]:
    """
    Rule 4: When a fused event combines 2+ sources, confidence = min().
    Never average; never invent.  Returns None if no valid confidences.

    For single-source events this function is not called -- the original
    confidence is kept as-is.
    """
    valid = [c for c in confidences if c is not None]
    if not valid:
        return None
    return min(valid)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _write_audit_log(result: dict) -> None:
    """Append an audit record to the daily JSONL log for Step 13."""
    try:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        today    = datetime.date.today().isoformat()
        log_path = os.path.join(AUDIT_LOG_DIR, f"step13_{today}.jsonl")
        record   = {
            "timestamp":           datetime.datetime.utcnow().isoformat() + "Z",
            "fused_event_count":   len(result.get("fused_timeline", [])),
            "conflict_count":      len(result.get("conflicts", [])),
            "no_signal_scene_count": len(result.get("scenes_with_no_signal", [])),
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        log.debug("Audit log written: %s", log_path)
    except Exception as exc:
        log.warning("Audit log write failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fuse_timeline(
    scenes:      List[dict],
    perception:  List[dict],
    asr:         List[dict],
    diarization: List[dict],
    ocr:         List[dict],
) -> dict:
    """
    Step 13 entry point: merge four source agent outputs into a fused timeline.

    Parameters
    ----------
    scenes      : Step 7 scene list [{scene_id, start_seconds, end_seconds}].
    perception  : Step 8 events (objects/faces/actions).
    asr         : Step 9 events (transcript words/segments).
    diarization : Step 10 events (speaker windows).
    ocr         : Step 11 events (on-screen text).

    Returns
    -------
    {
      "fused_timeline":        [...],   # Rule 1 + 2 + 4 + 5
      "conflicts":             [...],   # Rule 3
      "scenes_with_no_signal": [...],   # Rule 5
    }

    Rules applied
    -------------
    Rule 1 -- Timeline construction (sorted, scene-keyed).
    Rule 2 -- Speaker-transcript alignment (split at speaker boundaries).
    Rule 3 -- Conflict detection (>50% overlap, different sources).
    Rule 4 -- Confidence = min when combining; original when single-source.
    Rule 5 -- no_signal placeholder for every empty scene.
    Rule 6 -- Deterministic output: explicit sort everywhere.
    """
    # Rule 6: sort scenes explicitly before use
    sorted_scenes = _sort_scenes(scenes)

    # Rule 2: align ASR to diarization speakers
    aligned_asr = _align_asr_to_diarization(asr, diarization)

    # Tag each event with its canonical source name (in case caller omits it)
    def _tag(events: List[dict], source: str) -> List[dict]:
        out = []
        for ev in events:
            e = dict(ev)
            if "source" not in e:
                e["source"] = source
            out.append(e)
        return out

    tagged_perception  = _tag(perception,  SOURCE_PERCEPTION)
    tagged_asr         = _tag(aligned_asr, SOURCE_ASR)
    tagged_diarization = _tag(diarization, SOURCE_DIARIZATION)
    tagged_ocr         = _tag(ocr,         SOURCE_OCR)

    # All source events combined
    all_events = (
        tagged_perception
        + tagged_asr
        + tagged_diarization
        + tagged_ocr
    )

    # Rule 1: build sorted, scene-keyed fused timeline
    fused_timeline = _build_timeline(all_events, sorted_scenes)

    # Rule 3: detect conflicts BEFORE injecting no_signal placeholders
    # (placeholders have source_agent=None and are excluded from conflict checks)
    conflicts = _detect_conflicts(fused_timeline, sorted_scenes)

    # Rule 5: inject no_signal placeholders for empty scenes
    fused_timeline, no_signal_ids = _inject_no_signal_placeholders(
        fused_timeline, sorted_scenes
    )

    result = {
        "fused_timeline":        fused_timeline,
        "conflicts":             conflicts,
        "scenes_with_no_signal": no_signal_ids,
    }

    log.info(
        "Fusion complete: events=%d conflicts=%d no_signal_scenes=%d",
        len(fused_timeline), len(conflicts), len(no_signal_ids),
    )

    _write_audit_log(result)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Step 13 -- Fusion Agent: merges perception, ASR, diarization, OCR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python fusion_agent.py --scenes scenes.json --perception p.json \\\n"
            "      --asr a.json --diarization d.json --ocr o.json --pretty\n"
        ),
    )
    p.add_argument("--scenes",      required=True, metavar="JSON",
                   help="Path to Step 7 scenes JSON file.")
    p.add_argument("--perception",  required=True, metavar="JSON",
                   help="Path to Step 8 perception events JSON file.")
    p.add_argument("--asr",         required=True, metavar="JSON",
                   help="Path to Step 9 ASR events JSON file.")
    p.add_argument("--diarization", required=True, metavar="JSON",
                   help="Path to Step 10 diarization events JSON file.")
    p.add_argument("--ocr",         required=True, metavar="JSON",
                   help="Path to Step 11 OCR events JSON file.")
    p.add_argument("--pretty",      action="store_true",
                   help="Pretty-print output JSON.")
    return p


def _load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


if __name__ == "__main__":
    parser = _build_cli_parser()
    args   = parser.parse_args()

    result = fuse_timeline(
        scenes      = _load_json(args.scenes),
        perception  = _load_json(args.perception),
        asr         = _load_json(args.asr),
        diarization = _load_json(args.diarization),
        ocr         = _load_json(args.ocr),
    )
    print(json.dumps(result, indent=2 if args.pretty else None))
    sys.exit(0)

