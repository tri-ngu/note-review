export interface EditDraft {
  options: [string, string, string, string];
  correct_answers: number[];
  is_select_all: boolean;
  page_number: number;
}

export interface EditErrors {
  options?: string;
  correct_answers?: string;
  page_number?: string;
}

export function validateEdit(draft: EditDraft): EditErrors {
  const errors: EditErrors = {};

  if (draft.options.some((opt) => opt.trim() === '')) {
    errors.options = 'All 4 options must be filled in.';
  }

  const count = draft.correct_answers.length;
  if (draft.is_select_all) {
    if (count < 1 || count > 4) {
      errors.correct_answers = 'Select-All needs 1 to 4 correct answers marked.';
    }
  } else if (count !== 1) {
    errors.correct_answers = 'Multiple-Choice needs exactly 1 correct answer marked.';
  }

  if (!Number.isInteger(draft.page_number) || draft.page_number < 1) {
    errors.page_number = 'Page number must be a positive whole number.';
  }

  return errors;
}

export function hasEditErrors(errors: EditErrors): boolean {
  return Object.keys(errors).length > 0;
}
