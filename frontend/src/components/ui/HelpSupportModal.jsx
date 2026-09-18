import React, { useState } from 'react';
import { X, HelpCircle, BookOpen, Command, LifeBuoy, ShieldCheck, ExternalLink } from 'lucide-react';
import './UserMenuModals.css';

export default function HelpSupportModal({ isOpen, onClose, onOpenEvidence }) {
  const [search, setSearch] = useState('');

  if (!isOpen) return null;

  return (
    <div className="umm-overlay" onClick={onClose}>
      <div className="umm-modal umm-modal-wide" onClick={e => e.stopPropagation()}>
        <div className="umm-header">
          <div className="umm-header-left">
            <span className="umm-header-icon"><HelpCircle size={18} /></span>
            <h2>Help & Resources</h2>
          </div>
          <button className="umm-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="umm-body">
          {/* Status Banner */}
          <div className="umm-status-banner">
            <div>
              <span className="umm-status-dot"></span>
              <strong>Chorus Core AI Operational</strong> — Inference cluster latency: 18ms
            </div>
            <span style={{ fontSize: 11, opacity: 0.8 }}>v2.4 Enterprise</span>
          </div>

          {/* Quick Help Cards */}
          <div className="umm-help-grid">
            <div 
              className="umm-help-card" 
              style={{ cursor: 'pointer' }}
              onClick={() => {
                onClose();
                if (onOpenEvidence) onOpenEvidence();
              }}
            >
              <div className="umm-help-card-icon"><BookOpen size={20} /></div>
              <div className="umm-help-card-title">Evidence Room Guide ↗</div>
              <div className="umm-help-card-desc">
                Learn how to scrub through video timeline manifests, inspect synced camera angles, and verify cryptographic hashes.
              </div>
            </div>

            <div className="umm-help-card">
              <div className="umm-help-card-icon"><ShieldCheck size={20} /></div>
              <div className="umm-help-card-title">Tamper Audit Engine</div>
              <div className="umm-help-card-desc">
                Understand optical flow discontinuity, quantization frame splicing, and audio waveform desync flags.
              </div>
            </div>
          </div>

          {/* Keyboard Shortcuts */}
          <div className="umm-form-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Command size={14} />
              <span>Keyboard Shortcuts</span>
            </label>
            <div style={{ background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.07)', borderRadius: 10 }}>
              <div className="umm-shortcut-item">
                <span>Start New Analysis / Chat</span>
                <span className="umm-kbd">Ctrl + N</span>
              </div>
              <div className="umm-shortcut-item">
                <span>Search Investigation History</span>
                <span className="umm-kbd">Ctrl + K</span>
              </div>
              <div className="umm-shortcut-item">
                <span>Toggle Left Sidebar</span>
                <span className="umm-kbd">Ctrl + B</span>
              </div>
              <div className="umm-shortcut-item">
                <span>Close Popovers / Modals</span>
                <span className="umm-kbd">Esc</span>
              </div>
            </div>
          </div>

          {/* Contact Support */}
          <div className="umm-toggle-row">
            <div className="umm-toggle-info">
              <span className="umm-toggle-title">Emergency Cyber Forensics Support</span>
              <span className="umm-toggle-desc">24/7 direct escalation hotline for chain of custody validation and tamper incident response.</span>
            </div>
            <a 
              href="mailto:support@chorus.ai" 
              className="umm-btn-cancel" 
              style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <span>Contact Support</span>
              <ExternalLink size={13} />
            </a>
          </div>
        </div>

        <div className="umm-footer">
          <button type="button" className="umm-btn-primary" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
