import { forwardRef } from 'react';

export const Card = forwardRef(function Card({ className = '', children, variant = 'default', padding = 'md', ...props }, ref) {
  const variants = {
    default: 'bg-surface border border-default',
    elevated: 'bg-surface border border-default shadow-cyber-elevated',
    stage: 'bg-stage border border-default',
    interactive: 'bg-surface border border-default hover:border-accent transition-colors duration-fast cursor-pointer',
  };

  const paddings = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
    xl: 'p-8',
  };

  return (
    <div
      ref={ref}
      className={`rounded-card ${variants[variant]} ${paddings[padding]} ${className}`}
      style={{
        boxShadow: variant === 'stage' ? 'none' : 'var(--card-shadow)',
        borderColor: 'var(--border)',
        ...props.style
      }}
      {...props}
    >
      {children}
    </div>
  );
});

Card.displayName = 'Card';

export const CardHeader = forwardRef(function CardHeader({ className = '', children, ...props }, ref) {
  return (
    <div ref={ref} className={`mb-4 ${className}`} {...props}>
      {children}
    </div>
  );
});

CardHeader.displayName = 'CardHeader';

export const CardTitle = forwardRef(function CardTitle({ className = '', children, ...props }, ref) {
  return (
    <h3 ref={ref} className={`font-heading text-xl font-semibold text-primary ${className}`} {...props}>
      {children}
    </h3>
  );
});

CardTitle.displayName = 'CardTitle';

export const CardDescription = forwardRef(function CardDescription({ className = '', children, ...props }, ref) {
  return (
    <p ref={ref} className={`text-secondary text-sm mt-1 ${className}`} {...props}>
      {children}
    </p>
  );
});

CardDescription.displayName = 'CardDescription';

export const CardContent = forwardRef(function CardContent({ className = '', children, ...props }, ref) {
  return (
    <div ref={ref} className={className} {...props}>
      {children}
    </div>
  );
});

CardContent.displayName = 'CardContent';

export const CardFooter = forwardRef(function CardFooter({ className = '', children, ...props }, ref) {
  return (
    <div ref={ref} className={`mt-4 pt-4 border-t border-default flex items-center gap-3 ${className}`} {...props}>
      {children}
    </div>
  );
});

CardFooter.displayName = 'CardFooter';