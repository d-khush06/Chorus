import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield, Activity, Lock, ArrowRight, Server, Cpu, Fingerprint, Globe, CheckCircle, Zap } from 'lucide-react';
import BlueShadeBackground from '../components/BlueShadeBackground';
import './HomePage.css';

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="home-container">
      <BlueShadeBackground />
      <header className="home-header">
        <div className="home-brand">
          <span className="home-brand-name">Chorus</span>
          <span className="home-brand-badge">AI</span>
        </div>
        <nav className="home-nav">
          <button className="home-btn-outline" onClick={() => navigate('/login')}>Sign In</button>
          <button className="home-btn-primary" onClick={() => navigate('/login')}>Get Started</button>
        </nav>
      </header>

      <main className="home-main">
        {/* Hero Section */}
        <div className="home-hero">
          <div className="hero-badge"><Zap size={14} /> v2.0 Engine Live</div>
          <h1>Advanced Intelligence.<br/>Crystal Clear Analysis.</h1>
          <p>
            Experience the next generation of threat detection and evidence management.
            Built with state-of-the-art models to secure your enterprise.
          </p>
          <div className="hero-cta-group">
            <button className="home-btn-hero" onClick={() => navigate('/login')}>
              Enter the Interface <ArrowRight size={18} />
            </button>
            <button className="home-btn-hero secondary" onClick={() => navigate('/login')}>
              View Documentation
            </button>
          </div>
        </div>

        {/* Stats Bar */}
        <div className="home-stats-bar">
          <div className="stat-item">
            <h4>50M+</h4>
            <p>Threats Analyzed</p>
          </div>
          <div className="stat-item">
            <h4>99.99%</h4>
            <p>Uptime SLA</p>
          </div>
          <div className="stat-item">
            <h4><Globe size={28} /></h4>
            <p>Global Edge Network</p>
          </div>
          <div className="stat-item">
            <h4><Lock size={28} /></h4>
            <p>AES-256 Encryption</p>
          </div>
        </div>

        {/* Core Features */}
        <div className="section-header">
          <h2>Core Capabilities</h2>
          <p>Everything you need for zero-trust security orchestration.</p>
        </div>
        <div className="home-features">
          <div className="home-feature-card">
            <div className="home-feature-icon"><Activity size={24} /></div>
            <h3>Real-Time Analytics</h3>
            <p>Monitor threats globally with our multi-modal sensor fusion engine running at edge locations.</p>
          </div>
          <div className="home-feature-card">
            <div className="home-feature-icon"><Shield size={24} /></div>
            <h3>Deepfake Detection</h3>
            <p>Industry-leading synthetic voice and facial manipulation scanning using proprietary AI models.</p>
          </div>
          <div className="home-feature-card">
            <div className="home-feature-icon"><Lock size={24} /></div>
            <h3>Secure Evidence</h3>
            <p>Immutable audit trails and cryptographic case manifestation stored indefinitely.</p>
          </div>
        </div>

        {/* Pipeline Section */}
        <div className="home-pipeline-section">
          <div className="section-header">
            <h2>How Chorus Works</h2>
            <p>A seamless pipeline from raw data to actionable intelligence.</p>
          </div>
          <div className="pipeline-steps">
            <div className="pipeline-step">
              <div className="step-icon"><Server size={32} /></div>
              <h4>1. Ingest</h4>
              <p>Connect your data streams via our high-throughput secure API endpoints.</p>
            </div>
            <div className="pipeline-connector"></div>
            <div className="pipeline-step">
              <div className="step-icon"><Cpu size={32} /></div>
              <h4>2. Analyze</h4>
              <p>Our AI cluster processes inputs for anomalies in real-time under 50ms.</p>
            </div>
            <div className="pipeline-connector"></div>
            <div className="pipeline-step">
              <div className="step-icon"><Fingerprint size={32} /></div>
              <h4>3. Secure</h4>
              <p>Threat manifests are cryptographically signed and stored in cold storage.</p>
            </div>
          </div>
        </div>

        {/* Compliance / Enterprise List */}
        <div className="home-compliance">
          <div className="compliance-content">
            <h2>Built for the Enterprise</h2>
            <p>Chorus is designed from the ground up to meet the strictest compliance and regulatory standards.</p>
            <ul className="compliance-list">
              <li><CheckCircle size={18} className="check-icon" /> SOC 2 Type II Certified</li>
              <li><CheckCircle size={18} className="check-icon" /> GDPR & CCPA Compliant</li>
              <li><CheckCircle size={18} className="check-icon" /> End-to-End Encryption</li>
              <li><CheckCircle size={18} className="check-icon" /> Role-Based Access Control (RBAC)</li>
            </ul>
          </div>
        </div>

        {/* Final CTA */}
        <div className="home-final-cta">
          <h2>Ready to secure your enterprise?</h2>
          <p>Join the organizations trusting Chorus AI for their next-generation security infrastructure.</p>
          <button className="home-btn-primary large" onClick={() => navigate('/login')}>
            Deploy Chorus Now
          </button>
        </div>
      </main>

      <footer className="home-footer">
        <div className="footer-links">
          <span>Terms of Service</span>
          <span>Privacy Policy</span>
          <span>Status</span>
        </div>
        <p>&copy; {new Date().getFullYear()} Chorus Enterprise. All rights reserved.</p>
      </footer>
    </div>
  );
}
