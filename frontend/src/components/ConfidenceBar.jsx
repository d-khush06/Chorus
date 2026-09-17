/**
 * ConfidenceBar.jsx
 * Thin horizontal bar visualising a 0-1 confidence score.
 * Props: score (number 0–1), label (string, optional aria-label)
 */
import './ConfidenceBar.css';

function scoreClass(score) {
  if (score >= 0.8) return 'high';
  if (score >= 0.5) return 'mid';
  return 'low';
}

export default function ConfidenceBar({ score, label }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  const tier = scoreClass(score);

  return (
    <div
      className="conf-bar"
      role="meter"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? `Confidence: ${pct}%`}
      title={`Confidence: ${pct}%`}
    >
      <div className="conf-bar__track">
        <div className={`conf-bar__fill conf-bar__fill--${tier}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="conf-bar__label mono">{pct}%</span>
    </div>
  );
}
