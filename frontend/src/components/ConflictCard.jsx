/**
 * ConflictCard.jsx
 * Renders a conflict inline in the timeline at its timestamp position.
 * Red left-border card showing both conflicting values side by side.
 * Props:
 *   conflict  — conflict object from fusion output
 *   eventRef  — React ref to attach (for scroll targeting)
 */
import './ConflictCard.css';

const CONFLICT_TYPE_LABELS = {
  presence_contradiction: 'Presence Contradiction',
  content_mismatch:       'Content Mismatch',
  timing_mismatch:        'Timing Mismatch',
};

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export default function ConflictCard({ conflict, eventRef }) {
  const {
    scene_id, time_range,
    source_a, content_a,
    source_b, content_b,
    conflict_type,
  } = conflict;

  const label = CONFLICT_TYPE_LABELS[conflict_type] ?? conflict_type;
  const [t_start, t_end] = time_range;

  return (
    <article
      ref={eventRef}
      className="conflict-card"
      data-scene-id={scene_id}
      aria-label={`Conflict in scene ${scene_id}: ${label}`}
    >
      <div className="conflict-card__header">
        <span className="conflict-card__badge mono">⚑ {label}</span>
        <span className="conflict-card__time mono text-3">
          {formatTime(t_start)} → {formatTime(t_end)} · scene {scene_id}
        </span>
      </div>

      <div className="conflict-card__body">
        <div className="conflict-card__side">
          <div className="conflict-card__source mono">{source_a}</div>
          <p className="conflict-card__text">{content_a}</p>
        </div>
        <div className="conflict-card__divider" aria-hidden="true">vs</div>
        <div className="conflict-card__side">
          <div className="conflict-card__source mono">{source_b}</div>
          <p className="conflict-card__text">{content_b}</p>
        </div>
      </div>
    </article>
  );
}
