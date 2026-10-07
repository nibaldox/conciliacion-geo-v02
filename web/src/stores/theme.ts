import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { applyTheme } from '../utils/theme';

interface ThemeState {
  isDark: boolean;
  toggle: () => void;
}

export const useTheme = create<ThemeState>()(
  persist(
    (set) => ({
      isDark: true,
      toggle: () => set((state) => {
        const isDark = !state.isDark;
        applyTheme(isDark);
        return { isDark };
      }),
    }),
    {
      name: 'theme-preference',
    },
  ),
);

applyTheme(useTheme.getState().isDark);
