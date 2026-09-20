import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { ThemeToggle, useTheme } from '../../components/cyber/primitives/ThemeToggle';
import { Button } from '../../components/cyber/primitives/Button';
import { Badge } from '../../components/cyber/primitives/Badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../../components/cyber/primitives/Card';
import { StatusPill, StatusDot } from '../../components/cyber/primitives/StatusPill';
import { Tabs, TabTrigger, TabContent } from '../../components/cyber/primitives/Tabs';
import { EmptyState, LoadingState, ErrorState } from '../../components/cyber/primitives/EmptyState';
import { Skeleton } from '../../components/cyber/primitives/Skeleton';

describe('ThemeToggle', () => {
  beforeEach(() => {
    cleanup();
    localStorage.clear();
    vi.useFakeTimers();
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('renders sun icon in light mode', () => {
    render(<ThemeToggle />);
    expect(screen.getByLabelText('Switch to dark mode')).toBeInTheDocument();
  });

  it('toggles theme on click', () => {
    render(<ThemeToggle />);
    const button = screen.getByLabelText('Switch to dark mode');
    fireEvent.click(button);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.setItem).toHaveBeenCalledWith('cyber-theme', 'dark');
  });

  it('persists theme in localStorage', () => {
    localStorage.getItem.mockReturnValue('dark');
    render(<ThemeToggle />);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('respects prefers-color-scheme when no localStorage', () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    localStorage.getItem.mockReturnValue(null);
    render(<ThemeToggle />);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});

describe('useTheme hook', () => {
  beforeEach(() => {
    cleanup();
    localStorage.clear();
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('returns theme and toggle function', () => {
    let result;
    function TestComponent() {
      const theme = useTheme();
      result = theme;
      return null;
    }
    render(<TestComponent />);
    expect(result).toHaveProperty('theme');
    expect(result).toHaveProperty('setTheme');
    expect(typeof result.setTheme).toBe('function');
  });
});

describe('Button', () => {
  it('renders with correct variant classes', () => {
    render(<Button variant="primary">Primary</Button>);
    const btn = screen.getByRole('button', { name: 'Primary' });
    expect(btn).toHaveClass('bg-accent');
    expect(btn).toHaveClass('text-white');
  });

  it('renders with correct size classes', () => {
    render(<Button size="sm">Small</Button>);
    expect(screen.getByRole('button')).toHaveClass('px-3');
    expect(screen.getByRole('button')).toHaveClass('py-1.5');
  });

  it('shows loading spinner when loading', () => {
    render(<Button loading>Loading</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button')).toContainHTML('svg');
  });

  it('disables button when disabled', () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
    expect(screen.getByRole('button')).toHaveAttribute('aria-disabled', 'true');
  });

  it('renders left and right icons', () => {
    render(
      <Button leftIcon={<span data-testid="left">L</span>} rightIcon={<span data-testid="right">R</span>}>
        Button
      </Button>
    );
    expect(screen.getByTestId('left')).toBeInTheDocument();
    expect(screen.getByTestId('right')).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders with default variant', () => {
    render(<Badge>Default</Badge>);
    expect(screen.getByText('Default')).toHaveClass('bg-surface');
    expect(screen.getByText('Default')).toHaveClass('text-primary');
  });

  it('renders with accent variant', () => {
    render(<Badge variant="accent">Accent</Badge>);
    expect(screen.getByText('Accent')).toHaveClass('bg-accent');
    expect(screen.getByText('Accent')).toHaveClass('text-white');
  });

  it('renders semantic variants', () => {
    render(<Badge variant="ok" dot>OK</Badge>);
    expect(screen.getByText('OK')).toHaveClass('bg-ok/10');
    expect(screen.getByText('OK')).toHaveClass('text-ok');
    expect(screen.getByText('OK')).toHaveClass('border-ok/30');
  });

  it('renders dot when dot prop is true', () => {
    render(<Badge variant="ok" dot>OK</Badge>);
    const dot = screen.getByText('OK').parentElement.querySelector('span[aria-hidden="true"]');
    expect(dot).toHaveClass('bg-ok');
    expect(dot).toHaveClass('rounded-full');
  });
});

describe('Card', () => {
  it('renders with default variant', () => {
    render(<Card>Content</Card>);
    expect(screen.getByText('Content')).toHaveClass('bg-surface');
    expect(screen.getByText('Content')).toHaveClass('border');
    expect(screen.getByText('Content')).toHaveClass('border-default');
  });

  it('renders elevated variant with shadow', () => {
    render(<Card variant="elevated">Elevated</Card>);
    expect(screen.getByText('Elevated')).toHaveClass('shadow-cyber-elevated');
  });

  it('renders stage variant with stage background', () => {
    render(<Card variant="stage">Stage</Card>);
    expect(screen.getByText('Stage')).toHaveClass('bg-stage');
  });

  it('applies padding variants', () => {
    render(<Card padding="lg">Large</Card>);
    expect(screen.getByText('Large')).toHaveClass('p-6');
  });

  it('renders Card sub-components', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Description</CardDescription>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>
    );
    expect(screen.getByText('Title')).toHaveClass('font-heading');
    expect(screen.getByText('Title')).toHaveClass('text-xl');
    expect(screen.getByText('Description')).toHaveClass('text-secondary');
    expect(screen.getByText('Content')).toBeInTheDocument();
    expect(screen.getByText('Footer')).toHaveClass('border-t');
  });
});

describe('StatusPill', () => {
  it('renders with correct status colors', () => {
    render(<StatusPill status="ok" label="OK" />);
    const pill = screen.getByText('OK').parentElement;
    expect(pill).toHaveClass('bg-ok/10');
    expect(pill).toHaveClass('text-ok');
    expect(pill).toHaveClass('border-ok/30');
  });

  it('renders live status with pulse', () => {
    render(<StatusPill status="live" label="LIVE" pulse />);
    expect(screen.getByText('LIVE').parentElement).toHaveClass('animate-pulse-slow');
  });

  it('shows icon by default', () => {
    render(<StatusPill status="ok" label="OK" />);
    expect(screen.getByText('OK').parentElement).toContainHTML('svg');
  });

  it('hides icon when showIcon is false', () => {
    render(<StatusPill status="ok" label="OK" showIcon={false} />);
    expect(screen.getByText('OK').parentElement.querySelector('svg')).not.toBeInTheDocument();
  });
});

describe('StatusDot', () => {
  it('renders with correct status colors', () => {
    render(<StatusDot status="danger" />);
    const dot = screen.getByRole('presentation', { hidden: true });
    expect(dot).toHaveClass('bg-danger');
  });

  it('applies size variants', () => {
    render(<StatusDot status="ok" size="lg" />);
    const dot = screen.getByRole('presentation', { hidden: true });
    expect(dot).toHaveClass('w-4');
    expect(dot).toHaveClass('h-4');
  });

  it('pulses when pulse prop is true', () => {
    render(<StatusDot status="live" pulse />);
    const dot = screen.getByRole('presentation', { hidden: true });
    expect(dot).toHaveClass('animate-pulse-slow');
  });
});

describe('Tabs', () => {
  it('renders tab list and triggers', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabTrigger value="tab1">Tab 1</TabTrigger>
        <TabTrigger value="tab2">Tab 2</TabTrigger>
      </Tabs>
    );
    expect(screen.getByRole('tablist')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tab 1' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tab 2' })).toBeInTheDocument();
  });

  it('shows active tab content', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabTrigger value="tab1">Tab 1</TabTrigger>
        <TabTrigger value="tab2">Tab 2</TabTrigger>
        <TabContent value="tab1" activeValue="tab1">Content 1</TabContent>
        <TabContent value="tab2" activeValue="tab1">Content 2</TabContent>
      </Tabs>
    );
    expect(screen.getByText('Content 1')).toBeInTheDocument();
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument();
  });

  it('disables tab when disabled prop is true', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabTrigger value="tab1">Tab 1</TabTrigger>
        <TabTrigger value="tab2" disabled>Tab 2</TabTrigger>
      </Tabs>
    );
    expect(screen.getByRole('tab', { name: 'Tab 2' })).toBeDisabled();
  });
});

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(<EmptyState title="Empty" description="No data" />);
    expect(screen.getByText('Empty')).toHaveClass('font-heading');
    expect(screen.getByText('No data')).toHaveClass('text-secondary');
  });

  it('renders icon when provided', () => {
    render(<EmptyState icon={<span data-testid="icon">📦</span>} />);
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders action when provided', () => {
    render(<EmptyState action={<Button>Action</Button>} />);
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument();
  });
});

