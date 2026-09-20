import { forwardRef, useState, useRef, useEffect } from 'react';

export const Tabs = forwardRef(function Tabs({ className = '', children, defaultValue, onChange, variant = 'default', ...props }, ref) {
  const [activeValue, setActiveValue] = useState(defaultValue);
  const tabsListRef = useRef(null);

  const handleTabClick = (value) => {
    setActiveValue(value);
    onChange?.(value);
  };

  return (
    <div ref={ref} className={className} {...props}>
      <TabsList ref={tabsListRef} variant={variant} activeValue={activeValue} onTabClick={handleTabClick} />
      <TabsContent>{children}</TabsContent>
    </div>
  );
});

Tabs.displayName = 'Tabs';

const TabsList = forwardRef(function TabsList({ variant, activeValue, onTabClick, children }, ref) {
  const variants = {
    default: 'border-b border-default',
    underline: 'border-b border-default',
    pills: '',
  };

  return (
    <div
      ref={ref}
      role="tablist"
      aria-orientation="horizontal"
      className={`flex gap-1 ${variants[variant]}`}
    >
      {React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child;
        return React.cloneElement(child, {
          variant,
          isActive: child.props.value === activeValue,
          onClick: () => onTabClick(child.props.value),
        });
      })}
    </div>
  );
});

TabsList.displayName = 'TabsList';

function TabsContent({ children }) {
  return (
    <div className="mt-4">
      {React.Children.map(children, (child) => {
        if (!React.isValidElement(child)) return child;
        return child;
      })}
    </div>
  );
}

export const TabTrigger = forwardRef(function TabTrigger({
  className = '',
  children,
  value,
  disabled = false,
  isActive = false,
  onClick,
  variant = 'default',
  ...props
}, ref) {
  const variants = {
    default: 'bg-transparent text-secondary hover:text-primary data-[state=active]:text-primary data-[state=active]:font-semibold',
    underline: 'bg-transparent text-secondary hover:text-primary data-[state=active]:text-accent data-[state=active]:font-semibold',
    pills: 'bg-surface text-secondary hover:text-primary data-[state=active]:bg-accent data-[state=active]:text-white data-[state=active]:shadow-cyber-soft',
  };

  const baseStyles = 'inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-control transition-all duration-fast disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface';

  return (
    <button
      ref={ref}
      role="tab"
      aria-selected={isActive}
      aria-disabled={disabled}
      id={`tab-${value}`}
      tabIndex={isActive ? 0 : -1}
      className={`${baseStyles} ${variants[variant]} ${isActive ? 'data-[state=active]' : ''} ${className}`}
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

import React from 'react';