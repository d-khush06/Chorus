/**
 * StatusBadge.jsx
 * Reusable status pill. Color maps to actual state only.
 * Props: status (string) — "processing" | "sealed" | "flagged"
 */
import './StatusBadge.css';

export default function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-badge--${status}`} aria-label={`Status: ${status}`}>
      {status}
    </span>
  );
}
