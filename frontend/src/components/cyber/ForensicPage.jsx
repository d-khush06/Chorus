import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill, StatusDot } from './primitives/StatusPill';
import { Skeleton, SkeletonCard } from './primitives/Skeleton';
import { EmptyState, ErrorState } from './primitives/EmptyState';
import { Tabs, TabTrigger, TabContent } from './primitives/Tabs';

export function ForensicPage() {
  const [activeTab, setActiveTab] = useState('authenticity');
  const [currentFrame, setCurrentFrame] = useState(420);
  const totalFrames = 1847;
  const duration = 61.5;

  const mockAuthenticityChecks = [
    {
      id: 'sbi',
      title: 'SBI Deepfake Detection',
      score: 0.73,
      threshold: 0.65,
      status: 'danger',
      frameThreshold: 0.70,
      videoThreshold: 0.65,
      explanation: 'Frame 420 shows compression quantization inconsistent with surrounding frames. Optical flow discontinuity detected between frames 420-421.',
      limitations: 'SBI detector may produce false positives on heavily compressed footage. Requires manual verification of flagged frames.',
      evidence: { frame: 420, time: '00:14.200', confidence: 0.73 }
    },
    {
      id: 'ai-gen',
      title: 'AI Generation Screening',
      score: 0.12,
      threshold: 0.50,
      status: 'ok',
      explanation: 'No neural noise patterns or compression artifacts consistent with AI video generation detected.',
      limitations: 'Conservative screening only. Novel generation methods may not be detected. Not a proof of authenticity.',
      evidence: { framesAnalyzed: 12, confidence: 0.88 }
    },
    {
      id: 'quality',
      title: 'Quality Gate (8 Rules)',
      score: 7,
      threshold: 8,
      status: 'warning',
      passed: 7,
      total: 8,
      rules: [
        { id: 1, name: 'Resolution Check', passed: true },
        { id: 2, name: 'Frame Rate Consistency', passed: true },
        { id: 3, name: 'Audio Track Presence', passed: false, note: 'Zero audio track prior to container creation' },
        { id: 4, name: 'Codec Compliance', passed: true },
        { id: 5, name: 'Container Integrity', passed: true },
        { id: 6, name: 'Timestamp Monotonicity', passed: true },
        { id: 7, name: 'Keyframe Interval', passed: true },
        { id: 8, name: 'Bitrate Stability', passed: true },
      ],
      explanation: 'Audio track was zeroed out before file container creation. This is a strong indicator of post-processing.',
      limitations: 'Quality gate rules are heuristic. Some failures may have benign explanations (e.g., silent recording).'
    },
  ];

  const mockMetadata = [
    { key: 'Container', value: 'MP4 (ISO Base Media)' },
    { key: 'Video Codec', value: 'H.264 / AVC (High Profile)' },
    { key: 'Audio Codec', value: 'AAC-LC (48 kHz, stereo)' },
    { key: 'Encoder', value: 'Lavf58.76.100 (FFmpeg)' },
    { key: 'Creation Time', value: '2024-01-15T14:32:07Z' },
    { key: 'Duration', value: '61.5s' },
    { key: 'Resolution', value: '1920×1080' },
    { key: 'Frame Rate', value: '29.97 fps' },
    { key: 'Bitrate', value: '4.2 Mbps (CBR)' },
    { key: 'Editing Software Traces', value: 'None detected' },
  ];

  const mockCustodyEvents = [
    { event: 'uploaded', user: 'analyst@chorus.local', timestamp: '2024-01-15T14:32:10Z', hash: 'a3f2...8b1c' },
    { event: 'hashed', user: 'system', timestamp: '2024-01-15T14:32:11Z', hash: 'a3f2...8b1c' },
    { event: 'analyzed', user: 'system', timestamp: '2024-01-15T14:35:22Z', hash: 'a3f2...8b1c' },
    { event: 'viewed', user: 'analyst@chorus.local', timestamp: '2024-01-15T14:36:05Z', hash: 'a3f2...8b1c' },
    { event: 'exported', user: 'analyst@chorus.local', timestamp: '2024-01-15T14:40:12Z', hash: 'a3f2...8b1c' },
  ];

  const mockFindings = [
    { frame: 420, time: '00:14.200', type: 'Frame splice', severity: 'danger', description: 'I-frame splicing detected between frames 420-421' },
    { frame: 0, time: '00:00.000', type: 'Audio desync', severity: 'warning', description: 'Audio track zeroed out prior to container creation' },
    { frame: 960, time: '00:32.000', type: 'Timestamp gap', severity: 'info', description: 'Non-monotonic timestamp detected' },
  ];

  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 p-4 bg-surface border border-default rounded-card">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <span className="font-mono text-sm text-secondary">CASE: CR-2024-001</span>
            <span className="font-mono text-sm text-secondary">CCTV_Sector4.mp4</span>
            <span className="font-mono text-xs text-secondary">SHA-256: a3f2b8c4e9d1f7a6b3c2d5e8f1a4b7c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1f4a</span>
          </div>
          <StatusPill status="danger" label="Likely Manipulated" size="md" dot />
        </div>
        <div className="flex flex-wrap gap-3">
          <Button variant="primary">Save to Evidence Room</Button>
          <Button variant="secondary">Export Report</Button>
          <Button variant="outline">Route to Review Queue</Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-6">
          <Card variant="stage" padding="none" className="aspect-video relative overflow-hidden">
            <div className="absolute inset-0 bg-stage flex items-center justify-center">
              <div className="text-center">
                <div className="w-20 h-20 mx-auto mb-4 border-4 border-accent border-t-transparent rounded-full animate-spin" />
                <p className="text-secondary">Loading evidence...</p>
              </div>
            </div>
            <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between px-4">
              <div className="bg-surface/90 backdrop-blur-sm px-4 py-2 rounded-control flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="icon" onClick={() => setCurrentFrame(Math.max(0, currentFrame - 1))} aria-label="Previous frame">
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <polyline points="15 18 9 12 15 6" />
                    </svg>
                  </Button>
                  <span className="font-mono text-sm text-primary">Frame {currentFrame} / {totalFrames}</span>
                  <Button variant="ghost" size="icon" onClick={() => setCurrentFrame(Math.min(totalFrames, currentFrame + 1))} aria-label="Next frame">
                    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </Button>
                </div>
                <div className="flex items-center gap-2 text-secondary text-sm font-mono">
                  <span>{Math.floor(currentFrame / 30)}:{String((currentFrame % 30) * 33).padStart(3, '0')}</span>
                  <span>/</span>
                  <span>{Math.floor(duration / 60)}:{String(duration % 60).padStart(2, '0')}</span>
                </div>
              </div>
            </div>
          </Card>

          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-lg">Timeline</CardTitle>
            </CardHeader>
            <CardContent className="space-4">
              <div className="relative h-32 bg-surface rounded-control border border-default">
                <div className="absolute inset-0 flex items-end p-2" style={{ transform: 'scaleY(-1)' }}>
                  {Array.from({ length: 60 }, (_, i) => {
                    const height = 20 + Math.random() * 60;
                    const isAboveThreshold = height > 45;
                    return (
                      <div
                        key={i}
                        className={`w-full transition-colors ${isAboveThreshold ? 'bg-danger/60' : 'bg-border/50'}`}
                        style={{ height: `${height}%`, flex: 1, borderRadius: '1px 1px 0 0' }}
                      />
                    );
                  })}
                </div>
                <div className="absolute left-0 right-0 border-t border-danger/50" style={{ bottom: '45%' }} />
                <div className="absolute left-0 right-0 border-t border-ok/50" style={{ bottom: '65%' }} />
              </div>
              <div className="flex justify-between text-xs text-secondary font-mono">
                <span>0:00</span>
                <span>0:30</span>
                <span>1:00</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="danger" size="sm" dot>Scene cuts: 3</Badge>
                <Badge variant="warning" size="sm" dot>Timestamp gaps: 1</Badge>
                <Badge variant="info" size="sm" dot>Findings: 3</Badge>
              </div>
              <div className="space-2 border-t border-default pt-4">
                {mockFindings.map((finding, i) => (
                  <button
                    key={i}
                    onClick={() => setCurrentFrame(finding.frame)}
                    className="w-full text-left p-3 bg-surface rounded-control border border-default hover:border-accent transition-colors flex items-start gap-3"
                  >
                    <StatusDot status={finding.severity} size="sm" className="mt-0.5 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2 text-sm">
                        <span className="font-mono text-secondary">{finding.time}</span>
                        <Badge variant={finding.severity} size="sm">{finding.type}</Badge>
                      </div>
                      <p className="text-sm text-primary mt-1">{finding.description}</p>
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-6">
          <Card variant="default" padding="md">
            <Tabs defaultValue={activeTab} onChange={setActiveTab} variant="default" className="mb-4">
              <TabTrigger value="authenticity">Authenticity</TabTrigger>
              <TabTrigger value="metadata">Metadata</TabTrigger>
              <TabTrigger value="custody">Custody</TabTrigger>
            </Tabs>

            <TabContent value="authenticity" activeValue={activeTab} className="space-4">
              {mockAuthenticityChecks.map((check) => (
                <Card key={check.id} variant="default" padding="md" className="border-l-4 border-l-{check.status === 'danger' ? 'danger' : check.status === 'ok' ? 'ok' : 'warning'}">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div>
                      <h4 className="font-heading text-base font-semibold text-primary">{check.title}</h4>
                      <div className="flex items-center gap-3 mt-1 text-sm">
                        <span className="font-mono text-secondary">Score: {check.score}</span>
                        <span className="font-mono text-secondary">Threshold: {check.threshold}</span>
                        <StatusPill status={check.status} size="sm" label={check.status === 'danger' ? 'FLAGGED' : check.status === 'ok' ? 'CLEAN' : 'WARNING'} />
                      </div>
                    </div>
                  </div>
                  <p className="text-secondary text-sm mb-3">{check.explanation}</p>
                  <details className="group">
                    <summary className="text-xs text-secondary cursor-pointer flex items-center gap-1">
                      <span>Limitations</span>
                      <svg className="w-4 h-4 transition-transform group-open:rotate-90" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </summary>
                    <p className="text-xs text-secondary mt-2 pb-2 border-b border-default">{check.limitations}</p>
                  </details>
                </Card>
              ))}
              <div className="p-3 bg-surface rounded-control border border-default text-sm text-secondary">
                <strong>Frame-level tamper analysis: PLANNED</strong>
                <p className="mt-1">Per-frame manipulation heatmaps and region-level attribution require additional model integration (not yet available in pipeline).</p>
              </div>
            </TabContent>

            <TabContent value="metadata" activeValue={activeTab} className="space-2">
              {mockMetadata.map((item, i) => (
                <div key={i} className="flex justify-between py-2 border-b border-default/50 last:border-0">
                  <span className="text-secondary">{item.key}</span>
                  <span className="font-mono text-primary text-sm text-right max-w-[60%] truncate">{item.value}</span>
                </div>
              ))}
            </TabContent>

            <TabContent value="custody" activeValue={activeTab} className="space-2">
              <div className="mb-4 p-3 bg-surface rounded-control border border-default">
                <p className="text-secondary text-sm mb-1">SHA-256 (full)</p>
                <code className="font-mono text-xs text-primary break-all">a3f2b8c4e9d1f7a6b3c2d5e8f1a4b7c9d2e5f8a1b4c7d0e3f6a9b2c5d8e1f4a</code>
              </div>
              <div className="space-2">
                {mockCustodyEvents.map((event, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-surface rounded-control border border-default">
                    <div className="flex items-center gap-3">
                      <StatusDot
                        status={event.event === 'uploaded' ? 'info' : event.event === 'hashed' ? 'ok' : event.event === 'analyzed' ? 'ok' : 'info'}
                        size="sm"
                      />
                      <div>
                        <p className="font-medium text-primary capitalize">{event.event}</p>
                        <p className="text-xs text-secondary font-mono">{event.user}</p>
                      </div>
                    </div>
                    <span className="text-xs text-secondary font-mono">{new Date(event.timestamp).toLocaleString()}</span>
                  </div>
                ))}
              </div>
              <div className="mt-4 p-3 bg-surface rounded-control border border-default">
                <p className="font-medium text-primary mb-1">Merkle Verification</p>
                <div className="flex items-center gap-2">
                  <StatusDot status="ok" size="sm" />
                  <span className="text-sm text-secondary">Verified — leaf hash matches case manifest</span>
                </div>
              </div>
            </TabContent>
          </Card>
        </div>
      </div>
    </div>
  );
}