import React, { useState, useContext, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowRight, Shield, Activity, Lock, CheckCircle, 
  ExternalLink, ChevronDown, LogOut, Video, Terminal, Cpu
} from 'lucide-react';
import AuthContext from '../context/AuthContext';
import BlueShadeBackground from '../components/BlueShadeBackground';
import './HomePage.css';

export default function HomePage() {
  const navigate = useNavigate();
  const { token, user, logout } = useContext(AuthContext);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileMenuRef = useRef(null);

  // Close profile dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch login data and profile info from AuthContext and localStorage
  const storedAvatar = localStorage.getItem('chorus_user_avatar');
  const storedName = localStorage.getItem('chorus_user_name');
  const storedEmail = localStorage.getItem('chorus_user_email');

  const resolveUserName = () => {
    if (user?.name) return user.name;
    if (storedName) return storedName;
    const emailToUse = user?.email || storedEmail;
    if (emailToUse) {
      if (emailToUse.toLowerCase().includes('khush')) return 'Khush Desai';
      const prefix = emailToUse.split('@')[0];
      return prefix.replace(/[._-]/g, ' ');
    }
    return 'Khush Desai';
  };

  const rawName = resolveUserName();
  const displayName = rawName.includes(' ')
    ? rawName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
    : rawName.charAt(0).toUpperCase() + rawName.slice(1);

  const displayEmail = user?.email || storedEmail || (displayName.toLowerCase().replace(/\s+/g, '.') + '@chorus.ai');
  const avatarUrl = storedAvatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=222222&color=ffffff&bold=true`;

  const handleLogout = () => {
    setProfileOpen(false);
    logout();
  };

  return (
    <div className="home-container">
      <BlueShadeBackground />

      {/* Header */}
      <header className="home-header">
        <div className="home-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <span className="home-brand-name">Chorus</span>
          <span className="home-brand-badge">AI</span>
        </div>

        {/* Dynamic Navigation based on Auth State */}
        <nav className="home-nav">
          {token ? (
            /* Signed In: User Profile at Top Right Corner */
            <div className="home-user-corner" ref={profileMenuRef}>
              {/* Profile Avatar Button */}
              <div 
                className={`home-profile-btn ${profileOpen ? 'active' : ''}`}
                onClick={() => setProfileOpen(!profileOpen)}
                title="Account Menu"
              >
                <img 
                  src={avatarUrl} 
                  alt="Profile" 
                  className="home-profile-avatar"
                />
                <span className="home-profile-name">{displayName}</span>
                <ChevronDown size={14} className={`home-profile-chevron ${profileOpen ? 'open' : ''}`} />
              </div>

              {/* Profile Dropdown Menu - Sign Out Only */}
              {profileOpen && (
                <div className="home-profile-dropdown">
                  <button 
                    className="home-dropdown-item logout"
                    onClick={handleLogout}
                  >
                    <LogOut size={15} />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Logged Out: Show Sign In and Get Started (Sign Up) */
            <div className="home-auth-corner">
              <button 
                className="home-btn-outline" 
                onClick={() => navigate('/login?mode=login')}
              >
                Sign In
              </button>
              <button 
                className="home-btn-primary" 
                onClick={() => navigate('/login?mode=signup')}
              >
                Get Started
              </button>
            </div>
          )}
        </nav>
      </header>

      {/* Main Content */}
      <main className="home-main">
        {/* Centered Hero & Stats Section */}
        <section className="home-hero-section">
          <div className="home-hero">
            <h1>
              Advanced Intelligence.<br/>
              Crystal Clear Video Forensics.
            </h1>

            <p>
              Enterprise-grade multimodal intelligence to detect frame manipulation,
              neural deepfakes, and optical flow anomalies. Summarize hours of footage
              in seconds with state-of-the-art precision.
            </p>

            <div className="hero-cta-group">
              {token ? (
                <>
                  <button 
                    className="home-btn-hero primary" 
                    onClick={() => navigate('/analytics')}
                  >
                    <span>Launch Workspace</span>
                    <ArrowRight size={16} />
                  </button>
                  <button 
                    className="home-btn-hero secondary" 
                    onClick={() => navigate('/evidence')}
                  >
                    <span>Open Evidence Room</span>
                  </button>
                </>
              ) : (
                <>
                  <button 
                    className="home-btn-hero primary" 
                    onClick={() => navigate('/login?mode=signup')}
                  >
                    <span>Get Started Free</span>
                    <ArrowRight size={16} />
                  </button>
                  <button 
                    className="home-btn-hero secondary" 
                    onClick={() => navigate('/login?mode=login')}
                  >
                    <span>Sign In to Account</span>
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Stats Strip */}
          <div className="home-stats-bar">
            <div className="stat-item">
              <h4>50M+</h4>
              <p>Frames Verified</p>
            </div>
            <div className="stat-item">
              <h4>&lt; 14ms</h4>
              <p>Edge Inference Latency</p>
            </div>
            <div className="stat-item">
              <h4>99.9%</h4>
              <p>Tamper Detection Rate</p>
            </div>
            <div className="stat-item">
              <h4>100%</h4>
              <p>Cryptographic Chain of Custody</p>
            </div>
          </div>
        </section>

        {/* Core Capabilities */}
        <div className="section-header">
          <h2>Core Capabilities</h2>
          <p>Next-generation multimodal video intelligence and tamper forensic architecture.</p>
        </div>

        <div className="home-features">
          <div className="home-feature-card">
            <div className="home-feature-icon">
              <Activity size={22} />
            </div>
            <h3>Multimodal Video Intelligence</h3>
            <p>
              Natural language video Q&A, scene chapter segmentation, and executive takeaway
              synthesis across long-form video archives and YouTube streams.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-icon">
              <Shield size={22} />
            </div>
            <h3>Deepfake & Tamper Forensics</h3>
            <p>
              Frame splicing audit, optical flow vector discontinuity checks, and boundary
              diffusion screening to detect manipulated surveillance footage.
            </p>
          </div>

          <div className="home-feature-card">
            <div className="home-feature-icon">
              <Video size={22} />
            </div>
            <h3>Live RTSP Surveillance Gateway</h3>
            <p>
              Connect IP cameras, NVRs, and live video streams over RTSP/TCP/UDP.
              Continuous real-time telemetry, sliding buffer integrity, and clock sync checks.
            </p>
          </div>
        </div>

        {/* How It Works Pipeline */}
        <div className="home-pipeline-section">
          <div className="section-header">
            <h2>Three-Step Forensic Pipeline</h2>
            <p>Seamless ingestion to court-admissible cryptographic evidence.</p>
          </div>

          <div className="pipeline-steps">
            <div className="pipeline-step">
              <div className="step-num">01</div>
              <h4>Ingest</h4>
              <p>Upload video files (.mp4, .mov), stream YouTube links, or connect live RTSP feeds.</p>
            </div>
            <div className="pipeline-connector" />
            <div className="pipeline-step">
              <div className="step-num">02</div>
              <h4>Analyze</h4>
              <p>Chorus Flash for instant summaries or Chorus Deepthink for multi-step forensic reasoning.</p>
            </div>
            <div className="pipeline-connector" />
            <div className="pipeline-step">
              <div className="step-num">03</div>
              <h4>Certify</h4>
              <p>Generate immutable SHA-256 evidence packages and export tamper-proof audit certificates.</p>
            </div>
          </div>
        </div>

        {/* Enterprise Compliance */}
        <div className="home-compliance">
          <div className="compliance-content">
            <h2>Built for Enterprise Security</h2>
            <p>Designed to satisfy the most stringent compliance, data sovereignty, and legal standards.</p>
            <ul className="compliance-list">
              <li><CheckCircle size={17} className="check-icon" /> SOC 2 Type II Certified Pipeline</li>
              <li><CheckCircle size={17} className="check-icon" /> End-to-End Cryptographic Hashing</li>
              <li><CheckCircle size={17} className="check-icon" /> RFC-3161 TSA Timestamp Synchronization</li>
              <li><CheckCircle size={17} className="check-icon" /> Role-Based Access Control (RBAC)</li>
            </ul>
          </div>
        </div>

        {/* Bottom CTA */}
        <div className="home-final-cta">
          <h2>Ready to secure your video intelligence?</h2>
          <p>Experience the next generation of video analytics and tamper forensic verification.</p>
          <button 
            className="home-btn-primary large" 
            onClick={() => navigate(token ? '/analytics' : '/login?mode=signup')}
          >
            {token ? 'Launch Workspace' : 'Get Started with Chorus'}
          </button>
        </div>
      </main>

      {/* Footer */}
      <footer className="home-footer">
        <div className="footer-links">
          <span>Terms of Service</span>
          <span>Privacy Policy</span>
          <span>Security Whitepaper</span>
          <span>System Status</span>
        </div>
        <p>&copy; {new Date().getFullYear()} Chorus Enterprise AI. All rights reserved.</p>
      </footer>
    </div>
  );
}
