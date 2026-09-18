import React from 'react';
import './Card.css';

export function Card({ children, className = '', variant = 'default', padding = 'md', hover = false, ...props }) {
  const variantClass = `card-${variant}`;
  const paddingClass = `card-p-${padding}`;
  const hoverClass = hover ? 'card-hover' : '';

  return (
    <div
      className={`card ${variantClass} ${paddingClass} ${hoverClass} ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className = '', action, title, subtitle }) {
  return (
    <div className={`card-header ${className}`.trim()}>
      <div className="card-header-content">
        {title && <h3 className="card-title">{title}</h3>}
        {subtitle && <p className="card-subtitle">{subtitle}</p>}
      </div>
      {action && <div className="card-header-action">{action}</div>}
    </div>
  );
}

export function CardBody({ children, className = '' }) {
  return <div className={`card-body ${className}`.trim()}>{children}</div>;
}

export function CardFooter({ children, className = '', divided = true }) {
  return (
    <div className={`card-footer ${divided ? 'card-footer-divided' : ''} ${className}`.trim()}>
      {children}
    </div>
  );
}