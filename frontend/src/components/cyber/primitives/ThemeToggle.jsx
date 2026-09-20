import { useEffect, useState, useCallback } from 'react';
import { Button } from './Button';

function getInitialTheme() {
  try {
    const stored = localStorage.getItem('chorus-theme') || localStorage.getItem('cyber-theme');
    if (stored === 'light' || stored === 'dark') {
      return stored;
    }
  } catch (e) {
    // Ignore localStorage access issues
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'dark';
}

export function ThemeToggle({ className = '', showLabel = false, ...props }) {
  const [theme, setTheme] = useState(getInitialTheme);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const initial = getInitialTheme();
    setTheme(initial);
    document.documentElement.setAttribute('data-theme', initial);

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e) => {
      try {
        const stored = localStorage.getItem('chorus-theme') || localStorage.getItem('cyber-theme');
        if (!stored) {
          const next = e.matches ? 'dark' : 'light';
          setTheme(next);
          document.documentElement.setAttribute('data-theme', next);
        }
      } catch (err) {
        // Fallback
      }
    };

    if (mediaQuery?.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    try {
      localStorage.setItem('chorus-theme', newTheme);
      localStorage.setItem('cyber-theme', newTheme);
    } catch (e) {
      console.warn('Unable to persist theme to localStorage', e);
    }
    document.documentElement.classList.add('theme-transition');
    document.documentElement.setAttribute('data-theme', newTheme);
    document.documentElement.style.colorScheme = newTheme;
    setTimeout(() => {
      document.documentElement.classList.remove('theme-transition');
    }, 250);
  }, [theme]);

  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className={className} disabled aria-label="Toggle theme" {...props}>
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="12" r="5" />
          <line x1="12" y1="1" x2="12" y2="3" />
          <line x1="12" y1="21" x2="12" y2="23" />
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
          <line x1="1" y1="12" x2="3" y2="12" />
          <line x1="21" y1="12" x2="23" y2="12" />
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
        </svg>
      </Button>
    );
  }

  const SunIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );

  const MoonIcon = (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );

  return (
    <Button
      variant="ghost"
      size={showLabel ? 'sm' : 'icon'}
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
      className={`${className} inline-flex items-center gap-2`}
      {...props}
    >
      {theme === 'light' ? MoonIcon : SunIcon}
      {showLabel && (
        <span className="text-sm font-medium text-secondary">
          {theme === 'light' ? 'Dark' : 'Light'}
        </span>
      )}
    </Button>
  );
}

export function useTheme() {
  const [theme, setThemeState] = useState(getInitialTheme);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const initial = getInitialTheme();
    setThemeState(initial);
    document.documentElement.setAttribute('data-theme', initial);

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e) => {
      try {
        const stored = localStorage.getItem('chorus-theme') || localStorage.getItem('cyber-theme');
        if (!stored) {
          const next = e.matches ? 'dark' : 'light';
          setThemeState(next);
          document.documentElement.setAttribute('data-theme', next);
        }
      } catch (err) {}
    };
    if (mediaQuery?.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
  }, []);

  const toggleTheme = useCallback(() => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setThemeState(newTheme);
    try {
      localStorage.setItem('chorus-theme', newTheme);
      localStorage.setItem('cyber-theme', newTheme);
    } catch (e) {
      console.warn('Failed to save theme in localStorage', e);
    }
    document.documentElement.classList.add('theme-transition');
    document.documentElement.setAttribute('data-theme', newTheme);
    document.documentElement.style.colorScheme = newTheme;
    setTimeout(() => {
      document.documentElement.classList.remove('theme-transition');
    }, 250);
  }, [theme]);

  return { theme, toggleTheme, setTheme: toggleTheme, mounted };
}