/**
 * Typed NDJSON event protocol for the conversational AI agent.
 *
 * Exact TS mirror of `core/ai_v2/agent/events.py` (T0 contract freeze).
 * A stream is a sequence of JSON lines; each line parses into exactly
 * one `AgentEvent` variant, discriminated by `type`. A stream that asks
 * for confirmation ends in `confirmation_required` and is resumed by
 * POST /ai/chat/confirm, which emits its own NDJSON stream.
 */

export type AgentFinishReason = 'stop' | 'error' | 'confirmation_required';

export interface AgentUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  is_synthetic: boolean;
  duration_ms: number;
  cost_usd: number | null;
}

export interface AgentTextEvent {
  type: 'text';
  content: string;
}

export interface AgentToolCallEvent {
  type: 'tool_call';
  invocation_id: string;
  name: string;
  args: Record<string, unknown>;
  requires_confirmation: boolean;
}

export interface AgentToolResultEvent {
  type: 'tool_result';
  invocation_id: string;
  name: string;
  ok: boolean;
  summary: string;
  duration_ms: number;
  error: string | null;
}

export interface AgentConfirmationRequiredEvent {
  type: 'confirmation_required';
  invocation_id: string;
  name: string;
  args_summary: string;
}

export interface AgentErrorEvent {
  type: 'error';
  content: string;
}

export interface AgentDoneEvent {
  type: 'done';
  finish_reason: AgentFinishReason;
  usage: AgentUsage | null;
  cached: boolean;
}

export type AgentEvent =
  | AgentTextEvent
  | AgentToolCallEvent
  | AgentToolResultEvent
  | AgentConfirmationRequiredEvent
  | AgentErrorEvent
  | AgentDoneEvent;

export type AgentEventType = AgentEvent['type'];

const EVENT_TYPES: readonly AgentEventType[] = [
  'text',
  'tool_call',
  'tool_result',
  'confirmation_required',
  'error',
  'done',
];

export function isTextEvent(event: AgentEvent): event is AgentTextEvent {
  return event.type === 'text';
}

export function isToolCallEvent(event: AgentEvent): event is AgentToolCallEvent {
  return event.type === 'tool_call';
}

export function isToolResultEvent(event: AgentEvent): event is AgentToolResultEvent {
  return event.type === 'tool_result';
}

export function isConfirmationRequiredEvent(
  event: AgentEvent,
): event is AgentConfirmationRequiredEvent {
  return event.type === 'confirmation_required';
}

export function isErrorEvent(event: AgentEvent): event is AgentErrorEvent {
  return event.type === 'error';
}

export function isDoneEvent(event: AgentEvent): event is AgentDoneEvent {
  return event.type === 'done';
}

function isAgentEventShape(value: unknown): value is AgentEvent {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  return EVENT_TYPES.includes((value as { type?: unknown }).type as AgentEventType);
}

/**
 * Parse one NDJSON line into an AgentEvent.
 *
 * Fail-closed mirror of `parse_event_line`: unknown types, malformed
 * JSON and non-object payloads return `null` instead of throwing, so a
 * bad line never crashes the chat reader.
 */
export function parseAgentEventLine(line: string): AgentEvent | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (!isAgentEventShape(parsed)) return null;
  return parsed;
}
