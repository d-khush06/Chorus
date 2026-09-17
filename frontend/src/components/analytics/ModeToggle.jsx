/**
 * ModeToggle.jsx
 * Animated dual-mode switcher between General and Cyber modes.
 */
import { useEffect, useRef } from 'react';
import './ModeToggle.css';

export default function ModeToggle({ mode, onChange }) {
  const sliderRef = useRef(null);

  return (
    <div className="mode-toggle" role="group" aria-label="Analysis mode selector">
      <div className={`mode-toggle__track mode-toggle__track--${mode}`}>
        <div className={`mode-toggle__slider mode-toggle__slider--${mode}`} aria-hidden="true" />

        <button
          id="mode-general"
          className={`mode-toggle__btn ${mode === 'general' ? 'active' : ''}`}
          onClick={() => onChange('general')}
          aria-pressed={mode === 'general'}
        >
          <span className="mode-toggle__icon">⬡</span>
          <span className="mode-toggle__label">General</span>
          <span className="mode-toggle__sub">Video & YouTube</span>
        </button>

        <button
          id="mode-cyber"
          className={`mode-toggle__btn ${mode === 'cyber' ? 'active' : ''}`}
          onClick={() => onChange('cyber')}
          aria-pressed={mode === 'cyber'}
        >
          <span className="mode-toggle__icon">⬡</span>
          <span className="mode-toggle__label">Cyber</span>
          <span className="mode-toggle__sub">Crime & Forensics</span>
        </button>
      </div>
    </div>
  );
}
