/**
 * AnalyticsPage.jsx — Enterprise Edition
 * Universal Video Analytics Intelligence Platform
 * Elegant, minimalist, and professional multinational design.
 */
import { useState, useCallback, useEffect, useRef, useContext } from 'react';
import { runMockAnalysis } from '../data/analyticsMock.js';
import AuthContext from '../context/AuthContext.jsx';
import AnalysisResultsGeneral from '../components/analytics/AnalysisResultsGeneral.jsx';
import AnalysisResultsCyber  from '../components/analytics/AnalysisResultsCyber.jsx';
import ChatGPTGeneralView from '../components/analytics/ChatGPTGeneralView.jsx';
import './AnalyticsPage.css';

/* ─────────────────────────────────────
   CIRCULAR PROGRESS RING
───────────────────────────────────── */
function ProgressRing({ progress, mode, size = 120 }) {
  const R = 54, C = 2 * Math.PI * R;
  const offset = C - (progress / 100) * C;
  const color = mode === 'cyber' ? '#ef4444' : '#6366f1';
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" className="ap-ring-svg">
      <circle cx="60" cy="60" r={R} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4"/>
      <circle cx="60" cy="60" r={R} fill="none" stroke={color} strokeWidth="4"
        strokeLinecap="round" strokeDasharray={C} strokeDashoffset={offset}
        transform="rotate(-90 60 60)"
        style={{ transition: 'stroke-dashoffset 0.4s ease' }}/>
      <text x="60" y="66" textAnchor="middle" fill="rgba(255,255,255,0.9)"
        fontSize="18" fontWeight="500" fontFamily="Inter, sans-serif">
        {Math.round(progress)}%
      </text>
    </svg>
  );
}

