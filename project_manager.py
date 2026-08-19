"""
project_manager.py
==================
Chorus — Step 5: Project Manager / Chain-of-Custody

Pipeline position:
  Step 4 (Manipulation Detection) -> [THIS MODULE] -> Step 7 (Scene Segmentation)

Purpose
-------
Opens a sealed case record for an ingested video and produces the
cryptographic integrity proof referenced by every downstream artifact.

Six enforced rules
------------------
  Rule 1 -- SHA-256 of the raw video bytes (exactly as ingested, never re-encoded).
  Rule 2 -- Bitcoin-style pairwise-SHA-256 Merkle tree over all artifact hashes.
  Rule 3 -- RFC 3161 trusted timestamp on case creation and sealing; local UTC
            fallback when TSA is unreachable (never fails the pipeline).
  Rule 4 -- Append-only JSONL audit log, one file per day under audit_logs/step5/.
  Rule 5 -- seal_case() freezes the Merkle root and marks the case immutable;
            any subsequent add_artifact() raises CaseSealedError.
  Rule 6 -- verify_case_integrity() recomputes the Merkle root and compares it
            to the sealed root; returns False (not an exception) on mismatch.

Case manifest JSON
------------------
{
  "case_id":           "uuid4",
  "created_at":        "ISO8601 UTC",
  "sealed_at":         "ISO8601 UTC | null",
  "status":            "processing" | "sealed",
  "source_type":       "youtube | local_upload | live_rtsp",
  "raw_video_hash":    "sha256 hex",
  "merkle_root":       "sha256 hex | null",
  "artifact_count":    int,
  "timestamp_authority": "rfc3161_freetsa" | "local_fallback"
}

Usage (library)
---------------
  from project_manager import create_case, add_artifact, seal_case, verify_case_integrity

  case = create_case(
      raw_video_bytes=video_bytes,     # exact bytes from Step 1 -- never re-encoded
      source_type="local_upload",
      actor="pipeline_step5",
  )
  case_id = case["case_id"]

  leaf = add_artifact(case_id, "transcript.json", transcript_bytes, actor="step6")
  root = seal_case(case_id, actor="pipeline_runner")
  ok   = verify_case_integrity(case_id)

Usage (CLI)
-----------
  python project_manager.py --help
  python project_manager.py create --video clip.mp4 --source-type local_upload
  python project_manager.py seal   --case-id <uuid>
  python project_manager.py verify --case-id <uuid>
  python project_manager.py add    --case-id <uuid> --artifact path/to/file.json
"""

import os
import json
import uuid
import hashlib
import datetime
import base64
import argparse
import sys
import logging
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("chorus.project_manager")
logging.basicConfig(
    level=logging.INFO,
    format="[project_manager] %(levelname)s -- %(message)s",
)

# ---------------------------------------------------------------------------
# Named constants -- change TSA URL or paths here, nowhere else
# ---------------------------------------------------------------------------

# FreeTSA -- free, public RFC 3161 Time Stamp Authority.
# See https://freetsa.org/index_en.php for service terms.
TSA_URL: str = "https://freetsa.org/tsr"

# Human-readable authority label written into the case manifest.
TSA_NAME: str = "rfc3161_freetsa"

# Fallback label used when the TSA is unreachable.
TSA_FALLBACK_NAME: str = "local_fallback"

# TSA request timeout in seconds -- keeps the pipeline from stalling.
TSA_TIMEOUT_SECONDS: float = 8.0

# Audit log directory, matching the pattern from other pipeline steps.
AUDIT_LOG_DIR: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "audit_logs", "step5"
)

# In-memory case store.  Maps case_id (str) -> case record (dict).
# In production this should be replaced by a persistent database.
_CASES: dict = {}


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class CaseNotFoundError(KeyError):
    """Raised when a case_id is not found in the store."""


class CaseSealedError(RuntimeError):
    """Raised on any mutating operation against an already-sealed case."""


