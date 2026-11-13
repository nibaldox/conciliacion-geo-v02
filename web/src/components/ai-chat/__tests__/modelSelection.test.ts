import { describe, expect, it } from 'vitest';
import type { AIProvidersState } from '../../../api/aiChat';
import {
  modelOptionLabel,
  resolveChatModelSelection,
  shouldClearSessionModel,
  type ChatModelSelection,
} from '../../../utils/chatModelSelection';

function providers(
  overrides: Partial<AIProvidersState> = {},
): AIProvidersState {
  return {
    providers: ['lmstudio'],
    supports_tool_calls: { lmstudio: true },
    chat_enabled: true,
    chat_provider: 'lmstudio',
    chat_local_only: true,
    chat_model: 'loaded-model',
    ...overrides,
  };
}

function okModels(
  ids: Array<{ id: string; tool_use?: boolean | null }>,
  extra: Partial<AIProvidersState['chat_models']> = {},
): AIProvidersState['chat_models'] {
  return {
    status: 'ok',
    source: 'v1',
    models: ids.map((entry) => ({
      id: entry.id,
      label: entry.id,
      tool_use: entry.tool_use ?? true,
    })),
    selected: null,
    selected_source: null,
    ...extra,
  };
}

function selectionOf(
  state: AIProvidersState | null,
  sessionModel = '',
): ChatModelSelection {
  return resolveChatModelSelection(state, sessionModel);
}

describe('resolveChatModelSelection — legacy payloads', () => {
  it('keeps a concrete configured model without manual input', () => {
    const selection = selectionOf(providers({ chat_model: 'qwen3-32b' }));
    expect(selection).toEqual({
      kind: 'legacy',
      model: 'qwen3-32b',
      needsManual: false,
    });
  });

  it('keeps the placeholder manual flow when chat_models is absent', () => {
    const selection = selectionOf(providers(), '');
    expect(selection).toEqual({
      kind: 'legacy',
      model: 'loaded-model',
      needsManual: true,
    });
  });

  it('treats a missing provider state as the legacy placeholder flow', () => {
    expect(selectionOf(null)).toEqual({
      kind: 'legacy',
      model: 'loaded-model',
      needsManual: true,
    });
  });
});

describe('resolveChatModelSelection — detected models', () => {
  it('fixes the only loaded instance automatically', () => {
    const selection = selectionOf(
      providers({
        chat_model: 'alpha:2',
        chat_models: okModels(
          [{ id: 'alpha:2', tool_use: true }],
          { selected: 'alpha:2', selected_source: 'auto' },
        ),
      }),
    );
    expect(selection).toEqual({
      kind: 'fixed',
      model: 'alpha:2',
      toolUse: true,
    });
  });

  it('exposes tool_use=false for an honest no-tools warning', () => {
    const selection = selectionOf(
      providers({
        chat_model: 'alpha',
        chat_models: okModels(
          [{ id: 'alpha', tool_use: false }],
          { selected: 'alpha', selected_source: 'auto' },
        ),
      }),
    );
    expect(selection).toMatchObject({ kind: 'fixed', toolUse: false });
  });

  it('requires an explicit pick between several loaded models', () => {
    const state = providers({
      chat_models: okModels([{ id: 'alpha' }, { id: 'beta' }]),
    });
    expect(selectionOf(state)).toEqual({
      kind: 'pick',
      models: state.chat_models!.models,
      model: null,
      toolUse: null,
    });
    expect(selectionOf(state, 'beta')).toMatchObject({
      kind: 'pick',
      model: 'beta',
      toolUse: true,
    });
  });

  it('never accepts a session value outside the detected list', () => {
    const state = providers({
      chat_models: okModels([{ id: 'alpha' }, { id: 'beta' }]),
    });
    expect(selectionOf(state, 'ghost')).toMatchObject({
      kind: 'pick',
      model: null,
    });
  });

  it('reports zero loaded models as unresolved (no random pick)', () => {
    expect(selectionOf(providers({ chat_models: okModels([]) }))).toMatchObject({
      kind: 'unresolved',
      status: 'ok',
      needsManual: true,
      models: [],
    });
  });

  it('reports a disconnected server as unresolved, not configured', () => {
    expect(
      selectionOf(
        providers({
          chat_models: {
            status: 'unavailable',
            source: null,
            models: [],
            selected: null,
            selected_source: null,
          },
        }),
      ),
    ).toMatchObject({ kind: 'unresolved', status: 'unavailable' });
  });

  it('uses the override as a fixed model even with several loaded', () => {
    const selection = selectionOf(
      providers({
        chat_model: 'server-pinned',
        chat_models: okModels([{ id: 'alpha' }, { id: 'beta' }], {
          selected: 'server-pinned',
          selected_source: 'override',
        }),
      }),
      'beta',
    );
    expect(selection).toEqual({
      kind: 'fixed',
      model: 'server-pinned',
      toolUse: null,
    });
  });

  it('accepts an explicit manual id only when discovery has no answer', () => {
    const state = providers({
      chat_models: {
        status: 'unavailable',
        source: null,
        models: [],
        selected: null,
        selected_source: null,
      },
    });
    expect(selectionOf(state, '  typed-model  ')).toMatchObject({
      kind: 'unresolved',
      needsManual: false,
      manual: 'typed-model',
    });
  });

  it('never treats the legacy placeholder as a fixed server selection', () => {
    const selection = selectionOf(
      providers({
        chat_model: 'loaded-model',
        chat_models: okModels([{ id: 'alpha' }, { id: 'beta' }], {
          selected: 'loaded-model',
          selected_source: 'override',
        }),
      }),
    );
    expect(selection).toMatchObject({ kind: 'pick', model: null });
  });
});

