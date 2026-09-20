import React from 'react';

const STAGE_LABELS = {
  source_ingestion: 'Source Ingestion & Protocol Decoding',
  duplication_check: 'Cryptographic Duplication & Hashing',
  quality_gate: 'Quality Gate Stream & PTS Cadence',
  manipulation_detection: 'SBI Deepfake Screening',
  ai_generation_detection: 'AI Generation & Diffusion Artifacts',
  orchestrator_routing: 'Neural Orchestrator Routing',
  scene_segmentation: 'Temporal Scene Boundary Segmentation',
  asr_transcription: 'Whisper ASR Speech Transcription',
  vision_perception: 'Multimodal Vision Perception',
  multimodal_fusion: 'Temporal Multi-Agent Evidentiary Fusion',
  domain_output: 'Forensic Intelligence Synthesis',
  acoustic_event_detection: 'Acoustic Spectrum & Event Classification',
  geo_estimation: 'Keyframe Geographic Estimation',
  face_reid: 'Cross-Camera Facial Re-Identification',
  alert_system: 'Standing Watch Alert Rule Evaluation'
};

function formatStageName(name) {
  return STAGE_LABELS[name] || name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function StageTracker({ stages = [], currentStage = null, progress = 0 }) {
  if (!stages || stages.length === 0) {
    return (
      <div className="p-4 bg-surface border border-default rounded-card text-secondary text-sm">
        Initializing stage manifest...
      </div>
    );
  }

  return (
    <div className="bg-surface border border-default rounded-card p-5" aria-label="Pipeline Stage Execution Tracker">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-heading text-base font-semibold text-primary">
            Pipeline Progression
          </h3>
          <p className="text-xs text-secondary mt-0.5" aria-live="polite">
            {currentStage ? `Currently executing: ${formatStageName(currentStage)}` : 'Stages queued'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-semibold text-accent">
            {progress}%
          </span>
          <div className="w-20 h-1.5 bg-bg rounded-full overflow-hidden border border-default">
            <div
              className="h-full bg-accent transition-all duration-fast"
              style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-2.5" role="list" aria-live="polite">
        {stages.map((stage, idx) => {
          const isCurrent = stage.name === currentStage;
          const status = stage.status || (isCurrent ? 'running' : 'pending');

          let statusIcon = null;
          let badgeClass = 'text-secondary border-default bg-bg';

          if (status === 'completed') {
            badgeClass = 'text-ok border-ok/30 bg-surface';
            statusIcon = (
              <svg className="w-3.5 h-3.5 text-ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            );
          } else if (status === 'running') {
            badgeClass = 'text-accent border-accent/40 bg-surface animate-pulse-slow';
            statusIcon = (
              <div className="w-2 h-2 rounded-full bg-accent animate-ping" />
            );
          } else if (status === 'skipped' || status === 'not_applicable') {
            badgeClass = 'text-secondary border-default bg-bg/50';
            statusIcon = (
              <span className="text-[10px] font-mono text-secondary">SKIP</span>
            );
          } else if (status === 'failed') {
            badgeClass = 'text-danger border-danger/40 bg-surface';
            statusIcon = (
              <svg className="w-3.5 h-3.5 text-danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            );
          } else {
            statusIcon = (
              <div className="w-1.5 h-1.5 rounded-full bg-secondary/50" />
            );
          }

          return (
            <div
              key={stage.name || idx}
              role="listitem"
              className={`flex items-center justify-between p-2.5 rounded-control border transition-colors ${
                isCurrent
                  ? 'border-accent/60 bg-bg'
                  : 'border-default/60 bg-surface/50'
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-mono text-[11px] text-secondary w-5 text-right shrink-0">
                  {idx + 1}.
                </span>
                <span className="text-sm font-medium text-primary truncate">
                  {formatStageName(stage.name)}
                </span>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {stage.reason && (
                  <span className="text-xs text-secondary italic truncate max-w-[120px]">
                    ({stage.reason})
                  </span>
                )}
                <div
                  className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-mono capitalize ${badgeClass}`}
                >
                  {statusIcon}
                  <span>{status.replace('_', ' ')}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