/* ─────────────────────────────────────
   MAIN COMPONENT
───────────────────────────────────── */
export default function AnalyticsPage({ onBack }) {
  const [mode, setMode]               = useState(null); // 'general' | 'cyber' | null
  const [phase, setPhase]             = useState('mode_select'); // mode_select | input | processing | results
  const [file, setFile]               = useState(null);
  const [promptText, setPromptText]   = useState('');
  const [steps, setSteps]             = useState([]);
  const [currentStep, setCurrentStep] = useState(-1);
  const [result, setResult]           = useState(null);
  const [progress, setProgress]       = useState(0);
  const [mounted, setMounted]         = useState(false);

  const fileRef  = useRef(null);

  const isCyber   = mode === 'cyber';
  const hasInput  = !!file || promptText.trim().length > 0;

  // Entrance animation
  useEffect(() => { requestAnimationFrame(() => setMounted(true)); }, []);

  const handleModeSelect = (selectedMode) => {
    setMode(selectedMode);
    setPhase('input');
    setFile(null);
    setPromptText('');
  };

  const handleBackToModes = () => {
    setPhase('mode_select');
    setMode(null);
    setFile(null);
    setPromptText('');
  };

  const handleAnalyze = async () => {
    if (!hasInput || phase === 'processing') return;
    setPhase('processing'); setResult(null); setProgress(0); setCurrentStep(0);
    const { steps: s, result: r } = await runMockAnalysis(mode, 0);
    setSteps(s);
    for (let i = 0; i < s.length; i++) {
      setCurrentStep(i);
      setProgress(((i + 0.5) / s.length) * 100);
      await new Promise(res => setTimeout(res, 500 + Math.random() * 180));
    }
    setProgress(100);
    await new Promise(res => setTimeout(res, 400));
    setResult(r);
    setPhase('results');
  };

  const handleReset = () => {
    setPhase('input'); setFile(null); setPromptText(''); setResult(null); setSteps([]); setProgress(0); setCurrentStep(-1);
  };

  const fmtBytes = (b) => b < 1048576 ? `${(b/1024).toFixed(1)} KB` : `${(b/1048576).toFixed(1)} MB`;

  // If General Mode is active, render the ChatGPT-style interface with sidebar history & executive summary
  if (mode === 'general') {
    return <ChatGPTGeneralView onBack={handleBackToModes} onGoToEvidence={onBack} />;
  }

  // Determine active mode class for global styling (defaults to general for neutral state)
  const activeModeClass = mode ? mode : 'neutral';

  return (
    <div className={`ap ap--${activeModeClass} ${mounted ? 'ap--mounted' : ''}`}>
      
      {/* ── Background ── */}
      <div className="ap-bg" aria-hidden="true" />
      <div className="ap-bg-glow" aria-hidden="true" />

      {/* ══════════════════════════════
          HEADER
      ══════════════════════════════ */}
      <header className="ap-hdr">
        <div className="ap-hdr__left">
          <button className="ap-hdr__btn" onClick={onBack} aria-label="Back">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <span>Evidence Room</span>
          </button>
        </div>

        <div className="ap-hdr__center">
          <div className="ap-logo">
            <svg viewBox="0 0 24 24" fill="none" className="ap-logo-svg">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span className="ap-logo-text">UNIVANCE</span>
          </div>
        </div>

        <div className="ap-hdr__right" style={{ gap: '16px', display: 'flex', alignItems: 'center' }}>
          {mode && (
            <div className={`ap-status ap-status--${mode}`}>
              <span className="ap-status__dot" />
              <span>{isCyber ? 'Forensics Active' : 'AI Analysis Active'}</span>
            </div>
          )}
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingLeft: '16px', borderLeft: '1px solid rgba(255,255,255,0.1)' }}>
            <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.7)', fontWeight: '500' }}>
              {useContext(AuthContext).user?.email || 'Logged In'}
            </span>
            <button 
              className="ap-hdr__btn" 
              onClick={() => { useContext(AuthContext).logout(); window.location.href = '/login'; }}
              style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* ══════════════════════════════
          PHASE: MODE SELECT
      ══════════════════════════════ */}
      {phase === 'mode_select' && (
        <div className="ap-content ap-anim-fade">
          <div className="ap-hero">
            <h1 className="ap-hero__title">Select Analysis Mode</h1>
            <p className="ap-hero__desc">Choose the appropriate engine for your video processing needs.</p>
          </div>

          <div className="ap-mode-grid">
            {/* General Mode */}
            <div 
              className="ap-mode-card ap-mode-card--general"
              onClick={() => handleModeSelect('general')}
              role="button" tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleModeSelect('general')}
            >
              <div className="ap-mode-card__icon">
                <svg viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2v10z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </div>
              <h2 className="ap-mode-card__title">General Intelligence</h2>
              <p className="ap-mode-card__desc">Standard analysis for video content. Includes scene segmentation, sentiment analysis, object recognition, and transcription.</p>
              <ul className="ap-mode-card__features">
                <li>Scene Breakdown</li>
                <li>Object Detection</li>
                <li>Sentiment Arc</li>
              </ul>
            </div>

            {/* Cyber Mode */}
            <div 
              className="ap-mode-card ap-mode-card--cyber"
              onClick={() => handleModeSelect('cyber')}
              role="button" tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleModeSelect('cyber')}
            >
              <div className="ap-mode-card__icon">
                <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M7 11V7a5 5 0 0110 0v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </div>
              <h2 className="ap-mode-card__title">Cyber Forensics</h2>
              <p className="ap-mode-card__desc">Military-grade evidence analysis. Includes threat scoring, tamper detection, face recognition, and immutable audit logging.</p>
              <ul className="ap-mode-card__features">
                <li>Threat Scoring</li>
                <li>Evidence Integrity</li>
                <li>Chain of Custody</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ══════════════════════════════
          PHASE: INPUT (ChatGPT Style)
      ══════════════════════════════ */}
      {phase === 'input' && (
        <div className="ap-content ap-content--center ap-anim-fade">
          
          <div className="ap-chat-container">
            <button className="ap-btn-ghost ap-chat-back" onClick={handleBackToModes}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              Change Mode
            </button>
            
            <h2 className="ap-chat-title">
              {isCyber ? 'How can I help with forensics today?' : 'What video would you like to analyze?'}
            </h2>

            <div className="ap-chat-wrapper">
              
              {file && (
                <div className="ap-chat-attachment">
                  <div className="ap-chat-attachment__icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </div>
                  <span className="ap-chat-attachment__name">{file.name}</span>
                  <button className="ap-chat-attachment__remove" onClick={() => setFile(null)}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  </button>
                </div>
              )}

              <div className="ap-chat-input-box">
                <input 
                  ref={fileRef} type="file" className="sr-only" 
                  accept=".mp4,.mov,.avi,.webm,.mkv,.ts" 
                  onChange={(e) => { const f = e.target.files[0]; if (f) setFile(f); }} 
                />
                <button 
                  className="ap-chat-btn ap-chat-btn--attach" 
                  onClick={() => fileRef.current?.click()}
                  aria-label="Attach video"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
                
                <textarea 
                  className="ap-chat-textarea"
                  placeholder={isCyber ? "Paste a video URL or type a forensic command..." : "Paste a video URL or ask a question..."}
                  value={promptText}
                  onChange={e => setPromptText(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      if (hasInput) handleAnalyze();
                    }
                  }}
                  rows={1}
                />

                <button 
                  className={`ap-chat-btn ap-chat-btn--send ${hasInput ? 'active' : ''}`} 
                  disabled={!hasInput} 
                  onClick={handleAnalyze}
                  aria-label="Send command"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </button>
              </div>
            </div>
            
            <p className="ap-chat-footer-text">
              UNIVANCE AI can make mistakes. Check important information.
            </p>

          </div>
        </div>
      )}

      {/* ══════════════════════════════
          PROCESSING
      ══════════════════════════════ */}
      {phase === 'processing' && (
        <div className="ap-content ap-content--center ap-anim-fade">
          <ProgressRing progress={progress} mode={mode} />
          <h2 className="ap-proc-title">
            {isCyber ? 'Processing Evidence...' : 'Analyzing Content...'}
          </h2>
          <div className="ap-proc-steps">
            {steps.map((s, i) => (
              <div key={i} className={`ap-proc-step ${i < currentStep ? 'done' : i === currentStep ? 'active' : ''}`}>
                <div className="ap-proc-step__indicator">
                  {i < currentStep ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  ) : (
                    <div className="ap-proc-step__dot" />
                  )}
                </div>
                <span className="ap-proc-step__label">{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ══════════════════════════════
          RESULTS
      ══════════════════════════════ */}
      {phase === 'results' && result && (
        <div className="ap-results-container ap-anim-fade">
          <div className="ap-results-topbar">
            <div className="ap-results-info">
              <span className={`ap-badge ap-badge--${mode}`}>
                {isCyber ? 'FORENSIC REPORT' : 'ANALYSIS SUMMARY'}
              </span>
              <span className="ap-results-filename">{file ? file.name : promptText.substring(0, 30) + '...'}</span>
            </div>
            <div className="ap-results-actions">
              <button className="ap-btn-secondary" onClick={handleReset}>New Analysis</button>
            </div>
          </div>
          
          <div className="ap-results-content">
            {mode === 'general'
              ? <AnalysisResultsGeneral data={result} />
              : <AnalysisResultsCyber  data={result} />}
          </div>
        </div>
      )}
    </div>
  );
}
