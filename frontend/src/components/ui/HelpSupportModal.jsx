import React, { useState } from 'react';
import './UserMenuModals.css';

const SHORTCUTS = [
  { action: 'Start new session', keys: 'Ctrl + N' },
  { action: 'Search / focus input', keys: 'Ctrl + K' },
  { action: 'Toggle sidebar', keys: 'Ctrl + B' },
  { action: 'Switch to Flash model', keys: '/flash' },
  { action: 'Switch to Deepthink model', keys: '/deepthink' },
  { action: 'Pause or resume live stream', keys: 'Space' },
  { action: 'Close dialog or popover', keys: 'Esc' }
];

const FAQS = [
  {
    q: 'How do I connect an RTSP stream?',
    a: 'Switch to Cyber Mode, click the stream button next to the input, and enter your rtsp:// URL, port (default 554), and optional camera credentials.'
  },
  {
    q: 'What is the difference between General Mode and Cyber Mode?',
    a: 'General Mode is designed for video summarization, chapter breakdowns, and YouTube analysis. Cyber Mode is built for tamper detection, frame splice audits, and live stream telemetry.'
  },
  {
    q: 'What is the difference between Chorus Flash and Chorus Deepthink?',
    a: 'Chorus Flash provides fast responses (~800ms) for direct queries. Chorus Deepthink performs multi-step reasoning (~2400ms) with detailed analysis steps.'
  },
  {
    q: 'How do I analyze a YouTube video?',
    a: 'In General Mode, paste any YouTube link into the input bar. Chorus will parse the video, chapters, and executive summary.'
  }
];

export default function HelpSupportModal({ isOpen, onClose, onOpenEvidence }) {
  const [activeTab, setActiveTab] = useState('shortcuts');

  if (!isOpen) return null;

  return (
    <div className="umm-overlay" onClick={onClose}>
      <div className="umm-modal umm-modal-wide" onClick={e => e.stopPropagation()}>
        {/* Header (No icons) */}
        <div className="umm-header">
          <div className="umm-header-left">
            <h2>Help & Support</h2>
            <span className="umm-header-subtitle">Shortcuts, guides, and assistance</span>
          </div>
          <button className="umm-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {/* Tab Navigation (Text only, no icons) */}
        <div className="umm-tabs">
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'shortcuts' ? 'active' : ''}`}
            onClick={() => setActiveTab('shortcuts')}
          >
            Shortcuts
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'faq' ? 'active' : ''}`}
            onClick={() => setActiveTab('faq')}
          >
            FAQ
          </button>
          <button 
            type="button"
            className={`umm-tab-btn ${activeTab === 'contact' ? 'active' : ''}`}
            onClick={() => setActiveTab('contact')}
          >
            Support
          </button>
        </div>

        {/* Body (No colors, No icons) */}
        <div className="umm-body">
          {activeTab === 'shortcuts' && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {SHORTCUTS.map((sc, idx) => (
                <div key={idx} className="umm-list-row">
                  <span>{sc.action}</span>
                  <span className="umm-kbd">{sc.keys}</span>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'faq' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {FAQS.map((faq, idx) => (
                <div key={idx} className="umm-faq-item">
                  <div className="umm-faq-q">
                    {faq.q}
                  </div>
                  <div className="umm-faq-a">
                    {faq.a}
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === 'contact' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div className="umm-toggle-row">
                <div className="umm-toggle-info">
                  <span className="umm-toggle-title">Email Support</span>
                  <span className="umm-toggle-desc">Contact the engineering and support team</span>
                </div>
                <a 
                  href="mailto:support@chorus.ai" 
                  className="umm-btn-cancel" 
                  style={{ textDecoration: 'none' }}
                >
                  support@chorus.ai
                </a>
              </div>

              {onOpenEvidence && (
                <div className="umm-toggle-row">
                  <div className="umm-toggle-info">
                    <span className="umm-toggle-title">Evidence Room</span>
                    <span className="umm-toggle-desc">Open the multi-camera manifest evidence room</span>
                  </div>
                  <button
                    type="button"
                    className="umm-btn-cancel"
                    onClick={() => {
                      onClose();
                      onOpenEvidence();
                    }}
                  >
                    Open Evidence Room
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer (No icons) */}
        <div className="umm-footer">
          <button type="button" className="umm-btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
