import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
}

// Default is dark: the app is designed for a dark surface (see
// `index.html` which sets `class="dark"` on first paint) and the
// ThemeToggle is the only way to opt into light mode. A default of
// `false` here would race with `index.html` and leave a flash of
// unstyled content (white glass cards on dark sidebar).
export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      isDark: true,
      toggle: () => set((state) => ({ isDark: !state.isDark })),
    }),
    {
      name: 'theme-preference',
    },
  ),
);