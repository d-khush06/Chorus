/**
 * api.js
 * Data-fetching adapter layer.
 *
 * Currently backed by static mock files.
 * To swap to a real API: replace the import lines below with fetch() calls.
 * Nothing else in the app changes.
 *
 * One-line swap example:
 *   const cases = await fetch('/api/cases').then(r => r.json());
 *   const timeline = await fetch(`/api/cases/${caseId}/timeline`).then(r => r.json());
 */

import { mockCases } from './mockCases.js';
import { mockTimelines } from './mockTimelines.js';

// Helper to get auth headers for real API calls
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
};

/**
 * Returns the list of all case manifests.
 * @returns {Promise<Array>}
 */
export async function fetchCases() {
  // SWAP: return fetch('/api/cases').then(r => r.json());
  return Promise.resolve(mockCases);
}

/**
 * Returns the fused timeline + conflicts for a given case.
 * @param {string} caseId
 * @returns {Promise<{ fused_timeline, conflicts, scenes_with_no_signal }>}
 */
export async function fetchTimeline(caseId) {
  // SWAP: return fetch(`/api/cases/${caseId}/timeline`).then(r => r.json());
  const data = mockTimelines[caseId];
  if (!data) return Promise.resolve({ fused_timeline: [], conflicts: [], scenes_with_no_signal: [] });
  return Promise.resolve(data);
}

/**
 * Verifies cryptographic integrity of a case (mock).
 * @param {string} caseId
 * @returns {Promise<{ ok: boolean, message: string }>}
 */
export async function verifyIntegrity(caseId) {
  // SWAP: return fetch(`/api/cases/${caseId}/verify`, { method: 'POST' }).then(r => r.json());
  // Simulate async verification
  await new Promise(resolve => setTimeout(resolve, 800));
  // Case 3 (flagged) fails verification; others pass
  if (caseId === 'd1a59f83-4c7b-4e26-a91d-3b8f0e72c145') {
    return { ok: false, message: 'Merkle root mismatch — computed root differs from sealed root. Integrity check FAILED.' };
  }
  if (caseId === 'b8e20c47-1d9f-4a3c-8e72-5f9c3d04b6a1') {
    return { ok: false, message: 'Case is not sealed — no merkle root available to verify against.' };
  }
  return { ok: true, message: 'Merkle root matches. All artifact hashes verified. Integrity PASSED.' };
}
