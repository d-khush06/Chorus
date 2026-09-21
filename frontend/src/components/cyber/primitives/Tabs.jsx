import React, { forwardRef, useState, useRef } from 'react';

export const Tabs = forwardRef(function Tabs({
  className = '',
  children,
  defaultValue,
  value,
  onChange,
  variant = 'default',
  ...props
}, ref) {
  const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue);
  const activeValue = value !== undefined ? value : uncontrolledValue;

  const handleTabClick = (val) => {
    if (value === undefined) {
      setUncontrolledValue(val);
    }
    onChange?.(val);
  };

  const listVariants = {
    default: 'border-b border-border',
    underline: 'border-b border-border',
    pills: 'p-1 bg-surface-alt/60 rounded-control border border-border inline-flex gap-1',
  };

  const triggers = [];
  const contents = [];

  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return;
    if (child.type === TabContent || child.props?.role === 'tabpanel') {
      contents.push(child);
    } else {
      triggers.push(child);
    }
  });

  return (
    <div ref={ref} className={className} {...props}>
      <div
        role="tablist"
        aria-orientation="horizontal"
        className={`flex items-center gap-1 ${listVariants[variant] || ''}`}
        style={variant === 'underline' || variant === 'default' ? {
          borderTop: 'none',
          borderLeft: 'none',
          borderRight: 'none',
          borderBottom: '1px solid var(--border)',
        } : undefined}
      >
        {triggers.map((child, idx) =>
          React.cloneElement(child, {
            key: child.key || child.props.value || idx,
            variant: child.props.variant || variant,
            isActive: child.props.isActive !== undefined ? child.props.isActive : child.props.value === activeValue,
            onClick: (e) => {
              child.props.onClick?.(e);
              handleTabClick(child.props.value);
            },
          })
        )}
      </div>
      {contents.length > 0 && (
        <div className="mt-4">
          {contents.map((child, idx) =>
            React.cloneElement(child, {
              key: child.key || child.props.value || idx,
              activeValue: child.props.activeValue || activeValue,
            })
          )}
        </div>
      )}
    </div>
  );
});

Tabs.displayName = 'Tabs';

export const TabsList = forwardRef(function TabsList({ variant = 'default', activeValue, onTabClick, children, className = '' }, ref) {
  const variants = {
    default: 'border-b border-border',
    underline: 'border-b border-border',
    pills: 'p-1 bg-surface-alt/60 rounded-control border border-border inline-flex gap-1',
  };

  return (
    <div
      ref={ref}
      role="tablist"
      aria-orientation="horizontal"
      className={`flex items-center gap-1 ${variants[variant] || ''} ${className}`}
      style={variant === 'underline' || variant === 'default' ? {
        borderTop: 'none',
        borderLeft: 'none',
        borderRight: 'none',
        borderBottom: '1px solid var(--border)',
      } : undefined}
    >
      {React.Children.map(children, (child, idx) => {
        if (!React.isValidElement(child)) return child;
        return React.cloneElement(child, {
          key: child.key || child.props?.value || idx,
          variant,
          isActive: child.props.value === activeValue,
          onClick: () => onTabClick?.(child.props.value),
        });
      })}
    </div>
  );
});

TabsList.displayName = 'TabsList';

export const TabTrigger = forwardRef(function TabTrigger({
  className = '',
  children,
  value,
  disabled = false,
  isActive = false,
  onClick,
  variant = 'default',
  style,
  ...props
}, ref) {
  const isUnderline = variant === 'underline' || variant === 'default';

  const variants = {
    default: isActive
      ? 'bg-transparent text-primary font-semibold border-b-2 border-primary -mb-px rounded-none'
      : 'bg-transparent text-secondary hover:text-primary border-b-2 border-transparent -mb-px rounded-none',
    underline: isActive
      ? 'bg-transparent text-accent font-semibold border-b-2 border-accent -mb-px rounded-none'
      : 'bg-transparent text-secondary hover:text-primary border-b-2 border-transparent -mb-px rounded-none',
    pills: isActive
      ? 'bg-surface text-primary font-semibold shadow-sm border border-border rounded-control'
      : 'bg-transparent text-secondary hover:text-primary hover:bg-surface/50 border border-transparent rounded-control',
  };

  const baseStyles = 'inline-flex items-center justify-center px-3.5 py-2 text-xs font-medium transition-all duration-fast disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface';

  const underlineStyles = isUnderline ? {
    borderTop: 'none',
    borderLeft: 'none',
    borderRight: 'none',
    borderBottomWidth: '2px',
    borderBottomStyle: 'solid',
    borderBottomColor: isActive ? 'var(--accent)' : 'transparent',
    borderRadius: 0,
    backgroundColor: 'transparent',
    marginBottom: '-1px',
    ...style,
  } : style;

  return (
    <button
      ref={ref}
      role="tab"
      aria-selected={isActive}
      aria-disabled={disabled}
      data-state={isActive ? 'active' : 'inactive'}
      id={`tab-${value}`}
      tabIndex={isActive ? 0 : -1}
      className={`${baseStyles} ${variants[variant] || variants.default} ${className}`}
      style={underlineStyles}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
});

TabTrigger.displayName = 'TabTrigger';

export const TabContent = forwardRef(function TabContent({
  className = '',
  children,
  value,
  activeValue,
  ...props
}, ref) {
  if (value !== activeValue) return null;

  return (
    <div
      ref={ref}
      role="tabpanel"
      id={`panel-${value}`}
      aria-labelledby={`tab-${value}`}
      className={`animate-fade-in ${className}`}
      {...props}
    >
      {children}
    </div>
  );
});

TabContent.displayName = 'TabContent';