import { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import { useAIProviders, useAIModels } from '../../api/hooks';
import { Button } from '../ui/Button';

// ─── Types ───────────────────────────────────────────────────

type AIProvider = 'ollama' | 'lmstudio';

interface AIOptions {
  provider: AIProvider;
  model: string;
}

const PROVIDER_LABELS: Record<AIProvider, string> = {
  ollama: 'Ollama',
  lmstudio: 'LM Studio',
};

const API_BASE = import.meta.env.VITE_API_URL || '';

// ─── Component ───────────────────────────────────────────────

export function AIReporter() {
  const { t } = useTranslation();
  const [options, setOptions] = useState<AIOptions>({
    provider: 'ollama',
    model: '',
  });
  const [report, setReport] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isComplete, setIsComplete] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // ── Auto-detect providers ──────────────────────────────
  const { data: providersData, isLoading: providersLoading } = useAIProviders();
  const providers = providersData?.providers ?? {};
  const defaultProvider = providersData?.default_provider ?? 'ollama';

  // Resolve provider availability
  const ollamaAvailable = providers['ollama']?.available ?? false;
  const lmstudioAvailable = providers['lmstudio']?.available ?? false;

  // ── Auto-detect models ─────────────────────────────────
  const { data: modelsData } = useAIModels(
    options.provider === 'ollama' && ollamaAvailable ? 'ollama'
      : options.provider === 'lmstudio' && lmstudioAvailable ? 'lmstudio'
        : null,
  );
  const detectedModels = modelsData?.models ?? [];

  // Sync default provider on first load
  useEffect(() => {
    if (providersData && !options.model) {
      const prov = (defaultProvider === 'lmstudio' && lmstudioAvailable)
        ? 'lmstudio' as AIProvider
        : 'ollama' as AIProvider;
      // Only override if current provider has no models
      const currentModels = providers[options.provider]?.models ?? [];
      if (currentModels.length === 0 && providers[prov]?.models?.length) {
        setOptions({
          provider: prov,
          model: providers[prov]?.models?.[0] ?? '',
        });
      }
    }
  }, [providersData, defaultProvider, options.provider, options.model, ollamaAvailable, lmstudioAvailable, providers]);

  // ── Provider change handler ────────────────────────────
  const handleProviderChange = useCallback(
    (provider: AIProvider) => {
      setOptions({ provider, model: '' });
    },
    [],
  );

  // ── Streaming generation ───────────────────────────────
  const handleGenerate = useCallback(async () => {
    setIsGenerating(true);
    setError(null);
    setReport('');
    setIsComplete(false);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/report`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': localStorage.getItem('session_id') || '',
        },
        body: JSON.stringify({
          provider: options.provider,
          model: options.model,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error('No response body');

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                setIsComplete(true);
              } else if (data.content) {
                setReport((prev) => prev + data.content);
              }
            } catch {
              // Skip malformed JSON lines
            }
          }
        }
      }
      setIsComplete(true);
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Error al conectar con el modelo IA');
      }
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
    }
  }, [options.provider, options.model]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    setIsGenerating(false);
  }, []);

  const handleRetry = useCallback(() => {
    handleGenerate();
  }, [handleGenerate]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(report);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = report;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
  }, [report]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'Informe_IA_Conciliacion.md';
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  const hasContent = report.length > 0;
  const anyProviderAvailable = ollamaAvailable || lmstudioAvailable;

  // ── Render ─────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Options panel */}
      <div className="rounded-xl shadow-sm p-5" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>
          Configuración del Modelo IA
        </h4>

        {/* Provider toggle */}
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Proveedor
            </label>
            <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-border)' }}>
              {(['ollama', 'lmstudio'] as AIProvider[]).map((prov) => {
                const available = prov === 'ollama' ? ollamaAvailable : lmstudioAvailable;
                const loading = providersLoading;
                return (
                  <button
                    key={prov}
                    onClick={() => handleProviderChange(prov)}
                    className="flex-1 px-3 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5"
                    style={options.provider === prov
                      ? { backgroundColor: 'var(--color-mine-blue)', color: '#fff' }
                      : { backgroundColor: 'var(--color-surface)', color: 'var(--color-text-secondary)' }
                    }
                  >
                    <span
                      className="inline-block w-2 h-2 rounded-full"
                      style={loading ? { backgroundColor: 'var(--color-border-strong)', animation: 'pulse 1.5s infinite' } : available ? { backgroundColor: 'var(--color-mine-green)' } : { backgroundColor: 'var(--color-mine-red)' }}
                      title={loading ? t('ai.status_detecting') : available ? t('ai.status_available') : t('ai.status_unavailable')}
                    />
                    {PROVIDER_LABELS[prov]}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Model selector */}
          <div className="flex-1">
            <label className="block text-xs font-medium mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              {t('ai.model')}
            </label>
            <select
              value={options.model}
              onChange={(e) => setOptions((prev) => ({ ...prev, model: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-primary)', backgroundColor: 'var(--color-surface)' }}
            >
              {detectedModels.length > 0 ? (
                detectedModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))
              ) : (
                <option value="">
                  {providersLoading ? t('ai.loading_models') : t('ai.no_models')}
                </option>
              )}
            </select>
          </div>

          {/* Generate button */}
          <div>
            {!isGenerating ? (
              <Button
                onClick={handleGenerate}
                disabled={!anyProviderAvailable || !options.model}
                leftIcon={<span>✨</span>}
                className="!shadow-md hover:!shadow-lg"
              >
                {t('ai.generate')}
              </Button>
            ) : (
              <Button variant="danger" onClick={handleStop}>
                {t('ai.stop')}
              </Button>
            )}
          </div>
        </div>

        {/* No providers available — install instructions */}
        {!anyProviderAvailable && !providersLoading && (
          <div className="mt-4 rounded-lg p-4 text-sm" style={{ backgroundColor: 'var(--status-warn-bg)', border: '1px solid var(--status-warn-border)' }}>
            <p className="font-semibold mb-2" style={{ color: 'var(--status-warn-text)' }}>{t('ai.no_providers')}</p>
            <p className="mb-1" style={{ color: 'var(--status-warn-text)' }}>{t('ai.install_prompt')}</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li style={{ color: 'var(--status-warn-text)' }}>
                <strong>{t('ai.ollama_install_label')}</strong>{' '}
                <code className="px-1.5 py-0.5 rounded text-xs" style={{ backgroundColor: 'var(--status-warn-border)' }}>
                  curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.1:8b
                </code>
              </li>
              <li style={{ color: 'var(--status-warn-text)' }}>
                <strong>{t('ai.lmstudio_install_label')}</strong>{' '}
                {t('ai.lmstudio_install_detail', { link: (
                  <a href="https://lmstudio.ai" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--status-warn-text)', textDecoration: 'underline' }}>
                    lmstudio.ai
                  </a>
                )})}
              </li>
            </ul>
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl p-4 flex items-center justify-between" style={{ backgroundColor: 'var(--status-nok-bg)', border: '1px solid var(--status-nok-border)' }}>
          <p className="text-sm font-medium" style={{ color: 'var(--status-nok-text)' }}>{error}</p>
          <button
            onClick={handleRetry}
            className="px-3 py-1.5 text-white rounded-lg text-xs font-medium"
            style={{ backgroundColor: 'var(--color-mine-red)' }}
          >
            {t('ai.retry')}
          </button>
        </div>
      )}

      {/* Report display */}
      {(hasContent || isGenerating) && (
        <div className="rounded-xl shadow-sm" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
          {/* Header */}
          <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--color-border)' }}>
            <h4 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {t('ai.report_title')}
            </h4>
            {isGenerating && (
              <div className="flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: 'var(--color-mine-blue)', animationDelay: '0ms' }} />
                <span className="inline-block w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: 'var(--color-mine-blue)', animationDelay: '150ms' }} />
                <span className="inline-block w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: 'var(--color-mine-blue)', animationDelay: '300ms' }} />
                <span className="text-xs ml-1" style={{ color: 'var(--color-text-muted)' }}>{t('ai.generating')}</span>
              </div>
            )}
          </div>

          {/* Markdown content */}
          <div className="p-5 prose prose-sm max-w-none">
            <div style={{ color: 'var(--color-text-primary)' }}>
              <ReactMarkdown>{report}</ReactMarkdown>
            </div>
            {isGenerating && (
              <span className="inline-block w-0.5 h-4 animate-pulse align-text-bottom ml-0.5" style={{ backgroundColor: 'var(--color-mine-blue)' }} />
            )}
          </div>
        </div>
      )}

      {/* Action buttons (after completion) */}
      {isComplete && (
        <div className="flex gap-3 justify-end">
          <button
            onClick={handleCopy}
            className="px-4 py-2.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            {t('ai.copy')}
          </button>
          <button
            onClick={handleDownload}
            className="px-4 py-2.5 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
            style={{ backgroundColor: 'var(--color-mine-blue)' }}
          >
            {t('ai.download')}
          </button>
        </div>
      )}
    </div>
  );
}
