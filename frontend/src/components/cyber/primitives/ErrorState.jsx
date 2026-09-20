import './ErrorState.css';

export default function ErrorState({ 
  title,
  description,
  icon,
  className = ''
}) {
  return (
    <div className={`cyber-error-state ${className}`}>
      {icon && <div className="error-state-icon">{icon}</div>}
      <h3 className="error-state-title">{title}</h3>
      {description && <p className="error-state-description">{description}</p>}
    </div>
  );
}