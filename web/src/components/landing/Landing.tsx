import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { LanguageToggle } from '../layout/LanguageToggle';

/**
 * Public landing page (default route).
 *
 * Goal: in <30 seconds, a first-time visitor understands what the
 * app does, sees it's free/open-source, and can either try the
 * demo (no upload) or jump into the wizard. NO Streamlit is
 * mentioned — this is a modern webapp marketing page.
 */
export function Landing() {
  const { t } = useTranslation();
  const { setView, demoLoading, loadDemo } = useSession();

  const features = [
    { icon: '⛏️', titleKey: 'landing.feature1_title', descKey: 'landing.feature1_desc' },
    { icon: '📊', titleKey: 'landing.feature2_title', descKey: 'landing.feature2_desc' },
    { icon: '🌍', titleKey: 'landing.feature3_title', descKey: 'landing.feature3_desc' },
    { icon: '📈', titleKey: 'landing.feature4_title', descKey: 'landing.feature4_desc' },
    { icon: '🎮', titleKey: 'landing.feature5_title', descKey: 'landing.feature5_desc' },
    { icon: '🔓', titleKey: 'landing.feature6_title', descKey: 'landing.feature6_desc' },
  ];

  const steps = [
    { num: 1, titleKey: 'landing.step1_title', descKey: 'landing.step1_desc' },
    { num: 2, titleKey: 'landing.step2_title', descKey: 'landing.step2_desc' },
    { num: 3, titleKey: 'landing.step3_title', descKey: 'landing.step3_desc' },
    { num: 4, titleKey: 'landing.step4_title', descKey: 'landing.step4_desc' },
  ];

  const handleTryDemo = async () => {
    setView('app');
    await loadDemo();
  };

  const handleStart = () => {
    setView('app');
  };

  return (
    <div
      data-slot="landing"
      className="min-h-screen overflow-x-hidden"
      style={{ backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)' }}
    >
      {/* ── Top bar ───────────────────────────────────────── */}
      <header className="px-6 py-4 flex items-center justify-between border-b" style={{ borderColor: 'var(--color-border)' }}>
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-9 h-9 rounded-lg text-white font-bold"
            style={{ backgroundColor: 'var(--color-mine-blue)' }}
          >
            CG
          </div>
          <span className="font-semibold">{t('app.title')}</span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/nibaldox/conciliacion-geo-v02"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm px-3 py-1.5 rounded-md hover:opacity-80"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            GitHub ↗
          </a>
          <LanguageToggle />
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────── */}
      <section className="px-6 py-16 md:py-24 text-center" style={{ background: 'linear-gradient(180deg, var(--color-surface) 0%, var(--color-surface-muted) 100%)' }}>
        <div className="max-w-4xl mx-auto">
          <div
            className="inline-block px-3 py-1 rounded-full text-xs font-medium mb-6"
            style={{ backgroundColor: 'var(--status-extra-bg)', color: 'var(--status-extra-text)' }}
          >
            {t('landing.badge')}
          </div>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-4">
            {t('landing.hero_title')}
          </h1>
          <p className="text-lg md:text-xl mb-8" style={{ color: 'var(--color-text-secondary)' }}>
            {t('landing.hero_subtitle')}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center items-center">
            <button
              onClick={handleStart}
              data-slot="landing-cta-start"
              className="px-6 py-3 rounded-lg text-sm font-semibold transition-all hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue focus-visible:ring-offset-2"
              style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff', boxShadow: '0 2px 6px rgba(0,0,0,0.15)' }}
            >
              {t('landing.cta_start')} →
            </button>
            <button
              onClick={handleTryDemo}
              disabled={demoLoading}
              data-slot="landing-cta-demo"
              className="px-6 py-3 rounded-lg text-sm font-semibold border transition-all hover:opacity-90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2"
              style={{
                backgroundColor: 'var(--color-surface)',
                color: 'var(--color-text-primary)',
                borderColor: 'var(--color-border-strong)',
              }}
            >
              {demoLoading ? `⏳ ${t('common.loading')}` : `🎮 ${t('landing.cta_demo')}`}
            </button>
          </div>
          <p className="mt-4 text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {t('landing.cta_note')}
          </p>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────── */}
      <section className="px-6 py-12 md:py-16">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-10">
            {t('landing.features_title')}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((f) => (
              <div
                key={f.titleKey}
                className="p-5 rounded-xl border"
                style={{
                  backgroundColor: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div className="text-3xl mb-2">{f.icon}</div>
                <h3 className="font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>
                  {t(f.titleKey)}
                </h3>
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  {t(f.descKey)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────── */}
      <section className="px-6 py-12 md:py-16" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold text-center mb-3">
            {t('landing.how_title')}
          </h2>
          <p className="text-center mb-10" style={{ color: 'var(--color-text-secondary)' }}>
            {t('landing.how_subtitle')}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {steps.map((s) => (
              <div
                key={s.num}
                className="p-5 rounded-xl border relative"
                style={{
                  backgroundColor: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                }}
              >
                <div
                  className="absolute -top-3 -left-2 w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold"
                  style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff' }}
                >
                  {s.num}
                </div>
                <h3 className="font-semibold mb-1 mt-2" style={{ color: 'var(--color-text-primary)' }}>
                  {t(s.titleKey)}
                </h3>
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                  {t(s.descKey)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Stack ────────────────────────────────────────── */}
      <section className="px-6 py-12 md:py-16">
        <div className="max-w-5xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold mb-3">
            {t('landing.stack_title')}
          </h2>
          <p className="text-sm mb-6" style={{ color: 'var(--color-text-secondary)' }}>
            {t('landing.stack_subtitle')}
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {[
              'Python 3.12', 'FastAPI', 'trimesh', 'scipy', 'openpyxl', 'ezdxf',
              'React 19', 'Vite 6', 'TypeScript', 'CesiumJS', 'Plotly.js', 'Chart.js',
              'TanStack Query', 'Zustand', 'Tailwind CSS 4', 'PWA + Workbox',
            ].map((tech) => (
              <span
                key={tech}
                className="px-3 py-1 rounded-full text-xs font-medium border"
                style={{
                  backgroundColor: 'var(--color-surface)',
                  borderColor: 'var(--color-border)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {tech}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA bottom ──────────────────────────────────── */}
      <section className="px-6 py-12 md:py-16 text-center" style={{ backgroundColor: 'var(--color-surface-muted)' }}>
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl md:text-3xl font-bold mb-3">
            {t('landing.bottom_cta_title')}
          </h2>
          <p className="mb-6" style={{ color: 'var(--color-text-secondary)' }}>
            {t('landing.bottom_cta_subtitle')}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              onClick={handleStart}
              className="px-6 py-3 rounded-lg text-sm font-semibold transition-all hover:opacity-90"
              style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff' }}
            >
              {t('landing.cta_start')} →
            </button>
            <button
              onClick={handleTryDemo}
              disabled={demoLoading}
              className="px-6 py-3 rounded-lg text-sm font-semibold border transition-all hover:opacity-90 disabled:opacity-50"
              style={{
                backgroundColor: 'var(--color-surface)',
                color: 'var(--color-text-primary)',
                borderColor: 'var(--color-border-strong)',
              }}
            >
              {demoLoading ? `⏳ ${t('common.loading')}` : `🎮 ${t('landing.cta_demo')}`}
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────── */}
      <footer className="px-6 py-8 border-t" style={{ borderColor: 'var(--color-border)' }}>
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4 text-sm" style={{ color: 'var(--color-text-muted)' }}>
          <div>
            © {new Date().getFullYear()} Conciliación Geotécnica · MIT License
          </div>
          <div className="flex items-center gap-4">
            <a href="https://github.com/nibaldox/conciliacion-geo-v02" target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
              GitHub
            </a>
            <a href="https://github.com/nibaldox/conciliacion-geo-v02/blob/main/ARCHITECTURE.md" target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
              {t('landing.footer_docs')}
            </a>
            <a href="https://github.com/nibaldox/conciliacion-geo-v02/blob/main/CONTRIBUTING.md" target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
              {t('landing.footer_contribute')}
            </a>
            <a href="https://github.com/nibaldox/conciliacion-geo-v02/blob/main/CODE_OF_CONDUCT.md" target="_blank" rel="noopener noreferrer" className="hover:opacity-80">
              {t('landing.footer_coc')}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
