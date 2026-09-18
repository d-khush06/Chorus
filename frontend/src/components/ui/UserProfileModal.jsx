import React, { useState, useRef } from 'react';
import './UserMenuModals.css';

export default function UserProfileModal({ 
  isOpen, 
  onClose, 
  userName, 
  userEmail,
  userAvatar,
  onSaveProfile
}) {
  const [name, setName] = useState(userName || 'Khush Desai');
  const [email, setEmail] = useState(userEmail || 'khush.desai@chorus.ai');
  const [role, setRole] = useState('Forensic Analyst');
  const [department, setDepartment] = useState('Security Operations');
  const [avatar, setAvatar] = useState(userAvatar || localStorage.getItem('chorus_user_avatar') || '');
  const [saved, setSaved] = useState(false);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      alert("Image size must be less than 5MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result;
      if (typeof dataUrl === 'string') {
        setAvatar(dataUrl);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleRemovePhoto = () => {
    setAvatar('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSave = (e) => {
    e.preventDefault();
    setSaved(true);

    if (name) {
      localStorage.setItem('chorus_user_name', name);
    }
    if (email) {
      localStorage.setItem('chorus_user_email', email);
    }
    if (avatar) {
      localStorage.setItem('chorus_user_avatar', avatar);
    } else {
      localStorage.removeItem('chorus_user_avatar');
    }

    if (onSaveProfile) {
      onSaveProfile({ name, email, role, department, avatar });
    }

    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 500);
  };

  const currentPreview = avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(name || 'U')}&background=222222&color=ffffff&bold=true`;

  return (
    <div className="umm-overlay" onClick={onClose}>
      <div className="umm-modal" onClick={e => e.stopPropagation()}>
        {/* Header (No icons) */}
        <div className="umm-header">
          <div className="umm-header-left">
            <h2>Profile</h2>
            <span className="umm-header-subtitle">Manage your personal information</span>
          </div>
          <button className="umm-close-btn" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        {/* Form Body (Simple, Clean, No colors, No icons) */}
        <form className="umm-body" onSubmit={handleSave}>
          {/* Name and Photo together */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
            {/* Photo Avatar on the left */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
              <img 
                src={currentPreview} 
                alt="Profile preview" 
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '50%',
                  objectFit: 'cover',
                  background: '#202020',
                  border: '1px solid #333333',
                  display: 'block'
                }}
              />
              <input 
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                style={{ display: 'none' }}
                onChange={handlePhotoUpload}
              />
              <div style={{ display: 'flex', gap: '4px' }}>
                <button 
                  type="button" 
                  className="umm-btn-cancel"
                  style={{ fontSize: '11px', padding: '3px 7px' }}
                  onClick={() => fileInputRef.current?.click()}
                >
                  Change
                </button>
                {avatar && (
                  <button 
                    type="button" 
                    className="umm-btn-cancel"
                    style={{ fontSize: '11px', padding: '3px 7px' }}
                    onClick={handleRemovePhoto}
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>

            {/* Name Input on the right */}
            <div className="umm-form-group" style={{ flex: 1 }}>
              <label>Name</label>
              <input 
                type="text" 
                className="umm-input"
                value={name} 
                onChange={e => setName(e.target.value)} 
                placeholder="Your full name"
                required
              />
              <span className="umm-label-hint" style={{ marginTop: '2px' }}>
                JPEG, PNG or WEBP (Max 5MB)
              </span>
            </div>
          </div>

          {/* Below Name & Photo: Email Address */}
          <div className="umm-form-group">
            <label>Email Address</label>
            <input 
              type="email" 
              className="umm-input"
              value={email} 
              onChange={e => setEmail(e.target.value)} 
              required
            />
          </div>

          {/* Below Email: Role & Department */}
          <div className="umm-grid-2">
            <div className="umm-form-group">
              <label>Role</label>
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