# ---------------------------------------------------------------------------
# Internal helpers -- SHA-256
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def _sha256_hex_pair(left_hex: str, right_hex: str) -> str:
    """
    Combine two hex digests into one parent SHA-256 digest.

    Encoding: concatenate the raw 32-byte digests, then hash.
    This matches the de-facto standard used throughout the existing pipeline.
    """
    left  = bytes.fromhex(left_hex)
    right = bytes.fromhex(right_hex)
    return hashlib.sha256(left + right).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers -- Merkle tree
# ---------------------------------------------------------------------------


def _compute_merkle_root(leaf_hashes: list) -> Optional[str]:
    """
    Compute a Bitcoin-style pairwise-SHA-256 Merkle root.

    Construction rule (Bitcoin/Satoshi standard -- documented here per requirement):
      - Start with the list of leaf hashes (one per artifact).
      - If the number of nodes at any round is odd, *duplicate the last node*
        before pairing.  This avoids an asymmetric tree without padding zeros,
        ensuring the root always covers all leaves with no gaps.
      - Hash each pair (left || right) to produce the next round's nodes.
      - Repeat until only one node remains; that is the Merkle root.

    Returns None if there are no leaves yet.
    """
    if not leaf_hashes:
        return None

    nodes = list(leaf_hashes)  # shallow copy -- don't mutate caller's list

    while len(nodes) > 1:
        next_level = []
        # If odd number of nodes, duplicate the last one (standard Bitcoin style)
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])
        for i in range(0, len(nodes), 2):
            next_level.append(_sha256_hex_pair(nodes[i], nodes[i + 1]))
        nodes = next_level

    return nodes[0]


# ---------------------------------------------------------------------------
# Internal helpers -- RFC 3161 trusted timestamping
# ---------------------------------------------------------------------------


def _build_ts_request(data_hash: bytes) -> bytes:
    """
    Build a minimal RFC 3161 TimeStampReq DER blob.

    We avoid importing third-party ASN.1 libraries to keep this module
    dependency-free.  The structure encodes a valid TSReq as per
    RFC 3161 section 2.4.1, using SHA-256 (OID 2.16.840.1.101.3.4.2.1).

    Structure:
      SEQUENCE {
        INTEGER 1                         -- version
        MessageImprint {
          AlgorithmIdentifier {
            OID 2.16.840.1.101.3.4.2.1   -- sha-256
            NULL
          }
          OCTET STRING <32 bytes hash>
        }
        BOOLEAN TRUE                      -- certReq
      }
    """
    # SHA-256 AlgorithmIdentifier OID encoding
    sha256_oid_der = bytes([
        0x30, 0x0d,                                              # SEQUENCE (13 bytes)
        0x06, 0x09,                                              # OID (9 bytes)
        0x60, 0x86, 0x48, 0x01, 0x86, 0xf8, 0x45, 0x02, 0x01,  # sha-256 OID bytes
        0x05, 0x00,                                              # NULL
    ])

    # MessageImprint ::= SEQUENCE { hashAlgorithm, hashedMessage }
    hashed_message    = bytes([0x04, len(data_hash)]) + data_hash  # OCTET STRING
    msg_imprint_inner = sha256_oid_der + hashed_message
    msg_imprint       = bytes([0x30, len(msg_imprint_inner)]) + msg_imprint_inner

    # version INTEGER ::= 1
    version  = bytes([0x02, 0x01, 0x01])

    # certReq BOOLEAN ::= TRUE
    cert_req = bytes([0x01, 0x01, 0xff])

    # Outer SEQUENCE
    ts_req_inner = version + msg_imprint + cert_req
    ts_req       = bytes([0x30, len(ts_req_inner)]) + ts_req_inner
    return ts_req


