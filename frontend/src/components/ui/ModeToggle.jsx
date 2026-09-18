import React from 'react';
import './ModeToggle.css';

export function ModeToggle({ mode, onChange, compact = false }) {
  return (
    <div className={`mode-toggle ${compact ? 'compact' : ''}`} role="group" aria-label="Analysis mode selector">
      <div className={`mode-toggle-track mode-toggle-track--${mode}`}>
        <div className={`mode-toggle-slider mode-toggle-slider--${mode}`} aria-hidden="true" />

        <button
          id="mode-general"
          className={`mode-toggle-btn ${mode === 'general' ? 'active' : ''}`}
          onClick={() => onChange('general')}
          aria-pressed={mode === 'general'}
        >
          <span className="mode-toggle-icon" aria-hidden="true">⬡</span>
          <span className="mode-toggle-label">General</span>
          {!compact && <span className="mode-toggle-sub">Video & YouTube</span>}
        </button>

        <button
          id="mode-cyber"
          className={`mode-toggle-btn ${mode === 'cyber' ? 'active' : ''}`}
          onClick={() => onChange('cyber')}
          aria-pressed={mode === 'cyber'}
        >
          <span className="mode-toggle-icon" aria-hidden="true">⬡</span>
          <span className="mode-toggle-label">Cyber</span>
          {!compact && <span className="mode-toggle-sub">Crime & Forensics</span>}
        </button>
      </div>
    </div>
  );
}