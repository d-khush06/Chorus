import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill, StatusDot } from './primitives/StatusPill';
import { Skeleton, SkeletonCard } from './primitives/Skeleton';
import { EmptyState } from './primitives/EmptyState';
import { Tabs, TabTrigger, TabContent } from './primitives/Tabs';

export function LiveWatchPage() {
  const [cameraConnected, setCameraConnected] = useState(false);
  const [activeAgentTab, setActiveAgentTab] = useState('observations');
  const [rtspUrl, setRtspUrl] = useState('');

  const mockObservations = [
    { time: '14:32:07', message: 'Person detected at Sector 4 gate', type: 'detection' },
    { time: '14:32:05', message: 'Acoustic event: alarm', type: 'acoustic' },
    { time: '14:32:02', message: 'Chunk analyzed: 30s segment complete', type: 'chunk' },
    { time: '14:31:58', message: 'Frame continuity verified', type: 'continuity' },
    { time: '14:31:55', message: 'Deepfake screening: clean', type: 'deepfake' },
  ];

  const mockAlerts = [
    { time: '14:32:07', severity: 'warning', message: 'Acoustic alarm detected', source: 'acoustic' },
    { time: '14:31:45', severity: 'ok', message: 'Stream continuity OK', source: 'continuity' },
    { time: '14:30:22', severity: 'info', message: 'New chunk started', source: 'chunk' },
  ];

  if (!cameraConnected) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-heading text-2xl font-semibold text-primary">Live Watch</h1>
            <p className="text-secondary">Connect an RTSP camera to begin real-time monitoring</p>
          </div>
          <StatusPill status="neutral" label="No camera" size="md" />
        </div>

        <Card variant="default" padding="lg" className="max-w-2xl">
          <CardHeader>
            <CardTitle>Camera Connection</CardTitle>
          </CardHeader>
          <CardContent className="space-4">
            <div>
              <label className="block text-sm font-medium text-secondary mb-2">RTSP URL</label>
              <input
                type="text"
                value={rtspUrl}
                onChange={(e) => setRtspUrl(e.target.value)}
                placeholder="rtsp://user:pass@camera.local:554/stream"
                className="w-full px-4 py-2.5 bg-bg border border-default rounded-control text-primary placeholder:text-secondary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-surface font-mono text-sm"
              />
            </div>
            <div className="flex gap-3">
              <Button variant="secondary" onClick={() => setCameraConnected(true)} disabled={!rtspUrl}>
                Test Connection
              </Button>
              <Button variant="primary" onClick={() => setCameraConnected(true)} disabled={!rtspUrl}>
                Start Monitoring
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <div className="space-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-2xl font-semibold text-primary">Live Watch</h1>
            <p className="text-secondary">CAM-04 • rtsp://***:***@cam-04.perimeter.internal:554/live</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusDot status="live" size="md" pulse />
            <StatusPill status="live" label="LIVE" size="md" pulse />
          </div>
        </div>

        <Card variant="stage" padding="none" className="aspect-video relative overflow-hidden">
          <div className="absolute inset-0 bg-stage flex items-center justify-center">
            <div className="text-center text-secondary">
              <div className="w-16 h-16 mx-auto mb-4 border-4 border-accent border-t-transparent rounded-full animate-spin" />
              <p>Loading stream...</p>
            </div>
          </div>
          <div className="absolute top-4 left-4 flex items-center gap-2 bg-surface/90 backdrop-blur-sm px-3 py-1.5 rounded-control">
            <StatusDot status="live" size="sm" pulse />
            <span className="font-mono text-sm font-medium">LIVE</span>
          </div>
          <div className="absolute top-4 right-4 bg-surface/90 backdrop-blur-sm px-3 py-1.5 rounded-control font-mono text-sm">
            29.97 FPS • 4.2 Mbps
          </div>
          <div className="absolute bottom-4 left-4 bg-surface/90 backdrop-blur-sm px-3 py-1.5 rounded-control font-mono text-sm">
            Last chunk: 14:32:07
          </div>
        </Card>

        <Card variant="default" padding="md">
          <CardHeader>
            <CardTitle className="text-lg">Chunk Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative h-16 bg-surface rounded-control overflow-hidden border border-default">
              {Array.from({ length: 20 }, (_, i) => (
                <div
                  key={i}
                  className={`absolute top-0 bottom-0 border-r border-default transition-colors ${
                    i === 10 ? 'bg-accent/30' : 'bg-border/50 hover:bg-accent/10'
                  }`}
                  style={{ left: `${i * 5}%`, width: '5%' }}
                  title={`Chunk ${i + 1}: ${String(Math.floor(i * 1.5)).padStart(2, '0')}:00-${String(Math.floor((i + 1) * 1.5)).padStart(2, '0')}:00`}
                />
              ))}
              <div className="absolute top-0 bottom-0 w-px bg-accent animate-pulse-slow" style={{ left: '52.5%' }} />
            </div>
            <div className="flex justify-between text-xs text-secondary mt-2 font-mono">
              <span>0:00</span>
              <span>5:00</span>
              <span>10:00</span>
            </div>
          </CardContent>
        </Card>

        <Card variant="default" padding="md">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <StatusDot status="info" size="sm" />
              Alert Feed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-2 max-h-64 overflow-y-auto" role="log" aria-live="polite" aria-label="Alert feed">
              {mockAlerts.map((alert, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 p-3 bg-surface rounded-control border border-default"
                >
                  <StatusDot status={alert.severity} size="sm" className="mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-mono text-secondary">{alert.time}</span>
                      <Badge variant={alert.severity} size="sm" dot>{alert.source}</Badge>
                    </div>
                    <p className="text-primary text-sm mt-0.5">{alert.message}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-6">
        <Card variant="default" padding="md">
          <CardHeader>
            <CardTitle className="text-lg">Live Agent</CardTitle>
          </CardHeader>
          <CardContent className="space-4">
            <Tabs defaultValue={activeAgentTab} onChange={setActiveAgentTab} variant="pills">
              <TabTrigger value="observations">Observations</TabTrigger>
              <TabTrigger value="ask">Ask</TabTrigger>
              <TabTrigger value="rules">Rules</TabTrigger>
            </Tabs>

            <TabContent value="observations" activeValue={activeAgentTab}>
              <div className="space-3 max-h-96 overflow-y-auto">
                {mockObservations.map((obs, i) => (
                  <div key={i} className="flex gap-3 p-3 bg-surface rounded-control border border-default">
                    <span className="font-mono text-xs text-secondary flex-shrink-0">{obs.time}</span>
                    <span className="text-sm text-primary">{obs.message}</span>
                    <Badge variant={obs.type === 'acoustic' ? 'info' : obs.type === 'deepfake' ? 'ok' : 'default'} size="sm">
                      {obs.type}
                    </Badge>
                  </div>
                ))}
              </div>
              <div className="pt-3 border-t border-default">
                <p className="text-sm text-secondary font-mono">Last analyzed: 12s ago</p>
              </div>
            </TabContent>

            <TabContent value="ask" activeValue={activeAgentTab}>
              <div className="space-4">
                <div className="p-3 bg-surface rounded-control border border-default text-sm text-secondary">
                  <p>Ask about the recent feed. Answers are based on the last 5 minutes of observations.</p>
                  <p className="mt-1 font-mono text-xs">Model: Qwen2.5-VL • Window: 5 min</p>
                </div>
                <div className="flex flex-col gap-2">
                  <input
                    type="text"
                    placeholder="What happened at 14:31?"
                    className="px-4 py-2.5 bg-bg border border-default rounded-control text-primary placeholder:text-secondary focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-surface"
                  />
                  <Button variant="primary" size="sm">Ask</Button>
                </div>
              </div>
            </TabContent>

            <TabContent value="rules" activeValue={activeAgentTab}>
              <div className="space-3">
                <div className="p-3 bg-surface rounded-control border border-default text-sm text-secondary">
                  Create standing watch rules. Matches emit alerts.
                </div>
                <Button variant="secondary" size="sm" className="w-full">Create Rule</Button>
                <p className="text-xs text-secondary text-center">No rules configured</p>
              </div>
            </TabContent>
          </CardContent>
        </Card>

        <Card variant="default" padding="md">
          <CardHeader>
            <CardTitle className="text-lg">Session Controls</CardTitle>
          </CardHeader>
          <CardContent className="space-3">
            <Button variant="danger" className="w-full">Stop & Save Case</Button>
            <Button variant="outline" className="w-full">Stop Session</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}