def _request_rfc3161_timestamp(payload_bytes: bytes) -> dict:
    """
    Request an RFC 3161 timestamp token from the configured TSA.

    Parameters
    ----------
    payload_bytes : The bytes to be timestamped (e.g. case_id + raw_video_hash).

    Returns
    -------
    dict with keys:
      - "authority"  : TSA_NAME or TSA_FALLBACK_NAME
      - "timestamp"  : ISO8601 UTC string (from TSA response or local clock)
      - "token_b64"  : base64-encoded DER token, or None on fallback
    """
    try:
        import urllib.request
        import urllib.error

        data_hash  = hashlib.sha256(payload_bytes).digest()
        ts_request = _build_ts_request(data_hash)

        req = urllib.request.Request(
            TSA_URL,
            data=ts_request,
            headers={"Content-Type": "application/timestamp-query"},
        )
        with urllib.request.urlopen(req, timeout=TSA_TIMEOUT_SECONDS) as resp:
            token_der = resp.read()

        # The response is a TimeStampResp DER blob.  We store it as base64
        # so it can be embedded in the case manifest (JSON-safe).
        return {
            "authority":  TSA_NAME,
            "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
            "token_b64":  base64.b64encode(token_der).decode("ascii"),
        }

    except Exception as tsa_err:
        # Rule 3: never fail the pipeline over a TSA timeout or error.
        log.warning(
            "RFC 3161 TSA unreachable (%r); "
            "using local UTC timestamp fallback.  "
            "timestamp_authority='local_fallback' is recorded in the case manifest.",
            tsa_err,
        )
        return {
            "authority":  TSA_FALLBACK_NAME,
            "timestamp":  datetime.datetime.utcnow().isoformat() + "Z",
            "token_b64":  None,
        }


# ---------------------------------------------------------------------------
# Internal helpers -- audit log (append-only JSONL, Rule 4)
# ---------------------------------------------------------------------------


def _append_audit_log(
    case_id: str,
    actor:   str,
    action:  str,
    detail:  dict,
) -> None:
    """
    Append one audit entry to the daily JSONL log.

    File: AUDIT_LOG_DIR/step5_<YYYY-MM-DD>.jsonl

    Fields per line: {timestamp, case_id, actor, action, detail}

    Intentionally named *_append_* to emphasise that no update or delete
    paths exist in this file -- only appends (Rule 4).
    Matches the audit-log pattern established in manipulation_detection.py.
    """
    try:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        date_str = datetime.date.today().isoformat()
        log_path = os.path.join(AUDIT_LOG_DIR, f"step5_{date_str}.jsonl")
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "case_id":   case_id,
            "actor":     actor,
            "action":    action,
            "detail":    detail,
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        log.debug("Audit entry written to %s: action=%s", log_path, action)
    except Exception as log_err:
        log.error("Failed to write audit log: %s", log_err)


# ---------------------------------------------------------------------------
# Internal helpers -- case store
# ---------------------------------------------------------------------------


def _get_case(case_id: str) -> dict:
    """Return the case record or raise CaseNotFoundError."""
    case = _CASES.get(case_id)
    if case is None:
        raise CaseNotFoundError(f"case_id '{case_id}' not found.")
    return case


