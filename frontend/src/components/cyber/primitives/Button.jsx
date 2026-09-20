import { forwardRef } from 'react';

export const Button = forwardRef(function Button({
  className = '',
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  fullWidth = false,
  leftIcon,
  rightIcon,
  ...props
}, ref) {
  const variants = {
    primary: 'bg-accent text-white border-accent hover:bg-accent/90 focus:ring-accent',
    secondary: 'bg-surface text-primary border border-default hover:border-accent/50 focus:ring-accent',
    outline: 'bg-transparent text-primary border border-default hover:bg-surface focus:ring-accent',
    ghost: 'bg-transparent text-primary border-transparent hover:bg-surface focus:ring-accent',
    danger: 'bg-danger text-white border-danger hover:bg-danger/90 focus:ring-danger',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-sm gap-1.5',
    md: 'px-4 py-2 text-base gap-2',
    lg: 'px-6 py-3 text-lg gap-2.5',
    icon: 'p-2',
  };

  const baseStyles = 'inline-flex items-center justify-center font-semibold rounded-control transition-all duration-fast disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-surface';

  return (
    <button
      ref={ref}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${fullWidth ? 'w-full' : ''} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading}
      aria-disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      ) : (
        <>
          {leftIcon && <span className="flex-shrink-0" aria-hidden="true">{leftIcon}</span>}
          {children}
          {rightIcon && <span className="flex-shrink-0" aria-hidden="true">{rightIcon}</span>}
        </>
      )}
    </button>
  );
});

Button.displayName = 'Button';

export const ButtonGroup = forwardRef(function ButtonGroup({ className = '', children, ...props }, ref) {
  return (
    <div ref={ref} className={`inline-flex rounded-control ${className}`} {...props}>
      {children}
    </div>
  );
});

ButtonGroup.displayName = 'ButtonGroup';