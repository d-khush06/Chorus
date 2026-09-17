/**
 * UploadZone.jsx
 * Drag-and-drop file upload zone with YouTube URL tab.
 * Switches label copy and accepted formats based on mode.
 */
import { useState, useRef, useCallback } from 'react';
import './UploadZone.css';

const ACCEPTED_GENERAL = '.mp4,.mov,.avi,.webm,.mkv';
const ACCEPTED_CYBER   = '.mp4,.mov,.avi,.webm,.mkv,.h264,.ts,.mts';

export default function UploadZone({ mode, onAnalyze, analyzing }) {
  const [tab, setTab] = useState('file'); // 'file' | 'url'
  const [file, setFile] = useState(null);
  const [url, setUrl]   = useState('');
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  const isCyber   = mode === 'cyber';
  const hasInput  = tab === 'file' ? !!file : url.trim().length > 10;

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) { setFile(dropped); setTab('file'); }
  }, []);

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = () => setDragging(false);

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    if (f) setFile(f);
  };

  const handleAnalyze = () => {
    if (!hasInput || analyzing) return;
    onAnalyze(tab === 'file' ? { type: 'file', payload: file } : { type: 'url', payload: url.trim() });
  };

  const formatBytes = (bytes) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={`upload-zone upload-zone--${mode}`}>
      {/* Tabs */}
      <div className="upload-zone__tabs" role="tablist">
        <button
          id="tab-file"
          role="tab"
          aria-selected={tab === 'file'}
          className={`upload-zone__tab ${tab === 'file' ? 'active' : ''}`}
          onClick={() => setTab('file')}
        >
          {isCyber ? '🎞 Evidence File' : '📁 Upload File'}
        </button>
        <button
          id="tab-url"
          role="tab"
          aria-selected={tab === 'url'}
          className={`upload-zone__tab ${tab === 'url' ? 'active' : ''}`}
          onClick={() => setTab('url')}
        >
          {isCyber ? '🔗 Remote URL / Stream' : '▶ YouTube / URL'}
        </button>
      </div>

      {/* File drop area */}
      {tab === 'file' && (
        <div
          className={`upload-zone__droparea ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => !file && fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label="Drop video file or click to browse"
          onKeyDown={(e) => e.key === 'Enter' && !file && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={isCyber ? ACCEPTED_CYBER : ACCEPTED_GENERAL}
            className="upload-zone__file-input"
            onChange={handleFileChange}
            aria-hidden="true"
            tabIndex={-1}
          />

          {!file ? (
            <>
              <div className="upload-zone__drop-icon">
                {isCyber ? '🔒' : '🎬'}
              </div>
              <p className="upload-zone__drop-title">
                {isCyber ? 'Ingest Evidence Video' : 'Drop your video here'}
              </p>
              <p className="upload-zone__drop-sub">
                {isCyber
                  ? 'MP4, MOV, AVI, WEBM, H.264, TS, MTS supported'
                  : 'MP4, MOV, AVI, WEBM, MKV supported'}
              </p>
              <button
                className="upload-zone__browse-btn"
                onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
              >
                {isCyber ? 'Select Evidence File' : 'Browse Files'}
              </button>
            </>
          ) : (
            <div className="upload-zone__file-preview">
              <div className="upload-zone__file-icon">{isCyber ? '🔐' : '🎥'}</div>
              <div className="upload-zone__file-info">
                <span className="upload-zone__file-name">{file.name}</span>
                <span className="upload-zone__file-meta">{formatBytes(file.size)} · {file.type || 'video'}</span>
              </div>
              <button
                className="upload-zone__file-remove"
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                aria-label="Remove file"
              >✕</button>
            </div>
          )}
        </div>
      )}

      {/* URL input */}
      {tab === 'url' && (
        <div className="upload-zone__url-area">
          <div className="upload-zone__url-icon">{isCyber ? '📡' : '▶'}</div>
          <input
            id="url-input"
            type="url"
            className="upload-zone__url-input"
            placeholder={isCyber
              ? 'RTSP stream, remote URL, or evidence link…'
              : 'Paste YouTube URL or direct video link…'}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-label="Video URL input"
          />
          {url.length > 5 && (
            <div className={`upload-zone__url-status ${hasInput ? 'valid' : 'invalid'}`}>
              {hasInput ? '✓' : '?'}
            </div>
          )}
        </div>
      )}

      {/* Analyze CTA */}
      <button
        id="analyze-btn"
        className={`upload-zone__analyze-btn upload-zone__analyze-btn--${mode} ${hasInput && !analyzing ? 'ready' : ''}`}
        onClick={handleAnalyze}
        disabled={!hasInput || analyzing}
        aria-busy={analyzing}
      >
        {analyzing ? (
          <span className="upload-zone__btn-spinner" aria-hidden="true" />
        ) : (
          <span className="upload-zone__btn-icon">{isCyber ? '🔍' : '✦'}</span>
        )}
        <span>
          {analyzing
            ? 'Analyzing…'
            : isCyber
              ? 'Run Forensic Analysis'
              : 'Analyze Video'}
        </span>
      </button>

      {isCyber && (
        <p className="upload-zone__legal-note">
          ⚠ All evidence submissions are logged and immutably sealed to the audit chain.
        </p>
      )}
    </div>
  );
}
