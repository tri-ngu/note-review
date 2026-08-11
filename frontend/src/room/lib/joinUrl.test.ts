import { describe, expect, it } from 'vitest';
import { buildJoinUrl } from './joinUrl';

describe('buildJoinUrl', () => {
  it('builds a join URL from an origin and PIN', () => {
    expect(buildJoinUrl('https://example.com', '0427')).toBe('https://example.com/join/0427');
  });

  it('works with a localhost dev origin', () => {
    expect(buildJoinUrl('http://localhost:5173', '9981')).toBe('http://localhost:5173/join/9981');
  });
});
