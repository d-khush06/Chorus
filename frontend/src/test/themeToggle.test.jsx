import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ThemeToggle } from '../components/cyber/primitives/ThemeToggle';

describe('ThemeToggle Component', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders the theme toggle button and switches theme on click', () => {
    render(<ThemeToggle showLabel />);
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();

    // Initial state set on document
    const initialTheme = document.documentElement.getAttribute('data-theme');
    expect(['light', 'dark']).toContain(initialTheme);

    // Toggle
    fireEvent.click(button);
    const updatedTheme = document.documentElement.getAttribute('data-theme');
    expect(updatedTheme).not.toBe(initialTheme);

    // Verify localStorage persistence inside try/catch
    expect(localStorage.setItem).toHaveBeenCalledWith('chorus-theme', updatedTheme);
  });
});
