/**
 * TimelineScrubber.jsx
 * Horizontal scrubber bar showing:
 *  - Scene boundaries as tick marks
 *  - Conflict markers as red flags at exact time positions
 *  - Clicking a tick scrolls the timeline list to that scene
 *
 * Props:
 *   fusedTimeline  — array of fused events
 *   conflicts      — array of conflict objects
 *   totalDuration  — total seconds (computed from last event's end_seconds)
 *   onSceneClick   — (scene_id: number) => void
 */
import './TimelineScrubber.css';

/** Get unique scenes sorted by start time */
function getScenes(fusedTimeline) {
  const map = new Map();
  for (const ev of fusedTimeline) {
    if (!map.has(ev.scene_id)) {
      map.set(ev.scene_id, { scene_id: ev.scene_id, start: ev.start_seconds, end: ev.end_seconds });
    } else {
      const s = map.get(ev.scene_id);
      map.set(ev.scene_id, {
        ...s,
        start: Math.min(s.start, ev.start_seconds),
        end: Math.max(s.end, ev.end_seconds),
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.start - b.start);
}

/** Conflict positions: use start of time_range */
function getConflictPositions(conflicts) {
  return conflicts.map(c => ({
    scene_id: c.scene_id,
    t: c.time_range[0],
    label: c.conflict_type,
  }));
}

export default function TimelineScrubber({ fusedTimeline, conflicts, totalDuration, onSceneClick }) {
  if (!fusedTimeline || fusedTimeline.length === 0) {
    return <div className="scrubber scrubber--empty"><span className="mono text-3">No timeline data</span></div>;
  }

  const scenes = getScenes(fusedTimeline);
  const conflictPos = getConflictPositions(conflicts ?? []);
  const duration = totalDuration ?? Math.max(...fusedTimeline.map(e => e.end_seconds));

  function pct(t) {
    return `${((t / duration) * 100).toFixed(3)}%`;
  }

  function formatTime(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, '0')}`;
  }

  return (
    <div className="scrubber" role="navigation" aria-label="Timeline scrubber">
      <div className="scrubber__header">
        <span className="scrubber__label mono text-3">Timeline</span>
        <span className="scrubber__duration mono text-3">{formatTime(duration)}</span>
      </div>

      <div className="scrubber__track">
        {/* Scene tick marks */}
        {scenes.map(scene => (
          <button
            key={scene.scene_id}
            className="scrubber__tick"
            style={{ left: pct(scene.start) }}
            onClick={() => onSceneClick(scene.scene_id)}
            title={`Scene ${scene.scene_id} — ${formatTime(scene.start)}`}
            aria-label={`Jump to scene ${scene.scene_id} at ${formatTime(scene.start)}`}
          >
            <span className="scrubber__tick-line" />
            <span className="scrubber__tick-label mono">{scene.scene_id}</span>
          </button>
        ))}

        {/* Conflict flag markers */}
        {conflictPos.map((cp, i) => (
          <button
            key={i}
            className="scrubber__conflict-flag"
            style={{ left: pct(cp.t) }}
            onClick={() => onSceneClick(cp.scene_id)}
            title={`Conflict: ${cp.label} at ${formatTime(cp.t)}`}
            aria-label={`Conflict: ${cp.label} in scene ${cp.scene_id}`}
          >
            <svg viewBox="0 0 10 14" fill="none" aria-hidden="true" width="10" height="14">
              <path d="M0 0h8L5 6H0V0z" fill="var(--red)" />
              <line x1="0" y1="0" x2="0" y2="14" stroke="var(--red)" strokeWidth="1.5" />
            </svg>
          </button>
        ))}

        {/* Scene region bands */}
        {scenes.map(scene => (
          <div
            key={`band-${scene.scene_id}`}
            className={`scrubber__band${scene.scene_id % 2 === 0 ? ' scrubber__band--alt' : ''}`}
            style={{ left: pct(scene.start), width: pct(scene.end - scene.start) }}
            aria-hidden="true"
          />
        ))}
      </div>

      {/* Time axis labels */}
      <div className="scrubber__axis">
        <span className="scrubber__axis-label mono">0:00</span>
        <span className="scrubber__axis-label mono">{formatTime(duration / 4)}</span>
        <span className="scrubber__axis-label mono">{formatTime(duration / 2)}</span>
        <span className="scrubber__axis-label mono">{formatTime((duration * 3) / 4)}</span>
        <span className="scrubber__axis-label mono">{formatTime(duration)}</span>
      </div>
    </div>
  );
}
