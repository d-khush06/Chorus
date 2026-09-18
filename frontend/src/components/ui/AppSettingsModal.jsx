import React, { useState } from 'react';
import './UserMenuModals.css';

export default function AppSettingsModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('general');
  const [defaultModel, setDefaultModel] = useState('flash');
  const [streamResponse, setStreamResponse] = useState(true);
  const [soundAlerts, setSoundAlerts] = useState(false);
  const [sensitivity, setSensitivity] = useState('High');
  const [hashVerification, setHashVerification] = useState(true);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [autoLock, setAutoLock] = useState('30m');
  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSave = (e) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 600);
  };

  return (
    <div className="umm-overlay" onClick={onClose}>
      <div className="umm-modal umm-modal-wide" onClick={e => e.stopPropagation()}>
        {/* Header (No icons) */}
        <div className="umm-header">
          <div className="umm-header-left">
            <h2>Settings</h2>
            <span className="umm-header-subtitle">Preferences and system configuration</span>
          </div>
          <button className="umm-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {/* Tab Navigation (Text only, no icons) */}
        <div className="umm-tabs">
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'general' ? 'active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            General
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'forensics' ? 'active' : ''}`}
            onClick={() => setActiveTab('forensics')}
          >
            Forensics
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            Security
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'data' ? 'active' : ''}`}
            onClick={() => setActiveTab('data')}
          >
            Data
          </button>
        </div>

        {/* Form Body (No colors, No icons) */}
        <form className="umm-body" onSubmit={handleSave}>
          {activeTab === 'general' && (
            <>
              <div className="umm-form-group">
                <label>Default Model</label>
                <select
                  className="umm-input"
                  value={defaultModel}
                  onChange={e => setDefaultModel(e.target.value)}
                >
                  <option value="flash">Chorus Flash (Fast, 800ms)</option>
                  <option value="deepthink">Chorus Deepthink (Detailed reasoning)</option>
                </select>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Stream response</span>
                  <span className="umm-toggle-desc">Show text progressively as it is generated</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={streamResponse} 
                    onChange={e => setStreamResponse(e.target.checked)} 
                  />
                  <span className="umm-slider" />
                </label>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Sound notifications</span>
                  <span className="umm-toggle-desc">Play chime when high-severity anomalies are detected</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={soundAlerts} 
                    onChange={e => setSoundAlerts(e.target.checked)} 
                  />
                  <span className="umm-slider" />
                </label>
              </div>
            </>
          )}

          {activeTab === 'forensics' && (
            <>
              <div className="umm-form-group">
                <label>Detection Sensitivity</label>
                <select 
                  className="umm-input"
                  value={sensitivity} 
                  onChange={e => setSensitivity(e.target.value)}
                >
                  <option value="Maximum">Maximum (Flag minor discrepancies)</option>
                  <option value="High">High (Recommended)</option>
                  <option value="Balanced">Balanced (Standard)</option>
                </select>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Hash verification</span>
                  <span className="umm-toggle-desc">Continuously check SHA-256 signatures against stream source</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={hashVerification} 
                    onChange={e => setHashVerification(e.target.checked)} 
                  />
                  <span className="umm-slider" />
                </label>
              </div>
            </>
          )}

          {activeTab === 'security' && (
            <>
              <div className="umm-form-group">
                <label>Current Password</label>
                <input 
                  type="password" 
                  className="umm-input" 
                  value={currentPassword}
                  onChange={e => setCurrentPassword(e.target.value)}
                  placeholder="Enter current password"
                />
              </div>

              <div className="umm-form-group">
                <label>New Password</label>
                <input 
                  type="password" 
                  className="umm-input" 
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                />
              </div>

              <div className="umm-form-group">
                <label>Session Timeout</label>
                <select
                  className="umm-input"
                  value={autoLock}
                  onChange={e => setAutoLock(e.target.value)}
                >
                  <option value="15m">15 minutes</option>
                  <option value="30m">30 minutes</option>
                  <option value="1h">1 hour</option>
                  <option value="never">Never</option>
                </select>
              </div>
            </>
          )}

          {activeTab === 'data' && (
            <>
              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Export session data</span>
                  <span className="umm-toggle-desc">Download your investigation history and analysis logs</span>
                </div>
                <button
                  type="button"
                  className="umm-btn-cancel"
                  onClick={() => alert("Export started.")}
                >
                  Export
                </button>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Clear local cache</span>
                  <span className="umm-toggle-desc">Remove locally cached sessions and temporary analysis data</span>
                </div>
                <button
                  type="button"
                  className="umm-btn-cancel"
                  onClick={() => {
                    if (window.confirm("Clear local cache?")) {
                      alert("Cache cleared.");
                    }
                  }}
                >
                  Clear Cache
                </button>
              </div>
            </>
          )}

          {/* Footer (No icons) */}
          <div className="umm-footer" style={{ padding: '12px 0 0 0', border: 'none' }}>
            <button type="button" className="umm-btn-cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="umm-btn-primary">
              {saved ? 'Saved' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
