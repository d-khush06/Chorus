import React, { useState } from 'react';
import { X, User, Shield, Mail, Briefcase, Building, Check } from 'lucide-react';
import './UserMenuModals.css';

export default function UserProfileModal({ isOpen, onClose, userName, userEmail }) {
  const [name, setName] = useState(userName || 'Khush Desai');
  const [email, setEmail] = useState(userEmail || 'khush.desai@chorus.ai');
  const [role, setRole] = useState('Lead Forensic Investigator');
  const [department, setDepartment] = useState('Cyber Physical Intelligence Division');
  const [saved, setSaved] = useState(false);

  if (!isOpen) return null;

  const handleSave = (e) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 800);
  };

  return (
    <div className="umm-overlay" onClick={onClose}>
      <div className="umm-modal" onClick={e => e.stopPropagation()}>
        <div className="umm-header">
          <div className="umm-header-left">
            <span className="umm-header-icon"><User size={18} /></span>
            <h2>User Profile</h2>
          </div>
          <button className="umm-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <form className="umm-body" onSubmit={handleSave}>
          <div className="umm-profile-hero">
            <img 
              src={`https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=222222&color=ffffff&bold=true`} 
              alt="User Avatar" 
              className="umm-avatar-large"
            />
            <div className="umm-profile-meta">
              <h3>{name}</h3>
              <div className="umm-profile-badge">
                <Shield size={12} />
                <span>Tier-1 Enterprise Operator</span>
              </div>
            </div>
          </div>

          <div className="umm-form-group">
            <label>Display Name</label>
            <input 
              type="text" 
              className="umm-input"
              value={name} 
              onChange={e => setName(e.target.value)} 
              placeholder="Your full name"
              required
            />
          </div>

          <div className="umm-form-group">
            <label>Email Address</label>
            <input 
              type="email" 
              className="umm-input"
              value={email} 
              onChange={e => setEmail(e.target.value)} 
              placeholder="name@company.com"
              required
            />
          </div>

          <div className="umm-grid-2">
            <div className="umm-form-group">
              <label>Designation / Role</label>
              <input 
                type="text" 
                className="umm-input"
                value={role} 
                onChange={e => setRole(e.target.value)} 
              />
            </div>
            <div className="umm-form-group">
              <label>Department</label>
              <input 
                type="text" 
                className="umm-input"
                value={department} 
                onChange={e => setDepartment(e.target.value)} 
              />
            </div>
          </div>

          <div className="umm-footer" style={{ padding: '0', border: 'none', background: 'transparent' }}>
            <button type="button" className="umm-btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="umm-btn-primary">
              {saved ? (
                <>
                  <Check size={14} style={{ display: 'inline', marginRight: 4 }} /> Saved
                </>
              ) : 'Save Profile'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
