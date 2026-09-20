import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './primitives/Card';
import { Button } from './primitives/Button';
import { Badge } from './primitives/Badge';
import { StatusPill, StatusDot } from './primitives/StatusPill';
import { EmptyState } from './primitives/EmptyState';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export function TracePage() {
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [traceStatus, setTraceStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(false);

  const fetchTraceStatus = async () => {
    setLoadingStatus(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_BASE}/api/cyber/trace/status`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        setTraceStatus(data);
      }
    } catch (err) {
      console.warn('Failed to fetch trace status', err);
    } finally {
      setLoadingStatus(false);
    }
  };

  const handleOpenStatus = () => {
    setStatusDialogOpen(true);
    fetchTraceStatus();
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 route-enter">
      {/* ── Top Governance Banner ── */}
      <div
        className="p-5 border border-default rounded-card"
        style={{ backgroundColor: 'var(--card)', boxShadow: 'var(--card-shadow)' }}
      >
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <StatusPill status="warning" label="Coming soon" size="md" dot className="flex-shrink-0" />
            <div>
              <h2 className="font-heading text-lg font-semibold text-primary mb-1">
                Person Tracking & Geolocation (Policy G-14 Gated)
              </h2>
              <p className="text-secondary text-sm leading-relaxed max-w-3xl">
                This feature requires <code className="font-mono text-xs bg-bg px-1.5 py-0.5 rounded-small border border-default">face_reid_agent</code> and <code className="font-mono text-xs bg-bg px-1.5 py-0.5 rounded-small border border-default">geo_estimation_agent</code> to satisfy legal consent requirements before processing biometric streams.
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleOpenStatus}
            className="flex-shrink-0 self-start text-xs"
          >
            View status
          </Button>
        </div>
      </div>

      {/* ── Main Trace Console ── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-y-6">
          {/* Video Stage with Highlighted Track Placeholder */}
          <Card variant="stage" padding="none" className="aspect-video relative overflow-hidden border border-default rounded-card">
            <div
              className="absolute inset-0 flex items-center justify-center"
              style={{ backgroundColor: 'var(--stage-bg, #141413)' }}
            >
              <div className="text-center text-secondary p-6">
                <div className="w-12 h-12 mx-auto mb-3 text-secondary">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </div>
                <h3 className="font-heading text-lg font-semibold text-primary mb-1">
                  Trace Video Stage Ready (#141413)
                </h3>
                <p className="text-xs text-secondary max-w-sm mx-auto">
                  Highlighted person tracks and cross-feed re-identification bounding boxes will render here upon governance unlocking.
                </p>
              </div>
            </div>
          </Card>

          {/* Person Tracks Card */}
          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-base">Person Tracks</CardTitle>
            </CardHeader>
            <CardContent>
              <EmptyState
                title="No person tracks"
                description="Person tracks and re-ID trajectories will appear here once biometric consent verification is approved."
                variant="minimal"
              />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {/* Location Map Card */}
          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-base">Location Estimate Map</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="aspect-square bg-surface border border-default rounded-control flex items-center justify-center p-6 text-center">
                <div>
                  <div className="w-10 h-10 mx-auto mb-2 text-secondary">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 2v2M12 20v2M2 12h2M20 12h2" />
                    </svg>
                  </div>
                  <p className="text-primary font-medium text-sm">Geodetic Map View</p>
                  <p className="text-xs text-secondary mt-1">
                    Requires verified satellite licensing from geo_estimation_agent
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Governance Pipeline Gates Status */}
          <Card variant="default" padding="md">
            <CardHeader>
              <CardTitle className="text-base">Pipeline Governance Gates</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs font-mono">
              <div className="p-3 bg-surface border border-default rounded-control flex items-center justify-between">
                <div>
                  <div className="font-semibold text-primary">face_reid_agent</div>
                  <div className="text-secondary text-[11px] mt-0.5">Policy G-14 Biometric Consent</div>
                </div>
                <Badge variant="warning" size="sm">Gated</Badge>
              </div>

              <div className="p-3 bg-surface border border-default rounded-control flex items-center justify-between">
                <div>
                  <div className="font-semibold text-primary">geo_estimation_agent</div>
                  <div className="text-secondary text-[11px] mt-0.5">Geodetic Model Certification</div>
                </div>
                <Badge variant="neutral" size="sm">Gated</Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Status Dialog (from GET /api/cyber/trace/status) */}
      {statusDialogOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <Card variant="default" padding="lg" className="max-w-lg w-full">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Trace Governance & Policy Status</CardTitle>
                <button
                  onClick={() => setStatusDialogOpen(false)}
                  className="text-secondary hover:text-primary p-1"
                >
                  ✕
                </button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 text-xs">
              {loadingStatus ? (
                <div className="py-8 text-center text-secondary font-mono animate-pulse">
                  Querying GET /api/cyber/trace/status…
                </div>
              ) : traceStatus ? (
                <>
                  <div className="p-3 bg-surface border border-default rounded-control space-y-1.5">
                    <div className="flex items-center justify-between font-semibold text-primary">
                      <span>Facial Re-ID Gate:</span>
                      <Badge variant="danger" size="sm">{traceStatus.face_reid?.gate_status || 'RESTRICTED'}</Badge>
                    </div>
                    <p className="text-secondary leading-relaxed font-sans">
                      {traceStatus.face_reid?.reason}
                    </p>
                  </div>

                  <div className="p-3 bg-surface border border-default rounded-control space-y-1.5">
                    <div className="flex items-center justify-between font-semibold text-primary">
                      <span>Geolocation Gate:</span>
                      <Badge variant="warning" size="sm">{traceStatus.geo_estimation?.gate_status || 'RESTRICTED'}</Badge>
                    </div>
                    <p className="text-secondary leading-relaxed font-sans">
                      {traceStatus.geo_estimation?.reason}
                    </p>
                  </div>

                  <div className="p-3 bg-bg border border-default rounded-control space-y-1 font-mono text-[11px]">
                    <div className="text-secondary">ACTION REQUIRED:</div>
                    <div className="text-primary">{traceStatus.action_required}</div>
                    <div className="text-secondary mt-1">COMPLIANCE POLICY: {traceStatus.compliance_doc}</div>
                  </div>
                </>
              ) : (
                <div className="text-danger py-4">Unable to reach trace governance endpoint.</div>
              )}
            </CardContent>
            <CardFooter className="flex justify-end">
              <Button variant="primary" size="sm" onClick={() => setStatusDialogOpen(false)}>
                Close
              </Button>
            </CardFooter>
          </Card>
        </div>
      )}
    </div>
  );
}