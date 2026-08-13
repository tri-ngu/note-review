export interface ConceptSnippet {
  quote: string;
  page_number: number;
}

export interface ConceptAllocation {
  concept: string;
  weight_percentage: number;
  question_count: number;
  snippets: ConceptSnippet[];
}