describe('LoadingState', () => {
  it('renders title', () => {
    render(<LoadingState title="Loading..." />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(<LoadingState title="Loading..." description="Please wait" />);
    expect(screen.getByText('Please wait')).toBeInTheDocument();
  });
});

describe('ErrorState', () => {
  it('renders error icon and message', () => {
    render(<ErrorState title="Error" description="Something failed" />);
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Something failed')).toBeInTheDocument();
    expect(screen.getByRole('img', { hidden: true })).toBeInTheDocument();
  });

  it('renders action button', () => {
    render(<ErrorState action={<Button>Retry</Button>} />);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('Skeleton', () => {
  it('renders text variant by default', () => {
    render(<Skeleton />);
    const skeleton = screen.getByRole('presentation', { hidden: true });
    expect(skeleton).toHaveClass('h-4');
    expect(skeleton).toHaveClass('animate-shimmer');
  });

  it('renders multiple items when count > 1', () => {
    render(<Skeleton count={3} />);
    const skeletons = screen.getAllByRole('presentation', { hidden: true });
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });

  it('renders card variant', () => {
    render(<Skeleton variant="card" />);
    const skeleton = screen.getByRole('presentation', { hidden: true });
    expect(skeleton).toHaveClass('h-32');
    expect(skeleton).toHaveClass('rounded-card');
  });
});