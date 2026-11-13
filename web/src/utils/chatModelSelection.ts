/**
 * Pure model-selection logic for the chat panel.
 *
 * The backend (`GET /ai/providers.chat_models`) is the only authority on
 * what is loaded; this module never invents an id and never falls back
 * to a random model. Four outcomes:
 *
 * - `fixed`: a concrete id the server chose (env override or the single
 *   loaded instance) — the user cannot change it.
 * - `pick`: several loaded instances; the user must choose one of THESE
 *   ids (a free-text value outside the list is never accepted).
 * - `unresolved`: discovery has no usable answer (nothing loaded, server
 *   unreachable, unsupported endpoint). A manual id is allowed but never
 *   prefilled.
 * - `legacy`: older backend without `chat_models`; keep the historical
 *   placeholder flow byte for byte.
 */
import {
  LMSTUDIO_PLACEHOLDER_MODEL,
  type AIModelEntry,
  type AIModelsStatus,
  type AIProvidersState,
} from '../api/aiChat';

/** Where the current session model came from. */
export type SessionModelSource = 'none' | 'manual' | 'detected';

export type ChatModelSelection =
  | { kind: 'fixed'; model: string; toolUse: boolean | null }
  | {
      kind: 'pick';
      models: AIModelEntry[];
      model: string | null;
      toolUse: boolean | null;
    }
  | {
      kind: 'unresolved';
      status: AIModelsStatus;
      manual: string;
      needsManual: boolean;
      models: AIModelEntry[];
    }
  | { kind: 'legacy'; model: string; needsManual: boolean };

export function resolveChatModelSelection(
  providerState: AIProvidersState | null,
  sessionModel: string,
): ChatModelSelection {
  const manual = sessionModel.trim();
  if (!providerState) {
    return {
      kind: 'legacy',
      model: LMSTUDIO_PLACEHOLDER_MODEL,
      needsManual: true,
    };
  }
  const modelsState = providerState.chat_models;
  if (!modelsState) {
    const model = providerState.chat_model;
    return {
      kind: 'legacy',
      model,
      needsManual: model === LMSTUDIO_PLACEHOLDER_MODEL,
    };
  }
  if (
    modelsState.selected_source === 'override' &&
    modelsState.selected &&
    modelsState.selected !== LMSTUDIO_PLACEHOLDER_MODEL
  ) {
    const match = modelsState.models.find(
      (entry) => entry.id === modelsState.selected,
    );
    return {
      kind: 'fixed',
      model: modelsState.selected,
      toolUse: match?.tool_use ?? null,
    };
  }
  if (modelsState.status === 'ok') {
    if (modelsState.models.length === 1) {
      const entry = modelsState.models[0];
      return { kind: 'fixed', model: entry.id, toolUse: entry.tool_use ?? null };
    }
    if (modelsState.models.length > 1) {
      const chosen =
        modelsState.models.find((entry) => entry.id === manual) ?? null;
      return {
        kind: 'pick',
        models: modelsState.models,
        model: chosen?.id ?? null,
        toolUse: chosen?.tool_use ?? null,
      };
    }
  }
  return {
    kind: 'unresolved',
    status: modelsState.status,
    manual,
    needsManual: manual.length === 0,
    models: modelsState.models,
  };
}

/**
 * Human label for a `<option>`; repeated display names get the unique
 * instance id appended so two loaded instances can never look equal.
 */
export function modelOptionLabel(
  model: AIModelEntry,
  models: AIModelEntry[],
): string {
  const label = model.label?.trim();
  if (!label || label === model.id) return model.id;
  const duplicated = models.some(
    (other) => other.id !== model.id && other.label?.trim() === label,
  );
  return duplicated ? `${label} (${model.id})` : label;
}

/**
 * Whether a stored session model must be dropped after a refresh.
 *
 * A value the UI itself detected (auto selection or a pick from the
 * detected list) is only valid while discovery still reports it: it is
 * cleared on an authoritative empty list, on any non-ok status and when
 * the list no longer contains it. A MANUALLY typed id is the documented
 * escape hatch and survives an empty/unknown discovery state; only a
 * server-fixed model makes it irrelevant.
 */
export function shouldClearSessionModel(
  selection: ChatModelSelection,
  source: SessionModelSource,
): boolean {
  if (source === 'none') return false;
  if (selection.kind === 'fixed') return true;
  if (source === 'manual') return false;
  if (selection.kind === 'pick') return selection.model === null;
  if (selection.kind === 'unresolved') {
    return selection.status !== 'ok' || selection.models.length === 0;
  }
  return false;
}
