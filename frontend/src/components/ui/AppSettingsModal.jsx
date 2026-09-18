import React, { useState } from 'react';
import { X, Settings, Sliders, ShieldAlert, Key, Database, Check } from 'lucide-react';
import './UserMenuModals.css';

export default function AppSettingsModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('general');
  const [streamResponse, setStreamResponse] = useState(true);
  const [soundAlerts, setSoundAlerts] = useState(false);
  const [sensitivity, setSensitivity] = useState('High');
  const [hashLedger, setHashLedger] = useState(true);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
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
        <div className="umm-header">
          <div className="umm-header-left">
            <span className="umm-header-icon"><Settings size={18} /></span>
            <h2>Settings & Preferences</h2>
          </div>
          <button className="umm-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="umm-tabs">
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'general' ? 'active' : ''}`}
            onClick={() => setActiveTab('general')}
          >
            <Settings size={14} />
            <span>General</span>
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'forensics' ? 'active' : ''}`}
            onClick={() => setActiveTab('forensics')}
          >
            <ShieldAlert size={14} />
            <span>AI & Forensics</span>
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
          >
            <Key size={14} />
            <span>Security</span>
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'data' ? 'active' : ''}`}
            onClick={() => setActiveTab('data')}
          >
            <Database size={14} />
            <span>Data Controls</span>
          </button>
        </div>

        <div className="umm-body">
          {activeTab === 'general' && (
            <>
              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Real-time Stream Generation</span>
                  <span className="umm-toggle-desc">Show intelligence tokens progressively as the model synthesizes them.</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={streamResponse} 
                    onChange={e => setStreamResponse(e.target.checked)} 
                  />
                  <span className="umm-slider"></span>
                </label>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Auditory Critical Alerts</span>
                  <span className="umm-toggle-desc">Play chime notification when high-severity tamper anomalies are flagged.</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={soundAlerts} 
                    onChange={e => setSoundAlerts(e.target.checked)} 
                  />
                  <span className="umm-slider"></span>
                </label>
              </div>

              <div className="umm-form-group">
                <label>Default Interface Theme</label>
                <input 
                  type="text" 
                  className="umm-input" 
                  value="Cyber Pure Dark & Obsidian Glow (Default)" 
                  disabled 
                  style={{ opacity: 0.8, cursor: 'not-allowed' }}
                />
              </div>
            </>
          )}

          {activeTab === 'forensics' && (
            <>
              <div className="umm-form-group">
                <label>Tamper Anomaly Detection Sensitivity</label>
                <select 
                  className="umm-input"
                  value={sensitivity} 
                  onChange={e => setSensitivity(e.target.value)}
                  style={{ cursor: 'pointer' }}
                >
                  <option value="Maximum">Maximum (Flag minor frame discrepancies)</option>
                  <option value="High">High (Standard Enterprise Forensic Protocol)</option>
                  <option value="Balanced">Balanced (General review with moderate threshold)</option>
                </select>
              </div>

              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Automated Cryptographic Hash Verification</span>
                  <span className="umm-toggle-desc">Continuously verify SHA-256 signatures against camera hardware ledger.</span>
                </div>
                <label className="umm-switch">
                  <input 
                    type="checkbox" 
                    checked={hashLedger} 
                    onChange={e => setHashLedger(e.target.checked)} 
                  />
                  <span className="umm-slider"></span>
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
            </>
          )}

          {activeTab === 'data' && (
            <>
              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Export Forensic Audit Reports</span>
                  <span className="umm-toggle-desc">Download complete session transcripts, frame markers, and cryptographic proofs in JSON.</span>
                </div>
                <button 
                  type="button" 
                  className="umm-btn-cancel" 
                  onClick={() => alert("Audit log export started. File will download shortly.")}
                >
                  Export Log
                </button>
              </div>

              <div className="umm-toggle-row" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title" style={{ color: '#f87171' }}>Clear Audit Session History</span>
                  <span className="umm-toggle-desc">Permanently purge local conversation cache and temporary analysis cards.</span>
                </div>
                <button 
                  type="button" 
                  className="umm-btn-cancel" 
                  style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.4)' }}
                  onClick={() => {
                    if (confirm("Are you sure you want to clear your local session cache?")) {
                      localStorage.removeItem('chorus_history');
                      window.location.reload();
                    }
                  }}
                >
                  Clear History
                </button>
              </div>
            </>
          )}
        </div>

        <div className="umm-footer">
          <button type="button" className="umm-btn-cancel" onClick={onClose}>Close</button>
          <button type="button" className="umm-btn-primary" onClick={handleSave}>
            {saved ? (
              <>
                <Check size={14} style={{ display: 'inline', marginRight: 4 }} /> Saved
              </>
            ) : 'Save Preferences'}
          </button>
        </div>
      </div>
    </div>
  );
}