describe('modelOptionLabel — duplicate labels stay distinguishable', () => {
  it('appends the instance id when a label repeats', () => {
    const models = [
      { id: 'alpha:1', label: 'Alpha', tool_use: true },
      { id: 'alpha:2', label: 'Alpha', tool_use: true },
      { id: 'beta', label: 'Beta', tool_use: true },
    ];
    expect(modelOptionLabel(models[0], models)).toBe('Alpha (alpha:1)');
    expect(modelOptionLabel(models[1], models)).toBe('Alpha (alpha:2)');
    expect(modelOptionLabel(models[2], models)).toBe('Beta');
  });

  it('falls back to the id when there is no human label', () => {
    const models = [{ id: 'alpha:1', label: null, tool_use: true }];
    expect(modelOptionLabel(models[0], models)).toBe('alpha:1');
  });
});

describe('shouldClearSessionModel — stale detected values vs manual input', () => {
  const detectedPick = (
    state: AIProvidersState,
  ): ChatModelSelection =>
    resolveChatModelSelection(state, 'alpha');

  it('clears a detected choice once discovery fixes the only loaded model', () => {
    const selection = resolveChatModelSelection(
      providers({
        chat_model: 'beta',
        chat_models: okModels([{ id: 'beta' }], {
          selected: 'beta',
          selected_source: 'auto',
        }),
      }),
      'alpha',
    );
    expect(shouldClearSessionModel(selection, 'detected')).toBe(true);
  });

  it('clears a detected choice when the authoritative list is empty', () => {
    const selection = resolveChatModelSelection(
      providers({ chat_models: okModels([]) }),
      'alpha',
    );
    expect(shouldClearSessionModel(selection, 'detected')).toBe(true);
  });

  it('keeps a valid manual entry when discovery reports an empty list', () => {
    const selection = resolveChatModelSelection(
      providers({ chat_models: okModels([]) }),
      'typed-model',
    );
    expect(shouldClearSessionModel(selection, 'manual')).toBe(false);
  });

  it('keeps a manual entry when discovery cannot answer', () => {
    const selection = resolveChatModelSelection(
      providers({
        chat_models: {
          status: 'unavailable',
          source: null,
          models: [],
          selected: null,
          selected_source: null,
        },
      }),
      'typed-model',
    );
    expect(shouldClearSessionModel(selection, 'manual')).toBe(false);
  });

  it('clears a detected choice that is no longer in the list', () => {
    const selection = detectedPick(
      providers({ chat_models: okModels([{ id: 'beta' }, { id: 'gamma' }]) }),
    );
    expect(shouldClearSessionModel(selection, 'detected')).toBe(true);
  });

  it('keeps a detected choice that is still in the list', () => {
    const selection = detectedPick(
      providers({
        chat_models: okModels([{ id: 'alpha' }, { id: 'gamma' }]),
      }),
    );
    expect(shouldClearSessionModel(selection, 'detected')).toBe(false);
  });

  it('clears a detected value when discovery becomes unavailable', () => {
    const selection = resolveChatModelSelection(
      providers({
        chat_models: {
          status: 'unavailable',
          source: null,
          models: [],
          selected: null,
          selected_source: null,
        },
      }),
      'alpha',
    );
    expect(shouldClearSessionModel(selection, 'detected')).toBe(true);
  });
});
