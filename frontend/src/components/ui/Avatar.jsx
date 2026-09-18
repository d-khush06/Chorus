import React from 'react';
import './Avatar.css';

export function Avatar({
  src,
  alt,
  name,
  size = 'md',
  status,
  className = ''
}) {
  const sizeClasses = `avatar-${size}`;
  const statusClass = status ? `avatar-status-${status}` : '';

  const initials = name
    ? name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : '?';

  return (
    <div className={`avatar ${sizeClasses} ${statusClass} ${className}`.trim()}>
      {src ? (
        <img src={src} alt={alt || name || 'Avatar'} className="avatar-img" />
      ) : (
        <span className="avatar-fallback">{initials}</span>
      )}
      {status && <span className="avatar-status-dot" aria-label={status} />}
    </div>
  );
}

export function AvatarGroup({ avatars = [], max = 4, className = '', size = 'sm' }) {
  const visible = avatars.slice(0, max);
  const remaining = avatars.length - max;

  return (
    <div className={`avatar-group ${className}`.trim()} role="group" aria-label={`${avatars.length} users`}>
      {visible.map((avatar, i) => (
        <Avatar
          key={avatar.id || i}
          {...avatar}
          size={size}
          className="avatar-overlap"
        />
      ))}
      {remaining > 0 && (
        <div className={`avatar avatar-${size} avatar-overlap avatar-more`}>
          <span className="avatar-fallback">+{remaining}</span>
        </div>
      )}
    </div>
  );
}