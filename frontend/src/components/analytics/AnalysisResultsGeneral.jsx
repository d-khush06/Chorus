/**
 * AnalysisResultsGeneral.jsx
 * General mode analysis result cards:
 * scene breakdown, object detection, sentiment, transcript, keywords, engagement.
 */
import { useEffect, useRef, useState } from 'react';
import './AnalysisResultsGeneral.css';

/* ── Animated number counter ── */
function AnimatedNumber({ value, decimals = 0, suffix = '' }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    let start = 0;
    const duration = 1200;
    const step = (timestamp) => {
      if (!start) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(parseFloat((eased * value).toFixed(decimals)));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [value, decimals]);
  return <>{display.toLocaleString()}{suffix}</>;
}

/* ── Mini confidence bar ── */
function ConfBar({ value, accent }) {
  return (
    <div className="gres-confbar">
      <div
        className="gres-confbar__fill"
        style={{ width: `${(value * 100).toFixed(0)}%`, background: accent }}
      />
    </div>
  );
}

/* ── Sentiment arc ── */
function SentimentArc({ positive, neutral, negative }) {
  const total = positive + neutral + negative;
  const posAngle = (positive / total) * 180;
  const neutralAngle = (neutral / total) * 180;

  return (
    <div className="gres-sentiment-arc">
      <svg viewBox="0 0 200 110" className="gres-sentiment-svg">
        <defs>
          <linearGradient id="grad-pos" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#6ee7b7" />
          </linearGradient>
        </defs>
        {/* Background track */}
        <path d="M 10 100 A 90 90 0 0 1 190 100" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="14" strokeLinecap="round" />
        {/* Positive */}
        <path d="M 10 100 A 90 90 0 0 1 190 100" fill="none" stroke="url(#grad-pos)"
          strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${(positive / total) * 283} 283`} />
        {/* Neutral */}
        <path d="M 10 100 A 90 90 0 0 1 190 100" fill="none" stroke="#fbbf24"
          strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${(neutral / total) * 283} 283`}
          strokeDashoffset={`-${(positive / total) * 283}`} />
        {/* Negative */}
        <path d="M 10 100 A 90 90 0 0 1 190 100" fill="none" stroke="#f87171"
          strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${(negative / total) * 283} 283`}
          strokeDashoffset={`-${((positive + neutral) / total) * 283}`} />
        {/* Center label */}
        <text x="100" y="92" textAnchor="middle" fill="#34d399" fontSize="26" fontWeight="bold" fontFamily="Inter, sans-serif">{positive}%</text>
        <text x="100" y="108" textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="9" fontFamily="JetBrains Mono, monospace" letterSpacing="2">POSITIVE</text>
      </svg>
      <div className="gres-sentiment-legend">
        <span className="gres-sent-dot" style={{ background: '#34d399' }} />Positive {positive}%
        <span className="gres-sent-dot" style={{ background: '#fbbf24' }} />Neutral {neutral}%
        <span className="gres-sent-dot" style={{ background: '#f87171' }} />Negative {negative}%
      </div>
    </div>
  );
}

export default function AnalysisResultsGeneral({ data }) {
  if (!data) return null;

  const accent = '#818cf8';

  return (
    <div className="gres">
      {/* ── Overview row ── */}
      <div className="gres-overview">
        <div className="gres-stat-card">
          <span className="gres-stat-label">Overall Score</span>
          <span className="gres-stat-value gres-stat-value--highlight">
            <AnimatedNumber value={data.overallScore} /><span style={{ fontSize: '0.5em', opacity: 0.5 }}>/100</span>
          </span>
        </div>
        <div className="gres-stat-card">
          <span className="gres-stat-label">Duration</span>
          <span className="gres-stat-value">
            {Math.floor(data.duration / 60)}m {data.duration % 60}s
          </span>
        </div>
        <div className="gres-stat-card">
          <span className="gres-stat-label">Scenes</span>
          <span className="gres-stat-value"><AnimatedNumber value={data.scenes.length} /></span>
        </div>
        <div className="gres-stat-card">
          <span className="gres-stat-label">Speakers</span>
          <span className="gres-stat-value"><AnimatedNumber value={data.speakerCount} /></span>
        </div>
        <div className="gres-stat-card">
          <span className="gres-stat-label">Engagement</span>
          <span className="gres-stat-value gres-stat-value--engage">
            <AnimatedNumber value={data.engagementScore} /><span style={{ fontSize: '0.5em', opacity: 0.5 }}>%</span>
          </span>
        </div>
        <div className="gres-stat-card">
          <span className="gres-stat-label">Language</span>
          <span className="gres-stat-value" style={{ fontSize: '1.1rem' }}>{data.language}</span>
        </div>
      </div>

      <div className="gres-grid">
        {/* ── Scene breakdown ── */}
        <div className="gres-card gres-card--wide">
          <h3 className="gres-card__title">🎬 Scene Breakdown</h3>
          <div className="gres-scenes">
            {data.scenes.map((s) => (
              <div key={s.id} className="gres-scene">
                <div className="gres-scene__thumb" style={{ background: `linear-gradient(135deg, ${s.dominantColor}55, ${s.dominantColor}22)`, borderColor: `${s.dominantColor}66` }}>
                  <span style={{ fontSize: 22 }}>🎞</span>
                </div>
                <div className="gres-scene__info">
                  <span className="gres-scene__label">{s.label}</span>
                  <span className="gres-scene__time">{s.start}s – {s.end}s</span>
                  <ConfBar value={s.confidence} accent={s.dominantColor} />
                </div>
                <span className="gres-scene__conf">{(s.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Sentiment ── */}
        <div className="gres-card">
          <h3 className="gres-card__title">💬 Sentiment Analysis</h3>
          <SentimentArc
            positive={data.sentiment.positive}
            neutral={data.sentiment.neutral}
            negative={data.sentiment.negative}
          />
        </div>

        {/* ── Object Detection ── */}
        <div className="gres-card">
          <h3 className="gres-card__title">🔍 Detected Objects</h3>
          <div className="gres-objects">
            {data.objectDetection.map((obj) => (
              <div key={obj.label} className="gres-object-row">
                <span className="gres-object-label">{obj.label}</span>
                <span className="gres-object-count">×{obj.count}</span>
                <ConfBar value={obj.confidence} accent={accent} />
                <span className="gres-object-conf">{(obj.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Keyword Cloud ── */}
        <div className="gres-card">
          <h3 className="gres-card__title">🏷 Key Topics</h3>
          <div className="gres-keywords">
            {data.keywords.map((kw) => (
              <span
                key={kw.word}
                className="gres-keyword"
                style={{
                  fontSize: `${0.7 + kw.weight * 0.6}rem`,
                  opacity: 0.4 + kw.weight * 0.6,
                }}
              >
                {kw.word}
              </span>
            ))}
          </div>
        </div>

        {/* ── Transcript ── */}
        <div className="gres-card gres-card--wide">
          <h3 className="gres-card__title">📝 Auto-Transcript</h3>
          <div className="gres-transcript">
            {data.transcript.map((seg, i) => (
              <div key={i} className="gres-transcript-seg">
                <span className="gres-transcript-time">
                  {String(Math.floor(seg.start / 60)).padStart(2, '0')}:{String(seg.start % 60).padStart(2, '0')}
                </span>
                <p className="gres-transcript-text">{seg.text}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
