import { describe, it, expect } from 'vitest';
import {
  isConfirmationRequiredEvent,
  isDoneEvent,
  isErrorEvent,
  isTextEvent,
  isToolCallEvent,
  isToolResultEvent,
  parseAgentEventLine,
  type AgentEvent,
  type AgentFinishReason,
} from './agentChat.ts';

const NDJSON_FIXTURE = [
  '{"type":"text","content":"Voy a generar 78 secciones…"}',
  '{"type":"tool_call","invocation_id":"inv_abc","name":"generate_sections_auto","args":{"start":[0.0,0.0],"end":[400.0,250.0],"n_sections":10},"requires_confirmation":false}',
  '{"type":"tool_result","invocation_id":"inv_abc","name":"generate_sections_auto","ok":true,"summary":"78 secciones creadas","duration_ms":1200.5,"error":null}',
  '{"type":"confirmation_required","invocation_id":"inv_def","name":"run_reconciliation","args_summary":"Procesar 78 secciones (sobrescribe 78 resultados existentes)"}',
  '{"type":"error","content":"Proveedor sin soporte de herramientas"}',
  '{"type":"done","finish_reason":"stop","usage":{"prompt_tokens":812,"completion_tokens":64,"total_tokens":876,"is_synthetic":false,"duration_ms":2431.2,"cost_usd":null},"cached":false}',
].join('\n');

function parseFixture(): AgentEvent[] {
  return NDJSON_FIXTURE.split('\n').map((line) => parseAgentEventLine(line) as AgentEvent);
}

describe('parseAgentEventLine', () => {
  it('parses every event type of the contract fixture', () => {
    const events = parseFixture();
    expect(events.map((event) => event.type)).toEqual([
      'text',
      'tool_call',
      'tool_result',
      'confirmation_required',
      'error',
      'done',
    ]);
  });

  it('parses the text event', () => {
    const [event] = parseFixture();
    if (!isTextEvent(event)) throw new Error('expected text event');
    expect(event.content).toContain('78 secciones');
  });

  it('parses the tool_call event with args and confirmation flag', () => {
    const event = parseFixture()[1];
    if (!isToolCallEvent(event)) throw new Error('expected tool_call event');
    expect(event.invocation_id).toBe('inv_abc');
    expect(event.name).toBe('generate_sections_auto');
    expect(event.args).toEqual({
      start: [0.0, 0.0],
      end: [400.0, 250.0],
      n_sections: 10,
    });
    expect(event.requires_confirmation).toBe(false);
  });

  it('parses the tool_result event', () => {
    const event = parseFixture()[2];
    if (!isToolResultEvent(event)) throw new Error('expected tool_result event');
    expect(event.invocation_id).toBe('inv_abc');
    expect(event.ok).toBe(true);
    expect(event.summary).toBe('78 secciones creadas');
    expect(event.duration_ms).toBeCloseTo(1200.5);
    expect(event.error).toBeNull();
  });

  it('parses the confirmation_required event', () => {
    const event = parseFixture()[3];
    if (!isConfirmationRequiredEvent(event)) {
      throw new Error('expected confirmation_required event');
    }
    expect(event.invocation_id).toBe('inv_def');
    expect(event.name).toBe('run_reconciliation');
    expect(event.args_summary).toContain('sobrescribe 78 resultados');
  });

  it('parses the error event', () => {
    const event = parseFixture()[4];
    if (!isErrorEvent(event)) throw new Error('expected error event');
    expect(event.content).toContain('sin soporte');
  });

  it('parses the done event with usage', () => {
    const event = parseFixture()[5];
    if (!isDoneEvent(event)) throw new Error('expected done event');
    expect(event.finish_reason).toBe<AgentFinishReason>('stop');
    expect(event.usage).toEqual({
      prompt_tokens: 812,
      completion_tokens: 64,
      total_tokens: 876,
      is_synthetic: false,
      duration_ms: 2431.2,
      cost_usd: null,
    });
    expect(event.cached).toBe(false);
  });

  it('parses a done event with null usage and cached=true', () => {
    const event = parseAgentEventLine(
      '{"type":"done","finish_reason":"confirmation_required","usage":null,"cached":true}',
    );
    if (event === null || !isDoneEvent(event)) throw new Error('expected done event');
    expect(event.finish_reason).toBe('confirmation_required');
    expect(event.usage).toBeNull();
    expect(event.cached).toBe(true);
  });

  it('returns null for invalid lines without throwing', () => {
    expect(parseAgentEventLine('')).toBeNull();
    expect(parseAgentEventLine('   ')).toBeNull();
    expect(parseAgentEventLine('not json {')).toBeNull();
    expect(parseAgentEventLine('[]')).toBeNull();
    expect(parseAgentEventLine('null')).toBeNull();
    expect(parseAgentEventLine('"plain string"')).toBeNull();
    expect(parseAgentEventLine('{"type":"unknown_event","x":1}')).toBeNull();
  });

  it('round-trips events through JSON.stringify', () => {
    const events = parseFixture();
    for (const event of events) {
      const line = JSON.stringify(event);
      expect(parseAgentEventLine(line)).toEqual(event);
    }
  });
});

describe('type guards', () => {
  const events = parseFixture();

  it('narrow exactly one variant per guard', () => {
    expect(isTextEvent(events[0])).toBe(true);
    expect(isToolCallEvent(events[1])).toBe(true);
    expect(isToolResultEvent(events[2])).toBe(true);
    expect(isConfirmationRequiredEvent(events[3])).toBe(true);
    expect(isErrorEvent(events[4])).toBe(true);
    expect(isDoneEvent(events[5])).toBe(true);
  });

  it('reject other variants', () => {
    for (const guard of [
      isTextEvent,
      isToolCallEvent,
      isToolResultEvent,
      isConfirmationRequiredEvent,
      isErrorEvent,
      isDoneEvent,
    ]) {
      const matches = events.filter((event) => guard(event));
      expect(matches.length).toBeLessThanOrEqual(1);
    }
    expect(isTextEvent(events[4])).toBe(false);
    expect(isDoneEvent(events[0])).toBe(false);
  });
});
