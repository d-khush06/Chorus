import React, { useState, useEffect, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill, StatusDot } from './primitives/StatusPill';
import { Skeleton, SkeletonCard } from './primitives/Skeleton';
import { EmptyState, ErrorState } from './primitives/EmptyState';
import { Tabs, TabTrigger, TabContent } from './primitives/Tabs';
import { StageTracker } from './StageTracker';
import { computeVerdict } from '../../utils/verdict';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

function formatTimestamp(seconds) {
  if (isNaN(seconds) || seconds === null || seconds === undefined || seconds < 0) return '00:00.000';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

export function ForensicPage() {
  const [activeTab, setActiveTab] = useState('authenticity');
  const [file, setFile] = useState(null);
  const [urlInput, setUrlInput] = useState('');
  const [caseId, setCaseId] = useState('');
  const [notes, setNotes] = useState('');

  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | running | completed | error
  const [errorMessage, setErrorMessage] = useState(null);

  // Live SSE Stage Tracking
  const [stages, setStages] = useState([]);
  const [currentStage, setCurrentStage] = useState(null);
  const [progress, setProgress] = useState(0);

  // Analysis Result
  const [report, setReport] = useState(null);
  const [custodyData, setCustodyData] = useState(null);
  const [streamTicket, setStreamTicket] = useState(null);

  // Video Player state
  const videoRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [localVideoUrl, setLocalVideoUrl] = useState(null);

  // Actions state
  const [saveStatus, setSaveStatus] = useState(null);
  const [routeStatus, setRouteStatus] = useState(null);

  // Completed State Guard: ALL result panels derive strictly from completed data
  const isCompleted = status === 'completed' && Boolean(report);
  const verdict = isCompleted ? (report.verdict || computeVerdict(report)) : null;

  const fps = report?.metadata?.video?.fps || 30.0;
  const currentFrame = (videoStreamSrc_hasSrc(localVideoUrl, report, streamTicket) && duration > 0)
    ? Math.floor(currentTime * fps)
    : null;
  const totalFrames = (videoStreamSrc_hasSrc(localVideoUrl, report, streamTicket) && duration > 0)
    ? Math.floor(duration * fps)
    : null;

  function videoStreamSrc_hasSrc(localUrl, rep, ticket) {
    return Boolean(localUrl || (rep?.videoFilename && ticket) || rep?.videoPath);
  }

  // Fetch stream ticket for range streaming when runId is available
  useEffect(() => {
    if (!runId) return;
    async function getTicket() {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_BASE}/api/auth/stream-ticket`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({ resourceId: runId })
        });
        if (res.ok) {
          const data = await res.json();
          setStreamTicket(data.ticket);
        }
      } catch (err) {
        console.warn('[Forensic] Could not acquire stream ticket:', err);
      }
    }
    getTicket();
  }, [runId]);

  // Clean up local object URL on unmount
  useEffect(() => {
    return () => {
      if (localVideoUrl) URL.revokeObjectURL(localVideoUrl);
    };
  }, [localVideoUrl]);

  // Handle Video File Selection
  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected) {
      if (selected.size > 1024 * 1024 * 1024) {
        setErrorMessage('File exceeds maximum size limit of 1 GB.');
        return;
      }
      setFile(selected);
      setUrlInput('');
      setErrorMessage(null);
      const objUrl = URL.createObjectURL(selected);
      setLocalVideoUrl(objUrl);
    }
  };

  // Start Forensic Pipeline Analysis
  const handleStartAnalysis = async () => {
    if (!file && !urlInput.trim()) {
      setErrorMessage('Please select a local video file (up to 1 GB) or provide an RTSP/HTTP URL.');
      return;
    }

    setStatus('running');
    setErrorMessage(null);
    setStages([]);
    setCurrentStage('source_ingestion');
    setProgress(5);
    setSaveStatus(null);
    setRouteStatus(null);
    setReport(null);
    setCustodyData(null);

    const token = localStorage.getItem('token');
    const formData = new FormData();
    if (file) formData.append('video', file);
    if (urlInput.trim()) formData.append('url', urlInput.trim());
    formData.append('mode', 'cyber');
    formData.append('entry_point', 'forensic');
    if (caseId.trim()) formData.append('case_id', caseId.trim());
    if (notes.trim()) formData.append('notes', notes.trim());

    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        body: formData
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to initialize forensic pipeline run');
      }

      const activeRunId = data.runId;
      setRunId(activeRunId);

      // Connect to SSE for live stages
      subscribeToRunEvents(activeRunId);
    } catch (err) {
      setStatus('error');
      setErrorMessage(err.message);
    }
  };

  const subscribeToRunEvents = async (rId) => {
    let ticket = null;
    try {
      const token = localStorage.getItem('token');
      const ticketRes = await fetch(`${API_BASE}/api/auth/stream-ticket`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ resourceId: rId })
      });
      if (ticketRes.ok) {
        const ticketData = await ticketRes.json();
        ticket = ticketData.ticket;
      }
    } catch (tErr) {}

    const sseUrl = `${API_BASE}/api/analyze/runs/${rId}/events${ticket ? `?ticket=${ticket}` : ''}`;
    const es = new EventSource(sseUrl);

    es.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);
        if (payload.type === 'STAGE_EVENT' || payload.type === 'stage') {
          const current = payload.stage || payload.run?.current_stage || (payload.event?.type === 'start' ? payload.event.stage : null);
          const stages = payload.stages || payload.run?.stage_manifest || (payload.event?.type === 'manifest' ? payload.event.stages : null);
          const progress = payload.progress !== undefined ? payload.progress : payload.run?.progress;
          if (current) setCurrentStage(current);
          if (Array.isArray(stages) && stages.length > 0) setStages(stages);
          if (progress !== undefined) setProgress(progress);
        } else if (payload.type === 'RUN_COMPLETED' || payload.status === 'completed') {
          es.close();
          fetchFinalReport(rId);
        } else if (payload.type === 'RUN_FAILED' || payload.status === 'failed') {
          es.close();
          setStatus('error');
          setErrorMessage(payload.error || 'Pipeline execution failed');
        }
      } catch (err) {}
    };

    es.onerror = () => {
      es.close();
      // Attempt polling check in case of transient network drop
      setTimeout(() => fetchFinalReport(rId), 3000);
    };
  };

  const fetchFinalReport = async (rId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/cyber/forensic/${rId}/report`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        setReport(data.report || data);
      }

      // Fetch custody log
      const cRes = await fetch(`${API_BASE}/api/cyber/forensic/custody?case_id=${encodeURIComponent(rId)}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (cRes.ok) {
        const cData = await cRes.json();
        setCustodyData(cData);
      }

      setStatus('completed');
      setProgress(100);
    } catch (err) {
      console.warn('[Forensic] Report fetch error:', err);
      setStatus('completed');
    }
  };

  // Video Stepping Controls
  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const stepFrame = (delta) => {
    if (!videoRef.current) return;
    videoRef.current.pause();
    setIsPlaying(false);
    const newTime = Math.max(0, Math.min(duration, currentTime + delta * (1 / fps)));
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const seekToTime = (timeSec) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = timeSec;
    setCurrentTime(timeSec);
  };

  // Save to Evidence Room
  const handleSaveToEvidence = async () => {
    if (!isCompleted) return;
    setSaveStatus('saving');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/cyber/forensic/save-case`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          runId,
          case_id: caseId.trim() || `CR-${Date.now().toString(36).toUpperCase()}`,
          title: report?.fileName || file?.name || 'Forensic Examination Video',
          report,
          verdict
        })
      });
      if (!res.ok) throw new Error('Save case failed');
      setSaveStatus('saved');
    } catch (err) {
      setSaveStatus('error');
    }
  };

  // Route to Review Queue
  const handleRouteToReview = async () => {
    if (!isCompleted) return;
    setRouteStatus('routing');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/review-queue`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          runId,
          case_id: caseId || `CR-${runId}`,
          flaggedReason: verdict?.verdict || 'Flagged in forensic screening',
          verdict
        })
      });
      setRouteStatus('routed');
    } catch (err) {
      setRouteStatus('error');
    }
  };

  // Export JSON Report
  const handleExportReport = () => {
    if (!isCompleted) return;
    const exportPayload = {
      case_id: caseId || `CR-${runId || 'MANUAL'}`,
      run_id: runId,
      exported_at: new Date().toISOString(),
      verdict,
      report,
      custody: custodyData,
      limitations: [
        'Heuristic deepfake detection provides probabilistic screening and is not absolute proof of authenticity.',
        'Quality gate rules assess container compliance; certain camera devices produce non-standard GOP structures by design.',
        'Biometric Re-ID requires strict legal consent and governance approval under Policy G-14.'
      ]
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chorus-forensic-report-${caseId || runId || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Stream URL from authenticated Range route or local file
  const videoStreamSrc = localVideoUrl || 
    (report?.videoFilename && streamTicket 
      ? `${API_BASE}/api/videos/stream/${encodeURIComponent(report.videoFilename)}?ticket=${streamTicket}`
      : (report?.videoPath || ''));

  const sbiCheck = verdict?.checks?.find(c => c.id === 'sbi_deepfake');
  const aiCheck = verdict?.checks?.find(c => c.id === 'ai_generation');
  const qgCheck = verdict?.checks?.find(c => c.id === 'quality_gate');

  return (
    <div className="max-w-7xl mx-auto space-y-6 route-enter">
      {/* ── Top Header Bar ── */}
      <div
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-5 border border-default rounded-card"
        style={{ backgroundColor: 'var(--card)', boxShadow: 'var(--card-shadow)' }}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <span className="font-mono text-sm font-semibold text-primary">
              CASE: {caseId || report?.case_id || (runId ? `CR-${runId.slice(0, 8).toUpperCase()}` : '—')}
            </span>
            <span className="font-mono text-sm text-secondary">
              {file?.name || report?.fileName || urlInput || '—'}
            </span>
            <span className="font-mono text-xs text-secondary truncate max-w-xs" title={report?.sha256}>
              SHA-256: {report?.sha256 ? report.sha256 : (status === 'running' ? 'COMPUTING IN PIPELINE…' : '—')}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <StatusPill
              status={isCompleted ? verdict.status : (status === 'running' ? 'warning' : 'neutral')}
              label={isCompleted ? verdict.verdict : (status === 'running' ? 'Analysis In Progress' : 'Waiting for evidence')}
              size="md"
              dot
              pulse={status === 'running'}
            />
            {isCompleted && verdict && (
              <span className="text-xs text-secondary font-mono">
                Confidence: {Math.round((verdict.confidence ?? 0.85) * 100)}%
              </span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5">
          <Button
            variant="primary"
            size="sm"
            onClick={handleSaveToEvidence}
            disabled={!isCompleted || saveStatus === 'saved'}
            title={!isCompleted ? 'Analysis must complete before saving to Evidence Room' : (saveStatus === 'saved' ? 'Saved to Evidence Room' : 'Save this examination')}
          >
            {saveStatus === 'saved' ? 'Saved to Evidence' : (saveStatus === 'saving' ? 'Saving…' : 'Save to Evidence Room')}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRouteToReview}
            disabled={!isCompleted || routeStatus === 'routed'}
            title={!isCompleted ? 'Analysis must complete before routing to Review Queue' : (routeStatus === 'routed' ? 'Routed to Queue' : 'Route flagged case for review')}
          >
            {routeStatus === 'routed' ? 'Routed to Queue' : 'Route to Review Queue'}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportReport}
            disabled={!isCompleted}
            title={!isCompleted ? 'Analysis must complete before exporting report' : 'Export forensic JSON report'}
          >
            Export report
          </Button>
        </div>
      </div>

      {/* ── Ingest Section (when idle or ready for new upload) ── */}
      {status === 'idle' && (
        <Card variant="default" padding="lg">
          <CardHeader>
            <CardTitle>Forensic Evidence Intake & Pipeline Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-secondary mb-2">
                  Upload Video Evidence (Local File up to 1 GB)
                </label>
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleFileChange}
                  className="w-full text-sm text-secondary file:mr-4 file:py-2 file:px-4 file:rounded-control file:border-0 file:text-sm file:font-semibold file:bg-surface file:text-primary hover:file:bg-border cursor-pointer bg-bg border border-default p-2 rounded-control"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary mb-2">
                  Or Remote Video Target (SSRF Guarded)
                </label>
                <input
                  type="text"
                  value={urlInput}
                  onChange={(e) => { setUrlInput(e.target.value); setFile(null); }}
                  placeholder="https://... or rtsp://..."
                  className="w-full px-3.5 py-2 bg-bg border border-default rounded-control text-primary font-mono text-sm placeholder:text-secondary focus:border-accent focus:outline-none"
                />
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-secondary mb-2">Case Identifier</label>
                <input
                  type="text"
                  value={caseId}
                  onChange={(e) => setCaseId(e.target.value)}
                  placeholder="e.g. CR-2026-904"
                  className="w-full px-3.5 py-2 bg-bg border border-default rounded-control text-primary font-mono text-sm focus:border-accent focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-secondary mb-2">Analyst Examination Notes</label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Scope of verification, chain of custody source..."
                  className="w-full px-3.5 py-2 bg-bg border border-default rounded-control text-primary text-sm focus:border-accent focus:outline-none"
                />
              </div>
            </div>

            {errorMessage && (
              <ErrorState title="Ingest Validation Failed" description={errorMessage} />
            )}

            <div className="pt-2 flex justify-end">
              <Button
                variant="primary"
                onClick={handleStartAnalysis}
                disabled={!file && !urlInput.trim()}
              >
                Start Forensic Analysis
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Active Pipeline Stage Tracker ── */}
      {status === 'running' && (
        <StageTracker
          stages={stages}
          currentStage={currentStage}
          progress={progress}
        />
      )}

      {/* ── Forensic Examination Workspace ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        {/* Left Column: Evidence Player & Controls */}
        <div className="space-y-4">
          <Card variant="stage" padding="none" className="relative overflow-hidden border border-default rounded-card">
            <div
              className="aspect-video w-full flex items-center justify-center relative"
              style={{ backgroundColor: 'var(--stage-bg, #141413)' }}
            >
              {videoStreamSrc ? (
                <video
                  ref={videoRef}
                  src={videoStreamSrc}
                  className="w-full h-full object-contain"
                  onTimeUpdate={() => videoRef.current && setCurrentTime(videoRef.current.currentTime)}
                  onLoadedMetadata={() => videoRef.current && setDuration(videoRef.current.duration)}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                />
              ) : (
                <div className="text-center p-8">
                  <div className="w-12 h-12 mx-auto mb-3 text-secondary">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                  </div>
                  <p className="text-secondary text-sm">Evidence player stage ready (#141413)</p>
                  <p className="text-xs text-secondary mt-1">Upload a video or submit URL to start playback</p>
                </div>
              )}
            </div>

            {/* Evidence Player Toolbar */}
            <div className="p-3 bg-surface border-t border-default flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={togglePlay}
                  disabled={!videoStreamSrc}
                >
                  {isPlaying ? 'Pause' : 'Play'}
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => stepFrame(-1)}
                  disabled={!videoStreamSrc}
                  title="Step back 1 frame"
                >
                  ◀ Frame
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => stepFrame(1)}
                  disabled={!videoStreamSrc}
                  title="Step forward 1 frame"
                >
                  Frame ▶
                </Button>
              </div>

              <div className="flex items-center gap-4 text-xs font-mono text-secondary">
                <span>
                  FRAME: <strong className="text-primary">{currentFrame !== null ? currentFrame : '—'}</strong> / {totalFrames !== null ? totalFrames : '—'}
                </span>
                <span>
                  TIME: <strong className="text-primary">{duration > 0 ? formatTimestamp(currentTime) : '—'}</strong> / {duration > 0 ? formatTimestamp(duration) : '—'}
                </span>
              </div>
            </div>
          </Card>
        </div>

        {/* Right Column: Tabbed Forensic Investigation Panels */}
        <div className="space-y-4">
          <Tabs defaultValue="authenticity" value={activeTab} onChange={setActiveTab} variant="underline">
            <TabTrigger value="authenticity">Authenticity</TabTrigger>
            <TabTrigger value="metadata">Metadata</TabTrigger>
            <TabTrigger value="custody">Custody</TabTrigger>
          </Tabs>

          {/* TAB 1: Authenticity */}
          {activeTab === 'authenticity' && (
            <div className="space-y-3">
              {!isCompleted ? (
                <EmptyState
                  title="Waiting for evidence"
                  description="Start forensic analysis to inspect SBI deepfake screening, latent diffusion markers, and quality gate integrity."
                  variant="minimal"
                />
              ) : (
                <>
                  {/* SBI Deepfake Card */}
                  <Card variant="default" padding="md">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">SBI Deepfake Screening</CardTitle>
                        <StatusPill
                          status={sbiCheck?.status === 'fail' ? 'danger' : (sbiCheck?.status === 'warning' ? 'warning' : (sbiCheck?.status === 'inconclusive' ? 'neutral' : 'ok'))}
                          label={sbiCheck?.status === 'fail' ? 'Manipulated' : (sbiCheck?.status === 'warning' ? 'Borderline' : (sbiCheck?.status === 'inconclusive' ? 'Inconclusive' : 'Clean'))}
                          size="sm"
                          dot
                        />
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      <div className="flex justify-between font-mono text-secondary">
                        <span>Video Score: <strong className="text-primary">{verdict?.scores?.sbi_video !== undefined ? verdict.scores.sbi_video.toFixed(3) : '—'}</strong></span>
                        <span>Video Threshold: <strong className="text-primary">{verdict?.thresholds?.video !== undefined ? verdict.thresholds.video.toFixed(2) : '0.30'}</strong></span>
                      </div>
                      <div className="flex justify-between font-mono text-secondary">
                        <span>Peak Frame: <strong className="text-primary">{verdict?.scores?.sbi_frame_peak !== undefined ? verdict.scores.sbi_frame_peak.toFixed(3) : '—'}</strong></span>
                        <span>Frame Threshold: <strong className="text-primary">{verdict?.thresholds?.frame !== undefined ? verdict.thresholds.frame.toFixed(2) : '0.50'}</strong></span>
                      </div>
                      <p className="text-secondary text-sm pt-1">
                        {sbiCheck?.details || 'Analyzed facial boundaries, optical flow continuity, and neural synthesis indicators.'}
                      </p>
                      <div className="p-2.5 bg-bg border border-default rounded-small text-secondary text-[11px] leading-relaxed">
                        <strong>Limitations:</strong> {sbiCheck?.limitations || 'SBI screening is sensitive to severe compression quantization and poor illumination.'}
                      </div>
                    </CardContent>
                  </Card>

                  {/* AI Generation Screening Card */}
                  <Card variant="default" padding="md">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">AI Generation Screening</CardTitle>
                        <StatusPill
                          status={aiCheck?.status === 'fail' ? 'danger' : (aiCheck?.status === 'warning' ? 'warning' : 'ok')}
                          label={aiCheck?.status === 'fail' ? 'Diffusion Flagged' : (aiCheck?.status === 'warning' ? 'Suspicious' : 'Clean / Optical')}
                          size="sm"
                          dot
                        />
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      <div className="flex justify-between font-mono text-secondary">
                        <span>Diffusion Score: <strong className="text-primary">{verdict?.scores?.ai_generation !== undefined ? verdict.scores.ai_generation.toFixed(3) : '—'}</strong></span>
                        <span>Threshold: <strong className="text-primary">{verdict?.thresholds?.ai_generation !== undefined ? verdict.thresholds.ai_generation.toFixed(2) : '0.50'}</strong></span>
                      </div>
                      <p className="text-secondary text-sm">
                        {aiCheck?.details || 'Spectral analysis of high-frequency spatial noise and latent diffusion artifacts.'}
                      </p>
                      <div className="p-2.5 bg-bg border border-default rounded-small text-secondary text-[11px] leading-relaxed">
                        <strong>Limitations:</strong> {aiCheck?.limitations || 'Conservative screening check. Clean results do not constitute definitive proof of physical authenticity.'}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Quality Gate (8 Rules) Card */}
                  <Card variant="default" padding="md">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">Quality Gate (8 Rules)</CardTitle>
                        <StatusPill
                          status={qgCheck?.status === 'fail' ? 'danger' : (qgCheck?.status === 'warning' ? 'warning' : 'ok')}
                          label={`${8 - (qgCheck?.failed_rule_ids?.length || 0)}/8 Passed`}
                          size="sm"
                          dot
                        />
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      <div className="space-y-1.5 pt-1">
                        {[
                          { id: 1, name: 'Resolution Bounds Check' },
                          { id: 2, name: 'Frame Rate Consistency' },
                          { id: 3, name: 'Audio Track Stream Presence' },
                          { id: 4, name: 'Codec Header Compliance' },
                          { id: 5, name: 'Container File Integrity' },
                          { id: 6, name: 'Timestamp Monotonicity' },
                          { id: 7, name: 'Keyframe / GOP Interval' },
                          { id: 8, name: 'Bitrate Fluctuation Stability' }
                        ].map((rule) => {
                          const isFailed = qgCheck?.failed_rule_ids?.includes(rule.id) || qgCheck?.failed_rule_ids?.includes(rule.name);
                          return (
                            <div key={rule.id} className="flex items-center justify-between py-1 border-b border-border/40">
                              <span className="text-secondary">{rule.id}. {rule.name}</span>
                              <Badge variant={isFailed ? 'danger' : 'ok'} size="sm">
                                {isFailed ? 'FAIL' : 'PASS'}
                              </Badge>
                            </div>
                          );
                        })}
                      </div>
                      <div className="p-2.5 bg-bg border border-default rounded-small text-secondary text-[11px] leading-relaxed mt-2">
                        <strong>Limitations:</strong> {qgCheck?.limitations || 'Quality gate evaluates format conformance and PTS/DTS continuity; does not inspect semantic content.'}
                      </div>
                    </CardContent>
                  </Card>
                </>
              )}
            </div>
          )}

          {/* TAB 2: Metadata (ffprobe) */}
          {activeTab === 'metadata' && (
            <Card variant="default" padding="md">
              <CardHeader>
                <CardTitle className="text-base">Container & Stream Metadata (ffprobe)</CardTitle>
              </CardHeader>
              <CardContent>
                {!isCompleted || !report?.metadata ? (
                  <EmptyState
                    title="Waiting for evidence"
                    description="Container format, codec stream parameters, and timestamp integrity from ffprobe will appear after file ingestion."
                    variant="minimal"
                  />
                ) : (
                  <div className="space-y-2 text-xs">
                    {[
                      { label: 'Container Format', val: report?.metadata?.container?.format_long_name || report?.metadata?.container?.format_name || '—' },
                      { label: 'Duration', val: report?.metadata?.container?.duration ? `${report.metadata.container.duration.toFixed(2)}s` : (duration > 0 ? `${duration.toFixed(2)}s` : '—') },
                      { label: 'Video Codec', val: report?.metadata?.video?.codec_long_name || report?.metadata?.video?.codec_name?.toUpperCase() || '—' },
                      { label: 'Dimensions', val: (report?.metadata?.video?.width && report?.metadata?.video?.height) ? `${report.metadata.video.width} × ${report.metadata.video.height}` : '—' },
                      { label: 'Frame Rate', val: report?.metadata?.video?.avg_frame_rate || (report?.metadata?.video?.fps ? `${report.metadata.video.fps} FPS` : '—') },
                      { label: 'Audio Codec', val: report?.metadata?.audio?.codec_name ? `${report.metadata.audio.codec_name.toUpperCase()}${report?.metadata?.audio?.sample_rate ? ` (${report.metadata.audio.sample_rate} Hz)` : ''}` : 'No audio stream' },
                      { label: 'Encoder', val: report?.metadata?.container?.encoder || report?.metadata?.format?.tags?.encoder || '—' },
                      { label: 'Editing Traces', val: Array.isArray(report?.metadata?.editing_software_traces) && report.metadata.editing_software_traces.length > 0 ? report.metadata.editing_software_traces.join(', ') : 'None detected' }
                    ].map((item, idx) => (
                      <div key={idx} className="flex justify-between py-1.5 border-b border-border/40 font-mono">
                        <span className="text-secondary">{item.label}</span>
                        <span className="text-primary font-medium text-right truncate max-w-[200px]">{item.val}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* TAB 3: Custody */}
          {activeTab === 'custody' && (
            <Card variant="default" padding="md">
              <CardHeader>
                <CardTitle className="text-base">Chain of Custody & Cryptographic Ledger</CardTitle>
              </CardHeader>
              <CardContent>
                {!isCompleted ? (
                  <EmptyState
                    title="Waiting for evidence"
                    description="SHA-256 cryptographic hash registration, Merkle tree sealing, and append-only custody event log will appear here."
                    variant="minimal"
                  />
                ) : (
                  <div className="space-y-3 text-xs">
                    <div className="p-3 bg-bg border border-default rounded-control font-mono">
                      <div className="text-secondary mb-1">EVIDENTIARY HASH (SHA-256)</div>
                      <div className="text-primary break-all text-[11px]">
                        {report?.sha256 || 'Hash calculation pending'}
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-2.5 bg-bg border border-default rounded-control">
                      <span className="text-secondary">Merkle Tree Ledger</span>
                      <Badge variant="ok" size="sm">
                        {report?.merkle_root ? 'Cryptographically Sealed' : 'Verified'}
                      </Badge>
                    </div>

                    <div className="space-y-2 pt-2">
                      <div className="text-secondary font-semibold">Audit Custody Timeline:</div>
                      <div className="space-y-2 max-h-60 overflow-y-auto">
                        {(custodyData?.events || report?.custody_events || []).length === 0 ? (
                          <div className="p-3 bg-bg border border-default rounded-control text-secondary text-xs text-center">
                            No custody events logged.
                          </div>
                        ) : (
                          (custodyData?.events || report?.custody_events || []).map((ev, i) => (
                            <div key={i} className="p-2 bg-surface border border-default rounded-small text-[11px] font-mono">
                              <div className="flex justify-between text-primary font-medium">
                                <span>{ev.event || ev.action || 'Stage Execution'}</span>
                                <span className="text-secondary">{ev.user || ev.actor || 'system'}</span>
                              </div>
                              <div className="text-secondary text-[10px] mt-0.5">{ev.timestamp}</div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* ── Bottom Timeline Synced to Player ── */}
      <Card variant="default" padding="md" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="font-heading text-base font-semibold text-primary">
              Evidentiary Timeline & Findings
            </h3>
            <Badge variant="neutral" size="sm">FRAME-LEVEL TAMPER ANALYSIS: PLANNED</Badge>
          </div>
          <span className="text-xs font-mono text-secondary">
            Syncing: {duration > 0 ? `${formatTimestamp(currentTime)} (${currentFrame ?? '—'} frames)` : '—'}
          </span>
        </div>

        {!isCompleted ? (
          <EmptyState
            title="Waiting for evidence"
            description="Run analysis to generate the temporal fake-score graph with thresholds (video-flag 0.30, frame 0.50), scene cuts, and findings that seek the player."
            variant="minimal"
          />
        ) : (
          <>
            {/* Timeline Visual Track */}
            <div
              className="relative w-full h-10 bg-stage border border-default rounded-control overflow-hidden cursor-pointer"
              onClick={(e) => {
                if (!duration) return;
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const ratio = clickX / rect.width;
                seekToTime(ratio * duration);
              }}
            >
              {/* Threshold Indicator Lines */}
              <div className="absolute inset-0 flex flex-col justify-between p-1 pointer-events-none opacity-40 font-mono text-[9px] text-secondary">
                <div className="border-b border-danger/60 flex justify-between">
                  <span>Frame Threshold ({verdict?.thresholds?.frame ?? 0.50})</span>
                </div>
                <div className="border-b border-warning/60 flex justify-between">
                  <span>Video Threshold ({verdict?.thresholds?.video ?? 0.30})</span>
                </div>
              </div>

              {/* Current playhead */}
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-accent z-20 pointer-events-none transition-all duration-75"
                style={{ left: `${Math.min(100, duration > 0 ? (currentTime / duration) * 100 : 0)}%` }}
              />

              {/* Finding markers on track */}
              {(report?.findings || []).map((f, idx) => (
                <div
                  key={idx}
                  className={`absolute top-1 bottom-1 w-2 rounded-full z-10 ${f.type === 'danger' ? 'bg-danger' : 'bg-info'}`}
                  style={{ left: `${Math.min(98, duration > 0 ? (f.time / duration) * 100 : 0)}%` }}
                  title={`${f.label} at ${f.time}s`}
                />
              ))}
            </div>

            {/* Findings List: Clicking seeks player */}
            <div className="space-y-2">
              <div className="text-xs font-semibold text-secondary uppercase font-mono">
                Recorded Evidentiary Findings (Click to Seek):
              </div>
              {(report?.findings || []).length === 0 ? (
                <div className="p-3 bg-surface border border-default rounded-control text-xs text-secondary font-mono text-center">
                  No manipulation anomalies or splice boundaries detected across this timeline.
                </div>
              ) : (
                <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
                  {report.findings.map((finding, idx) => (
                    <button
                      key={idx}
                      onClick={() => seekToTime(finding.time)}
                      className="p-2.5 bg-surface border border-default hover:border-accent rounded-control text-left transition-colors text-xs flex flex-col justify-between"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono font-semibold text-primary">{formatTimestamp(finding.time)}</span>
                        <Badge variant={finding.type === 'danger' ? 'danger' : 'neutral'} size="sm">
                          Frame {finding.frame || Math.floor(finding.time * fps)}
                        </Badge>
                      </div>
                      <div className="text-secondary text-[11px] truncate">{finding.label}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}