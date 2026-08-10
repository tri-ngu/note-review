export interface Question {
  concept: string;
  question_text: string;
  options: [string, string, string, string];
  correct_answers: (1 | 2 | 3 | 4)[]; // 1-4 entries, not enforced at the type level
  is_select_all: boolean;
  explanation: string;
  page_number: number;
  source_quote: string;
}

export interface QuestionSet {
  questions: Question[];
}
