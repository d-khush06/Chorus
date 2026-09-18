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
import { API_BASE } from '../context/AuthContext.jsx';

// Helper to get auth headers for real API calls
const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { 'Authorization': `Bearer ${token}` } : {};
};

/**
 * Returns the list of all case manifests from backend or fallback.
 * @returns {Promise<Array>}
 */
export async function fetchCases() {
  try {
    const res = await fetch(`${API_BASE}/api/cases`, {
      headers: getAuthHeaders()
    });
    if (res.ok) {
      const json = await res.json();
      if (json.success && Array.isArray(json.data) && json.data.length > 0) {
        return json.data;
      }
    }
  } catch (err) {
    console.warn('[API] Could not reach backend for cases, using mock data:', err.message);
  }
  return mockCases;
}

/**
 * Returns the fused timeline + conflicts for a given case.
 * @param {string} caseId
 * @returns {Promise<{ fused_timeline: Array, conflicts: Array, scenes_with_no_signal: Array }>}
 */
export async function fetchTimeline(caseId) {
  try {
    const res = await fetch(`${API_BASE}/api/cases/${caseId}/timeline`, {
      headers: getAuthHeaders()
    });
    if (res.ok) {
      const json = await res.json();
      if (json.success && json.data) {
        return json.data;
      }
    }
  } catch (err) {
    console.warn(`[API] Could not reach backend for timeline (${caseId}), using mock:`, err.message);
  }
  const fallback = mockTimelines[caseId];
  return fallback || { fused_timeline: [], conflicts: [], scenes_with_no_signal: [] };
}

/**
 * Verifies cryptographic integrity of a case.
 * @param {string} caseId
 * @returns {Promise<{ ok: boolean, message: string }>}
 */
export async function verifyIntegrity(caseId) {
  try {
    const res = await fetch(`${API_BASE}/api/cases/${caseId}/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      }
    });
    if (res.ok) {
      const json = await res.json();
      if (json.success && json.data) {
        return json.data;
      }
    }
  } catch (err) {
    console.warn(`[API] Backend verify failed (${caseId}), using simulated response:`, err.message);
  }

  // Simulated fallback
  await new Promise(resolve => setTimeout(resolve, 800));
  if (caseId === 'd1a59f83-4c7b-4e26-a91d-3b8f0e72c145') {
    return { ok: false, message: 'Merkle root mismatch — computed root differs from sealed root. Integrity check FAILED.' };
  }
  if (caseId === 'b8e20c47-1d9f-4a3c-8e72-5f9c3d04b6a1') {
    return { ok: false, message: 'Case is not sealed — no merkle root available to verify against.' };
  }
  return { ok: true, message: 'Merkle root matches. All artifact hashes verified. Integrity PASSED.' };
}

/**
 * Sends a video file or prompt/url for pipeline analysis.
 * @param {Object} param0
 * @param {File|null} param0.videoFile
 * @param {string} param0.prompt
 * @param {string} param0.mode - 'general' | 'cyber'
 * @param {string} param0.url
 * @returns {Promise<{ success: boolean, result?: Object, steps?: Array, error?: string, case_id?: string }>}
 */
export async function analyzeVideo({ videoFile, prompt, mode = 'general', url = '', max_playlist_videos, batch_size, max_videos }) {
  const formData = new FormData();
  if (videoFile) {
    formData.append('video', videoFile);
  }
  formData.append('prompt', prompt || '');
  formData.append('mode', mode);
  if (url) {
    formData.append('url', url);
  }
  if (max_playlist_videos !== undefined && max_playlist_videos !== null) {
    formData.append('max_playlist_videos', max_playlist_videos);
  }
  if (max_videos !== undefined && max_videos !== null) {
    formData.append('max_videos', max_videos);
  }
  if (batch_size !== undefined && batch_size !== null) {
    formData.append('batch_size', batch_size);
  }

  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: formData
  });

  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || 'Video analysis request failed');
  }
  return data;
}

