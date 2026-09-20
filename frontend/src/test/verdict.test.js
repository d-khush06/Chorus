import { describe, it, expect } from 'vitest';
import { computeVerdict } from '../utils/verdict.js';

describe('Forensic Verdict Module', () => {
  it('returns Authentic-looking when all applicable checks run clean', () => {
    const payload = {
      manipulation_result: {
        verdict: 'CLEAN',
        video_score: 0.08,
        frames_evaluated: 30,
        detector_error: false
      },
      ai_generation_result: {
        verdict: 'CLEAN',
        confidence: 0.12,
        threshold: 0.65
      },
      quality_gate_result: {
        overall_verdict: 'PASS',
        rules_evaluated: 8,
        failed_rule_ids: []
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Authentic-looking');
    expect(result.is_proof_of_authenticity).toBe(false);
    expect(result.explanation).toContain('not constitute mathematical proof of authenticity');
    expect(result.scores.video_manipulation_score).toBe(0.08);
    expect(result.scores.ai_generation_score).toBe(0.12);
    expect(result.checks.length).toBe(3);
  });

  it('returns Likely manipulated when manipulation detection is FLAGGED', () => {
    const payload = {
      manipulation_result: {
        verdict: 'FLAGGED',
        video_score: 0.88,
        thresholds: { frame: 0.85, video: 0.70 },
        frames_evaluated: 24
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Likely manipulated');
    expect(result.confidence_score).toBeGreaterThanOrEqual(0.85);
    expect(result.explanation).toContain('Substantial forensic evidence of manipulation detected');
  });

  it('returns Likely manipulated when AI-generation screening is positive', () => {
    const payload = {
      manipulation_result: {
        verdict: 'CLEAN',
        video_score: 0.15,
        frames_evaluated: 20
      },
      ai_generation_result: {
        verdict: 'FLAGGED',
        confidence: 0.82,
        threshold: 0.65
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Likely manipulated');
    expect(result.checks.find(c => c.id === 'ai_generation').status).toBe('fail');
  });

  it('returns Suspicious on borderline manipulation scores', () => {
    const payload = {
      manipulation_result: {
        verdict: 'SUSPICIOUS',
        video_score: 0.58,
        thresholds: { video: 0.70 },
        frames_evaluated: 20
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Suspicious');
    expect(result.checks.find(c => c.id === 'sbi_deepfake').status).toBe('warning');
  });

  it('returns Suspicious when quality gate issues warnings', () => {
    const payload = {
      manipulation_result: {
        verdict: 'CLEAN',
        video_score: 0.10,
        frames_evaluated: 15
      },
      quality_gate_result: {
        overall_verdict: 'WARNING',
        failed_rule_ids: ['timestamp_monotonicity']
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Suspicious');
    expect(result.checks.find(c => c.id === 'quality_gate').status).toBe('warning');
  });

  it('returns Inconclusive on detector_error', () => {
    const payload = {
      manipulation_result: {
        detector_error: true,
        error_reason: 'Face detector backend failed to initialize CUDA tensor'
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Inconclusive');
    expect(result.explanation).toContain('detector error');
    expect(result.checks.find(c => c.id === 'sbi_deepfake').status).toBe('error');
  });

  it('returns Inconclusive on NO_FACES_DETECTED with no other usable evidence', () => {
    const payload = {
      manipulation_result: {
        verdict: 'NO_FACES_DETECTED',
        error_reason: 'NO_FACES_DETECTED: No facial landmarks located in frame sequence',
        frames_evaluated: 10
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Inconclusive');
    expect(result.explanation).toContain('No detectable human faces');
  });

  it('returns Inconclusive when too few decodable frames (<4)', () => {
    const payload = {
      manipulation_result: {
        verdict: 'CLEAN',
        video_score: 0.12,
        frames_evaluated: 2
      }
    };

    const result = computeVerdict(payload);
    expect(result.verdict).toBe('Inconclusive');
    expect(result.explanation).toContain('too few decodable frames (2)');
  });
});
