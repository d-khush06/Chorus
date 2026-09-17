/**
 * CaseList.jsx
 * Scrollable left sidebar listing all cases.
 * Props:
 *   cases       — array of case manifests
 *   selectedId  — currently selected case_id
 *   collapsed   — boolean (icon-only mode at narrow widths)
 *   onSelect    — (case_id: string) => void
 *   onToggle    — () => void (toggle collapsed state)
 */
import CaseListItem from './CaseListItem.jsx';
import './CaseList.css';

export default function CaseList({ cases, selectedId, collapsed, onSelect, onToggle }) {
  return (
    <aside
      className={`case-list${collapsed ? ' case-list--collapsed' : ''}`}
      aria-label="Case list"
    >
      <div className="case-list__header">
        {!collapsed && <span className="case-list__title mono">Cases</span>}
        <button
          className="case-list__toggle"
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="14" height="14">
            {collapsed
              ? <path d="M5 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              : <path d="M11 3L6 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            }
          </svg>
        </button>
      </div>

      <div className="case-list__count mono" aria-live="polite">
        {!collapsed && <span className="text-3">{cases.length} case{cases.length !== 1 ? 's' : ''}</span>}
      </div>

      <nav className="case-list__items" role="list">
        {cases.map(c => (
          <CaseListItem
            key={c.case_id}
            caseData={c}
            isActive={c.case_id === selectedId}
            collapsed={collapsed}
            onClick={() => onSelect(c.case_id)}
          />
        ))}
      </nav>
    </aside>
  );
}
