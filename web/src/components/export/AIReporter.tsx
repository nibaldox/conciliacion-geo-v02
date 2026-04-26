import { useState, useRef, useCallback, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { useAIProviders, useAIModels } from '../../api/hooks';

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
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h4 className="text-sm font-semibold text-gray-800 mb-3">
          Configuración del Modelo IA
        </h4>

        {/* Provider toggle */}
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Proveedor
            </label>
            <div className="flex rounded-lg border border-gray-300 overflow-hidden">
              {(['ollama', 'lmstudio'] as AIProvider[]).map((prov) => {
                const available = prov === 'ollama' ? ollamaAvailable : lmstudioAvailable;
                const loading = providersLoading;
                return (
                  <button
                    key={prov}
                    onClick={() => handleProviderChange(prov)}
                    className={`
                      flex-1 px-3 py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5
                      ${options.provider === prov
                        ? 'bg-mine-blue text-white'
                        : 'bg-white text-gray-600 hover:bg-gray-50'
                      }
                    `}
                  >
                    <span
                      className={`inline-block w-2 h-2 rounded-full ${loading ? 'bg-gray-300 animate-pulse' : available ? 'bg-green-400' : 'bg-red-400'}`}
                      title={loading ? 'Detectando...' : available ? 'Disponible' : 'No disponible'}
                    />
                    {PROVIDER_LABELS[prov]}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Model selector */}
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Modelo
            </label>
            <select
              value={options.model}
              onChange={(e) => setOptions((prev) => ({ ...prev, model: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white
                         focus:ring-2 focus:ring-mine-blue/20 focus:border-mine-blue outline-none"
            >
              {detectedModels.length > 0 ? (
                detectedModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))
              ) : (
                <option value="">
                  {providersLoading ? 'Cargando modelos...' : 'Sin modelos detectados'}
                </option>
              )}
            </select>
          </div>

          {/* Generate button */}
          <div>
            {!isGenerating ? (
              <button
                onClick={handleGenerate}
                disabled={!anyProviderAvailable || !options.model}
                className="px-5 py-2.5 bg-gradient-to-r from-mine-blue to-blue-600 text-white rounded-lg
                           text-sm font-semibold shadow-md hover:shadow-lg transition-all
                           hover:scale-[1.02] active:scale-[0.98] flex items-center gap-2
                           disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-md"
              >
                <span>✨</span>
                Generar Informe con IA
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="px-5 py-2.5 bg-red-500 text-white rounded-lg
                           text-sm font-semibold hover:bg-red-600 transition-colors
                           flex items-center gap-2"
              >
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Detener
              </button>
            )}
          </div>
        </div>

        {/* No providers available — install instructions */}
        {!anyProviderAvailable && !providersLoading && (
          <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
            <p className="font-semibold mb-2">No se detectaron proveedores de IA locales.</p>
            <p className="mb-1">Instala al menos uno para generar informes:</p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>
                <strong>Ollama:</strong>{' '}
                <code className="bg-amber-100 px-1.5 py-0.5 rounded text-xs">
                  curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.1:8b
                </code>
              </li>
              <li>
                <strong>LM Studio:</strong>{' '}
                Descarga desde{' '}
                <a href="https://lmstudio.ai" target="_blank" rel="noopener noreferrer" className="underline">
                  lmstudio.ai
                </a>{' '}
                y habilita el servidor local.
              </li>
            </ul>
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center justify-between">
          <p className="text-sm text-red-600 font-medium">{error}</p>
          <button
            onClick={handleRetry}
            className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs font-medium
                       hover:bg-red-600 transition-colors"
          >
            Reintentar
          </button>
        </div>
      )}

      {/* Report display */}
      {(hasContent || isGenerating) && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          {/* Header */}
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-800">
              Informe Generado
            </h4>
            {isGenerating && (
              <div className="flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 bg-mine-blue rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="inline-block w-1.5 h-1.5 bg-mine-blue rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="inline-block w-1.5 h-1.5 bg-mine-blue rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                <span className="text-xs text-gray-500 ml-1">Generando...</span>
              </div>
            )}
          </div>

          {/* Markdown content */}
          <div className="p-5 prose prose-sm max-w-none prose-headings:text-gray-800 prose-p:text-gray-700 prose-li:text-gray-700">
            <ReactMarkdown>{report}</ReactMarkdown>
            {isGenerating && (
              <span className="inline-block w-0.5 h-4 bg-mine-blue animate-pulse align-text-bottom ml-0.5" />
            )}
          </div>
        </div>
      )}

      {/* Action buttons (after completion) */}
      {isComplete && (
        <div className="flex gap-3 justify-end">
          <button
            onClick={handleCopy}
            className="px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-600
                       hover:bg-gray-50 transition-colors flex items-center gap-2"
          >
            📋 Copiar al portapapeles
          </button>
          <button
            onClick={handleDownload}
            className="px-4 py-2.5 bg-mine-blue text-white rounded-lg text-sm font-medium
                       hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            💾 Descargar
          </button>
        </div>
      )}
    </div>
  );
}
