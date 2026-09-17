/**
 * AnalysisResultsCyber.jsx
 * Cyber mode forensic analysis results:
 * Threat score, suspicious timestamps, face detection, anomaly heatmap,
 * crime classification, metadata forensics, chain of custody.
 */
import { useEffect, useState } from 'react';
import './AnalysisResultsCyber.css';

/* ── Animated number ── */
function AnimatedNumber({ value, decimals = 0 }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    let start = 0;
    const duration = 1400;
    const step = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(parseFloat((eased * value).toFixed(decimals)));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [value, decimals]);
  return <>{display}</>;
}

/* ── Threat gauge ── */
function ThreatGauge({ score, level }) {
  const colors = { LOW: '#34d399', MEDIUM: '#fbbf24', HIGH: '#f97316', CRITICAL: '#ef4444' };
  const color = colors[level] ?? '#ef4444';
  const angle = -90 + (score / 100) * 180;

  return (
    <div className="cyber-gauge">
      <svg viewBox="0 0 200 120" className="cyber-gauge__svg">
        {/* Track */}
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="16" strokeLinecap="round" />
        {/* LOW zone */}
        <path d="M 20 100 A 80 80 0 0 1 80 28" fill="none" stroke="rgba(52,211,153,0.25)" strokeWidth="16" strokeLinecap="round" />
        {/* MEDIUM zone */}
        <path d="M 80 28 A 80 80 0 0 1 120 28" fill="none" stroke="rgba(251,191,36,0.25)" strokeWidth="16" strokeLinecap="round" />
        {/* HIGH zone */}
        <path d="M 120 28 A 80 80 0 0 1 180 100" fill="none" stroke="rgba(239,68,68,0.25)" strokeWidth="16" strokeLinecap="round" />
        {/* Score arc */}
        <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke={color}
          strokeWidth="16" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * 251} 251`}
          style={{ filter: `drop-shadow(0 0 8px ${color}88)` }} />
        {/* Needle */}
        <g transform={`rotate(${angle}, 100, 100)`}>
          <line x1="100" y1="100" x2="100" y2="32" stroke={color} strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="100" cy="100" r="5" fill={color} />
        </g>
        {/* Labels */}
        <text x="22"  y="115" fill="rgba(255,255,255,0.25)" fontSize="8" fontFamily="JetBrains Mono">LOW</text>
        <text x="100" y="18"  fill="rgba(255,255,255,0.25)" fontSize="8" fontFamily="JetBrains Mono" textAnchor="middle">MED</text>
        <text x="170" y="115" fill="rgba(255,255,255,0.25)" fontSize="8" fontFamily="JetBrains Mono" textAnchor="end">HIGH</text>
      </svg>
      <div className="cyber-gauge__score" style={{ color }}>
        <AnimatedNumber value={score} />
        <span className="cyber-gauge__score-sub">/100</span>
      </div>
      <div className="cyber-gauge__level" style={{ color, borderColor: `${color}44`, background: `${color}11` }}>
        {level} THREAT
      </div>
    </div>
  );
}

/* ── Severity badge ── */
function SeverityBadge({ level }) {
  const map = {
    critical: { label: '● CRITICAL', cls: 'sev-critical' },
    high:     { label: '● HIGH',     cls: 'sev-high'     },
    medium:   { label: '● MEDIUM',   cls: 'sev-medium'   },
    low:      { label: '● LOW',      cls: 'sev-low'      },
  };
  const m = map[level] ?? map.low;
  return <span className={`cyber-sev-badge ${m.cls}`}>{m.label}</span>;
}

export default function AnalysisResultsCyber({ data }) {
  if (!data) return null;

  const formatTs = (iso) => new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
  const formatTime = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  return (
    <div className="cres">
      {/* ── Evidence Header ── */}
      <div className="cres-evidence-header">
        <div className="cres-evidence-id">
          <span className="cres-evidence-label">CASE ID</span>
          <span className="cres-evidence-value">{data.caseId}</span>
        </div>
        <div className={`cres-integrity-badge ${data.integrityStatus === 'VERIFIED' ? 'verified' : 'failed'}`}>
          {data.integrityStatus === 'VERIFIED' ? '🔒 INTEGRITY VERIFIED' : '⚠ INTEGRITY FAILED'}
        </div>
        <div className="cres-hash-row">
          <span className="cres-hash-label">SHA-256</span>
          <span className="cres-hash-value">{data.evidenceHash.slice(0, 52)}…</span>
        </div>
      </div>

      {/* ── Threat Score Row ── */}
      <div className="cres-threat-row">
        <div className="cres-card cres-threat-gauge-card">
          <h3 className="cres-card__title">⚡ Threat Score</h3>
          <ThreatGauge score={data.threatScore} level={data.threatLevel} />
        </div>

        <div className="cres-card cres-stats-card">
          <h3 className="cres-card__title">📊 Evidence Stats</h3>
          <div className="cres-stat-grid">
            <div className="cres-stat">
              <span className="cres-stat-label">Duration</span>
              <span className="cres-stat-val">{Math.floor(data.duration / 60)}m {data.duration % 60}s</span>
            </div>
            <div className="cres-stat">
              <span className="cres-stat-label">Resolution</span>
              <span className="cres-stat-val">{data.resolution}</span>
            </div>
            <div className="cres-stat">
              <span className="cres-stat-label">Subjects</span>
              <span className="cres-stat-val"><AnimatedNumber value={data.faceDetection.length} /></span>
            </div>
            <div className="cres-stat">
              <span className="cres-stat-label">Incidents</span>
              <span className="cres-stat-val cres-stat-val--red"><AnimatedNumber value={data.suspiciousTimestamps.length} /></span>
            </div>
            <div className="cres-stat">
              <span className="cres-stat-label">Ingest Time</span>
              <span className="cres-stat-val" style={{ fontSize: '0.75rem' }}>{formatTs(data.ingestTimestamp)}</span>
            </div>
            <div className="cres-stat">
              <span className="cres-stat-label">Camera</span>
              <span className="cres-stat-val" style={{ fontSize: '0.7rem' }}>{data.metadataForensics.deviceMake.split(' ')[0]}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="cres-grid">
        {/* ── Suspicious Timestamps ── */}
        <div className="cres-card cres-card--wide">
          <h3 className="cres-card__title">🚨 Flagged Incidents</h3>
          <div className="cres-incidents">
            {data.suspiciousTimestamps.map((inc, i) => (
              <div key={i} className={`cres-incident cres-incident--${inc.severity}`}>
                <div className="cres-incident__time">{formatTime(inc.time)}</div>
                <div className="cres-incident__body">
                  <SeverityBadge level={inc.severity} />
                  <span className="cres-incident__label">{inc.label}</span>
                </div>
                <div className="cres-incident__conf">{(inc.confidence * 100).toFixed(0)}%</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Face Detection ── */}
        <div className="cres-card">
          <h3 className="cres-card__title">👤 Subject Detection</h3>
          <div className="cres-faces">
            {data.faceDetection.map((face) => (
              <div key={face.id} className={`cres-face cres-face--${face.status === 'DATABASE MATCH' ? 'match' : 'unknown'}`}>
                <div className="cres-face__avatar">
                  {face.status === 'DATABASE MATCH' ? '⚠' : '?'}
                </div>
                <div className="cres-face__info">
                  <span className="cres-face__id">{face.id}</span>
                  <span className="cres-face__meta">{face.appearances}× · {face.totalSeconds}s total</span>
                  <span className={`cres-face__status cres-face__status--${face.status === 'DATABASE MATCH' ? 'match' : face.status === 'PARTIAL' ? 'partial' : 'unknown'}`}>
                    {face.status}
                  </span>
                </div>
                {face.matchScore && (
                  <span className="cres-face__score">{(face.matchScore * 100).toFixed(0)}%</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* ── Anomaly Heatmap ── */}
        <div className="cres-card">
          <h3 className="cres-card__title">🔥 Activity Heatmap</h3>
          <div className="cres-heatmap">
            {data.anomalyHeatmap.map((zone) => {
              const intensity = zone.activityScore / 100;
              const r = Math.round(220 * intensity);
              const g = Math.round(38 * intensity);
              const color = `rgb(${r}, ${g}, 38)`;
              return (
                <div key={zone.zone} className="cres-heatmap-row">
                  <span className="cres-heatmap-zone">{zone.zone}</span>
                  <div className="cres-heatmap-bar">
                    <div
                      className="cres-heatmap-fill"
                      style={{
                        width: `${zone.activityScore}%`,
                        background: color,
                        boxShadow: `0 0 8px ${color}88`,
                      }}
                    />
                  </div>
                  <span className="cres-heatmap-score">{zone.activityScore}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Crime Classification ── */}
        <div className="cres-card">
          <h3 className="cres-card__title">📋 Crime Classification</h3>
          <div className="cres-classifications">
            {data.crimeClassification.map((cat, i) => (
              <div key={i} className="cres-classif-row">
                <span className="cres-classif-label">{cat.category}</span>
                <div className="cres-classif-bar">
                  <div
                    className="cres-classif-fill"
                    style={{ width: `${(cat.probability * 100).toFixed(0)}%` }}
                  />
                </div>
                <span className="cres-classif-prob">{(cat.probability * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Metadata Forensics ── */}
        <div className="cres-card">
          <h3 className="cres-card__title">🔬 Metadata Forensics</h3>
          <div className="cres-meta-grid">
            {[
              ['GPS',      data.metadataForensics.gpsCoordinates],
              ['Device',   data.metadataForensics.deviceMake],
              ['Codec',    data.metadataForensics.codec],
              ['Bitrate',  data.metadataForensics.bitrate],
              ['Created',  formatTs(data.metadataForensics.creationDate)],
            ].map(([k, v]) => (
              <div key={k} className="cres-meta-row">
                <span className="cres-meta-key">{k}</span>
                <span className="cres-meta-val">{v}</span>
              </div>
            ))}
          </div>
          {data.metadataForensics.tamperIndicators.length > 0 && (
            <div className="cres-tamper-warning">
              <span className="cres-tamper-title">⚠ Tamper Indicators Detected</span>
              {data.metadataForensics.tamperIndicators.map((t, i) => (
                <span key={i} className="cres-tamper-item">· {t}</span>
              ))}
            </div>
          )}
        </div>

        {/* ── Chain of Custody ── */}
        <div className="cres-card">
          <h3 className="cres-card__title">🔗 Chain of Custody</h3>
          <div className="cres-custody">
            {data.chainOfCustody.map((entry, i) => (
              <div key={i} className="cres-custody-entry">
                <div className="cres-custody-line">
                  <div className={`cres-custody-dot ${i === 0 ? 'first' : ''}`} />
                  {i < data.chainOfCustody.length - 1 && <div className="cres-custody-connector" />}
                </div>
                <div className="cres-custody-body">
                  <span className="cres-custody-action">{entry.action}</span>
                  <span className="cres-custody-actor">{entry.actor}</span>
                  <span className="cres-custody-time">{formatTs(entry.timestamp)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
