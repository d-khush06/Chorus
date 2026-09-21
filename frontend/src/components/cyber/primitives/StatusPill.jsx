import { forwardRef } from 'react';

const statusIcons = {
  ok: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
  warning: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" x2="12" y1="9" y2="13" />
      <line x1="12" x2="12.01" y1="17" y2="17" />
    </svg>
  ),
  danger: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="15" x2="9" y1="9" y2="15" />
      <line x1="9" x2="15" y1="9" y2="15" />
    </svg>
  ),
  info: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" x2="12" y1="16" y2="12" />
      <line x1="12" x2="12.01" y1="8" y2="8" />
    </svg>
  ),
  live: (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="12" r="5" />
    </svg>
  ),
  neutral: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="8" x2="16" y1="12" y2="12" />
    </svg>
  ),
};

const statusLabels = {
  ok: 'OK',
  warning: 'Warning',
  danger: 'Danger',
  info: 'Info',
  live: 'LIVE',
  neutral: 'Pending',
};

export const StatusPill = forwardRef(function StatusPill({
  className = '',
  status = 'neutral',
  label,
  showIcon = true,
  size = 'md',
  pulse = false,
  dot = false,
  ...props
}, ref) {
  const variants = {
    ok: 'bg-ok/10 text-ok border-ok/30',
    warning: 'bg-warning/10 text-warning border-warning/30',
    danger: 'bg-danger/10 text-danger border-danger/30',
    info: 'bg-info/10 text-info border-info/30',
    live: 'bg-accent/10 text-accent border-accent/30',
    neutral: 'bg-surface text-secondary border border-default',
  };

  const sizes = {
    sm: 'px-2 py-1 text-xs gap-1',
    md: 'px-3 py-1.5 text-sm gap-1.5',
    lg: 'px-4 py-2 text-base gap-2',
  };

  const baseStyles = 'inline-flex items-center font-medium rounded-full border transition-colors duration-fast';

  const displayLabel = label ?? statusLabels[status];

  return (
    <span
      ref={ref}
      className={`${baseStyles} ${variants[status]} ${sizes[size]} ${pulse ? 'animate-pulse-slow' : ''} ${className}`}
      {...props}
    >
      {showIcon && statusIcons[status]}
      <span>{displayLabel}</span>
    </span>
  );
});

StatusPill.displayName = 'StatusPill';

export const StatusDot = forwardRef(function StatusDot({
  className = '',
  status = 'neutral',
  size = 'md',
  pulse = false,
  ...props
}, ref) {
  const variants = {
    ok: 'bg-ok',
    warning: 'bg-warning',
    danger: 'bg-danger',
    info: 'bg-info',
    live: 'bg-accent',
    neutral: 'bg-text-secondary',
  };

  const sizes = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4',
  };

  return (
    <span
      ref={ref}
      className={`rounded-full ${variants[status]} ${sizes[size]} ${pulse ? 'animate-pulse-slow' : ''} ${className}`}
      role="presentation"
      aria-hidden="true"
      {...props}
    />
  );
});

StatusDot.displayName = 'StatusDot';