const DELIMITERS = /[:—,-]/;

export function trimConcept(concept: string): string {
  const index = concept.search(DELIMITERS);
  if (index === -1) return concept;
  return concept.slice(0, index).trim();
}
