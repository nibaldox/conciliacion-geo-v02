import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { useTheme } from '../../../stores/theme';
import { applyTheme } from '../../../utils/theme';
import { ThemeToggle } from '../ThemeToggle';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

beforeEach(() => {
  localStorage.clear();
  useTheme.setState({ isDark: true });
  applyTheme(true);
});

describe('ThemeToggle', () => {
  it('activates the light theme by keyboard and saves the preference', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ThemeToggle /></I18nextProvider>);
    screen.getByRole('button', { name: 'Cambiar a modo claro' }).focus();
    await user.keyboard('{Enter}');
    expect(document.documentElement).toHaveClass('light');
    expect(document.documentElement).not.toHaveClass('dark');
    expect(document.documentElement.style.colorScheme).toBe('light');
    expect(JSON.parse(localStorage.getItem('theme-preference')!).state.isDark).toBe(false);
    expect(screen.getByRole('button', { name: 'Cambiar a modo oscuro' })).toHaveTextContent('Oscuro');
  });

  it('returns to dark mode and restores the saved light preference', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ThemeToggle /></I18nextProvider>);
    await user.click(screen.getByRole('button', { name: 'Cambiar a modo claro' }));
    const saved = localStorage.getItem('theme-preference')!;
    await user.click(screen.getByRole('button', { name: 'Cambiar a modo oscuro' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(document.documentElement).not.toHaveClass('light');
    localStorage.setItem('theme-preference', saved);
    await useTheme.persist.rehydrate();
    expect(useTheme.getState().isDark).toBe(false);
  });
});
