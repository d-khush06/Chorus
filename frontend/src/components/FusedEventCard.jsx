/**
 * FusedEventCard.jsx
 * Renders a single fused timeline event.
 * Props:
 *   event     — fused timeline event object
 *   eventRef  — React ref to attach (for scroll targeting)
 */
import ConfidenceBar from './ConfidenceBar.jsx';
import './FusedEventCard.css';

const EVENT_TYPE_LABELS = {
  speech:      'ASR',
  object:      'OBJ',
  text:        'OCR',
  diarization: 'DIARZ',
  no_signal:   'SIL',
};

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.round((s % 1) * 10);
  return `${m}:${String(sec).padStart(2, '0')}.${ms}`;
}

export default function FusedEventCard({ event, eventRef }) {
  const {
    scene_id, start_seconds, end_seconds,
    event_type, content, source_agent, confidence,
  } = event;

  const isNoSignal = event_type === 'no_signal';
  const typeLabel = EVENT_TYPE_LABELS[event_type] ?? event_type.toUpperCase();

  return (
    <article
      ref={eventRef}
      className={`fused-event${isNoSignal ? ' fused-event--no-signal' : ''}`}
      data-scene-id={scene_id}
      aria-label={`Scene ${scene_id} — ${event_type} at ${formatTime(start_seconds)}`}
    >
      <div className="fused-event__timestamp-col">
        <span className="fused-event__time mono">{formatTime(start_seconds)}</span>
        <span className="fused-event__time-end mono text-3">→ {formatTime(end_seconds)}</span>
      </div>

      <div className="fused-event__main">
        <div className="fused-event__top">
          <span className={`fused-event__type-tag fused-event__type-tag--${event_type} mono`}>
            {typeLabel}
          </span>
          {source_agent && (
            <span className="fused-event__source mono text-3">{source_agent}</span>
          )}
          <span className="fused-event__scene mono text-3">scene {scene_id}</span>
        </div>

        <p className={`fused-event__content${isNoSignal ? ' text-3' : ''}`}>
          {content}
        </p>

        {confidence != null && (
          <ConfidenceBar score={confidence} label={`${source_agent ?? event_type} confidence`} />
        )}
      </div>
    </article>
  );
}
