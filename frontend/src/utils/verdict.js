/**
 * Frontend Forensic Verdict Helper
 * Mirror of backend verdict service to ensure unified rendering and thresholds across UI.
 */

export const DEFAULT_THRESHOLDS = {
  frame: 0.50,
  video: 0.30,
  ai_generation: 0.50
};

export function computeVerdict(payload = {}) {
  const manip = payload.manipulation_result || payload.manipulationCheck || {};
  const aiGen = payload.ai_generation_result || payload.aiGeneration || {};
  const qg = payload.quality_gate_result || payload.qualityGate || {};

  const thresholds = {
    frame: manip.thresholds?.frame ?? DEFAULT_THRESHOLDS.frame,
    video: manip.thresholds?.video ?? DEFAULT_THRESHOLDS.video,
    ai_generation: aiGen.threshold ?? DEFAULT_THRESHOLDS.ai_generation
  };

  const framesEvaluated = manip.frames_evaluated ?? 
                          (Array.isArray(manip.frame_scores) ? manip.frame_scores.length : (manip.frames_analyzed ?? 0));
  const videoScore = typeof manip.video_score === 'number' ? manip.video_score : 
                     (typeof manip.score === 'number' ? manip.score : 0.0);
  const aiScore = typeof aiGen.confidence === 'number' ? aiGen.confidence : 
                  (typeof aiGen.score === 'number' ? aiGen.score : (aiGen.probability ?? 0.0));

  const detectorError = Boolean(
    manip.detector_error || 
    manip.error || 
    (manip.verdict && manip.verdict.toLowerCase().includes('error'))
  );

  const errorReason = manip.error_reason || manip.reason || manip.message || '';
  const noFacesDetected = Boolean(
    errorReason.toUpperCase().includes('NO_FACES_DETECTED') || 
    errorReason.toLowerCase().includes('no face') ||
    manip.verdict === 'NO_FACES_DETECTED'
  );

  const tooFewFrames = framesEvaluated > 0 && framesEvaluated < 4;

  const checks = [];

  // 1: SBI Deepfake Detection
  let sbiStatus = 'pass';
  let sbiDetails = 'Facial boundary diffusion and texture artifacts within normal baseline.';
  if (detectorError) {
    sbiStatus = 'error';
    sbiDetails = `Detector error encountered: ${errorReason || 'Inspection process interrupted'}.`;
  } else if (noFacesDetected) {
    sbiStatus = 'inconclusive';
    sbiDetails = 'No human faces detected in analyzed video frames.';
  } else if (tooFewFrames) {
    sbiStatus = 'inconclusive';
    sbiDetails = `Insufficient decodable frames (${framesEvaluated} evaluated; minimum 4 required).`;
  } else if (manip.verdict === 'FLAGGED' || videoScore >= thresholds.video) {
    sbiStatus = 'fail';
    sbiDetails = `Facial manipulation detected (score: ${videoScore.toFixed(3)}, threshold: ${thresholds.video.toFixed(2)}).`;
  } else if (videoScore >= (thresholds.video * 0.70)) {
    sbiStatus = 'warning';
    sbiDetails = `Borderline facial inconsistency detected (score: ${videoScore.toFixed(3)}, threshold: ${thresholds.video.toFixed(2)}).`;
  }

  checks.push({
    id: 'sbi_deepfake',
    name: 'Self-Blended Image (SBI) Deepfake Screening',
    status: sbiStatus,
    score: videoScore,
    threshold: thresholds.video,
    frame_threshold: thresholds.frame,
    frames_evaluated: framesEvaluated,
    details: sbiDetails,
    limitations: 'Trained primarily on facial blending and face-swap artifacts; non-facial or diffusion-based whole-frame synthesis may not register on this detector.'
  });

  // 2: AI-Generation Screening
  let aiStatus = 'pass';
  let aiDetails = 'Diffusion noise residual and high-frequency spectral markers appear consistent with optical camera capture.';
  const isAiFlagged = Boolean(
    aiGen.verdict === 'FLAGGED' || 
    aiGen.verdict === 'POSITIVE' || 
    aiGen.is_synthetic === true || 
    aiScore >= thresholds.ai_generation
  );

  if (aiGen.error) {
    aiStatus = 'inconclusive';
    aiDetails = `AI generation screening error: ${aiGen.error}`;
  } else if (isAiFlagged) {
    aiStatus = 'fail';
    aiDetails = `AI-generation screening positive (score: ${aiScore.toFixed(3)}, threshold: ${thresholds.ai_generation.toFixed(2)}). Synthetic generation traces detected.`;
  } else if (aiScore >= (thresholds.ai_generation * 0.70)) {
    aiStatus = 'warning';
    aiDetails = `Borderline synthetic diffusion markers detected (score: ${aiScore.toFixed(3)}, threshold: ${thresholds.ai_generation.toFixed(2)}).`;
  } else if (!payload.ai_generation_result) {
    aiStatus = 'skipped';
    aiDetails = 'AI-generation screening stage not executed or optional.';
  }

  checks.push({
    id: 'ai_generation',
    name: 'Synthetic / AI-Generation Artifact Screening',
    status: aiStatus,
    score: aiScore,
    threshold: thresholds.ai_generation,
    details: aiDetails,
    limitations: 'Diffusion detectors may exhibit sensitivity to heavy video compression, re-encoding, or extreme downscaling.'
  });

  // 3: Quality Gate
  const qgRules = qg.rules_evaluated || 8;
  const qgFailedRules = qg.failed_rule_ids || qg.failed_rules || [];
  const qgVerdict = qg.overall_verdict || 'PASS';
  let qgStatus = 'pass';
  let qgDetails = `All ${qgRules} container, stream, and timestamp integrity rules verified.`;

  if (qgVerdict === 'WARNING') {
    qgStatus = 'warning';
    qgDetails = `Quality gate issued warnings for video metadata or timestamp cadence: ${qgFailedRules.join(', ') || 'anomalies noted'}.`;
  } else if (qgVerdict === 'FAIL' || qgFailedRules.length > 0) {
    qgStatus = 'fail';
    qgDetails = `Integrity check flagged ${qgFailedRules.length} rule violation(s): ${qgFailedRules.join(', ')}.`;
  }

  checks.push({
    id: 'quality_gate',
    name: 'Quality Gate Stream & Container Integrity',
    status: qgStatus,
    rules_evaluated: qgRules,
    failed_rule_ids: qgFailedRules,
    notes: qg.notes || [],
    details: qgDetails,
    limitations: 'Evaluates format container conformance, PTS/DTS continuity, and audio-visual synchronization; does not inspect semantic visual content.'
  });

  let verdict = 'Authentic-looking';
  let explanation = '';
  let confidence = 0.90;

  if (detectorError) {
    verdict = 'Inconclusive';
    confidence = 0.0;
    explanation = `Analysis is inconclusive due to a detector error encountered during inspection: ${errorReason || 'Pipeline detector error'}.`;
  } else if (tooFewFrames && !isAiFlagged) {
    verdict = 'Inconclusive';
    confidence = 0.25;
    explanation = `Analysis is inconclusive because too few decodable frames (${framesEvaluated}) were available to establish a statistically valid forensic baseline (minimum 4 required).`;
  } else if (noFacesDetected && !isAiFlagged && sbiStatus === 'inconclusive') {
    verdict = 'Inconclusive';
    confidence = 0.30;
    explanation = 'Analysis is inconclusive: No detectable human faces were identified in the footage, and no secondary synthetic anomalies were found.';
  } else if (sbiStatus === 'fail' || isAiFlagged) {
    verdict = 'Likely manipulated';
    confidence = Math.max(videoScore, aiScore, 0.85);
    const reasons = [];
    if (sbiStatus === 'fail') reasons.push(`facial blending anomalies exceeding detection threshold (${videoScore.toFixed(2)} >= ${thresholds.video.toFixed(2)})`);
    if (isAiFlagged) reasons.push(`synthetic diffusion artifact screening (${aiScore.toFixed(2)} >= ${thresholds.ai_generation.toFixed(2)})`);
    explanation = `Substantial forensic evidence of manipulation detected: ${reasons.join(' and ')}. Manual evidentiary review strongly advised.`;
  } else if (sbiStatus === 'warning' || aiStatus === 'warning' || qgStatus === 'warning' || qgStatus === 'fail') {
    verdict = 'Suspicious';
    confidence = Math.max(videoScore, aiScore, 0.65);
    explanation = 'Borderline anomalous metrics or container integrity irregularities detected. Video warrants further forensic inspection.';
  } else {
    verdict = 'Authentic-looking';
    confidence = Math.max(0.85, 1.0 - Math.max(videoScore, aiScore));
    explanation = 'All applicable automated forensic and tamper checks ran clean. Note: This automated assessment does not constitute mathematical proof of authenticity, as novel or advanced generative techniques may evade current forensic baselines.';
  }

  return {
    verdict,
    verdict_code: verdict.toUpperCase().replace(/\s+/g, '_').replace(/-/g, '_'),
    confidence_score: Number(confidence.toFixed(3)),
    thresholds,
    scores: {
      video_manipulation_score: videoScore,
      ai_generation_score: aiScore,
      frames_evaluated: framesEvaluated
    },
    checks,
    explanation,
    limitations: 'Automated forensic pipelines evaluate targeted statistical anomalies and known deepfake signatures. Absence of detected manipulation does not preclude analog tampering, source-level staging, or adversarial evasion.',
    is_proof_of_authenticity: false,
    evaluated_at: new Date().toISOString()
  };
}
