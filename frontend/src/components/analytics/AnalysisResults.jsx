/**
 * AnalysisResults.jsx
 * Root results orchestrator — renders progress screen or mode-specific results.
 */
import { useState, useEffect } from 'react';
import AnalysisResultsGeneral from './AnalysisResultsGeneral.jsx';
import AnalysisResultsCyber  from './AnalysisResultsCyber.jsx';
import './AnalysisResults.css';

export default function AnalysisResults({ mode, steps, currentStep, data }) {
  const isProcessing = !data && steps.length > 0;

  if (isProcessing) {
    return (
      <div className="aresults-processing">
        <div className={`aresults-processing__orb aresults-processing__orb--${mode}`} />
        <div className="aresults-processing__status">
          <div className="aresults-processing__step-list">
            {steps.map((step, i) => (
              <div
                key={i}
                className={`aresults-processing__step ${
                  i < currentStep ? 'done' : i === currentStep ? 'active' : 'pending'
                }`}
              >
                <span className="aresults-step-indicator">
                  {i < currentStep ? '✓' : i === currentStep ? '▶' : '·'}
                </span>
                <span className="aresults-step-text">{step}</span>
              </div>
            ))}
          </div>
          <div className="aresults-processing__progress">
            <div
              className={`aresults-processing__progress-fill aresults-processing__progress-fill--${mode}`}
              style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
            />
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className={`aresults aresults--${mode}`}>
      <div className="aresults__header">
        <span className={`aresults__badge aresults__badge--${mode}`}>
          {mode === 'general' ? '✦ Analysis Complete' : '🔒 Forensic Report Ready'}
        </span>
        <button
          className="aresults__reset-btn"
          onClick={() => window.location.reload()}
          aria-label="Start new analysis"
        >
          ↩ New Analysis
        </button>
      </div>

      {mode === 'general'
        ? <AnalysisResultsGeneral data={data} />
        : <AnalysisResultsCyber data={data} />
      }
    </div>
  );
}
