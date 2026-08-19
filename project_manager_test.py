"""
project_manager_test.py
=======================
Chorus -- Step 5: Project Manager Unit Tests

Follows the exact pattern of test_manipulation_detection.py:
  - Pure unittest, no ML/LLM/GPU dependencies
  - Mock TSA calls so tests run offline and deterministically
  - Covers: case creation, artifact hashing, Merkle tree correctness,
    audit log writes, sealing, immutability, integrity verification,
    and tamper detection.

Run:
    python project_manager_test.py
    python -m pytest project_manager_test.py -v
"""

import json
import os
import hashlib
import unittest
import datetime
from unittest.mock import patch, MagicMock

import project_manager as pm
from project_manager import (
    # Public API
    create_case,
    add_artifact,
    get_root_hash,
    seal_case,
    verify_case_integrity,
    # Internal helpers exposed for unit testing
    _sha256_bytes,
    _sha256_hex_pair,
    _compute_merkle_root,
    _build_ts_request,
    _request_rfc3161_timestamp,
    _case_manifest,
    _get_case,
    # Exceptions
    CaseNotFoundError,
    CaseSealedError,
    # Constants
    TSA_NAME,
    TSA_FALLBACK_NAME,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Deterministic fake TSA response used by all patched calls in these tests.
_FAKE_TSA_RESPONSE = {
    "authority":  TSA_NAME,
    "timestamp":  "2026-01-01T00:00:00Z",
    "token_b64":  "AAEC",   # minimal base64 placeholder
}

_FAKE_FALLBACK_RESPONSE = {
    "authority":  TSA_FALLBACK_NAME,
    "timestamp":  "2026-01-01T00:00:00Z",
    "token_b64":  None,
}


def _make_video_bytes(content: str = "fake_raw_video_bytes") -> bytes:
    """Return deterministic fake video bytes for testing."""
    return content.encode("utf-8")


def _make_artifact_bytes(tag: str) -> bytes:
    return f"artifact_content_{tag}".encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Before each test: clear the in-memory case store so tests are independent.
# ---------------------------------------------------------------------------

class _ClearCasesBase(unittest.TestCase):
    """Base class that resets _CASES before each test."""

    def setUp(self):
        pm._CASES.clear()


# ---------------------------------------------------------------------------
# Test 1: Case creation
# ---------------------------------------------------------------------------

class TestCaseCreation(_ClearCasesBase):
    """Test 1: create_case() produces a valid, correctly populated manifest."""

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_manifest_fields_present(self, mock_audit, mock_ts):
        """All required manifest fields must be present and correctly typed."""
        raw = _make_video_bytes()
        manifest = create_case(raw, source_type="local_upload", actor="test")

        required = {
            "case_id", "created_at", "sealed_at", "status", "source_type",
            "raw_video_hash", "merkle_root", "artifact_count", "timestamp_authority",
        }
        self.assertTrue(required.issubset(set(manifest.keys())))

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_initial_status_is_processing(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "youtube", actor="test")
        self.assertEqual(manifest["status"], "processing")

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_sealed_at_is_null_before_sealing(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload", actor="test")
        self.assertIsNone(manifest["sealed_at"])

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_merkle_root_is_null_before_artifacts(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload", actor="test")
        self.assertIsNone(manifest["merkle_root"])

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_artifact_count_zero_on_creation(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "live_rtsp", actor="test")
        self.assertEqual(manifest["artifact_count"], 0)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_source_type_stored_correctly(self, mock_audit, mock_ts):
        for st in ("youtube", "local_upload", "live_rtsp"):
            pm._CASES.clear()
            manifest = create_case(_make_video_bytes(), st, actor="test")
            self.assertEqual(manifest["source_type"], st)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_two_cases_get_different_ids(self, mock_audit, mock_ts):
        m1 = create_case(_make_video_bytes("a"), "youtube")
        m2 = create_case(_make_video_bytes("b"), "youtube")
        self.assertNotEqual(m1["case_id"], m2["case_id"])

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_audit_log_called_on_create(self, mock_audit, mock_ts):
        create_case(_make_video_bytes(), "local_upload", actor="test_actor")
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        # action must be "create_case"
        self.assertEqual(call_kwargs[1]["action"], "create_case")
        self.assertEqual(call_kwargs[1]["actor"], "test_actor")


# ---------------------------------------------------------------------------
# Test 2: Raw-video SHA-256 (Rule 1)
# ---------------------------------------------------------------------------

class TestRawVideoHashing(_ClearCasesBase):
    """Test 2: SHA-256 must be computed on the exact raw bytes."""

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_raw_video_hash_matches_direct_sha256(self, mock_audit, mock_ts):
        """Rule 1: raw_video_hash must equal SHA-256 of exactly the supplied bytes."""
        raw = b"\x00\x01\x02\x03\xFF" * 1000  # binary content
        manifest = create_case(raw, "local_upload")
        expected = _sha256(raw)
        self.assertEqual(manifest["raw_video_hash"], expected)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_different_bytes_produce_different_hash(self, mock_audit, mock_ts):
        raw_a = _make_video_bytes("video_a")
        raw_b = _make_video_bytes("video_b")
        m_a = create_case(raw_a, "local_upload")
        m_b = create_case(raw_b, "local_upload")
        self.assertNotEqual(m_a["raw_video_hash"], m_b["raw_video_hash"])

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_hash_is_64_char_hex(self, mock_audit, mock_ts):
        manifest = create_case(b"hello", "youtube")
        h = manifest["raw_video_hash"]
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


# ---------------------------------------------------------------------------
# Test 3: Merkle tree — add artifacts, get_root_hash, verify construction
# ---------------------------------------------------------------------------

class TestMerkleTree(_ClearCasesBase):
    """Test 3: Merkle tree construction, add_artifact, and get_root_hash."""

    def _create(self):
        with patch("project_manager._request_rfc3161_timestamp",
                   return_value=_FAKE_TSA_RESPONSE), \
             patch("project_manager._append_audit_log"):
            return create_case(_make_video_bytes(), "local_upload")

    def test_single_leaf_root_equals_leaf_hash(self):
        """With 1 artifact, Merkle root == that artifact's leaf hash."""
        manifest = self._create()
        cid = manifest["case_id"]

        a_bytes = _make_artifact_bytes("A")
        with patch("project_manager._append_audit_log"):
            leaf = add_artifact(cid, "a.json", a_bytes)

        # Single leaf: root == leaf (no pairing needed)
        with patch("project_manager._append_audit_log"):
            root = get_root_hash(cid)

        self.assertEqual(root, _sha256(a_bytes))
        self.assertEqual(root, leaf)

    def test_two_leaves_root_equals_hash_of_pair(self):
        """With 2 artifacts, root == SHA-256(leaf_a || leaf_b)."""
        manifest = self._create()
        cid = manifest["case_id"]

        a_bytes = _make_artifact_bytes("A")
        b_bytes = _make_artifact_bytes("B")
        with patch("project_manager._append_audit_log"):
            leaf_a = add_artifact(cid, "a.json", a_bytes)
            leaf_b = add_artifact(cid, "b.json", b_bytes)

        with patch("project_manager._append_audit_log"):
            root = get_root_hash(cid)

        expected = _sha256_hex_pair(leaf_a, leaf_b)
        self.assertEqual(root, expected)

    def test_odd_leaves_duplicates_last_bitcoin_style(self):
        """
        With 3 leaves [A, B, C], Bitcoin-style construction pads to [A,B,C,C],
        producing root = SHA256(SHA256(A||B) || SHA256(C||C)).
        """
        manifest = self._create()
        cid = manifest["case_id"]

        leaves = []
        with patch("project_manager._append_audit_log"):
            for tag in ("A", "B", "C"):
                bts = _make_artifact_bytes(tag)
                leaves.append(add_artifact(cid, f"{tag}.json", bts))

        with patch("project_manager._append_audit_log"):
            root = get_root_hash(cid)

        # Expected: round 1 -> [SHA256(A||B), SHA256(C||C)], round 2 -> root
        ab   = _sha256_hex_pair(leaves[0], leaves[1])
        cc   = _sha256_hex_pair(leaves[2], leaves[2])
        expected = _sha256_hex_pair(ab, cc)
        self.assertEqual(root, expected)

    def test_four_leaves_correct_root(self):
        """With 4 leaves [A,B,C,D]: root = SHA256(SHA256(A||B) || SHA256(C||D))."""
        manifest = self._create()
        cid = manifest["case_id"]

        leaves = []
        with patch("project_manager._append_audit_log"):
            for tag in ("A", "B", "C", "D"):
                bts = _make_artifact_bytes(tag)
                leaves.append(add_artifact(cid, f"{tag}.json", bts))

        with patch("project_manager._append_audit_log"):
            root = get_root_hash(cid)

        ab = _sha256_hex_pair(leaves[0], leaves[1])
        cd = _sha256_hex_pair(leaves[2], leaves[3])
        expected = _sha256_hex_pair(ab, cd)
        self.assertEqual(root, expected)

    def test_get_root_hash_none_with_no_artifacts(self):
        """Merkle root must be None when no artifacts have been added."""
        manifest = self._create()
        cid = manifest["case_id"]
        with patch("project_manager._append_audit_log"):
            root = get_root_hash(cid)
        self.assertIsNone(root)

    def test_add_artifact_returns_correct_leaf_hash(self):
        """add_artifact return value must equal SHA-256 of the artifact bytes."""
        manifest = self._create()
        cid = manifest["case_id"]
        a_bytes = b"some artifact data"
        with patch("project_manager._append_audit_log"):
            leaf = add_artifact(cid, "x.json", a_bytes)
        self.assertEqual(leaf, _sha256(a_bytes))

    def test_artifact_count_increments(self):
        """artifact_count in the internal record increments with each add_artifact."""
        manifest = self._create()
        cid = manifest["case_id"]
        for i in range(4):
            with patch("project_manager._append_audit_log"):
                add_artifact(cid, f"art_{i}.json", _make_artifact_bytes(str(i)))
        case = pm._CASES[cid]
        self.assertEqual(len(case["artifact_leaves"]), 4)


# ---------------------------------------------------------------------------
# Test 4: TSA timestamping + local fallback (Rule 3)
# ---------------------------------------------------------------------------

class TestTimestamping(_ClearCasesBase):
    """Test 4: RFC 3161 TSA is called; local fallback is used when TSA is down."""

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_tsa_authority_stored_when_tsa_succeeds(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        self.assertEqual(manifest["timestamp_authority"], TSA_NAME)

    @patch("project_manager._request_rfc3161_timestamp",
           return_value=_FAKE_FALLBACK_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_local_fallback_authority_stored_when_tsa_down(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        self.assertEqual(manifest["timestamp_authority"], TSA_FALLBACK_NAME)

    @patch("project_manager._request_rfc3161_timestamp",
           return_value=_FAKE_FALLBACK_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_pipeline_does_not_raise_when_tsa_down(self, mock_audit, mock_ts):
        """Rule 3: TSA failure must never crash the pipeline."""
        try:
            manifest = create_case(_make_video_bytes(), "youtube")
        except Exception as e:
            self.fail(f"create_case raised unexpectedly when TSA is down: {e}")
        self.assertIsNotNone(manifest["case_id"])

    def test_request_rfc3161_falls_back_on_network_error(self):
        """
        _request_rfc3161_timestamp must return local_fallback on ANY exception,
        including network errors.
        """
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = _request_rfc3161_timestamp(b"test_payload")
        self.assertEqual(result["authority"], TSA_FALLBACK_NAME)
        self.assertIsNone(result["token_b64"])
        self.assertIn("Z", result["timestamp"])  # still an ISO8601 timestamp

    def test_build_ts_request_returns_bytes(self):
        """_build_ts_request must return a non-empty bytes object."""
        fake_hash = b"\x00" * 32
        der = _build_ts_request(fake_hash)
        self.assertIsInstance(der, bytes)
        self.assertGreater(len(der), 0)


# ---------------------------------------------------------------------------
# Test 5: Audit log (Rule 4)
# ---------------------------------------------------------------------------

class TestAuditLog(_ClearCasesBase):
    """Test 5: Verify audit log writes for all key operations."""

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_create_case_writes_audit_entry(self, mock_audit, mock_ts):
        create_case(_make_video_bytes(), "local_upload", actor="auditTest")
        mock_audit.assert_called()
        args = mock_audit.call_args[1]
        self.assertEqual(args["action"], "create_case")

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_add_artifact_writes_audit_entry(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        mock_audit.reset_mock()
        add_artifact(manifest["case_id"], "x.json", b"bytes", actor="art_actor")
        mock_audit.assert_called()
        args = mock_audit.call_args[1]
        self.assertEqual(args["action"], "add_artifact")
        self.assertEqual(args["actor"], "art_actor")

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_seal_case_writes_audit_entry(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        mock_audit.reset_mock()
        seal_case(manifest["case_id"], actor="sealer")
        # Must have been called at least once with action="seal_case"
        actions = [c[1]["action"] for c in mock_audit.call_args_list]
        self.assertIn("seal_case", actions)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_verify_writes_audit_entry(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        cid = manifest["case_id"]
        add_artifact(cid, "x.json", b"data")
        seal_case(cid)
        mock_audit.reset_mock()
        verify_case_integrity(cid, actor="inspector")
        actions = [c[1]["action"] for c in mock_audit.call_args_list]
        self.assertIn("verify_case_integrity", actions)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_get_root_hash_writes_audit_entry(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "local_upload")
        cid = manifest["case_id"]
        add_artifact(cid, "x.json", b"data")
        mock_audit.reset_mock()
        get_root_hash(cid, actor="root_reader")
        actions = [c[1]["action"] for c in mock_audit.call_args_list]
        self.assertIn("get_root_hash", actions)

    def test_audit_log_file_is_jsonl(self):
        """
        A real _append_audit_log call must create a file whose content is valid JSONL.
        """
        import tempfile
        orig_dir = pm.AUDIT_LOG_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                pm.AUDIT_LOG_DIR = tmpdir
                from project_manager import _append_audit_log
                _append_audit_log("cid_test", "pytest", "test_action", {"key": "val"})
                date_str = datetime.date.today().isoformat()
                log_path = os.path.join(tmpdir, f"step5_{date_str}.jsonl")
                self.assertTrue(os.path.exists(log_path))
                with open(log_path, "r", encoding="utf-8") as f:
                    line = f.readline()
                entry = json.loads(line)
                self.assertEqual(entry["case_id"], "cid_test")
                self.assertEqual(entry["action"], "test_action")
        finally:
            pm.AUDIT_LOG_DIR = orig_dir


# ---------------------------------------------------------------------------
# Test 6: Sealing — happy path (Rule 5)
# ---------------------------------------------------------------------------

class TestSealCase(_ClearCasesBase):
    """Test 6: seal_case() freezes the Merkle root and updates the manifest."""

    def _make_sealed_case(self, n_artifacts: int = 3):
        """
        Helper: create a case, add n_artifacts, seal it.
        Returns (case_id, manifest, artifact_leaf_hashes).
        """
        with patch("project_manager._request_rfc3161_timestamp",
                   return_value=_FAKE_TSA_RESPONSE), \
             patch("project_manager._append_audit_log"):
            manifest = create_case(_make_video_bytes(), "local_upload")
            cid = manifest["case_id"]
            leaves = []
            for i in range(n_artifacts):
                leaf = add_artifact(cid, f"art_{i}.json", _make_artifact_bytes(str(i)))
                leaves.append(leaf)
            sealed_manifest = seal_case(cid)
        return cid, sealed_manifest, leaves

    def test_status_becomes_sealed(self):
        _, manifest, _ = self._make_sealed_case()
        self.assertEqual(manifest["status"], "sealed")

    def test_sealed_at_is_populated(self):
        _, manifest, _ = self._make_sealed_case()
        self.assertIsNotNone(manifest["sealed_at"])

    def test_merkle_root_populated_after_sealing(self):
        _, manifest, _ = self._make_sealed_case()
        self.assertIsNotNone(manifest["merkle_root"])
        # Must be a valid 64-char hex string
        self.assertEqual(len(manifest["merkle_root"]), 64)

    def test_sealed_merkle_root_matches_manual_computation(self):
        """The root stored at sealing must equal _compute_merkle_root over the same leaves."""
        _, manifest, leaves = self._make_sealed_case(n_artifacts=4)
        expected = _compute_merkle_root(leaves)
        self.assertEqual(manifest["merkle_root"], expected)

    def test_artifact_count_correct_after_sealing(self):
        _, manifest, _ = self._make_sealed_case(n_artifacts=3)
        self.assertEqual(manifest["artifact_count"], 3)

    def test_sealing_already_sealed_case_raises(self):
        cid, _, _ = self._make_sealed_case()
        with self.assertRaises(CaseSealedError):
            with patch("project_manager._request_rfc3161_timestamp",
                       return_value=_FAKE_TSA_RESPONSE), \
                 patch("project_manager._append_audit_log"):
                seal_case(cid)

    def test_manifest_is_json_serializable(self):
        """Full sealed manifest must be JSON-serializable without errors."""
        _, manifest, _ = self._make_sealed_case()
        try:
            serialized = json.dumps(manifest)
        except TypeError as e:
            self.fail(f"Sealed manifest is not JSON-serializable: {e}")
        self.assertIn("sealed", serialized)


# ---------------------------------------------------------------------------
# Test 7: Immutability (Rule 5)
# ---------------------------------------------------------------------------

class TestImmutability(_ClearCasesBase):
    """Test 7: add_artifact on a sealed case must raise CaseSealedError."""

    def _make_sealed_case(self):
        with patch("project_manager._request_rfc3161_timestamp",
                   return_value=_FAKE_TSA_RESPONSE), \
             patch("project_manager._append_audit_log"):
            manifest = create_case(_make_video_bytes(), "local_upload")
            cid = manifest["case_id"]
            add_artifact(cid, "art.json", b"some data")
            seal_case(cid)
        return cid

    def test_add_artifact_after_seal_raises(self):
        """Rule 5: add_artifact on a sealed case must raise CaseSealedError."""
        cid = self._make_sealed_case()
        with self.assertRaises(CaseSealedError) as ctx:
            with patch("project_manager._append_audit_log"):
                add_artifact(cid, "new.json", b"new data")
        self.assertIn("sealed", str(ctx.exception).lower())

    def test_add_artifact_error_message_mentions_case_id(self):
        cid = self._make_sealed_case()
        with self.assertRaises(CaseSealedError) as ctx:
            with patch("project_manager._append_audit_log"):
                add_artifact(cid, "new.json", b"new data")
        self.assertIn(cid, str(ctx.exception))

    def test_add_artifact_on_unknown_case_raises_not_found(self):
        with self.assertRaises(CaseNotFoundError):
            with patch("project_manager._append_audit_log"):
                add_artifact("nonexistent-uuid", "x.json", b"data")


# ---------------------------------------------------------------------------
# Test 8: verify_case_integrity -- happy path (Rule 6)
# ---------------------------------------------------------------------------

class TestVerifyIntegrityHappyPath(_ClearCasesBase):
    """Test 8: verify_case_integrity returns True for a sealed, untampered case."""

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_verify_returns_true_for_intact_case(self, mock_audit, mock_ts):
        """
        Core happy-path test (mirrors quality_gate_test.py style):
        create case -> add 4 artifacts -> seal -> verify -> assert True.
        """
        manifest = create_case(_make_video_bytes(), "local_upload", actor="pipeline")
        cid = manifest["case_id"]

        artifact_data = [
            ("transcript.json",     b'{"text": "Hello world"}'),
            ("detected_objects.json", b'{"objects": ["car", "person"]}'),
            ("fused_timeline.json",  b'{"events": []}'),
            ("scene_segments.json",  b'{"segments": [1, 2, 3]}'),
        ]
        for name, data in artifact_data:
            add_artifact(cid, name, data, actor="step6")

        seal_case(cid, actor="pipeline_runner")
        ok = verify_case_integrity(cid, actor="verifier")
        self.assertTrue(ok)

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_verify_with_single_artifact_returns_true(self, mock_audit, mock_ts):
        manifest = create_case(_make_video_bytes(), "youtube")
        cid = manifest["case_id"]
        add_artifact(cid, "only.json", b"data")
        seal_case(cid)
        self.assertTrue(verify_case_integrity(cid))

    @patch("project_manager._request_rfc3161_timestamp", return_value=_FAKE_TSA_RESPONSE)
    @patch("project_manager._append_audit_log")
    def test_verify_with_no_artifacts_returns_true(self, mock_audit, mock_ts):
        """
        An empty artifact list is valid: Merkle root is None both at seal and verify.
        """
        manifest = create_case(_make_video_bytes(), "local_upload")
        cid = manifest["case_id"]
        seal_case(cid)
        # Both sealed_root and computed_root will be None -- no mismatch
        self.assertTrue(verify_case_integrity(cid))


# ---------------------------------------------------------------------------
# Test 9: verify_case_integrity -- tamper detection (Rule 6)
# ---------------------------------------------------------------------------

class TestVerifyIntegrityTamperDetection(_ClearCasesBase):
    """Test 9: verify_case_integrity returns False when a stored leaf is changed."""

    def _sealed_case_with_artifacts(self, n: int = 3):
        with patch("project_manager._request_rfc3161_timestamp",
                   return_value=_FAKE_TSA_RESPONSE), \
             patch("project_manager._append_audit_log"):
            manifest = create_case(_make_video_bytes(), "local_upload")
            cid = manifest["case_id"]
            for i in range(n):
                add_artifact(cid, f"art_{i}.json", _make_artifact_bytes(str(i)))
            seal_case(cid)
        return cid

    def test_tampered_leaf_hash_returns_false(self):
        """
        Directly mutate a stored leaf hash after sealing --
        verify_case_integrity must detect the mismatch and return False.
        """
        cid = self._sealed_case_with_artifacts(n=4)
        # Tamper: change the leaf_hash of the first artifact to a bogus value
        pm._CASES[cid]["artifact_leaves"][0]["leaf_hash"] = "a" * 64

        with patch("project_manager._append_audit_log"):
            ok = verify_case_integrity(cid, actor="tamper_tester")
        self.assertFalse(ok)

    def test_added_extra_leaf_after_sealing_via_direct_mutation_returns_false(self):
        """
        Directly inject a new leaf into the case store after sealing
        (simulates a database-level injection attack).
        verify_case_integrity must detect the discrepancy.
        """
        cid = self._sealed_case_with_artifacts(n=2)
        # Inject a rogue artifact leaf directly into the store
        pm._CASES[cid]["artifact_leaves"].append({
            "name": "injected.json",
            "leaf_hash": _sha256(b"injected content"),
        })
        with patch("project_manager._append_audit_log"):
            ok = verify_case_integrity(cid)
        self.assertFalse(ok)

    def test_removed_leaf_after_sealing_returns_false(self):
        """
        Removing a leaf after sealing must trigger a mismatch.
        """
        cid = self._sealed_case_with_artifacts(n=3)
        pm._CASES[cid]["artifact_leaves"].pop()  # remove last leaf

        with patch("project_manager._append_audit_log"):
            ok = verify_case_integrity(cid)
        self.assertFalse(ok)

    def test_verify_on_unsealed_case_returns_false(self):
        """verify_case_integrity on a non-sealed case must return False, not raise."""
        with patch("project_manager._request_rfc3161_timestamp",
                   return_value=_FAKE_TSA_RESPONSE), \
             patch("project_manager._append_audit_log"):
            manifest = create_case(_make_video_bytes(), "local_upload")
            cid = manifest["case_id"]

        with patch("project_manager._append_audit_log"):
            ok = verify_case_integrity(cid)
        self.assertFalse(ok)

    def test_verify_on_nonexistent_case_returns_false(self):
        """verify_case_integrity on an unknown case_id must return False, not raise."""
        with patch("project_manager._append_audit_log"):
            ok = verify_case_integrity("totally-fake-uuid")
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# Test 10: Merkle tree unit tests (pure algorithmic)
# ---------------------------------------------------------------------------

class TestMerkleTreePure(unittest.TestCase):
    """Test 10: Pure unit tests for _compute_merkle_root."""

    def test_empty_list_returns_none(self):
        self.assertIsNone(_compute_merkle_root([]))

    def test_single_leaf_returns_same_hash(self):
        leaf = _sha256(b"singleton")
        root = _compute_merkle_root([leaf])
        self.assertEqual(root, leaf)

    def test_two_leaves(self):
        a = _sha256(b"A")
        b = _sha256(b"B")
        expected = _sha256_hex_pair(a, b)
        self.assertEqual(_compute_merkle_root([a, b]), expected)

    def test_three_leaves_bitcoin_padding(self):
        a = _sha256(b"A")
        b = _sha256(b"B")
        c = _sha256(b"C")
        ab  = _sha256_hex_pair(a, b)
        cc  = _sha256_hex_pair(c, c)  # Bitcoin-style: duplicate last leaf
        expected = _sha256_hex_pair(ab, cc)
        self.assertEqual(_compute_merkle_root([a, b, c]), expected)

    def test_five_leaves(self):
        leaves = [_sha256(bytes([i])) for i in range(5)]
        # Round 1: [AB, CD, EE]
        ab = _sha256_hex_pair(leaves[0], leaves[1])
        cd = _sha256_hex_pair(leaves[2], leaves[3])
        ee = _sha256_hex_pair(leaves[4], leaves[4])
        # Round 2: [ABCD, EEEE]
        abcd = _sha256_hex_pair(ab, cd)
        eeee = _sha256_hex_pair(ee, ee)
        expected = _sha256_hex_pair(abcd, eeee)
        self.assertEqual(_compute_merkle_root(leaves), expected)

    def test_input_list_not_mutated(self):
        """_compute_merkle_root must not mutate the input list."""
        leaves = [_sha256(bytes([i])) for i in range(3)]
        original = list(leaves)
        _compute_merkle_root(leaves)
        self.assertEqual(leaves, original)

    def test_result_is_64_char_hex(self):
        leaves = [_sha256(bytes([i])) for i in range(4)]
        root = _compute_merkle_root(leaves)
        self.assertEqual(len(root), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in root))


# ---------------------------------------------------------------------------
# Test 11: Constants contract
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    """Test 11: Verify TSA constants are at their expected contract values."""

    def test_tsa_name_is_freetsa(self):
        self.assertEqual(TSA_NAME, "rfc3161_freetsa")

    def test_fallback_name_is_local_fallback(self):
        self.assertEqual(TSA_FALLBACK_NAME, "local_fallback")

    def test_tsa_url_is_https(self):
        from project_manager import TSA_URL
        self.assertTrue(TSA_URL.startswith("https://"), msg=f"TSA_URL must be HTTPS: {TSA_URL}")

    def test_tsa_timeout_is_positive(self):
        from project_manager import TSA_TIMEOUT_SECONDS
        self.assertGreater(TSA_TIMEOUT_SECONDS, 0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Chorus Step 5 -- Project Manager Unit Tests")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    for cls in [
        TestCaseCreation,
        TestRawVideoHashing,
        TestMerkleTree,
        TestTimestamping,
        TestAuditLog,
        TestSealCase,
        TestImmutability,
        TestVerifyIntegrityHappyPath,
        TestVerifyIntegrityTamperDetection,
        TestMerkleTreePure,
        TestConstants,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    exit(0 if result.wasSuccessful() else 1)
