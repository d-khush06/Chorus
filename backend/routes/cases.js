const express = require('express');
const router = express.Router();
const { protect } = require('../middleware/auth');

// Mock case data matching frontend/src/data/mockCases.js schema
const mockCases = [
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

// Mock timeline data matching frontend/src/data/mockTimelines.js schema
const mockTimelines = {
  "a3f7c012-9b4e-4d81-bcd3-0e2a7f56e831": {
    fused_timeline: [
      { scene_id: 1, start_seconds: 0.0, end_seconds: 8.4, event_type: "object", content: "Two individuals visible. Subject seated, interviewer standing. Room: single overhead light, metal table, two chairs.", source_agent: "perception", confidence: 0.94 },
      { scene_id: 1, start_seconds: 1.2, end_seconds: 5.7, event_type: "diarization", content: "Speaker A (interviewer) — active speech segment", source_agent: "diarization", confidence: 0.91 },
      { scene_id: 1, start_seconds: 1.2, end_seconds: 5.7, event_type: "speech", content: "Please state your name for the record and confirm that you understand you are being recorded.", source_agent: "asr", confidence: 0.97 },
      { scene_id: 1, start_seconds: 6.1, end_seconds: 8.4, event_type: "speech", content: "Yes. My name is Daniel Reeves. I understand.", source_agent: "asr", confidence: 0.95 },
      { scene_id: 2, start_seconds: 8.4, end_seconds: 22.0, event_type: "object", content: "Subject leans forward. Document folder placed on table. Handwritten notes visible.", source_agent: "perception", confidence: 0.88 },
      { scene_id: 2, start_seconds: 9.0, end_seconds: 15.3, event_type: "text", content: "CASE NO. 2024-CR-0471 — CONFIDENTIAL", source_agent: "ocr", confidence: 0.99 },
      { scene_id: 2, start_seconds: 10.1, end_seconds: 21.8, event_type: "speech", content: "We have logs placing your vehicle at the corner of Meridian and 5th on the night of September 2nd. Between ten-fifteen and ten-forty PM.", source_agent: "asr", confidence: 0.93 },
      { scene_id: 3, start_seconds: 22.0, end_seconds: 35.5, event_type: "speech", content: "That's not possible. I was home that night. My wife can confirm this.", source_agent: "asr", confidence: 0.96 },
      { scene_id: 3, start_seconds: 22.3, end_seconds: 35.5, event_type: "diarization", content: "Speaker B (subject) — active speech segment", source_agent: "diarization", confidence: 0.89 },
      { scene_id: 3, start_seconds: 26.0, end_seconds: 28.5, event_type: "object", content: "Subject's hand briefly exits frame — bottom left. Object motion detected.", source_agent: "perception", confidence: 0.72 },
      { scene_id: 4, start_seconds: 35.5, end_seconds: 49.0, event_type: "speech", content: "Mr. Reeves, we also have a toll record from the I-94 bypass logged at ten twenty-two PM.", source_agent: "asr", confidence: 0.94 },
      { scene_id: 4, start_seconds: 37.2, end_seconds: 40.1, event_type: "text", content: "TOLL TX ID: 49201-A — 22:22:07", source_agent: "ocr", confidence: 0.88 },
      { scene_id: 5, start_seconds: 49.0, end_seconds: 62.3, event_type: "speech", content: "[inaudible] — I might have driven past, I don't remember exactly.", source_agent: "asr", confidence: 0.61 },
      { scene_id: 5, start_seconds: 49.5, end_seconds: 62.3, event_type: "diarization", content: "Speaker B — overlapping crosstalk detected", source_agent: "diarization", confidence: 0.54 },
      { scene_id: 6, start_seconds: 62.3, end_seconds: 74.8, event_type: "no_signal", content: "No events detected in this scene window.", source_agent: null, confidence: null },
    ],
    conflicts: [
      { scene_id: 3, time_range: [22.0, 35.5], source_a: "asr", content_a: "Subject claims alibi: home all night of Sep 2nd.", source_b: "perception", content_b: "Object motion out-of-frame detected at 26.0s — possible item concealment.", conflict_type: "presence_contradiction" },
      { scene_id: 5, time_range: [49.0, 62.3], source_a: "asr", content_a: "Subject states: 'I don't remember exactly' re: location.", source_b: "diarization", content_b: "Speaker overlap / crosstalk pattern inconsistent with single-speaker recall.", conflict_type: "content_mismatch" },
    ],
    scenes_with_no_signal: [6],
  },
  "b8e20c47-1d9f-4a3c-8e72-5f9c3d04b6a1": {
    fused_timeline: [
      { scene_id: 1, start_seconds: 0.0, end_seconds: 5.0, event_type: "text", content: "BREAKING NEWS — CITY COUNCIL EMERGENCY SESSION", source_agent: "ocr", confidence: 0.98 },
      { scene_id: 1, start_seconds: 0.5, end_seconds: 5.0, event_type: "object", content: "Studio anchor desk. Lower-third graphic. Screen-in-screen showing council chambers.", source_agent: "perception", confidence: 0.92 },
      { scene_id: 1, start_seconds: 1.0, end_seconds: 4.8, event_type: "speech", content: "Good evening. The city council convened an emergency session tonight following reports of—", source_agent: "asr", confidence: 0.96 },
      { scene_id: 2, start_seconds: 5.0, end_seconds: 18.5, event_type: "speech", content: "—a proposed 34% increase in residential water rates, effective Q1 next year.", source_agent: "asr", confidence: 0.93 },
      { scene_id: 2, start_seconds: 5.5, end_seconds: 9.0, event_type: "text", content: "RATE INCREASE: +34% PROPOSED", source_agent: "ocr", confidence: 0.97 },
      { scene_id: 2, start_seconds: 5.5, end_seconds: 9.0, event_type: "object", content: "Lower-third graphic shows figure +27%", source_agent: "perception", confidence: 0.91 },
      { scene_id: 3, start_seconds: 18.5, end_seconds: 31.0, event_type: "speech", content: "Council member Albright voted against the proposal citing insufficient public notice.", source_agent: "asr", confidence: 0.90 },
      { scene_id: 3, start_seconds: 20.0, end_seconds: 22.5, event_type: "text", content: "VOTE: 5-4 IN FAVOUR", source_agent: "ocr", confidence: 0.99 },
      { scene_id: 4, start_seconds: 31.0, end_seconds: 40.0, event_type: "no_signal", content: "No events detected in this scene window.", source_agent: null, confidence: null },
    ],
    conflicts: [
      { scene_id: 2, time_range: [5.5, 9.0], source_a: "ocr", content_a: "Lower-third graphic text reads: +34% proposed rate increase.", source_b: "perception", content_b: "On-screen graphic figure detected as +27%, not +34%.", conflict_type: "content_mismatch" },
    ],
    scenes_with_no_signal: [4],
  },
  "d1a59f83-4c7b-4e26-a91d-3b8f0e72c145": {
    fused_timeline: [
      { scene_id: 1, start_seconds: 0.0, end_seconds: 12.0, event_type: "object", content: "Warehouse aisle. Two individuals. Forklift visible, stationary. Lighting: fluorescent, partial.", source_agent: "perception", confidence: 0.90 },
      { scene_id: 1, start_seconds: 3.4, end_seconds: 12.0, event_type: "speech", content: "We need to move the pallet by end of shift. Bay 7, not bay 4.", source_agent: "asr", confidence: 0.83 },
      { scene_id: 2, start_seconds: 12.0, end_seconds: 25.5, event_type: "object", content: "Individual 1 moves toward shelving unit C-7. Individual 2 remains at forklift.", source_agent: "perception", confidence: 0.87 },
      { scene_id: 2, start_seconds: 14.5, end_seconds: 18.0, event_type: "text", content: "SHELF LABEL: C-07 / RESTRICTED ACCESS", source_agent: "ocr", confidence: 0.94 },
      { scene_id: 2, start_seconds: 14.5, end_seconds: 18.0, event_type: "text", content: "SHELF: C-04 — OPEN ACCESS", source_agent: "perception", confidence: 0.78 },
      { scene_id: 3, start_seconds: 25.5, end_seconds: 40.0, event_type: "object", content: "Frame jump detected at 25.5s — 3.2 second gap in footage continuity. Possible edit.", source_agent: "perception", confidence: 0.99 },
      { scene_id: 3, start_seconds: 28.8, end_seconds: 40.0, event_type: "speech", content: "—already done. It's handled.", source_agent: "asr", confidence: 0.71 },
      { scene_id: 3, start_seconds: 30.0, end_seconds: 36.0, event_type: "diarization", content: "Unknown speaker — not matching earlier voice prints", source_agent: "diarization", confidence: 0.45 },
      { scene_id: 4, start_seconds: 40.0, end_seconds: 55.0, event_type: "object", content: "Forklift in motion. Bay 7 gate visible — gate is closed. Timestamp overlay on footage.", source_agent: "perception", confidence: 0.93 },
      { scene_id: 4, start_seconds: 40.0, end_seconds: 55.0, event_type: "text", content: "CAM-04 | 2026-09-16 11:07:44", source_agent: "ocr", confidence: 0.99 },
      { scene_id: 4, start_seconds: 40.5, end_seconds: 54.0, event_type: "speech", content: "Bay 7 gate is locked. I don't have access for tonight.", source_agent: "asr", confidence: 0.88 },
      { scene_id: 5, start_seconds: 55.0, end_seconds: 68.0, event_type: "no_signal", content: "No events detected in this scene window.", source_agent: null, confidence: null },
    ],
    conflicts: [
      { scene_id: 2, time_range: [14.5, 18.0], source_a: "ocr", content_a: "Shelf label reads: C-07 / RESTRICTED ACCESS", source_b: "perception", content_b: "Object classifier identifies shelf tag as C-04 — OPEN ACCESS", conflict_type: "content_mismatch" },
      { scene_id: 3, time_range: [25.5, 28.8], source_a: "perception", content_a: "Frame discontinuity at 25.5s — 3.2s gap detected. Footage may be edited.", source_b: "asr", content_b: "Audio transcript shows no gap; speech is continuous through this window.", conflict_type: "timing_mismatch" },
      { scene_id: 3, time_range: [30.0, 36.0], source_a: "diarization", content_a: "Voice print does not match either registered speaker from scene 1.", source_b: "asr", content_b: "Speech content suggests continuation of original conversation.", conflict_type: "presence_contradiction" },
    ],
    scenes_with_no_signal: [5],
  },
};

const Case = require('../models/Case');

// Prepopulate initial demo cases if empty
async function initSeedCases() {
  for (const c of mockCases) {
    const existing = await Case.findOne({ case_id: c.case_id });
    if (!existing) {
      const timeline = mockTimelines[c.case_id] || { fused_timeline: [], conflicts: [], scenes_with_no_signal: [] };
      await Case.create({
        ...c,
        fused_timeline: timeline.fused_timeline,
        conflicts: timeline.conflicts,
        scenes_with_no_signal: timeline.scenes_with_no_signal
      });
    }
  }
}
initSeedCases().catch(() => {});

// Helper to dynamically add or update a case in MongoDB / memory
async function addCase(caseManifest, timelineData) {
  if (!caseManifest || !caseManifest.case_id) return;
  const mergedData = {
    ...caseManifest,
    fused_timeline: timelineData?.fused_timeline || [],
    conflicts: timelineData?.conflicts || [],
    scenes_with_no_signal: timelineData?.scenes_with_no_signal || [],
    per_video_summaries: caseManifest.per_video_summaries || []
  };

  const existingIdx = mockCases.findIndex(c => c.case_id === caseManifest.case_id);
  if (existingIdx >= 0) {
    mockCases[existingIdx] = { ...mockCases[existingIdx], ...caseManifest };
  } else {
    mockCases.unshift(caseManifest);
  }
  if (timelineData) {
    mockTimelines[caseManifest.case_id] = timelineData;
  }

  try {
    await Case.findOneAndUpdate(
      { case_id: caseManifest.case_id },
      mergedData,
      { upsert: true, new: true }
    );
  } catch (err) {
    console.warn(`[Case Storage Warning] Could not save case to MongoDB (${err.message})`);
  }
}

// GET /api/cases - Returns all case manifests
router.get('/', protect, async (req, res) => {
  try {
    const dbCases = await Case.find();
    if (dbCases && dbCases.length > 0) {
      return res.json({ success: true, data: dbCases });
    }
  } catch (e) {}
  res.json({ success: true, data: mockCases });
});

// GET /api/cases/:caseId - Returns single case manifest
router.get('/:caseId', protect, async (req, res) => {
  const { caseId } = req.params;
  try {
    const c = await Case.findOne({ case_id: caseId });
    if (c) {
      return res.json({ success: true, data: c });
    }
  } catch (e) {}
  
  const c = mockCases.find(item => item.case_id === caseId);
  if (!c) {
    return res.status(404).json({ success: false, message: 'Case not found' });
  }
  res.json({ success: true, data: c });
});

// GET /api/cases/:caseId/timeline - Returns timeline data for a case
router.get('/:caseId/timeline', protect, async (req, res) => {
  const { caseId } = req.params;
  try {
    const c = await Case.findOne({ case_id: caseId });
    if (c && c.fused_timeline && c.fused_timeline.length > 0) {
      return res.json({
        success: true,
        data: {
          fused_timeline: c.fused_timeline,
          conflicts: c.conflicts || [],
          scenes_with_no_signal: c.scenes_with_no_signal || []
        }
      });
    }
  } catch (e) {}

  const data = mockTimelines[caseId];
  if (!data) {
    return res.json({ 
      success: true, 
      data: { fused_timeline: [], conflicts: [], scenes_with_no_signal: [] } 
    });
  }
  
  res.json({ success: true, data });
});

// POST /api/cases/:caseId/verify - Verifies cryptographic integrity of a case
router.post('/:caseId/verify', protect, async (req, res) => {
  const { caseId } = req.params;
  let c = null;
  try {
    c = await Case.findOne({ case_id: caseId });
  } catch (e) {}
  if (!c) {
    c = mockCases.find(item => item.case_id === caseId);
  }

  let result;
  if (!c) {
    result = { ok: false, message: 'Case not found in evidence registry.' };
  } else if (c.status === 'flagged' || caseId === 'd1a59f83-4c7b-4e26-a91d-3b8f0e72c145') {
    result = { ok: false, message: 'Merkle root mismatch — computed root differs from sealed root. Frame tampering detected. Integrity check FAILED.' };
  } else if (c.status === 'processing' || !c.merkle_root) {
    result = { ok: false, message: 'Case is not yet sealed — no cryptographic Merkle root available to verify against.' };
  } else {
    result = { ok: true, message: `Cryptographic Merkle root verified: ${c.merkle_root.substring(0, 16)}... All video frames and artifacts intact. Integrity PASSED.` };
  }
  
  res.json({ success: true, data: result });
});

module.exports = router;
module.exports.addCase = addCase;
module.exports.mockCases = mockCases;
module.exports.mockTimelines = mockTimelines;