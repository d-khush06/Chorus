import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { Tabs, TabTrigger } from './primitives/Tabs';
import { ThemeToggle } from './primitives/ThemeToggle';
import { StatusPill } from './primitives/StatusPill';
import { Button } from './primitives/Button';
import { useTheme } from './primitives/ThemeToggle';

const CYBER_TABS = [
  { value: 'live', label: 'Live Watch' },
  { value: 'forensic', label: 'Forensic' },
  { value: 'trace', label: 'Trace' },
];

export function CyberLayout({ connectionStatus = 'standby' }) {
  const navigate = useNavigate();
  const location = useLocation();

  const activeTab = location.pathname.split('/').pop() || 'live';

  const handleBackToChat = () => {
    navigate('/analytics');
  };

  const handleTabChange = (value) => {
    navigate(`/cyber/${value}`);
  };

  return (
    <div className="cyber-console min-h-screen flex flex-col" style={{ backgroundColor: 'var(--bg)', color: 'var(--text)' }}>
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <header
        className="flex items-center justify-between px-6 py-3 border-b sticky top-0 z-50"
        style={{ backgroundColor: 'var(--topbar)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-3">
          {/* Theme toggle placed at the far left of the Cyber console top bar */}
          <ThemeToggle className="text-secondary hover:text-primary" />
          <div className="h-4 w-px bg-border" />
          
          <Button
            variant="ghost"
            size="sm"
            onClick={handleBackToChat}
            aria-label="Back to chat"
            className="flex items-center gap-2 text-secondary hover:text-primary font-medium"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <line x1="19" x2="5" y1="12" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            <span>Back to chat</span>
          </Button>

          <div className="h-4 w-px bg-border hidden sm:block" />

          <Tabs defaultValue={activeTab} value={activeTab} onChange={handleTabChange} variant="underline" className="max-w-md justify-center">
            {CYBER_TABS.map((tab) => (
              <TabTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabTrigger>
            ))}
          </Tabs>
        </div>

        <div className="flex items-center gap-4">
          <StatusPill
            status={connectionStatus === 'connected' ? 'live' : (connectionStatus === 'running' ? 'warning' : 'neutral')}
            label={connectionStatus === 'connected' ? 'Connected' : (connectionStatus === 'running' ? 'Running' : 'Standby')}
            size="sm"
            dot
            pulse={connectionStatus === 'connected' || connectionStatus === 'running'}
          />
        </div>
      </header>

      <main id="main-content" className="flex-1 p-6 overflow-auto route-enter" tabIndex="-1">
        <Outlet />
      </main>
    </div>
  );
}

export function CyberLandingPage() {
  const navigate = useNavigate();
  const [recentCases, setRecentCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(true);

  useEffect(() => {
    async function loadCyberCases() {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:5000'}/api/cases?case_type=cyber`, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
        if (res.ok) {
          const json = await res.json();
          if (json.success && Array.isArray(json.data)) {
            setRecentCases(json.data);
          }
        }
      } catch (err) {
        console.warn('Failed to load recent cyber cases', err);
      } finally {
        setLoadingCases(false);
      }
    }
    loadCyberCases();
  }, []);

  const cards = [
    {
      id: 'live',
      title: 'Live Watch',
      description: 'Real-time RTSP stream surveillance. Detect frame splicing, deepfakes, and stream continuity interruptions in 30-second sliding windows.',
      icon: (
        <svg className="w-9 h-9 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      ),
      status: 'Ready',
      action: 'Open Live Watch',
      href: '/cyber/live',
      disabled: false,
    },
    {
      id: 'forensic',
      title: 'Forensic Analysis',
      description: 'Multi-layer evidentiary examination. SBI facial deepfake screening, latent diffusion artifact detection, and cryptographic Merkle sealing.',
      icon: (
        <svg className="w-9 h-9 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      ),
      status: 'Ready',
      action: 'Start Forensic Run',
      href: '/cyber/forensic',
      disabled: false,
    },
    {
      id: 'trace',
      title: 'Trace',
      description: 'Cross-feed identity re-identification and satellite-referenced scene geolocation. Requires Policy G-14 governance approval.',
      icon: (
        <svg className="w-9 h-9 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v4.5M12 17.5V22M4.93 4.93l3.15 3.15M15.93 15.93l3.15 3.15M2 12h4.5M17.5 12H22M4.93 19.07l3.15-3.15M15.93 8.07l3.15-3.15" />
        </svg>
      ),
      status: 'Gated (Policy G-14)',
      action: 'View Trace Console',
      href: '/cyber/trace',
      disabled: false,
    },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-8 route-enter">
      <div className="text-center">
        <h1 className="font-heading text-3xl sm:text-4xl font-bold text-primary mb-3">
          Cyber Investigation Console
        </h1>
        <p className="text-secondary text-base max-w-2xl mx-auto">
          Enterprise operational security, video tamper detection, and cryptographic evidence verification.
        </p>
      </div>

      {/* Three Equal Cards */}
      <div className="grid gap-6 md:grid-cols-3 card-group">
        {cards.map((card) => (
          <div
            key={card.id}
            onClick={() => navigate(card.href)}
            className="cursor-pointer border border-border rounded-card p-6 transition-all duration-fast hover:border-accent flex flex-col justify-between"
            style={{
              backgroundColor: 'var(--card)',
              borderColor: 'var(--border)',
              boxShadow: 'var(--card-shadow)'
            }}
          >
            <div>
              <div className="mb-4" aria-hidden="true">
                {card.icon}
              </div>
              <h2 className="font-heading text-xl font-semibold text-primary mb-2">
                {card.title}
              </h2>
              <p className="text-secondary text-sm leading-relaxed mb-6">
                {card.description}
              </p>
            </div>
            <div className="flex items-center justify-between pt-4 border-t border-border">
              <span className="text-xs font-mono text-secondary">{card.status}</span>
              <Button
                variant={card.id === 'forensic' ? 'primary' : 'outline'}
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(card.href);
                }}
              >
                {card.action}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* Recent Investigations Card from Real Cases */}
      <div
        className="border border-border rounded-card p-6"
        style={{
          backgroundColor: 'var(--card)',
          borderColor: 'var(--border)',
          boxShadow: 'var(--card-shadow)'
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-heading text-lg font-semibold text-primary">
              Recent Cyber Investigations
            </h2>
            <p className="text-secondary text-xs mt-0.5">
              Cryptographically preserved records from the Evidence Room
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/evidence')}
            className="text-secondary hover:text-primary text-xs"
          >
            View Evidence Room →
          </Button>
        </div>

        {loadingCases ? (
          <div className="py-8 text-center text-secondary font-mono text-xs animate-pulse">
            Loading investigation records…
          </div>
        ) : recentCases.length === 0 ? (
          <div
            className="py-8 text-center border border-dashed border-border rounded-control"
            style={{ borderColor: 'var(--border)' }}
          >
            <p className="text-primary font-medium text-sm mb-1">No recent investigations</p>
            <p className="text-secondary text-xs max-w-sm mx-auto">
              Completed forensic runs and sealed live monitoring sessions will appear here with cryptographic integrity hashes.
            </p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {recentCases.slice(0, 5).map((c) => (
              <div
                key={c.case_id}
                onClick={() => navigate('/evidence')}
                className="p-3.5 rounded-control flex items-center justify-between gap-4 cursor-pointer transition-colors border border-border"
                style={{ backgroundColor: 'var(--surface-alt)', borderColor: 'var(--border)' }}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-primary">
                      {c.case_id}
                    </span>
                    {c.title && (
                      <span className="text-xs text-secondary truncate">
                        — {c.title}
                      </span>
                    )}
                  </div>
                  <div className="font-mono text-[11px] text-secondary truncate max-w-md mt-0.5">
                    SHA-256: {c.raw_video_hash || c.sha256 || 'Pending seal'}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <StatusPill
                    status={c.status === 'flagged' ? 'warning' : 'ok'}
                    label={c.status === 'flagged' ? 'Flagged' : 'Sealed'}
                    size="sm"
                    dot
                  />
                  <span className="text-[11px] font-mono text-secondary hidden sm:inline">
                    {c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}