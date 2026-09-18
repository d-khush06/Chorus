import React, { useState } from 'react';
import { X } from 'lucide-react';
import './AccountSettingsModal.css';

export default function AccountSettingsModal({ onClose }) {
  const [profileName, setProfileName] = useState('Khush');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleSave = (e) => {
    e.preventDefault();
    if (newPassword && newPassword !== confirmPassword) {
      alert("New passwords do not match.");
      return;
    }
    // Mock save
    alert("Settings saved successfully!");
    onClose();
  };

  return (
    <div className="asm-overlay" onClick={onClose}>
      <div className="asm-modal" onClick={e => e.stopPropagation()}>
        <div className="asm-header">
          <h2>Account Settings</h2>
          <button className="asm-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        
        <form className="asm-body" onSubmit={handleSave}>
          <div className="asm-form-group">
            <label>Profile Name</label>
            <input 
              type="text" 
              value={profileName}
              onChange={e => setProfileName(e.target.value)}
              placeholder="Your name"
            />
          </div>

          <div className="asm-form-divider">Change Password</div>

          <div className="asm-form-group">
            <label>Current Password</label>
            <input 
              type="password" 
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              placeholder="Enter current password"
            />
          </div>
          <div className="asm-form-group">
            <label>New Password</label>
            <input 
              type="password" 
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Enter new password"
            />
          </div>
          <div className="asm-form-group">
            <label>Confirm New Password</label>
            <input 
              type="password" 
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              placeholder="Confirm new password"
            />
          </div>

          <div className="asm-footer">
            <button type="button" className="asm-btn-cancel" onClick={onClose}>Cancel</button>
            <button type="submit" className="asm-btn-save">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  );
}
