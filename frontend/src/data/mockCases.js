/**
 * mockCases.js
 * Mock case manifests matching the project_manager.py schema exactly:
 * { case_id, created_at, sealed_at, status, source_type,
 *   raw_video_hash, merkle_root, artifact_count, timestamp_authority }
 *
 * status values: "processing" | "sealed" | "flagged"
 * source_type values: "youtube" | "local_upload" | "live_rtsp"
 * timestamp_authority: "rfc3161_freetsa" | "local_fallback"
 */

export const mockCases = [
  {
    case_id: "a3f7c012-9b4e-4d81-bcd3-0e2a7f56e831",
    created_at: "2026-09-15T08:14:22Z",
    sealed_at:  "2026-09-15T08:19:47Z",
    status: "sealed",
    source_type: "local_upload",
    raw_video_hash:
      "e3b7d94c2a1f88305d60ac5b9f7e2c4a3b8d1e06f5c7a9b2d4e6f8a0c1b3d5e7",
    merkle_root:
      "4a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
    artifact_count: 12,
    timestamp_authority: "rfc3161_freetsa",
  },
  {
    case_id: "b8e20c47-1d9f-4a3c-8e72-5f9c3d04b6a1",
    created_at: "2026-09-16T06:31:05Z",
    sealed_at:  null,
    status: "processing",
    source_type: "youtube",
    raw_video_hash:
      "9f2c4a8d1e6b3f7a0c5d2e9b4f1a7c3d8e5b2f6a9c0d4e1b7f3a5c8d2e6b0f4a",
    merkle_root: null,
    artifact_count: 5,
    timestamp_authority: "local_fallback",
  },
  {
    case_id: "d1a59f83-4c7b-4e26-a91d-3b8f0e72c145",
    created_at: "2026-09-16T11:02:48Z",
    sealed_at:  "2026-09-16T11:18:33Z",
    status: "flagged",
    source_type: "live_rtsp",
    raw_video_hash:
      "c7a2e5d9b4f1a8c3e6d0b5f2a9c4e7d1b6f3a0c8e5d2b7f4a1c9e6d3b8f5a2c0",
    merkle_root:
      "f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
    artifact_count: 18,
    timestamp_authority: "rfc3161_freetsa",
  },
];
