/**
 * VideoInsightsPanel.jsx
 * =====================
 * Video Insights cards showing real engine_profile data.
 * 
 * States per card: loading | empty | error | unavailable | data
 * No fake data — if data is null, shows "Analyzer unavailable" or empty state.
 * Clicking any timestamp item calls onSeek(seconds).
 */

import React, { useState } from 'react';
import './VideoInsightsPanel.css';

// ─── Utility ─────────────────────────────────────────────────────────────────

function fmt(n, decimals = 1) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return Number(n).toFixed(decimals);
}

function fmtTs(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${String(m).padStart(2, '0')}:${s.padStart(4, '0')}`;
}

// ─── Card primitives ─────────────────────────────────────────────────────────

function InsightCard({ title, icon, status, children, badge }) {
  return (
    <div className={`vi-card vi-card--${status || 'ok'}`}>
      <div className="vi-card__header">
        <span className="vi-card__icon">{icon}</span>
        <span className="vi-card__title">{title}</span>
        {badge && <span className={`vi-card__badge vi-card__badge--${badge.type}`}>{badge.label}</span>}
      </div>
      <div className="vi-card__body">{children}</div>
    </div>
  );
}

function UnavailableState({ reason }) {
  return (
    <div className="vi-unavailable">
      <span className="vi-unavailable__icon">⚠</span>
      <span className="vi-unavailable__text">Analyzer unavailable</span>
      {reason && <span className="vi-unavailable__reason">{reason}</span>}
    </div>
  );
}

function EmptyState({ message = 'No data' }) {
  return <div className="vi-empty">{message}</div>;
}

function LoadingState() {
  return (
    <div className="vi-loading">
      <span className="vi-loading__dot" />
      <span className="vi-loading__dot" />
      <span className="vi-loading__dot" />
      <span>Analyzing…</span>
    </div>
  );
}

// ─── Quality Card ────────────────────────────────────────────────────────────

function QualityCard({ quality, loading }) {
  if (loading) return <InsightCard title="Video Quality" icon="🎥"><LoadingState /></InsightCard>;
  if (!quality) return <InsightCard title="Video Quality" icon="🎥"><EmptyState message="No quality data" /></InsightCard>;

  const { avg_blur, avg_exposure, avg_contrast, black_frame_count, frozen_frame_count, warnings } = quality;

  function blurLabel(v) {
    if (v === null) return '—';
    if (v < 30) return `${fmt(v)} (blurry)`;
    if (v < 100) return `${fmt(v)} (moderate)`;
    return `${fmt(v)} (sharp)`;
  }

  return (
    <InsightCard
      title="Video Quality"
      icon="🎥"
      badge={warnings?.length > 0 ? { type: 'warn', label: `${warnings.length} warning${warnings.length > 1 ? 's' : ''}` } : null}
    >
      <dl className="vi-dl">
        <dt>Blur (Laplacian var.)</dt><dd>{blurLabel(avg_blur)}</dd>
        <dt>Avg. Exposure</dt><dd>{fmt(avg_exposure)} / 255</dd>
        <dt>Avg. Contrast (σ)</dt><dd>{fmt(avg_contrast)}</dd>
        <dt>Black frames</dt><dd>{black_frame_count ?? '—'}</dd>
        <dt>Frozen frames</dt><dd>{frozen_frame_count ?? '—'}</dd>
      </dl>
      {warnings?.length > 0 && (
        <ul className="vi-warnings">
          {warnings.map((w, i) => <li key={i} className="vi-warning-item">⚠ {w}</li>)}
        </ul>
      )}
    </InsightCard>
  );
}

// ─── Motion Card ─────────────────────────────────────────────────────────────

function MotionCard({ motion, loading, onSeek }) {
  if (loading) return <InsightCard title="Motion & Activity" icon="📊"><LoadingState /></InsightCard>;
  if (!motion) return <InsightCard title="Motion & Activity" icon="📊"><EmptyState /></InsightCard>;

  const { avg_activity, peaks, heatmap_available } = motion;

  return (
    <InsightCard title="Motion & Activity" icon="📊">
      <dl className="vi-dl">
        <dt>Avg. Activity</dt>
        <dd>
          <div className="vi-bar-wrap">
            <div className="vi-bar" style={{ width: `${Math.min(100, (avg_activity || 0) * 100)}%` }} />
          </div>
          {fmt(avg_activity * 100)}%
        </dd>
        <dt>Motion peaks</dt><dd>{peaks?.length ?? '—'}</dd>
        <dt>Heatmap</dt><dd>{heatmap_available ? '✔ Available' : 'Not computed'}</dd>
      </dl>
      {peaks?.length > 0 && (
        <div className="vi-chips-section">
          <div className="vi-chips-label">Peak timestamps</div>
          <div className="vi-chips">
            {peaks.slice(0, 12).map((ts, i) => (
              <button
                key={i}
                className="vi-chip vi-chip--motion"
                onClick={() => onSeek?.(ts)}
                title={`Seek to ${fmtTs(ts)}`}
              >
                {fmtTs(ts)}
              </button>
            ))}
          </div>
        </div>
      )}
    </InsightCard>
  );
}

// ─── Shots / Keyframes Card ───────────────────────────────────────────────────

function ShotsCard({ shots, loading, onSeek }) {
  if (loading) return <InsightCard title="Shots & Keyframes" icon="🎬"><LoadingState /></InsightCard>;
  if (!shots) return <InsightCard title="Shots & Keyframes" icon="🎬"><EmptyState /></InsightCard>;

  const { cut_count, scene_count, keyframe_timestamps } = shots;

  return (
    <InsightCard title="Shots & Keyframes" icon="🎬">
      <dl className="vi-dl">
        <dt>Cuts detected</dt><dd>{cut_count ?? '—'}</dd>
        <dt>Scenes</dt><dd>{scene_count ?? '—'}</dd>
      </dl>
      {keyframe_timestamps?.length > 0 && (
        <div className="vi-chips-section">
          <div className="vi-chips-label">Keyframe timestamps</div>
          <div className="vi-chips">
            {keyframe_timestamps.slice(0, 12).map((ts, i) => (
              <button
                key={i}
                className="vi-chip vi-chip--shot"
                onClick={() => onSeek?.(ts)}
                title={`Seek to ${fmtTs(ts)}`}
              >
                {fmtTs(ts)}
              </button>
            ))}
          </div>
        </div>
      )}
    </InsightCard>
  );
}

// ─── Faces Card ──────────────────────────────────────────────────────────────

function FacesCard({ faces, loading }) {
  if (loading) return <InsightCard title="Face Detection" icon="👤"><LoadingState /></InsightCard>;
  if (!faces) return <InsightCard title="Face Detection" icon="👤"><EmptyState /></InsightCard>;

  if (!faces.available) {
    return (
      <InsightCard title="Face Detection" icon="👤" status="unavailable">
        <UnavailableState reason={faces.reason} />
      </InsightCard>
    );
  }

  return (
    <InsightCard title="Face Detection" icon="👤">
      <dl className="vi-dl">
        <dt>Total instances detected</dt><dd>{faces.total_instances ?? '—'}</dd>
      </dl>
      <p className="vi-note">Detection only — no identification. Governance gated.</p>
    </InsightCard>
  );
}

// ─── Objects Card ─────────────────────────────────────────────────────────────

function ObjectsCard({ objects, loading }) {
  if (loading) return <InsightCard title="Object Detection" icon="📦"><LoadingState /></InsightCard>;
  if (!objects) return <InsightCard title="Object Detection" icon="📦"><EmptyState /></InsightCard>;

  if (!objects.available) {
    return (
      <InsightCard title="Object Detection" icon="📦" status="unavailable">
        <UnavailableState reason={objects.reason} />
      </InsightCard>
    );
  }

  const counts = objects.class_counts || {};
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  return (
    <InsightCard title="Object Detection" icon="📦">
      {sorted.length === 0
        ? <EmptyState message="No objects detected" />
        : (
          <ul className="vi-obj-list">
            {sorted.slice(0, 8).map(([label, count]) => (
              <li key={label} className="vi-obj-item">
                <span className="vi-obj-label">{label}</span>
                <span className="vi-obj-count">{count}</span>
              </li>
            ))}
          </ul>
        )}
    </InsightCard>
  );
}

// ─── Text / QR Card ──────────────────────────────────────────────────────────

function TextCard({ text, loading, onSeek }) {
  if (loading) return <InsightCard title="Text & QR Codes" icon="🔤"><LoadingState /></InsightCard>;
  if (!text) return <InsightCard title="Text & QR Codes" icon="🔤"><EmptyState /></InsightCard>;

  const { codes_detected, texts_detected, backends } = text;

  return (
    <InsightCard title="Text & QR Codes" icon="🔤">
      <dl className="vi-dl">
        <dt>QR / barcodes</dt><dd>{codes_detected ?? '—'}</dd>
        <dt>Text segments (OCR)</dt><dd>{texts_detected ?? '—'}</dd>
      </dl>
      {backends?.length > 0 && (
        <div className="vi-backends">
          {backends.map((b, i) => <span key={i} className="vi-backend-chip">{b}</span>)}
        </div>
      )}
    </InsightCard>
  );
}

// ─── Main Panel ───────────────────────────────────────────────────────────────

/**
 * VideoInsightsPanel
 * 
 * Props
 * -----
 * engine_insights : object from API response (null while loading)
 * loading         : bool
 * onSeek          : (seconds: number) => void  — called when user clicks a timestamp
 */
export function VideoInsightsPanel({ engine_insights, loading, onSeek }) {
  const ei = engine_insights || {};

  return (
    <div className="vi-panel">
      <h3 className="vi-panel__title">
        <span className="vi-panel__title-icon">⚡</span>
        Video Engine Insights
      </h3>

      <div className="vi-grid">
        <QualityCard quality={ei.quality} loading={loading} />
        <MotionCard motion={ei.motion} loading={loading} onSeek={onSeek} />
        <ShotsCard shots={ei.shots} loading={loading} onSeek={onSeek} />
        <FacesCard faces={ei.faces} loading={loading} />
        <ObjectsCard objects={ei.objects} loading={loading} />
        <TextCard text={ei.text} loading={loading} onSeek={onSeek} />
      </div>
    </div>
  );
}

export default VideoInsightsPanel;
