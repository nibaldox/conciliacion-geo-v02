import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBar } from '../StatusBar';

describe('StatusBar', () => {
  it('renders the default title', () => {
    render(<StatusBar entries={[{ level: 'system', text: 'ok' }]} />);
    expect(screen.getByText('TERMINAL DE STATUS')).toBeInTheDocument();
  });

  it('renders a custom title', () => {
    render(<StatusBar title="CONSOLE" entries={[]} />);
    expect(screen.getByText('CONSOLE')).toBeInTheDocument();
  });

  it('renders each entry with its level prefix', () => {
    render(
      <StatusBar
        entries={[
          { level: 'system', text: 'Ingest core initialised' },
          { level: 'scan', text: 'Waiting for packets' },
          { level: 'geo', text: 'EPSG:4326' },
        ]}
      />,
    );
    expect(screen.getByText('[SYSTEM]')).toBeInTheDocument();
    expect(screen.getByText('[SCAN]')).toBeInTheDocument();
    expect(screen.getByText('[GEO]')).toBeInTheDocument();
    expect(screen.getByText('Ingest core initialised')).toBeInTheDocument();
  });

  it('renders a blinking cursor only on the last entry', () => {
    const { container } = render(
      <StatusBar
        entries={[
          { level: 'system', text: 'first' },
          { level: 'scan', text: 'last' },
        ]}
        showCursor
      />,
    );
    // The cursor is an inline-block span with animate-pulse. There
    // should be exactly one.
    const cursors = container.querySelectorAll('.animate-pulse');
    expect(cursors).toHaveLength(1);
  });

  it('does not render a cursor when showCursor is false', () => {
    const { container } = render(
      <StatusBar entries={[{ level: 'system', text: 'x' }]} showCursor={false} />,
    );
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });
});
