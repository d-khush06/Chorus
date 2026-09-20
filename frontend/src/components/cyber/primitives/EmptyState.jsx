import { forwardRef } from 'react';
import { Card } from './Card';

export const EmptyState = forwardRef(function EmptyState({
  className = '',
  title,
  description,
  icon,
  action,
  variant = 'default',
  children,
  ...props
}, ref) {
  const variants = {
    default: 'bg-surface border border-default',
    stage: 'bg-stage border border-default',
    minimal: 'bg-transparent border-none',
  };

  return (
    <Card
      ref={ref}
      variant={variant}
      padding="xl"
      className={`flex flex-col items-center text-center py-12 ${className}`}
      {...props}
    >
      {icon && (
        <div className="text-accent mb-4" aria-hidden="true">
          {icon}
        </div>
      )}
      {children}
      {title && (
        <h3 className="font-heading text-lg font-semibold text-primary mb-2">
          {title}
        </h3>
      )}
      {description && (
        <p className="text-secondary text-base max-w-md">
          {description}
        </p>
      )}
      {action && (
        <div className="mt-6">
          {action}
        </div>
      )}
    </Card>
  );
});

EmptyState.displayName = 'EmptyState';

export const LoadingState = forwardRef(function LoadingState({
  className = '',
  title = 'Loading...',
  description,
  variant = 'default',
  ...props
}, ref) {
  return (
    <EmptyState
      ref={ref}
      variant={variant}
      title={title}
      description={description}
      className={className}
      {...props}
    >
      <div className="w-8 h-8 border-3 border-accent border-t-transparent rounded-full animate-spin" aria-hidden="true" />
    </EmptyState>
  );
});

LoadingState.displayName = 'LoadingState';

export const ErrorState = forwardRef(function ErrorState({
  className = '',
  title = 'Something went wrong',
  description,
  action,
  variant = 'default',
  ...props
}, ref) {
  return (
    <EmptyState
      ref={ref}
      variant={variant}
      title={title}
      description={description}
      action={action}
      className={className}
      {...props}
    >
      <svg className="w-12 h-12 text-danger mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" role="img" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" x2="12" y1="8" y2="12" />
        <line x1="12" x2="12.01" y1="16" y2="16" />
      </svg>
    </EmptyState>
  );
});

ErrorState.displayName = 'ErrorState';