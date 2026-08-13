import { useState } from 'react';
import type { Question } from '../types/question';
import { validateEdit, hasEditErrors, type EditErrors } from '../lib/validateEdit';
import { conceptCollides } from '../lib/renameConcept';
import styles from './QuestionEditForm.module.css';

interface QuestionEditFormProps {
  question: Question;
  otherConcepts: string[];
  onSave: (updated: Question, renameFrom?: string) => void;
  onCancel: () => void;
  saveError?: string | null;
  isSaving?: boolean;
}

type FormErrors = EditErrors & { concept?: string };

export function QuestionEditForm({ question, otherConcepts, onSave, onCancel, saveError, isSaving }: QuestionEditFormProps) {
  const [questionText, setQuestionText] = useState(question.question_text);
  const [options, setOptions] = useState<[string, string, string, string]>([...question.options]);
  const [correctAnswers, setCorrectAnswers] = useState<number[]>([...question.correct_answers]);
  const [isSelectAll, setIsSelectAll] = useState(question.is_select_all);
  const [explanation, setExplanation] = useState(question.explanation);
  const [pageNumberInput, setPageNumberInput] = useState(String(question.page_number));
  const [conceptRename, setConceptRename] = useState(question.concept);
  const [conceptReassign, setConceptReassign] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});

  const setOptionText = (i: number, value: string) => {
    setOptions((opts) => opts.map((o, idx) => (idx === i ? value : o)) as [string, string, string, string]);
  };

  const toggleCorrect = (optionNumber: number) => {
    setCorrectAnswers((prev) => {
      if (isSelectAll) {
        return prev.includes(optionNumber) ? prev.filter((n) => n !== optionNumber) : [...prev, optionNumber];
      }
      return [optionNumber];
    });
  };

  const handleRenameChange = (value: string) => {
    setConceptRename(value);
    setConceptReassign('');
  };

  const handleReassignChange = (value: string) => {
    setConceptReassign(value);
    setConceptRename(question.concept);
  };

  const handleSave = () => {
    const pageNumber = Number(pageNumberInput);
    const nextErrors: FormErrors = validateEdit({
      options,
      correct_answers: correctAnswers,
      is_select_all: isSelectAll,
      page_number: pageNumber,
    });

    let finalConcept = question.concept;
    let renameFrom: string | undefined;

    if (conceptReassign) {
      finalConcept = conceptReassign;
    } else if (conceptRename.trim() !== question.concept) {
      const trimmed = conceptRename.trim();
      if (trimmed === '') {
        nextErrors.concept = 'Concept name cannot be empty.';
      } else if (conceptCollides(otherConcepts, trimmed)) {
        nextErrors.concept = `"${trimmed}" is already used by a different concept.`;
      } else {
        finalConcept = trimmed;
        renameFrom = question.concept;
      }
    }

    if (hasEditErrors(nextErrors)) {
      setErrors(nextErrors);
      return;
    }

    onSave(
      {
        ...question,
        question_text: questionText,
        options,
        correct_answers: correctAnswers as (1 | 2 | 3 | 4)[],
        is_select_all: isSelectAll,
        explanation,
        page_number: pageNumber,
        concept: finalConcept,
      },
      renameFrom,
    );
  };

  return (
    <div className={styles.editForm}>
      <label className={styles.field}>
        <span className={styles.label}>Question</span>
        <textarea className={styles.textarea} value={questionText} onChange={(e) => setQuestionText(e.target.value)} rows={3} />
      </label>

      <div className={styles.field}>
        <span className={styles.label}>Type</span>
        <div className={styles.typeToggle}>
          <label>
            <input type="radio" name="question-type" checked={!isSelectAll} onChange={() => setIsSelectAll(false)} />
            Multiple-Choice
          </label>
          <label>
            <input type="radio" name="question-type" checked={isSelectAll} onChange={() => setIsSelectAll(true)} />
            Select-All
          </label>
        </div>
      </div>

      <div className={styles.field}>
        <span className={styles.label}>Options (mark correct)</span>
        {options.map((option, i) => {
          const optionNumber = i + 1;
          return (
            <div className={styles.optionRow} key={i}>
              <input
                type={isSelectAll ? 'checkbox' : 'radio'}
                name="edit-correct"
                checked={correctAnswers.includes(optionNumber)}
                onChange={() => toggleCorrect(optionNumber)}
              />
              <input className={styles.optionInput} value={option} onChange={(e) => setOptionText(i, e.target.value)} />
            </div>
          );
        })}
        {errors.options && <p className={styles.error}>{errors.options}</p>}
        {errors.correct_answers && <p className={styles.error}>{errors.correct_answers}</p>}
      </div>

      <label className={styles.field}>
        <span className={styles.label}>Explanation</span>
        <textarea className={styles.textarea} value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={2} />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Page number</span>
        <input
          className={styles.numberInput}
          type="number"
          value={pageNumberInput}
          onChange={(e) => setPageNumberInput(e.target.value)}
        />
        {errors.page_number && <p className={styles.error}>{errors.page_number}</p>}
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Rename concept</span>
        <input className={styles.textInput} value={conceptRename} onChange={(e) => handleRenameChange(e.target.value)} />
      </label>

      <label className={styles.field}>
        <span className={styles.label}>Move to existing concept</span>
        <select
          className={styles.select}
          value={conceptReassign}
          onChange={(e) => handleReassignChange(e.target.value)}
          disabled={otherConcepts.length === 0}
        >
          <option value="">— keep current concept —</option>
          {otherConcepts.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
      {errors.concept && <p className={styles.error}>{errors.concept}</p>}
      {saveError && <p className={styles.error}>{saveError}</p>}

      <div className={styles.actions}>
        <button className={styles.saveBtn} onClick={handleSave} disabled={isSaving}>
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button className={styles.cancelBtn} onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
      </div>
    </div>
  );
}