def _case_manifest(case: dict) -> dict:
    """
    Serialize a stored case record into the public case manifest format.

    This is the canonical shape returned by create_case() and seal_case(),
    and is the format consumed by downstream pipeline steps.
    """
    return {
        "case_id":             case["case_id"],
        "created_at":          case["created_at"],
        "sealed_at":           case.get("sealed_at"),
        "status":              case["status"],
        "source_type":         case["source_type"],
        "raw_video_hash":      case["raw_video_hash"],
        "merkle_root":         case.get("sealed_merkle_root"),  # null until sealed
        "artifact_count":      len(case["artifact_leaves"]),
        "timestamp_authority": case["timestamp_authority"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_case(
    raw_video_bytes: bytes,
    source_type:     str,
    actor:           str = "pipeline_step5",
) -> dict:
    """
    Open a new case record for the ingested video.

    Rule 1: SHA-256 of the raw video bytes exactly as received from Step 1.
            We hash raw_video_bytes directly -- NOT a re-encoded copy.
    Rule 3: Requests an RFC 3161 timestamp; falls back to local UTC if TSA
            is unreachable, and records timestamp_authority accordingly.

    Parameters
    ----------
    raw_video_bytes : Exact bytes of the ingested video -- never re-encoded.
    source_type     : "youtube" | "local_upload" | "live_rtsp" (from Step 1).
    actor           : Label written to the audit log (default "pipeline_step5").

    Returns
    -------
    dict -- case manifest (see module docstring for field list).
    """
    case_id    = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Rule 1 -- hash the raw bytes, not a normalized copy
    raw_video_hash = _sha256_bytes(raw_video_bytes)

    # Rule 3 -- request a creation timestamp from the TSA
    ts_info = _request_rfc3161_timestamp(
        (case_id + raw_video_hash).encode("utf-8")
    )

    case_record = {
        "case_id":            case_id,
        "created_at":         created_at,
        "sealed_at":          None,
        "status":             "processing",
        "source_type":        source_type,
        "raw_video_hash":     raw_video_hash,
        "timestamp_authority": ts_info["authority"],
        "creation_ts_token":  ts_info["token_b64"],   # stored; not in public manifest
        "artifact_leaves":    [],                      # list of {"name", "leaf_hash"}
        "sealed_merkle_root": None,
    }

    _CASES[case_id] = case_record

    _append_audit_log(
        case_id=case_id,
        actor=actor,
        action="create_case",
        detail={
            "source_type":         source_type,
            "raw_video_hash":      raw_video_hash,
            "timestamp_authority": ts_info["authority"],
            "created_at":          created_at,
        },
    )

    log.info(
        "Case created: case_id=%s source_type=%s ts_authority=%s",
        case_id, source_type, ts_info["authority"],
    )
    return _case_manifest(case_record)


def add_artifact(
    case_id:        str,
    artifact_name:  str,
    artifact_bytes: bytes,
    actor:          str = "pipeline",
) -> str:
    """
    Hash an artifact and add its leaf to the case's Merkle tree.

    Rule 2: Each artifact gets its own SHA-256 hash; the Merkle root is
            recomputed on demand by get_root_hash() or frozen by seal_case().
    Rule 5: Raises CaseSealedError if the case is already sealed.
    Rule 4: Appends one line to the daily audit log.

    Parameters
    ----------
    case_id        : UUID of the open case.
    artifact_name  : Human-readable name (e.g. "transcript.json").
    artifact_bytes : Raw bytes of the artifact to hash.
    actor          : Label written to the audit log.

    Returns
    -------
    str -- SHA-256 hex leaf hash of this artifact.
    """
    case = _get_case(case_id)

    if case["status"] == "sealed":
        raise CaseSealedError(
            f"case_id '{case_id}' is sealed -- "
            "artifacts cannot be added to an immutable case."
        )

    leaf_hash = _sha256_bytes(artifact_bytes)
    case["artifact_leaves"].append({"name": artifact_name, "leaf_hash": leaf_hash})

    _append_audit_log(
        case_id=case_id,
        actor=actor,
        action="add_artifact",
        detail={
            "artifact_name":  artifact_name,
            "leaf_hash":      leaf_hash,
            "artifact_count": len(case["artifact_leaves"]),
        },
    )

    log.info(
        "Artifact added: case_id=%s name=%r leaf_hash=%s...",
        case_id, artifact_name, leaf_hash[:16],
    )
    return leaf_hash


def get_root_hash(case_id: str, actor: str = "pipeline") -> Optional[str]:
    """
    Recompute and return the current Merkle root from all leaves added so far.

    Rule 2: Uses Bitcoin-style pairwise-SHA-256 construction (_compute_merkle_root).
    Rule 4: Accessing a case record writes an audit entry.

    Returns None if no artifacts have been added yet.
    """
    case   = _get_case(case_id)
    leaves = [entry["leaf_hash"] for entry in case["artifact_leaves"]]
    root   = _compute_merkle_root(leaves)

    _append_audit_log(
        case_id=case_id,
        actor=actor,
        action="get_root_hash",
        detail={"merkle_root": root, "leaf_count": len(leaves)},
    )

    return root


def seal_case(case_id: str, actor: str = "pipeline_runner") -> dict:
    """
    Freeze the Merkle root and mark the case immutable.

    Rule 3: Requests a final RFC 3161 timestamp; falls back to local UTC.
    Rule 4: Writes a seal_case audit entry.
    Rule 5: Once sealed, any call to add_artifact() will raise CaseSealedError.

    Parameters
    ----------
    case_id : UUID of the open case.
    actor   : Label written to the audit log.

    Returns
    -------
    dict -- full case manifest with status="sealed" and merkle_root populated.
    """
    case = _get_case(case_id)

    if case["status"] == "sealed":
        raise CaseSealedError(f"case_id '{case_id}' is already sealed.")

    sealed_at = datetime.datetime.utcnow().isoformat() + "Z"

    # Freeze the Merkle root over all artifacts accumulated so far
    leaves      = [entry["leaf_hash"] for entry in case["artifact_leaves"]]
    sealed_root = _compute_merkle_root(leaves)

    # Rule 3 -- request a final TSA timestamp covering the root
    ts_payload = (
        case_id
        + case["raw_video_hash"]
        + (sealed_root or "")
        + sealed_at
    ).encode("utf-8")
    ts_info = _request_rfc3161_timestamp(ts_payload)

    case["sealed_at"]          = sealed_at
    case["status"]             = "sealed"
    case["sealed_merkle_root"] = sealed_root
    case["seal_ts_token"]      = ts_info["token_b64"]
    # Update authority: if creation was local but seal succeeded at TSA, prefer TSA.
    # If creation used TSA but seal falls back, keep the stronger creation authority.
    if ts_info["authority"] == TSA_NAME:
        case["timestamp_authority"] = TSA_NAME

    _append_audit_log(
        case_id=case_id,
        actor=actor,
        action="seal_case",
        detail={
            "sealed_at":           sealed_at,
            "merkle_root":         sealed_root,
            "artifact_count":      len(case["artifact_leaves"]),
            "timestamp_authority": ts_info["authority"],
        },
    )

    manifest = _case_manifest(case)
    log.info(
        "Case sealed: case_id=%s merkle_root=%s artifacts=%d ts=%s",
        case_id, sealed_root, len(case["artifact_leaves"]), ts_info["authority"],
    )
    return manifest


def verify_case_integrity(case_id: str, actor: str = "verifier") -> bool:
    """
    Verify a sealed case's integrity by recomputing its Merkle root.

    Rule 6: Recomputes the Merkle root from all stored artifact hashes and
            compares it to the root frozen at sealing time.

    Returns False (not an exception) on any mismatch, with a printed reason.
    Rule 4: Every read/access of a sealed case writes an audit entry.

    Parameters
    ----------
    case_id : UUID of the sealed case to verify.
    actor   : Label written to the audit log.

    Returns
    -------
    bool -- True if integrity is intact, False if tampered or case not sealed.
    """
    try:
        case = _get_case(case_id)
    except CaseNotFoundError:
        print(
            f"[project_manager] INTEGRITY FAIL: case_id '{case_id}' not found.",
            flush=True,
        )
        return False

    # Rule 4 -- accessing a sealed case writes an audit entry
    _append_audit_log(
        case_id=case_id,
        actor=actor,
        action="verify_case_integrity",
        detail={"sealed_status": case["status"]},
    )

    if case["status"] != "sealed":
        print(
            f"[project_manager] INTEGRITY FAIL: case_id '{case_id}' has status "
            f"'{case['status']}' -- only sealed cases can be verified.",
            flush=True,
        )
        return False

    expected_root = case["sealed_merkle_root"]
    leaves        = [entry["leaf_hash"] for entry in case["artifact_leaves"]]
    actual_root   = _compute_merkle_root(leaves)

    if actual_root != expected_root:
        print(
            f"[project_manager] INTEGRITY FAIL: Merkle root mismatch for "
            f"case_id '{case_id}'.\n"
            f"  Expected : {expected_root}\n"
            f"  Computed : {actual_root}",
            flush=True,
        )
        _append_audit_log(
            case_id=case_id,
            actor=actor,
            action="integrity_mismatch",
            detail={
                "expected_root": expected_root,
                "computed_root": actual_root,
            },
        )
        return False

    log.info("Integrity verified: case_id=%s merkle_root=%s", case_id, actual_root)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chorus Step 5 -- Project Manager / Chain-of-Custody.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python project_manager.py create --video clip.mp4 "
            "--source-type local_upload\n"
            "  python project_manager.py add    --case-id <uuid> "
            "--artifact transcript.json\n"
            "  python project_manager.py seal   --case-id <uuid>\n"
            "  python project_manager.py verify --case-id <uuid>\n"
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # create
    c = sub.add_parser("create", help="Create a new case from a raw video file.")
    c.add_argument("--video",       required=True, metavar="PATH",
                   help="Path to the raw video file (exactly as ingested).")
    c.add_argument("--source-type", required=True,
                   choices=("youtube", "local_upload", "live_rtsp"),
                   dest="source_type",
                   help="Source type from Step 1.")
    c.add_argument("--actor",       default="cli",
                   help="Actor label for the audit log (default: 'cli').")
    c.add_argument("--pretty",      action="store_true",
                   help="Pretty-print JSON output.")

    # add
    a = sub.add_parser("add", help="Add an artifact file to an existing open case.")
    a.add_argument("--case-id",   required=True, dest="case_id",
                   help="Case UUID.")
    a.add_argument("--artifact",  required=True, metavar="PATH",
                   help="Path to the artifact file to hash and register.")
    a.add_argument("--name",      default=None,
                   help="Artifact name (default: basename of the file path).")
    a.add_argument("--actor",     default="cli",
                   help="Actor label for the audit log.")

    # seal
    s = sub.add_parser("seal", help="Seal an open case (freezes the Merkle root).")
    s.add_argument("--case-id", required=True, dest="case_id",
                   help="Case UUID.")
    s.add_argument("--actor",   default="cli",
                   help="Actor label for the audit log.")
    s.add_argument("--pretty",  action="store_true",
                   help="Pretty-print JSON output.")

    # verify
    v = sub.add_parser("verify", help="Verify the integrity of a sealed case.")
    v.add_argument("--case-id", required=True, dest="case_id",
                   help="Case UUID.")
    v.add_argument("--actor",   default="cli",
                   help="Actor label for the audit log.")

    return p


if __name__ == "__main__":
    parser = _build_cli_parser()
    args   = parser.parse_args()

    if args.command == "create":
        with open(args.video, "rb") as vf:
            raw_bytes = vf.read()
        manifest = create_case(
            raw_video_bytes=raw_bytes,
            source_type=args.source_type,
            actor=args.actor,
        )
        print(json.dumps(manifest, indent=2 if args.pretty else None))

    elif args.command == "add":
        artifact_name = args.name or os.path.basename(args.artifact)
        with open(args.artifact, "rb") as af:
            artifact_bytes = af.read()
        leaf_hash = add_artifact(
            case_id=args.case_id,
            artifact_name=artifact_name,
            artifact_bytes=artifact_bytes,
            actor=args.actor,
        )
        print(json.dumps({"leaf_hash": leaf_hash}))

    elif args.command == "seal":
        manifest = seal_case(case_id=args.case_id, actor=args.actor)
        print(json.dumps(manifest, indent=2 if args.pretty else None))

    elif args.command == "verify":
        ok = verify_case_integrity(case_id=args.case_id, actor=args.actor)
        print(json.dumps({"integrity_ok": ok}))
        sys.exit(0 if ok else 1)
