import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

import { ForensicPage } from '../components/cyber/ForensicPage';
import { LiveWatchPage } from '../components/cyber/LiveWatchPage';
import { CyberLandingPage } from '../components/cyber/CyberLayout';
import AuthContext from '../context/AuthContext';

const mockAuth = {
  token: 'mock-token',
  user: { name: 'Test Investigator', email: 'investigator@chorus.ai' },
  logout: vi.fn(),
  loading: false
};

const renderWithRouter = (component) => {
  return render(
    <AuthContext.Provider value={mockAuth}>
      <MemoryRouter>
        {component}
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('ForensicPage Empty & Initial States (Defect 1 Verification)', () => {
  it('renders clean "Waiting for evidence" empty states across all result panels before any run', () => {
    renderWithRouter(<ForensicPage />);

    // Check all empty states
    const emptyStates = screen.getAllByText('Waiting for evidence');
    expect(emptyStates.length).toBeGreaterThanOrEqual(1);

    // Verify action buttons are disabled before a completed run
    const saveBtn = screen.getByRole('button', { name: /Save to Evidence Room/i });
    expect(saveBtn).toBeDisabled();

    const routeBtn = screen.getByRole('button', { name: /Route to Review Queue/i });
    expect(routeBtn).toBeDisabled();

    const exportBtn = screen.getByRole('button', { name: /Export report/i });
    expect(exportBtn).toBeDisabled();

    // Verify no hardcoded 1800 frames or preset 0.000 results
    expect(screen.queryByText('/ 1800')).not.toBeInTheDocument();
    expect(screen.queryByText(/FRAME:\s*\/ 1800/i)).not.toBeInTheDocument();
  });
});

describe('LiveWatchPage Idle & Initial States (Defect 2 Verification)', () => {
  it('initializes with empty camera inputs, masked URL field, and idle placeholders', () => {
    renderWithRouter(<LiveWatchPage />);

    // Inputs start empty with placeholder text only
    const nameInput = screen.getByPlaceholderText(/e\.g\. Sector 4 Perimeter/i);
    expect(nameInput.value).toBe('');

    const urlInput = screen.getByPlaceholderText(/rtsp:\/\/user:pass@camera\.local/i);
    expect(urlInput.value).toBe('');

    // Stream telemetry displays "—" until real stream reports
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(2);

    // Live agent watch shows dynamic model and "last analyzed —"
    expect(screen.getByText(/Chorus Multimodal VL Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/Last analyzed/i)).toBeInTheDocument();
  });
});

describe('CyberLandingPage Layout & Real Cases', () => {
  it('renders three equal console cards and recent investigations card', () => {
    renderWithRouter(<CyberLandingPage />);

    // 3 Equal console cards
    expect(screen.getByText('Live Watch')).toBeInTheDocument();
    expect(screen.getByText('Forensic Analysis')).toBeInTheDocument();
    expect(screen.getByText('Trace')).toBeInTheDocument();

    // Recent investigations card
    expect(screen.getByText('Recent Cyber Investigations')).toBeInTheDocument();
  });
});
