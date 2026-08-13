import { describe, expect, it } from 'vitest';
import { parseSseBuffer } from './sseParse';

describe('parseSseBuffer', () => {
  it('parses a single complete event with no remainder', () => {
    const result = parseSseBuffer<{ stage: string }>('data: {"stage":"done"}\n\n');
    expect(result).toEqual({ events: [{ stage: 'done' }], remainder: '' });
  });

  it('parses multiple complete events in one buffer', () => {
    const buffer = 'data: {"stage":"a"}\n\ndata: {"stage":"b"}\n\n';
    const result = parseSseBuffer<{ stage: string }>(buffer);
    expect(result.events).toEqual([{ stage: 'a' }, { stage: 'b' }]);
    expect(result.remainder).toBe('');
  });

  it('keeps a trailing incomplete event as remainder', () => {
    const buffer = 'data: {"stage":"a"}\n\ndata: {"stage":"b"';
    const result = parseSseBuffer<{ stage: string }>(buffer);
    expect(result.events).toEqual([{ stage: 'a' }]);
    expect(result.remainder).toBe('data: {"stage":"b"');
  });

  it('returns no events for an empty buffer', () => {
    expect(parseSseBuffer('')).toEqual({ events: [], remainder: '' });
  });
});
