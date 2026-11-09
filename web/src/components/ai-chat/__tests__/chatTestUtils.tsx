import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from 'i18next';
import { I18nextProvider, initReactI18next } from 'react-i18next';
import { type ReactElement } from 'react';
import { render } from '@testing-library/react';
import es from '../../../locales/es.json';
import en from '../../../locales/en.json';

let initialized = false;

export function initChatI18n(): typeof i18n {
  if (!initialized) {
    void i18n.use(initReactI18next).init({
      lng: 'es',
      fallbackLng: 'es',
      supportedLngs: ['es', 'en'],
      resources: {
        es: { translation: es },
        en: { translation: en },
      },
      interpolation: { escapeValue: false },
    });
    initialized = true;
  }
  return i18n;
}

export function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={initChatI18n()}>{ui}</I18nextProvider>
    </QueryClientProvider>,
  );
}

export function makeNdjsonResponse(
  lines: string[],
  { conversationId }: { conversationId?: string } = {},
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const line of lines) controller.enqueue(encoder.encode(`${line}\n`));
      controller.close();
    },
  });
  const headers: Record<string, string> = {
    'Content-Type': 'application/x-ndjson',
  };
  if (conversationId) headers['X-Conversation-Id'] = conversationId;
  return new Response(stream, { status: 200, headers });
}

export const CHAT_TEXT_DONE = [
  '{"type":"text","content":"Hola, ¿en qué te ayudo?"}',
  '{"type":"done","finish_reason":"stop","usage":null,"cached":false}',
];
