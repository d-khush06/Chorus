import React, { useState } from 'react';
import './UserMenuModals.css';

export default function RtspConnectorModal({ isOpen, onClose, onConnect }) {
  const [streamUrl, setStreamUrl] = useState('');
  const [cameraLabel, setCameraLabel] = useState('');
  const [transport, setTransport] = useState('TCP');
  const [port, setPort] = useState('554');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [error, setError] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);

  if (!isOpen) return null;

  const handleApplyPreset = (url, label) => {
    setStreamUrl(url);
    setCameraLabel(label);
    setError('');
  };

  const handleConnect = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    const trimmedUrl = streamUrl.trim();

    if (!trimmedUrl) {
      setError('Please enter an RTSP stream URL.');
      return;
    }

    if (!/^(rtsp|rtmp|http|https):\/\//i.test(trimmedUrl)) {
      setError('Stream URL must start with rtsp://, rtmp://, or http(s)://');
      return;
    }

    setError('');
    setIsConnecting(true);

    // Simple realistic handshake delay
    await new Promise(r => setTimeout(r, 600));

    setIsConnecting(false);

    let finalUrl = trimmedUrl;
    if (authUsername && authPassword && !trimmedUrl.includes('@')) {
      const schemeSplit = trimmedUrl.split('://');
      if (schemeSplit.length === 2) {
        finalUrl = `${schemeSplit[0]}://${encodeURIComponent(authUsername)}:${encodeURIComponent(authPassword)}@${schemeSplit[1]}`;
      }
    }

    onConnect({
      streamUrl: finalUrl,
      displayUrl: trimmedUrl,
      cameraLabel: cameraLabel.trim() || `Camera (${trimmedUrl.replace(/^.*:\/\//, '').split('/')[0]})`,
      transport: transport.toUpperCase(),
      port: port || '554'
    });

    onClose();
  };

  return (
    <div className="umm-overlay" onClick={isConnecting ? undefined : onClose}>
      <div className="umm-modal" onClick={e => e.stopPropagation()}>
        {/* Header (No icons) */}
        <div className="umm-header">
          <div className="umm-header-left">
            <h2>Connect RTSP Stream</h2>
            <span className="umm-header-subtitle">Direct live camera feed connection</span>
          </div>
          {!isConnecting && (
            <button className="umm-close-btn" onClick={onClose} aria-label="Close">
              &times;
            </button>
          )}
        </div>

        {/* Form Body (Simple, Clean, No colors, No icons) */}
        <form className="umm-body" onSubmit={handleConnect}>
          {/* Quick Presets */}
          <div className="umm-form-group">
            <label>Presets</label>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="umm-preset-btn"
                onClick={() => handleApplyPreset('rtsp://cam-04.perimeter.internal:554/live', 'Sector 4 Perimeter Gate')}
              >
                Sector 4 Perimeter
              </button>
              <button
                type="button"
                className="umm-preset-btn"
                onClick={() => handleApplyPreset('rtsp://192.168.1.120:8554/h264_main', 'Data Center Cam')}
              >
                Data Center
              </button>
              <button
                type="button"
                className="umm-preset-btn"
                onClick={() => {
                  setStreamUrl('');
                  setCameraLabel('');
                  setError('');
                }}
              >
                Clear
              </button>
            </div>
          </div>

          <div className="umm-form-group">
            <label>Stream URL</label>
            <input
              type="text"
              className="umm-input"
              value={streamUrl}
              onChange={e => {
                setStreamUrl(e.target.value);
                setError('');
              }}
              placeholder="rtsp://192.168.1.100:554/live"
              disabled={isConnecting}
              autoFocus
            />
          </div>

          <div className="umm-form-group">
            <label>Camera Name (Optional)</label>
            <input
              type="text"
              className="umm-input"
              value={cameraLabel}
              onChange={e => setCameraLabel(e.target.value)}
              placeholder="e.g. North Gate Camera"
              disabled={isConnecting}
            />
          </div>

          <div className="umm-grid-2">
            <div className="umm-form-group">
              <label>Transport</label>
              <select
                className="umm-input"
                value={transport}
                onChange={e => setTransport(e.target.value)}
                disabled={isConnecting}
              >
                <option value="TCP">TCP</option>
                <option value="UDP">UDP</option>
              </select>
            </div>

            <div className="umm-form-group">
              <label>Port</label>
              <input
                type="text"
                className="umm-input"
                value={port}
                onChange={e => setPort(e.target.value)}
                placeholder="554"
                disabled={isConnecting}
              />
            </div>
          </div>

          <div className="umm-grid-2">
            <div className="umm-form-group">
              <label>Username (Optional)</label>
              <input
                type="text"
                className="umm-input"
                value={authUsername}
                onChange={e => setAuthUsername(e.target.value)}
                placeholder="admin"
                disabled={isConnecting}
              />
            </div>

            <div className="umm-form-group">
              <label>Password (Optional)</label>
              <input
                type="password"
                className="umm-input"
                value={authPassword}
                onChange={e => setAuthPassword(e.target.value)}
                placeholder="••••••••"
                disabled={isConnecting}
              />
            </div>
          </div>

          {error && (
            <div className="umm-error-text">
              {error}
            </div>
          )}

          {isConnecting && (
            <div style={{ fontSize: '12px', color: '#999999', textAlign: 'center', padding: '6px' }}>
              Connecting to RTSP stream...
            </div>
          )}

          {/* Footer (No icons) */}
          <div className="umm-footer" style={{ padding: '12px 0 0 0', border: 'none' }}>
            <button
              type="button"
              className="umm-btn-cancel"
              onClick={onClose}
              disabled={isConnecting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="umm-btn-primary"
              disabled={isConnecting}
            >
              {isConnecting ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
