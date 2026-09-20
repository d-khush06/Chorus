import { forwardRef } from 'react';

export const Badge = forwardRef(function Badge({
  className = '',
  children,
  variant = 'default',
  size = 'md',
  dot = false,
  ...props
}, ref) {
  const variants = {
    default: 'bg-surface text-primary border border-default',
    accent: 'bg-accent text-white border-accent',
    ok: 'bg-ok/10 text-ok border-ok/30',
    warning: 'bg-warning/10 text-warning border-warning/30',
    danger: 'bg-danger/10 text-danger border-danger/30',
    info: 'bg-info/10 text-info border-info/30',
    outline: 'bg-transparent text-primary border border-default',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
    lg: 'px-3 py-1.5 text-base',
  };

  const dotColors = {
    default: 'bg-text-secondary',
    accent: 'bg-accent',
    ok: 'bg-ok',
    warning: 'bg-warning',
    danger: 'bg-danger',
    info: 'bg-info',
  };

  return (
    <span
      ref={ref}
      className={`inline-flex items-center gap-1.5 rounded-control font-medium ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotColors[variant]}`} aria-hidden="true" />}
      {children}
    </span>
  );
});

Badge.displayName = 'Badge';