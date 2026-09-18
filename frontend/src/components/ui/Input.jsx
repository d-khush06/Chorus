import React, { forwardRef } from 'react';
import './Input.css';

const Input = forwardRef(({
  type = 'text',
  className = '',
  disabled = false,
  error = false,
  leftIcon,
  rightIcon,
  ...props
}, ref) => {
  return (
    <div className={`input-wrapper ${error ? 'input-error' : ''} ${disabled ? 'input-disabled' : ''} ${className}`.trim()}>
      {leftIcon && <span className="input-icon input-icon-left" aria-hidden="true">{leftIcon}</span>}
      <input
        ref={ref}
        type={type}
        className="input-field"
        disabled={disabled}
        aria-invalid={error}
        {...props}
      />
      {rightIcon && <span className="input-icon input-icon-right" aria-hidden="true">{rightIcon}</span>}
    </div>
  );
});

Input.displayName = 'Input';

const Textarea = forwardRef(({
  className = '',
  disabled = false,
  error = false,
  autoResize = true,
  ...props
}, ref) => {
  const textareaRef = React.useRef(null);
  const wrappedRef = ref || textareaRef;

  React.useEffect(() => {
    if (autoResize && wrappedRef.current) {
      wrappedRef.current.style.height = 'auto';
      wrappedRef.current.style.height = `${Math.min(wrappedRef.current.scrollHeight, 180)}px`;
    }
  }, [props.value, autoResize, wrappedRef]);

  return (
    <div className={`input-wrapper textarea-wrapper ${error ? 'input-error' : ''} ${disabled ? 'input-disabled' : ''} ${className}`.trim()}>
      <textarea
        ref={wrappedRef}
        className="input-field textarea-field"
        disabled={disabled}
        aria-invalid={error}
        {...props}
      />
    </div>
  );
});

Textarea.displayName = 'Textarea';

export { Input, Textarea };