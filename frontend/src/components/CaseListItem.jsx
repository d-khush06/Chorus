/**
 * CaseListItem.jsx
 * Single case row in the left sidebar.
 * Props:
 *   caseData  — case manifest object
 *   isActive  — boolean
 *   collapsed — boolean (icon-only mode)
 *   onClick   — () => void
 */
import StatusBadge from './StatusBadge.jsx';
import './CaseListItem.css';

// Source type icons (inline SVG to avoid asset pipeline complexity)
const SOURCE_ICONS = {
  youtube: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="source-icon">
      <rect x="2" y="5" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 8l5 2-5 2V8z" fill="currentColor" />
    </svg>
  ),
  local_upload: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="source-icon">
      <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 13V7M7 10l3-3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  live_rtsp: (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" className="source-icon">
      <circle cx="10" cy="10" r="3" fill="currentColor" />
      <path d="M5.5 5.5a6.5 6.5 0 0 0 0 9M14.5 5.5a6.5 6.5 0 0 1 0 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
};

/**
 * Returns a human-readable relative time string (e.g. "2h ago", "just now")
 */
function relativeTime(isoString) {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diff = Math.floor((now - then) / 1000);

  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(isoString).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function CaseListItem({ caseData, isActive, collapsed, onClick }) {
  const { case_id, source_type, status, created_at } = caseData;
  const icon = SOURCE_ICONS[source_type] ?? SOURCE_ICONS.local_upload;
  const shortId = case_id.slice(0, 8) + '…';

  return (
    <button
      className={`case-list-item${isActive ? ' case-list-item--active' : ''}`}
      onClick={onClick}
      title={case_id}
      aria-pressed={isActive}
      aria-label={`Case ${shortId} — ${status}`}
    >
      <span className="case-list-item__icon" aria-hidden="true">
        {icon}
      </span>
      {!collapsed && (
        <span className="case-list-item__body">
          <span className="case-list-item__id mono truncate">{shortId}</span>
          <span className="case-list-item__meta">
            <StatusBadge status={status} />
            <span className="case-list-item__time mono">{relativeTime(created_at)}</span>
          </span>
        </span>
      )}
    </button>
  );
}
