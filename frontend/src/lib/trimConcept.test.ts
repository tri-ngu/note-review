import { describe, expect, it } from 'vitest';
import { trimConcept } from './trimConcept';

describe('trimConcept', () => {
  it('splits on a colon', () => {
    expect(trimConcept('Blood Vessels: structure, operations and significance')).toBe('Blood Vessels');
  });

  it('splits on an em dash', () => {
    expect(trimConcept('Water Cycle — evaporation and condensation')).toBe('Water Cycle');
  });

  it('splits on a hyphen', () => {
    expect(trimConcept('Muscle Types - cardiac, smooth, skeletal')).toBe('Muscle Types');
  });

  it('splits on a comma', () => {
    expect(trimConcept('Bone Types, long and flat')).toBe('Bone Types');
  });

  it('uses whichever delimiter occurs first', () => {
    expect(trimConcept('Precipitation, forms - rain and snow')).toBe('Precipitation');
  });

  it('returns the full string untrimmed when no delimiter is present', () => {
    expect(trimConcept('Transpiration')).toBe('Transpiration');
  });
});
