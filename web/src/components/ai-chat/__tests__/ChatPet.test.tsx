import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { ChatPet } from '../ChatPet';

describe('ChatPet', () => {
  it('renders the mascot svg with helmet, eyes and mouth', () => {
    const { getByTestId } = render(<ChatPet />);
    expect(getByTestId('ai-chat-pet')).toBeInTheDocument();
    expect(getByTestId('ai-pet-helmet')).toBeInTheDocument();
    expect(getByTestId('ai-pet-eyes')).toBeInTheDocument();
    expect(getByTestId('ai-pet-mouth')).toBeInTheDocument();
    expect(getByTestId('ai-chat-pet').querySelectorAll('.ai-pet__eye')).toHaveLength(2);
    expect(getByTestId('ai-chat-pet').querySelectorAll('.ai-pet__pupil')).toHaveLength(2);
  });

  it('keeps the mascot aria-hidden for assistive tech', () => {
    const { getByTestId } = render(<ChatPet />);
    expect(getByTestId('ai-chat-pet')).toHaveAttribute('aria-hidden', 'true');
  });

  it('toggles the working pulse class from the streaming prop', () => {
    const { container, rerender } = render(<ChatPet streaming={false} />);
    expect(container.querySelector('.ai-pet')?.className).not.toContain('ai-pet--working');
    expect(container.querySelector('.ai-pet__lamp-halo')).not.toBeNull();
    rerender(<ChatPet streaming />);
    expect(container.querySelector('.ai-pet--working')).not.toBeNull();
  });
});
