import { forwardRef } from 'react';

export const Skeleton = forwardRef(function Skeleton({
  className = '',
  variant = 'text',
  width = '100%',
  height,
  count = 1,
  ...props
}, ref) {
  const baseStyles = 'animate-shimmer rounded-small bg-border';
  const variants = {
    text: 'h-4',
    title: 'h-6 w-3/4',
    card: 'h-32 w-full rounded-card',
    avatar: 'rounded-full',
    button: 'h-10 w-24 rounded-control',
    thumbnail: 'aspect-video w-full rounded-card',
  };

  const items = Array.from({ length: count }, (_, i) => (
    <div
      key={i}
      ref={i === 0 ? ref : undefined}
      className={`${baseStyles} ${variants[variant]} ${className}`}
      style={{ width, height }}
      role="presentation"
      aria-hidden="true"
      {...props}
    />
  ));

  return <>{items}</>;
});

Skeleton.displayName = 'Skeleton';

export const SkeletonCard = forwardRef(function SkeletonCard({ className = '', lines = 3, ...props }, ref) {
  return (
    <div ref={ref} className={`bg-surface border border-default rounded-card p-4 space-3 ${className}`} {...props}>
      <Skeleton variant="title" width="40%" />
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} variant="text" width={i === lines - 1 ? '60%' : '100%'} />
      ))}
    </div>
  );
});

SkeletonCard.displayName = 'SkeletonCard';

export const SkeletonTable = forwardRef(function SkeletonTable({
  className = '',
  rows = 5,
  columns = 4,
  ...props
}, ref) {
  return (
    <div ref={ref} className={`space-3 ${className}`} {...props}>
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
        {Array.from({ length: columns }, (_, i) => (
          <Skeleton key={`header-${i}`} variant="text" width="60%" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="grid gap-4" style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}>
          {Array.from({ length: columns }, (_, col) => (
            <Skeleton key={`${row}-${col}`} variant="text" width="80%" />
          ))}
        </div>
      ))}
    </div>
  );
});

SkeletonTable.displayName = 'SkeletonTable';