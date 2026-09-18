import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { PanelLeft, RotateCcw, Settings, Scale, Search, X } from 'lucide-react';
import { Button } from './Button';
import { Input } from './Input';
import { Badge } from './Badge';
import { Avatar } from './Avatar';
import { ModeToggle } from './ModeToggle';
import './Header.css';

export function Header({
  sidebarOpen,
  onToggleSidebar,
  onNewChat,
  onOpenSettings,
  onOpenEvidence,
  user,
  mode,
  onModeChange
}) {
  const location = useLocation();
  const isAnalytics = location.pathname === '/analytics';
  const [searchOpen, setSearchOpen] = React.useState(false);

  return (
    <header className="header" role="banner">
      <div className="header-left">
        <Button
          variant="ghost"
          size="icon"
          className="header-menu-btn"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          aria-expanded={sidebarOpen}
        >
          <PanelLeft size={20} />
        </Button>

        {isAnalytics && !sidebarOpen && (
          <NavLink to="/analytics" className="header-brand" title="Chorus Home">
            <span className="header-logo" aria-hidden="true">♫</span>
            <span className="header-title">Chorus</span>
          </NavLink>
        )}
      </div>

      <div className="header-center">
        {isAnalytics && (
          <ModeToggle mode={mode} onChange={onModeChange} />
        )}
      </div>

      <div className="header-right">
        {isAnalytics && (
          <>
            <Button
              variant="glass"
              size="sm"
              leftIcon={<Scale size={14} />}
              className="header-evidence-btn"
              onClick={onOpenEvidence}
            >
              Evidence Room
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="header-new-btn"
              onClick={onNewChat}
              title="New analysis"
            >
              <RotateCcw size={16} />
            </Button>
          </>
        )}

        <Button
          variant="ghost"
          size="icon"
          className="header-settings-btn"
          onClick={onOpenSettings}
          title="Settings"
        >
          <Settings size={16} />
        </Button>

        <Avatar name={user?.name || user?.email?.split('@')[0] || 'User'} size="sm" />
      </div>
    </header>
  );
}