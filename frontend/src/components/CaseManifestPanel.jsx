/**
 * CaseManifestPanel.jsx
 * Right sidebar — shows case manifest data and verification.
 * Props:
 *   caseData   — case manifest object (or null if none selected)
 *   onVerify   — async () => { ok, message } — called on button click
 */
import { useState, useCallback, useEffect } from 'react';
import StatusBadge from './StatusBadge.jsx';
import './CaseManifestPanel.css';

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard API may fail in non-secure contexts
    }
  }, [text]);

  return (
    <button
      className="copy-btn"
      onClick={handleCopy}
      title={`Copy ${label}`}
      aria-label={copied ? 'Copied!' : `Copy ${label}`}
    >
      {copied
        ? (
          <svg viewBox="0 0 14 14" fill="none" width="12" height="12" aria-hidden="true">
            <path d="M2 7l3.5 3.5L12 3" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 14 14" fill="none" width="12" height="12" aria-hidden="true">
            <rect x="4" y="1" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
            <rect x="1" y="4" width="9" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.2" fill="var(--surface)" />
          </svg>
        )
      }
    </button>
  );
}

function HashField({ label, value }) {
  if (!value) {
    return (
      <div className="manifest-field">
        <dt className="manifest-field__label">{label}</dt>
        <dd className="manifest-field__value manifest-field__value--null mono text-3">—</dd>
      </div>
    );
  }

  return (
    <div className="manifest-field">
      <dt className="manifest-field__label">{label}</dt>
      <dd className="manifest-field__hash">
        <span className="mono truncate" title={value}>{value}</span>
        <CopyButton text={value} label={label} />
      </dd>
    </div>
  );
}

function formatDateTime(isoString) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleString('en-US', {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  });
}

export default function CaseManifestPanel({ caseData, onVerify }) {
  const [verifyState, setVerifyState] = useState(null); // null | 'loading' | { ok, message }

  // Reset verification result when case changes
  useEffect(() => {
    setVerifyState(null);
  }, [caseData?.case_id]);

  const handleVerify = useCallback(async () => {
    setVerifyState('loading');
    try {
      const result = await onVerify();
      setVerifyState(result);
    } catch (err) {
      setVerifyState({ ok: false, message: `Verification error: ${err.message}` });
    }
  }, [onVerify]);

  if (!caseData) {
    return (
      <aside className="manifest-panel" aria-label="Case manifest">
        <div className="manifest-panel__empty">
          <span className="mono text-3">Select a case to inspect</span>
        </div>
      </aside>
    );
  }

  const {
    case_id, created_at, sealed_at, status, source_type,
    raw_video_hash, merkle_root, artifact_count, timestamp_authority,
  } = caseData;

  return (
    <aside className="manifest-panel" aria-label="Case manifest">
      <div className="manifest-panel__header">
        <span className="manifest-panel__title mono">Manifest</span>
        <StatusBadge status={status} />
      </div>

      <dl className="manifest-panel__fields">
        <div className="manifest-field">
          <dt className="manifest-field__label">Case ID</dt>
          <dd className="manifest-field__hash">
            <span className="mono truncate" title={case_id}>{case_id}</span>
            <CopyButton text={case_id} label="Case ID" />
          </dd>
        </div>

        <div className="manifest-field">
          <dt className="manifest-field__label">Source</dt>
          <dd className="manifest-field__value mono">{source_type}</dd>
        </div>

        <div className="manifest-field">
          <dt className="manifest-field__label">Created</dt>
          <dd className="manifest-field__value mono">{formatDateTime(created_at)}</dd>
        </div>

        <div className="manifest-field">
          <dt className="manifest-field__label">Sealed</dt>
          <dd className="manifest-field__value mono">{formatDateTime(sealed_at)}</dd>
        </div>

        <div className="manifest-field">
          <dt className="manifest-field__label">Artifacts</dt>
          <dd className="manifest-field__value mono">{artifact_count}</dd>
        </div>

        <div className="manifest-field">
          <dt className="manifest-field__label">Timestamp Authority</dt>
          <dd className="manifest-field__value mono">{timestamp_authority}</dd>
        </div>

        <HashField label="Raw Video SHA-256" value={raw_video_hash} />
        <HashField label="Merkle Root" value={merkle_root} />
      </dl>

      <div className="manifest-panel__verify">
        <button
          id={`verify-btn-${case_id}`}
          className="verify-btn"
          onClick={handleVerify}
          disabled={verifyState === 'loading'}
          aria-busy={verifyState === 'loading'}
        >
          {verifyState === 'loading' && <span className="verify-btn__spinner" aria-hidden="true" />}
          {verifyState === 'loading' ? 'Verifying…' : 'Verify Integrity'}
        </button>

        {verifyState && verifyState !== 'loading' && (
          <div
            className={`verify-result${verifyState.ok ? ' verify-result--pass' : ' verify-result--fail'}`}
            role="status"
            aria-live="polite"
          >
            <span className="verify-result__icon" aria-hidden="true">
              {verifyState.ok ? '✓' : '✕'}
            </span>
            <p className="verify-result__message sans">{verifyState.message}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
