import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React, { useState } from 'react';
import { StageTracker } from '../components/cyber/StageTracker';

function SimulatedSSETracker({ sseEvents = [] }) {
  const [stages, setStages] = useState([]);
  const [currentStage, setCurrentStage] = useState(null);
  const [progress, setProgress] = useState(0);

  // Apply mocked SSE events
  React.useEffect(() => {
    for (const event of sseEvents) {
      if (event.type === 'manifest') {
        setStages(event.stages);
      } else if (event.type === 'start') {
        setCurrentStage(event.stage);
        setStages(prev => prev.map(s => s.name === event.stage ? { ...s, status: 'running' } : s));
      } else if (event.type === 'complete') {
        setStages(prev => {
          const updated = prev.map(s => s.name === event.stage ? { ...s, status: 'completed' } : s);
          const completedCount = updated.filter(s => s.status === 'completed' || s.status === 'skipped').length;
          setProgress(Math.round((completedCount / updated.length) * 100));
          return updated;
        });
      } else if (event.type === 'skip') {
        setStages(prev => {
          const updated = prev.map(s => s.name === event.stage ? { ...s, status: 'skipped', reason: event.reason } : s);
          const completedCount = updated.filter(s => s.status === 'completed' || s.status === 'skipped').length;
          setProgress(Math.round((completedCount / updated.length) * 100));
          return updated;
        });
      }
    }
  }, [sseEvents]);

  return <StageTracker stages={stages} currentStage={currentStage} progress={progress} />;
}

describe('StageTracker Component driven by SSE events', () => {
  it('renders stages strictly from the backend manifest and updates via stage events', () => {
    const mockManifest = [
      { name: 'source_ingestion', status: 'pending' },
      { name: 'quality_gate', status: 'pending' },
      { name: 'manipulation_detection', status: 'pending' },
      { name: 'ai_generation_detection', status: 'pending' }
    ];

    const sseEvents = [
      { type: 'manifest', stages: mockManifest },
      { type: 'start', stage: 'source_ingestion' },
      { type: 'complete', stage: 'source_ingestion' },
      { type: 'start', stage: 'quality_gate' },
      { type: 'skip', stage: 'quality_gate', reason: 'no audio stream' },
      { type: 'start', stage: 'manipulation_detection' }
    ];

    render(<SimulatedSSETracker sseEvents={sseEvents} />);

    // Renders all 4 stages in exact manifest order
    const listItems = screen.getAllByRole('listitem');
    expect(listItems.length).toBe(4);

    // Stage 1 is completed
    expect(listItems[0]).toHaveTextContent(/Source Ingestion/i);
    expect(listItems[0]).toHaveTextContent(/completed/i);

    // Stage 2 is skipped with reason
    expect(listItems[1]).toHaveTextContent(/Quality Gate/i);
    expect(listItems[1]).toHaveTextContent(/skipped/i);
    expect(listItems[1]).toHaveTextContent(/no audio stream/i);

    // Stage 3 is currently running
    expect(listItems[2]).toHaveTextContent(/Deepfake/i);
    expect(listItems[2]).toHaveTextContent(/running/i);

    // Progress percentage
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
});
