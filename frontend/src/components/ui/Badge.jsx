import React from 'react';
import './Badge.css';

export function Badge({
  children,
  variant = 'neutral',
  size = 'md',
  dot = false,
  className = '',
  ...props
}) {
  const variantClass = `badge-${variant}`;
  const sizeClass = `badge-${size}`;
  const dotClass = dot ? 'badge-dot' : '';

  return (
    <span className={`badge ${variantClass} ${sizeClass} ${dotClass} ${className}`.trim()} {...props}>
      {dot && <span className="badge-dot-indicator" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status, className = '', ...props }) {
  const variants = {
    verified: 'success',
    failed: 'cyber',
    pending: 'amber',
    processing: 'cyan',
    unknown: 'neutral',
    match: 'cyber',
    partial: 'amber',
    clean: 'success',
    warning: 'amber',
    critical: 'cyber',
    high: 'cyber',
    medium: 'amber',
    low: 'success'
  };

  const labels = {
    verified: 'Verified',
    failed: 'Failed',
    pending: 'Pending',
    processing: 'Processing',
    unknown: 'Unknown',
    match: 'Match',
    partial: 'Partial',
    clean: 'Clean',
    warning: 'Warning',
    critical: 'Critical',
    high: 'High',
    medium: 'Medium',
    low: 'Low'
  };

  return (
    <Badge variant={variants[status] || 'neutral'} className={className} {...props}>
      {labels[status] || status}
    </Badge>
  );
}