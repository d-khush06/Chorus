import { Card, CardHeader, CardTitle, CardContent } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill } from './primitives/StatusPill';

export function TracePage() {
  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6 p-4 bg-surface border border-warning/30 rounded-card">
        <div className="flex items-start gap-4">
          <StatusPill status="warning" label="Coming Soon" size="md" dot className="flex-shrink-0" />
          <div className="flex-1">
            <h2 className="font-heading text-lg font-semibold text-primary mb-2">Person Tracking & Geolocation</h2>
            <p className="text-secondary text-base mb-3">
              This feature requires <code className="font-mono text-sm bg-bg px-1.5 py-0.5 rounded-small">face_reid_agent</code> and
              <code className="font-mono text-sm bg-bg px-1.5 py-0.5 rounded-small">geo_estimation_agent</code>
              to produce usable output in a normal run and pass governance gates.
            </p>
            <div className="space-2 text-sm text-secondary">
              <p><strong>Planned capabilities:</strong></p>
              <ul className="list-disc list-inside space-1 ml-4">
                <li>Person identity tracking across multiple camera feeds</li>
                <li>GPS location estimation from scene frames</li>
                <li>Movement trajectory visualization on map</li>
                <li>Cross-camera person re-identification</li>
              </ul>
              <p className="mt-2">
                <strong>Governance requirement:</strong> Face re-identification requires <code className="font-mono text-sm bg-bg px-1.5 py-0.5 rounded-small">governance_approved: true</code>
                with a real legal/consent process (BIPA, GDPR biometric provisions).
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-6">
          <Card variant="stage" padding="none" className="aspect-video relative overflow-hidden">
            <div className="absolute inset-0 bg-stage flex items-center justify-center">
              <div className="text-center text-secondary">
                <svg className="w-16 h-16 mx-auto mb-4 text-border" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" x2="12" y1="8" y2="12" />
                  <line x1="12" x2="12.01" y1="16" y2="16" />
                </svg>
                <p className="font-heading text-xl font-semibold text-primary mb-1">No trace data</p>
                <p>Connect a forensic case with person tracking enabled</p>
              </div>
            </div>
          </Card>

          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-lg">Person Tracks</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No person tracks"
                description="Person tracks appear here after a forensic analysis with face re-identification enabled."
                variant="minimal"
              />
            </CardContent>
          </Card>
        </div>

        <div className="space-6">
          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-lg">Location Estimate</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="aspect-square bg-surface border border-default rounded-control flex items-center justify-center">
                <div className="text-center text-secondary">
                  <svg className="w-12 h-12 mx-auto mb-3 text-border" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                    <circle cx="12" cy="12" r="10" />
                    <path d="M12 2v2M12 20v2M2 12h2M20 12h2" />
                  </svg>
                  <p>Map view placeholder</p>
                  <p className="text-sm mt-1">Requires geo_estimation_agent output</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-lg">Pipeline Status</CardTitle>
            </CardHeader>
            <CardContent className="space-3">
              <div className="flex items-center justify-between p-3 bg-surface rounded-control border border-default">
                <div className="flex items-center gap-3">
                  <StatusDot status="neutral" size="md" />
                  <div>
                    <p className="font-medium text-primary">face_reid_agent</p>
                    <p className="text-xs text-secondary">Governance gate not passed</p>
                  </div>
                </div>
                <Badge variant="neutral" size="sm">Blocked</Badge>
              </div>
              <div className="flex items-center justify-between p-3 bg-surface rounded-control border border-default">
                <div className="flex items-center gap-3">
                  <StatusDot status="neutral" size="md" />
                  <div>
                    <p className="font-medium text-primary">geo_estimation_agent</p>
                    <p className="text-xs text-secondary">Model not loaded</p>
                  </div>
                </div>
                <Badge variant="neutral" size="sm">Not loaded</Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}