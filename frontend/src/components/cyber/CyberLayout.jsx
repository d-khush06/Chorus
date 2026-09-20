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

export function CyberLayout({ connectionStatus = 'disconnected' }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme } = useTheme();

  const activeTab = location.pathname.split('/').pop() || 'live';

  const handleBackToChat = () => {
    navigate('/analytics');
  };

  const handleTabChange = (value) => {
    navigate(`/cyber/${value}`);
  };

  return (
    <div className="cyber-console min-h-screen flex flex-col">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      <header className="flex items-center justify-between px-6 py-4 border-b border-default bg-surface/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleBackToChat}
            aria-label="Back to chat"
            className="hidden sm:flex items-center gap-2 text-secondary hover:text-primary"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <line x1="19" x2="5" y1="12" y2="12" />
              <polyline points="12 19 5 12 12 5" />
            </svg>
            <span>Back to chat</span>
          </Button>

          <Tabs defaultValue={activeTab} onChange={handleTabChange} variant="underline" className="flex-1 max-w-md justify-center">
            {CYBER_TABS.map((tab) => (
              <TabTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabTrigger>
            ))}
          </Tabs>
        </div>

        <div className="flex items-center gap-4">
          <StatusPill
            status={connectionStatus === 'connected' ? 'live' : 'neutral'}
            label={connectionStatus === 'connected' ? 'Connected' : 'Not connected'}
            size="sm"
            pulse={connectionStatus === 'connected'}
          />
          <ThemeToggle showLabel />
        </div>
      </header>

      <main id="main-content" className="flex-1 p-6 overflow-auto" tabIndex="-1">
        <Outlet />
      </main>
    </div>
  );
}

export function CyberLandingPage() {
  const navigate = useNavigate();

  const cards = [
    {
      id: 'live',
      title: 'Live Watch',
      description: 'Monitor RTSP camera feeds in real-time. Detect tampering, deepfakes, and stream anomalies as they happen.',
      icon: (
        <svg className="w-10 h-10 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
      ),
      status: 'Not connected',
      action: 'Enter RTSP URL',
      href: '/cyber/live',
    },
    {
      id: 'forensic',
      title: 'Forensic Analysis',
      description: 'Analyze video files for manipulation, deepfakes, and integrity violations. Frame-level tamper detection and cryptographic verification.',
      icon: (
        <svg className="w-10 h-10 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" x2="12" y1="8" y2="12" />
          <line x1="12" x2="12.01" y1="16" y2="16" />
        </svg>
      ),
      status: 'Upload file or URL',
      action: 'Start analysis',
      href: '/cyber/forensic',
    },
    {
      id: 'trace',
      title: 'Trace',
      description: 'Track persons across camera feeds and estimate geolocation from scene frames. Requires governance approval.',
      icon: (
        <svg className="w-10 h-10 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v4.5M12 17.5V22M4.93 4.93l3.15 3.15M15.93 15.93l3.15 3.15M2 12h4.5M17.5 12H22M4.93 19.07l3.15-3.15M15.93 8.07l3.15-3.15" />
        </svg>
      ),
      status: 'Coming soon',
      action: 'Not available',
      disabled: true,
    },
  ];

  return (
    <div className="max-w-6xl mx-auto">
      <div className="text-center mb-12">
        <h1 className="font-heading text-4xl font-bold text-primary mb-4">
          Cyber Investigation Console
        </h1>
        <p className="text-secondary text-lg max-w-2xl mx-auto">
          Three specialized views onto the same forensic pipeline. Choose your entry point.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {cards.map((card) => (
          <a
            key={card.id}
            href={card.href}
            className="block"
            style={{ pointerEvents: card.disabled ? 'none' : 'auto' }}
          >
            <div className="bg-surface border border-default rounded-card p-6 hover:border-accent transition-colors duration-fast h-full flex flex-col">
              <div className="mb-4" aria-hidden="true">
                {card.icon}
              </div>
              <h3 className="font-heading text-xl font-semibold text-primary mb-2">
                {card.title}
              </h3>
              <p className="text-secondary text-base mb-4 flex-1">
                {card.description}
              </p>
              <div className="flex items-center justify-between pt-4 border-t border-default">
                <span className="text-sm text-secondary">{card.status}</span>
                <Button
                  variant={card.disabled ? 'ghost' : 'primary'}
                  size="sm"
                  disabled={card.disabled}
                  className="w-auto"
                >
                  {card.action}
                </Button>
              </div>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}