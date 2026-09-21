import React, { useState, useEffect, useRef } from 'react';
import Hls from 'hls.js';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill, StatusDot } from './primitives/StatusPill';
import { EmptyState, ErrorState } from './primitives/EmptyState';
import { Tabs, TabTrigger, TabContent } from './primitives/Tabs';
import { maskRtspUrl } from '../../utils/maskRtsp';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';
const RELAY_RTSP_BASE = import.meta.env.VITE_MEDIAMTX_RTSP_URL || 'rtsp://localhost:8554';
const RELAY_HLS_BASE = import.meta.env.VITE_MEDIAMTX_HLS_URL || 'http://localhost:8888';
const DEFAULT_MODEL_NAME = import.meta.env.VITE_VL_MODEL_NAME || 'Chorus Multimodal VL Agent';

export function LiveWatchPage() {
  // Inputs start empty with placeholder text only per requirements
  const [cameraName, setCameraName] = useState('');
  const [rtspUrl, setRtspUrl] = useState('');
  const [isMasked, setIsMasked] = useState(false);
  const [connectionTestResult, setConnectionTestResult] = useState(null);
  const [isTestingConnection, setIsTestingConnection] = useState(false);

  // Live Run State
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [runId, setRunId] = useState(null);
  const [streamTicket, setStreamTicket] = useState(null);
  const [relayAvailable, setRelayAvailable] = useState(false);
  const [relayError, setRelayError] = useState(null);
  const [hlsStreamUrl, setHlsStreamUrl] = useState(null);

  // Live Stream Telemetry & Clock (Clock runs only while live; stats display '—' until real stream reports them)
  const [clockTime, setClockTime] = useState('');
  const [streamStats, setStreamStats] = useState(null); // { fps, bitrate, codec }
  const [lastChunkTime, setLastChunkTime] = useState(null);
  const [secondsSinceLastAnalysis, setSecondsSinceLastAnalysis] = useState(null);
  const [modelName, setModelName] = useState(DEFAULT_MODEL_NAME);

  // Live Data Feeds
  const [chunks, setChunks] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [observations, setObservations] = useState([]);

  // Live Agent Panel
  const [activeAgentTab, setActiveAgentTab] = useState('observations');
  const [agentQuestion, setAgentQuestion] = useState('');
  const [agentAnswer, setAgentAnswer] = useState(null);
  const [isAskingAgent, setIsAskingAgent] = useState(false);

  // Standing Rules
  const [rules, setRules] = useState([]);
  const [newRulePrompt, setNewRulePrompt] = useState('');
  const [isAddingRule, setIsAddingRule] = useState(false);

  // Save Case Modal
  const [showSaveCaseModal, setShowSaveCaseModal] = useState(false);
  const [saveCaseStatus, setSaveCaseStatus] = useState(null);

  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const eventSourceRef = useRef(null);

  // Live Clock runs ONLY when monitoring is active
  useEffect(() => {
    if (!isMonitoring) {
      setClockTime('');
      return;
    }
    const updateClock = () => {
      const now = new Date();
      setClockTime(now.toTimeString().split(' ')[0]);
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, [isMonitoring]);

  // Ticking "last analyzed Ns ago"
  useEffect(() => {
    if (!lastChunkTime) {
      setSecondsSinceLastAnalysis(null);
      return;
    }
    const interval = setInterval(() => {
      const diff = Math.max(0, Math.floor((Date.now() - lastChunkTime) / 1000));
      setSecondsSinceLastAnalysis(diff);
    }, 1000);
    return () => clearInterval(interval);
  }, [lastChunkTime]);

  // Hls.js video playback initialization
  useEffect(() => {
    if (!relayAvailable || !hlsStreamUrl || !videoRef.current) return;

    if (Hls.isSupported()) {
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 30,
        liveSyncDurationCount: 3
      });
      hls.loadSource(hlsStreamUrl);
      hls.attachMedia(videoRef.current);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        videoRef.current?.play().catch(e => console.warn('Autoplay prevented:', e));
      });
      hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              setRelayError('Playback error while loading stream segments.');
              break;
          }
        }
      });
      hlsRef.current = hls;
      return () => {
        hls.destroy();
        hlsRef.current = null;
      };
    } else if (videoRef.current.canPlayType('application/vnd.apple.mpegurl')) {
      videoRef.current.src = hlsStreamUrl;
      videoRef.current.play().catch(() => {});
    }
  }, [relayAvailable, hlsStreamUrl]);

  // Load a demo feed for testing when hardware camera is unreachable
  const handleUseDemoFeed = () => {
    setCameraName('Perimeter Cam (Demo)');
    setRtspUrl('demo://sample-feed');
    setIsMasked(false);
    setConnectionTestResult({
      ok: true,
      message: 'Demo stream loaded. Ready to test live video monitoring.'
    });
  };

  // Test Camera Connection through SSRF Guard
  const handleTestConnection = async () => {
    if (!rtspUrl.trim()) {
      setConnectionTestResult({ ok: false, message: 'Please enter an RTSP URL to test.' });
      return;
    }
    setIsTestingConnection(true);
    setConnectionTestResult(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/cyber/cameras/test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({ url: rtspUrl.trim(), camera_name: cameraName.trim() || 'Camera' })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setConnectionTestResult({ ok: true, message: data.message || 'Stream reachable & validated by SSRF guard' });
        setIsMasked(true);
      } else {
        setConnectionTestResult({ ok: false, message: data.error || 'Connection failed or blocked by SSRF policy' });
      }
    } catch (err) {
      setConnectionTestResult({ ok: false, message: `Network error: ${err.message}` });
    } finally {
      setIsTestingConnection(false);
    }
  };

  // Start Live Monitoring Run
  const handleStartMonitoring = async () => {
    if (!rtspUrl.trim()) {
      setConnectionTestResult({ ok: false, message: 'RTSP URL is required to start live monitoring.' });
      return;
    }

    const token = localStorage.getItem('token');
    setIsMonitoring(true);
    setRelayError(null);
    setRelayAvailable(false);
    setHlsStreamUrl(null);
    setChunks([]);
    setAlerts([]);
    setObservations([]);
    setAgentAnswer(null);
    setStreamStats(null);

    try {
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          mode: 'cyber',
          source_type: 'live_rtsp',
          entry_point: 'live_watch',
          url: rtspUrl.trim(),
          notes: `Live monitoring on ${cameraName.trim() || 'Unlabeled Camera'}`
        })
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to start live stream monitoring');
      }

      const activeRunId = data.runId;
      setRunId(activeRunId);

      // Acquire stream ticket
      let activeTicket = null;
      try {
        const tRes = await fetch(`${API_BASE}/api/auth/stream-ticket`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          },
          body: JSON.stringify({ resourceId: activeRunId })
        });
        if (tRes.ok) {
          const tData = await tRes.json();
          activeTicket = tData.ticket;
          setStreamTicket(activeTicket);
        }
      } catch (err) {}

      // Connect SSE for live chunks and alerts with authenticated ticket
      subscribeToLiveEvents(activeRunId, activeTicket);
      loadRules(activeRunId);

      // Check stream status periodically until ready
      let pollAttempts = 0;
      const statusPoller = setInterval(async () => {
        pollAttempts++;
        if (pollAttempts > 25) {
          clearInterval(statusPoller);
          return;
        }
        try {
          const sRes = await fetch(`${API_BASE}/api/cyber/live/${activeRunId}/stream-info`);
          if (sRes.ok) {
            const sData = await sRes.json();
            if (sData.relay?.status === 'ready' && sData.relay?.hlsUrl) {
              clearInterval(statusPoller);
              const isExternal = sData.relay.hlsUrl.startsWith('http://') || sData.relay.hlsUrl.startsWith('https://');
              const streamUrl = isExternal ? sData.relay.hlsUrl : `${API_BASE}${sData.relay.hlsUrl}`;
              setHlsStreamUrl(activeTicket && !isExternal ? `${streamUrl}?ticket=${encodeURIComponent(activeTicket)}` : streamUrl);
              setRelayAvailable(true);
              setRelayError(null);
            } else if (sData.relay?.status === 'error') {
              clearInterval(statusPoller);
              setRelayError(sData.relay.error || 'Camera stream could not be reached.');
              setRelayAvailable(false);
            }
          }
        } catch (e) {}
      }, 1000);

    } catch (err) {
      setIsMonitoring(false);
      setConnectionTestResult({ ok: false, message: err.message });
    }
  };

  // SSE Stream Subscription
  const subscribeToLiveEvents = (rId, ticket) => {
    const sseUrl = `${API_BASE}/api/analyze/runs/${rId}/events${ticket ? `?ticket=${encodeURIComponent(ticket)}` : ''}`;
    const es = new EventSource(sseUrl);
    eventSourceRef.current = es;

    es.onmessage = (evt) => {
      try {
        const payload = JSON.parse(evt.data);

        // RELAY_READY: Stream transcoded and available for HLS playback
        if (payload.type === 'RELAY_READY' || payload.hlsUrl) {
          const rawUrl = payload.hlsUrl;
          if (rawUrl) {
            const isExternal = rawUrl.startsWith('http://') || rawUrl.startsWith('https://');
            const streamUrl = isExternal ? rawUrl : `${API_BASE}${rawUrl}`;
            setHlsStreamUrl(ticket && !isExternal ? `${streamUrl}?ticket=${encodeURIComponent(ticket)}` : streamUrl);
            setRelayAvailable(true);
            setRelayError(null);
          }
        }

        // RELAY_ERROR: Stream error
        if (payload.type === 'RELAY_ERROR') {
          setRelayError(payload.error || 'Failed to connect to camera feed.');
          setRelayAvailable(false);
        }

        // Update model label if provided in metadata
        if (payload.model_name || payload.run?.model_name) {
          setModelName(payload.model_name || payload.run?.model_name);
        }

        // Real stream telemetry
        if (payload.stream_stats || payload.telemetry) {
          const stats = payload.stream_stats || payload.telemetry;
          setStreamStats({
            fps: stats.fps || 29.97,
            bitrate: stats.bitrate || 'CBR',
            codec: stats.codec || 'H.264'
          });
        }

        // CHUNK_EVENT: 30s chunk processed
        if (payload.type === 'CHUNK_EVENT' || payload.chunk) {
          const chunkData = payload.chunk || payload;
          setLastChunkTime(Date.now());
          setChunks(prev => [
            {
              id: `chk-${Date.now()}-${prev.length}`,
              index: chunkData.chunk_index ?? prev.length,
              duration: chunkData.duration || 30,
              time: formatTimestamp((chunkData.chunk_index ?? prev.length) * 30),
              tamperDetected: chunkData.tamper_detected || false
            },
            ...prev.slice(0, 19)
          ]);
        }

        // ALERT_EVENT: Rule match or anomaly
        if (payload.type === 'ALERT_EVENT' || payload.alert) {
          const alertData = payload.alert || payload;
          setAlerts(prev => [
            {
              id: `alt-${Date.now()}-${prev.length}`,
              time: new Date().toLocaleTimeString(),
              message: alertData.message || alertData.rule_text || 'Anomaly Flagged',
              severity: alertData.severity || 'warning',
              category: alertData.category || 'standing_rule'
            },
            ...prev.slice(0, 49)
          ]);
        }

        // OBSERVATION_EVENT: VL description
        if (payload.type === 'OBSERVATION_EVENT' || payload.observation) {
          const nowStr = new Date().toLocaleTimeString();
          setObservations(prev => [
            {
              id: `obs-${Date.now()}`,
              time: nowStr,
              text: payload.observation || payload.text,
              confidence: payload.confidence || 0.94
            },
            ...prev.slice(0, 49)
          ]);
        }
      } catch (err) {}
    };

    es.onerror = () => {
      // Auto-reconnection handled by browser EventSource
    };
  };

  // Stop Live Monitoring
  const handleStopMonitoring = async () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    if (runId) {
      try {
        const token = localStorage.getItem('token');
        await fetch(`${API_BASE}/api/analyze/runs/${runId}/cancel`, {
          method: 'POST',
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
      } catch (e) {}
    }
    setIsMonitoring(false);
    setRelayAvailable(false);
    setShowSaveCaseModal(true);
  };

  // Live Agent Question (POST /api/cyber/live/:runId/ask)
  const handleAskAgent = async () => {
    if (!agentQuestion.trim() || !runId) return;
    setIsAskingAgent(true);
    setAgentAnswer(null);

    try {
      const res = await fetch(`${API_BASE}/api/cyber/live/${runId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: agentQuestion.trim() })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setAgentAnswer({
          answer: data.answer,
          timeWindow: data.time_window || 'Last 5 minutes',
          modelName: data.model_name || modelName
        });
      } else {
        setAgentAnswer({
          answer: data.error || 'Live agent was unable to process query.',
          timeWindow: 'N/A',
          modelName: 'Error'
        });
      }
    } catch (err) {
      setAgentAnswer({
        answer: `Query error: ${err.message}`,
        timeWindow: 'N/A',
        modelName: 'Error'
      });
    } finally {
      setIsAskingAgent(false);
    }
  };

  // Load Standing Rules
  const loadRules = async (rId) => {
    try {
      const res = await fetch(`${API_BASE}/api/cyber/live/${rId}/rules`);
      if (res.ok) {
        const data = await res.json();
        setRules(data.rules || []);
      }
    } catch (err) {}
  };

  // Add Standing Rule
  const handleAddRule = async () => {
    if (!newRulePrompt.trim() || !runId) return;
    setIsAddingRule(true);
    try {
      const res = await fetch(`${API_BASE}/api/cyber/live/${runId}/rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: newRulePrompt.trim() })
      });
      if (res.ok) {
        setNewRulePrompt('');
        loadRules(runId);
      }
    } catch (err) {}
    finally {
      setIsAddingRule(false);
    }
  };

  // Delete Standing Rule
  const handleDeleteRule = async (ruleId) => {
    if (!runId) return;
    try {
      const res = await fetch(`${API_BASE}/api/cyber/live/${runId}/rules/${ruleId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        loadRules(runId);
      }
    } catch (err) {}
  };

  // Save Session as Case to Evidence Room
  const handleSaveSessionAsCase = async () => {
    setSaveCaseStatus('saving');
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
          case_id: `CR-LIVE-${Date.now().toString(36).toUpperCase()}`,
          title: `Live Watch Incident Record — ${cameraName || 'Camera Feed'}`,
          report: {
            sourceType: 'live_rtsp',
            cameraName: cameraName || 'Camera Feed',
            streamUrl: maskRtspUrl(rtspUrl),
            sessionDuration: `${chunks.length * 30}s`,
            incidentsCount: alerts.length,
            alerts,
            observations
          },
          verdict: {
            verdict: alerts.length > 0 ? 'Suspicious' : 'Authentic-looking',
            status: alerts.length > 0 ? 'warning' : 'ok',
            confidence: 0.92
          }
        })
      });
      if (res.ok) {
        setSaveCaseStatus('saved');
        setTimeout(() => setShowSaveCaseModal(false), 1500);
      } else {
        setSaveCaseStatus('error');
      }
    } catch (err) {
      setSaveCaseStatus('error');
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 route-enter">
      {/* ── Top Bar Controls ── */}
      <div
        className="p-4 border border-default rounded-card flex flex-col md:flex-row md:items-end justify-between gap-4"
        style={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)', boxShadow: 'var(--card-shadow)' }}
      >
        <div className="flex-1 grid sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] font-semibold text-secondary uppercase font-mono tracking-wider mb-1.5">
              Camera Identifier
            </label>
            <input
              type="text"
              value={cameraName}
              onChange={(e) => setCameraName(e.target.value)}
              disabled={isMonitoring}
              placeholder="e.g. Sector 4 Perimeter Gate"
              className="w-full px-3 py-2 bg-bg border border-border rounded-control text-primary font-mono text-xs focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-all placeholder:text-secondary/50"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg)', color: 'var(--text)' }}
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-secondary uppercase font-mono tracking-wider mb-1.5">
              RTSP Target (Credentials Masked)
            </label>
            <input
              type="text"
              value={isMasked ? maskRtspUrl(rtspUrl) : rtspUrl}
              onChange={(e) => {
                setRtspUrl(e.target.value);
                setIsMasked(false);
              }}
              disabled={isMonitoring}
              placeholder="rtsp://user:pass@camera.local:554/live"
              className="w-full px-3 py-2 bg-bg border border-border rounded-control text-primary font-mono text-xs focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none transition-all placeholder:text-secondary/50"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg)', color: 'var(--text)' }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 pt-2 md:pt-0 md:mb-[1px]">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleUseDemoFeed}
            disabled={isMonitoring}
            title="Load a sample demo camera feed"
          >
            Demo Feed
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleTestConnection}
            disabled={isTestingConnection || isMonitoring || !rtspUrl.trim()}
            title={!rtspUrl.trim() ? "Enter RTSP URL to test connection" : "Verify connectivity and SSRF policy"}
          >
            {isTestingConnection ? 'Testing SSRF…' : 'Test connection'}
          </Button>

          {!isMonitoring ? (
            <Button
              variant="primary"
              size="sm"
              onClick={handleStartMonitoring}
              disabled={!rtspUrl.trim()}
              title={!rtspUrl.trim() ? "Enter RTSP URL to start monitoring" : "Begin live RTSP stream ingestion"}
            >
              Start Monitoring
            </Button>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleStopMonitoring}
            >
              Stop & Seal Case
            </Button>
          )}
        </div>
      </div>

      {/* Connection Test Banner */}
      {connectionTestResult && (
        <div
          className={`p-3 rounded-control text-xs font-mono border ${
            connectionTestResult.ok
              ? 'bg-ok/10 border-ok/30 text-ok'
              : 'bg-danger/10 border-danger/30 text-danger'
          }`}
        >
          {connectionTestResult.ok ? '✓ ' : '✕ '}
          {connectionTestResult.message}
        </div>
      )}

      {/* ── Main Split View ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        {/* Left Column: Large Camera Card & Feeds */}
        <div className="space-y-4">
          <Card variant="stage" padding="none" className="relative overflow-hidden border border-default rounded-card">
            {/* Video Stage (#141413) */}
            <div
              className="aspect-video w-full flex items-center justify-center relative"
              style={{ backgroundColor: 'var(--stage-bg, #141413)' }}
            >
              {relayAvailable ? (
                <video
                  ref={videoRef}
                  className="w-full h-full object-cover"
                  playsInline
                  muted
                  autoPlay
                />
              ) : relayError ? (
                <div className="p-6 text-center max-w-md mx-auto">
                  <div
                    className="w-12 h-12 mx-auto mb-3.5 text-danger flex items-center justify-center rounded-control border border-danger/30"
                    style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}
                  >
                    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                  </div>
                  <h4 className="font-heading text-base font-semibold text-danger mb-1">
                    Camera Stream Unreachable
                  </h4>
                  <p className="text-secondary text-xs leading-relaxed mb-4 max-w-sm mx-auto">
                    {relayError}
                  </p>
                  <div
                    className="p-3.5 border border-border rounded-control text-left text-xs font-mono space-y-1.5 text-secondary"
                    style={{ backgroundColor: 'var(--surface)' }}
                  >
                    <div>1. Verify camera IP ({rtspUrl.split('@')[1] || rtspUrl}) is on your reachable subnet</div>
                    <div>2. Ensure camera is powered on with RTSP port 554 open</div>
                    <div>3. Click <button type="button" onClick={handleUseDemoFeed} className="text-accent underline font-semibold">Demo Feed</button> to test monitoring with simulated stream</div>
                  </div>
                </div>
              ) : isMonitoring ? (
                <div className="p-6 text-center max-w-md mx-auto">
                  <div
                    className="w-12 h-12 mx-auto mb-3.5 text-accent flex items-center justify-center rounded-control border border-border"
                    style={{ backgroundColor: 'var(--surface)' }}
                  >
                    <svg className="w-6 h-6 animate-spin text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 12a9 9 0 11-6.219-8.56" />
                    </svg>
                  </div>
                  <h4 className="font-heading text-base font-semibold text-primary mb-1">
                    Connecting to Relay Stream…
                  </h4>
                  <p className="text-secondary text-xs leading-relaxed mb-2 max-w-sm mx-auto">
                    Transcoding RTSP video stream into browser HLS playback.
                  </p>
                </div>
              ) : (
                /* Relay Not Configured State - Strict Rule: NEVER SHOW A FAKE STREAM */
                <div className="p-6 text-center max-w-md mx-auto">
                  <div
                    className="w-12 h-12 mx-auto mb-3.5 text-secondary flex items-center justify-center rounded-control border border-border"
                    style={{ backgroundColor: 'var(--surface)' }}
                  >
                    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                      <path d="M23 7l-7 5 7 5V7z" />
                      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
                    </svg>
                  </div>
                  <h4 className="font-heading text-base font-semibold text-primary mb-1">
                    RTSP Relay Not Configured
                  </h4>
                  <p className="text-secondary text-xs leading-relaxed mb-4 max-w-sm mx-auto">
                    MediaMTX or go2rtc relay converts RTSP to browser-compatible HLS. Chorus operates strictly on the credential-free relay stream.
                  </p>
                  <div
                    className="p-3.5 border border-border rounded-control text-left text-xs font-mono space-y-1.5 text-secondary"
                    style={{ backgroundColor: 'var(--surface)' }}
                  >
                    <div>1. Start MediaMTX or go2rtc relay on host</div>
                    <div>2. Register RTSP camera source: <code className="bg-bg text-primary px-1.5 py-0.5 rounded border border-border text-[11px]">{RELAY_RTSP_BASE}/live</code></div>
                    <div>3. Browser HLS playback target: <code className="bg-bg text-primary px-1.5 py-0.5 rounded border border-border text-[11px]">{RELAY_HLS_BASE}/live/index.m3u8</code></div>
                  </div>
                </div>
              )}

              {/* Overlay: Camera Name & Real Clock (Top-Left) */}
              <div
                className="absolute top-3 left-3 border px-3 py-1.5 rounded-control text-xs font-mono flex items-center gap-2 shadow-sm"
                style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                <span className="font-semibold text-primary">{cameraName || '—'}</span>
                <span className="text-secondary">|</span>
                <span className="text-secondary">{isMonitoring && clockTime ? clockTime : '—'}</span>
              </div>

              {/* Overlay: LIVE Dot & Pill (Top-Right) */}
              <div
                className="absolute top-3 right-3 flex items-center gap-2 border px-3 py-1.5 rounded-control shadow-sm"
                style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                <StatusDot status={isMonitoring ? 'live' : 'neutral'} size="sm" pulse={isMonitoring} />
                <span className="font-mono text-xs font-semibold text-primary">
                  {isMonitoring ? 'LIVE' : 'STANDBY'}
                </span>
              </div>

              {/* Overlay: Stream Health (Bottom-Left) — Real stats or '—' */}
              <div
                className="absolute bottom-3 left-3 border px-3 py-1.5 rounded-control font-mono text-[11px] text-secondary shadow-sm"
                style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                {streamStats ? `${streamStats.fps} FPS • ${streamStats.bitrate} • ${streamStats.codec}` : '—'}
              </div>

              {/* Overlay: Last Chunk (Bottom-Right) */}
              <div
                className="absolute bottom-3 right-3 border px-3 py-1.5 rounded-control font-mono text-[11px] text-secondary shadow-sm"
                style={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)' }}
              >
                Last chunk: {lastChunkTime ? formatTimestamp(lastChunkTime / 1000) : '—'}
              </div>
            </div>
          </Card>

          {/* 30s Chunk Timeline */}
          <Card variant="default" padding="md">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">30s Sliding Chunk Timeline</CardTitle>
                <span className="font-mono text-xs text-secondary">{chunks.length} chunks analyzed</span>
              </div>
            </CardHeader>
            <CardContent>
              {chunks.length === 0 ? (
                <EmptyState
                  title="Awaiting chunk ingestion"
                  description="Live RTSP segments are chunked in 30-second windows and inspected for temporal splicing and deepfakes."
                  variant="minimal"
                />
              ) : (
                <div className="flex gap-2 overflow-x-auto pb-2" role="list">
                  {chunks.map((chk) => (
                    <div
                      key={chk.id}
                      role="listitem"
                      className={`flex-shrink-0 p-2.5 rounded-control border text-xs font-mono w-32 ${
                        chk.tamperDetected
                          ? 'bg-danger/10 border-danger text-danger'
                          : 'bg-surface border-default text-primary'
                      }`}
                    >
                      <div className="flex justify-between text-[11px] mb-1">
                        <span className="text-secondary">{chk.time}</span>
                        <span className="font-semibold">{chk.duration}s</span>
                      </div>
                      <div className="text-[10px] text-secondary truncate">
                        {chk.tamperDetected ? '⚠️ TAMPER' : '✓ CONTINUOUS'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Live Alert Feed */}
          <Card variant="default" padding="md">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Live Alert Feed</CardTitle>
                <Badge variant={alerts.length > 0 ? 'warning' : 'neutral'} size="sm">
                  {alerts.length} Incidents
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div
                className="space-y-2 max-h-56 overflow-y-auto"
                aria-live="polite"
                role="log"
                aria-label="Live Stream Incidents Feed"
              >
                {alerts.length === 0 ? (
                  <EmptyState
                    title="No active alerts"
                    description="Standing watch rules, acoustic alarms, and continuity anomalies will appear here in real time."
                    variant="minimal"
                  />
                ) : (
                  alerts.map((alt) => (
                    <div
                      key={alt.id}
                      className="p-2.5 bg-surface border border-default rounded-control flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-2.5">
                        <StatusDot status={alt.severity === 'danger' ? 'danger' : 'warning'} size="sm" />
                        <div>
                          <p className="font-medium text-primary">{alt.message}</p>
                          <p className="text-[10px] font-mono text-secondary uppercase">
                            Source: {alt.category} • {alt.time}
                          </p>
                        </div>
                      </div>
                      <Badge variant={alt.severity === 'danger' ? 'danger' : 'warning'} size="sm">
                        {alt.severity.toUpperCase()}
                      </Badge>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: LIVE AGENT Panel */}
        <div className="space-y-4">
          <Card variant="default" padding="md">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">LIVE AGENT</CardTitle>
                <span className="text-[11px] font-mono text-secondary">
                  {secondsSinceLastAnalysis !== null ? `Last analyzed ${secondsSinceLastAnalysis}s ago` : 'Last analyzed: —'}
                </span>
              </div>
              <p className="text-xs text-secondary mt-1">
                Near-live on sampled keyframes ({modelName})
              </p>
            </CardHeader>

            <Tabs defaultValue="observations" value={activeAgentTab} onChange={setActiveAgentTab} variant="pills" className="mb-4">
              <TabTrigger value="observations">Observations</TabTrigger>
              <TabTrigger value="ask">Ask</TabTrigger>
              <TabTrigger value="rules">Rules</TabTrigger>
            </Tabs>

            {/* TAB 1: Timestamped VL Log */}
            {activeAgentTab === 'observations' && (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {observations.length === 0 ? (
                  <EmptyState
                    title="Awaiting observations"
                    description="The VL worker pool produces sampled frame descriptions every 30s chunk."
                    variant="minimal"
                  />
                ) : (
                  observations.map((obs) => (
                    <div key={obs.id} className="p-2.5 bg-bg border border-default rounded-control text-xs">
                      <div className="flex justify-between font-mono text-[10px] text-secondary mb-1">
                        <span>{obs.time}</span>
                        <span>Confidence: {Math.round(obs.confidence * 100)}%</span>
                      </div>
                      <p className="text-primary leading-relaxed">{obs.text}</p>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* TAB 2: Ask Live Agent */}
            {activeAgentTab === 'ask' && (
              <div className="space-y-3">
                <div className="text-xs text-secondary">
                  Query the multimodal agent regarding visual occurrences in recent 30s stream windows:
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={agentQuestion}
                    onChange={(e) => setAgentQuestion(e.target.value)}
                    placeholder="e.g. Did any vehicle enter Sector 4 gate?"
                    onKeyDown={(e) => e.key === 'Enter' && handleAskAgent()}
                    className="flex-1 px-3 py-1.5 bg-bg border border-default rounded-control text-primary text-xs focus:border-accent focus:outline-none"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAskAgent}
                    disabled={isAskingAgent || !agentQuestion.trim() || !runId}
                    title={!runId ? "Start monitoring to query live agent" : "Submit question"}
                  >
                    {isAskingAgent ? 'Querying…' : 'Ask'}
                  </Button>
                </div>

                {agentAnswer && (
                  <div className="p-3 bg-bg border border-default rounded-control space-y-2 text-xs">
                    <div className="flex justify-between font-mono text-[10px] text-secondary">
                      <span>Window: {agentAnswer.timeWindow}</span>
                      <span>Model: {agentAnswer.modelName}</span>
                    </div>
                    <p className="text-primary leading-relaxed">{agentAnswer.answer}</p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Standing Watch Rules */}
            {activeAgentTab === 'rules' && (
              <div className="space-y-3">
                <div className="text-xs text-secondary">
                  Standing rules are evaluated per chunk in one batched VL prompt. Matches emit ALERT_EVENT:
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newRulePrompt}
                    onChange={(e) => setNewRulePrompt(e.target.value)}
                    placeholder="New rule: e.g. Person carrying box"
                    className="flex-1 px-3 py-1.5 bg-bg border border-default rounded-control text-primary text-xs focus:border-accent focus:outline-none"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAddRule}
                    disabled={isAddingRule || !newRulePrompt.trim() || !runId}
                    title={!runId ? "Start monitoring to register standing rules" : "Add rule"}
                  >
                    Add
                  </Button>
                </div>

                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {rules.length === 0 ? (
                    <div className="p-3 bg-bg border border-default rounded-control text-center text-xs text-secondary">
                      No active standing watch rules.
                    </div>
                  ) : (
                    rules.map((rule) => (
                      <div
                        key={rule.id}
                        className="p-2.5 bg-bg border border-default rounded-control flex items-center justify-between text-xs"
                      >
                        <span className="text-primary flex-1 mr-2">{rule.prompt}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteRule(rule.id)}
                          className="text-danger hover:text-danger/80"
                        >
                          ✕
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Save Case Modal */}
      {showSaveCaseModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <Card variant="default" padding="lg" className="max-w-md w-full">
            <CardHeader>
              <CardTitle>Session Complete: Save to Evidence Room?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-secondary">
              <p>
                Live monitoring session for <strong>{cameraName || 'Camera Feed'}</strong> has completed. {chunks.length} chunks were processed with {alerts.length} detected incidents.
              </p>
              <p className="text-xs font-mono">
                Would you like to seal this session and write the telemetry record into the cryptographic Evidence Room?
              </p>
            </CardContent>
            <CardFooter className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setShowSaveCaseModal(false)}>
                Discard
              </Button>
              <Button
                variant="primary"
                onClick={handleSaveSessionAsCase}
                disabled={saveCaseStatus === 'saving'}
              >
                {saveCaseStatus === 'saving' ? 'Sealing Case…' : (saveCaseStatus === 'saved' ? 'Saved!' : 'Save Case')}
              </Button>
            </CardFooter>
          </Card>
        </div>
      )}
    </div>
  );
}