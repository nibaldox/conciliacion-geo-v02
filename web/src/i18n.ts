/**
 * i18next configuration.
 *
 * Languages: es (default, primary), en.
 * Detection order:
 *   1. localStorage 'conciliacion.lang' (user-set preference)
 *   2. <html lang> attribute (set in index.html)
 *   3. navigator.language (browser preference)
 *   4. fallback to 'es'
 *
 * Strings live in web/src/locales/{es,en}.json. Use the `useTranslation`
 * hook inside React components. For non-React code (axios
 * interceptors, side-effects), import `i18n` directly and call
 * `i18n.t('key')`.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import es from './locales/es.json';
import en from './locales/en.json';

const SUPPORTED = ['es', 'en'] as const;
export type SupportedLocale = (typeof SUPPORTED)[number];
const STORAGE_KEY = 'conciliacion.lang';
const DEFAULT_LOCALE: SupportedLocale = 'es';

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      es: { translation: es },
      en: { translation: en },
    },
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED as unknown as string[],
    // Don't silently switch to the user's browser locale if it's
    // not in our supported list — we'd be guessing about strings
    // that don't exist yet (en) and the partial-key fallback to
    // es would be confusing. Show English only if explicitly
    // requested, otherwise default to Spanish.
    load: 'currentOnly',
    fallbackNS: 'translation',
    debug: false,
    interpolation: {
      escapeValue: false,  // React already escapes
    },
    detection: {
      order: ['localStorage', 'htmlTag', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: STORAGE_KEY,
      // localStorage can return 'es' or 'en'; only honour those.
      convertDetectedLanguage: (lng: string): string => {
        if (lng.startsWith('es')) return 'es';
        if (lng.startsWith('en')) return 'en';
        return DEFAULT_LOCALE;
      },
    },
    react: {
      useSuspense: false,  // Suspense complicates the lazy App — keep it simple
    },
  });

/** Programmatic locale change. Use this from a Language toggle button. */
export function setLocale(locale: SupportedLocale): void {
  void i18n.changeLanguage(locale);
  document.documentElement.lang = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // localStorage may be unavailable (privacy mode, SSR) — silently ignore
  }
}

export const SUPPORTED_LOCALES = SUPPORTED;
export { STORAGE_KEY };
export default i18n;
