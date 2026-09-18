import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { PanelLeft, Scale, LogOut, Settings, Search, X, ChevronDown } from 'lucide-react';
import { Button } from './Button';
import { Avatar } from './Avatar';
import { Badge } from './Badge';
import { Input } from './Input';
import './Sidebar.css';

const NAV_ITEMS = [
  { path: '/analytics', label: 'AI Chat & Cyber', icon: '💬', badge: null },
  { path: '/evidence', label: 'Evidence Room', icon: '⚖️', badge: null },
];

export function Sidebar({ collapsed = false, onToggle, user }) {
  const location = useLocation();
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState('');

  const handleToggle = () => {
    onToggle?.(!collapsed);
    if (!collapsed) setSearchOpen(false);
  };

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`} aria-label="Main navigation">
      {/* Brand Header */}
      <div className="sidebar-header">
        <NavLink to="/analytics" className="sidebar-brand" onClick={handleToggle} title="Chorus Home">
          <span className="sidebar-logo" aria-hidden="true">♫</span>
          {!collapsed && <span className="sidebar-title">Chorus</span>}
        </NavLink>

        {!collapsed && (
          <Button
            variant="ghost"
            size="icon-sm"
            className="sidebar-toggle-btn"
            onClick={handleToggle}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <PanelLeft size={18} />
          </Button>
        )}
      </div>

      {/* Search */}
      {!collapsed && searchOpen && (
        <div className="sidebar-search">
          <Input
            type="search"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            leftIcon={<Search size={16} />}
            rightIcon={searchQuery && (
              <button className="search-clear" onClick={() => setSearchQuery('')}>
                <X size={14} />
              </button>
            )}
            autoFocus
          />
        </div>
      )}

      {/* Navigation */}
      <nav className="sidebar-nav" aria-label="Primary">
        <ul className="sidebar-nav-list">
          {NAV_ITEMS.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => `sidebar-nav-item ${isActive ? 'active' : ''}`}
                onClick={handleToggle}
                title={collapsed ? item.label : undefined}
              >
                <span className="sidebar-nav-icon" aria-hidden="true">{item.icon}</span>
                {!collapsed && (
                  <>
                    <span className="sidebar-nav-label">{item.label}</span>
                    {item.badge && <Badge variant="cyber" size="xs">{item.badge}</Badge>}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {!collapsed && (
        <>
          {/* User Section */}
          <div className="sidebar-divider" />

          <div className="sidebar-user" onClick={() => { /* settings */ }}>
            <Avatar
              name={user?.name || user?.email?.split('@')[0] || 'User'}
              size="sm"
              status="online"
            />
            <div className="sidebar-user-info">
              <span className="sidebar-user-name">
                {user?.name || user?.email?.split('@')[0] || 'User'}
              </span>
              <span className="sidebar-user-plan">Chorus Enterprise</span>
            </div>
            <Button variant="ghost" size="icon-sm" className="sidebar-user-settings">
              <Settings size={16} />
            </Button>
          </div>

          {/* Sign Out */}
          <div className="sidebar-signout">
            <Button
              variant="ghost"
              size="sm"
              fullWidth
              leftIcon={<LogOut size={16} />}
              className="sidebar-signout-btn"
            >
              Sign Out
            </Button>
          </div>
        </>
      )}
    </aside>
  );
}