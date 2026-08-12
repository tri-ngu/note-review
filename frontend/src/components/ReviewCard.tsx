import type { Question } from '../types/question';
import { trimConcept } from '../lib/trimConcept';
import styles from './ReviewCard.module.css';

interface ReviewCardProps {
  question: Question;
  groupName: string;
  selected: number[];
  submitted: boolean;
  onToggleOption: (optionNumber: number) => void;
  onSubmit: () => void;
}

export function ReviewCard({ question, groupName, selected, submitted, onToggleOption, onSubmit }: ReviewCardProps) {
  const cardClass = [styles.card, submitted ? styles.isFlipped : '', question.is_select_all ? styles.isSa : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cardClass}>
      <div className={styles.cardInner}>
        <div className={`${styles.cardFace} ${styles.cardFront}`}>
          <div className={styles.qBody}>
            <span className={styles.typeTag}>{question.is_select_all ? 'Select All' : 'Multiple Choice'}</span>
            <p className={styles.qText}>{question.question_text}</p>
            <ul className={styles.options}>
              {question.options.map((option, i) => {
                const optionNumber = i + 1;
                return (
                  <li key={i}>
                    <label className={styles.optLabel}>
                      <input
                        className={styles.optInput}
                        type={question.is_select_all ? 'checkbox' : 'radio'}
                        name={groupName}
                        checked={selected.includes(optionNumber)}
                        disabled={submitted}
                        onChange={() => onToggleOption(optionNumber)}
                      />
                      <span className={styles.optMark} />
                      {option}
                    </label>
                  </li>
                );
              })}
            </ul>
            <button className={styles.submitBtn} disabled={selected.length === 0 || submitted} onClick={onSubmit}>
              Submit
            </button>
          </div>
        </div>
        <div className={`${styles.cardFace} ${styles.cardBack}`}>
          <div className={styles.qBody}>
            <span className={styles.typeTag}>{question.is_select_all ? 'Select All' : 'Multiple Choice'}</span>
            <p className={styles.qText}>{question.question_text}</p>
            <ul className={styles.options}>
              {question.options.map((option, i) => {
                const optionNumber = i + 1;
                const isCorrect = (question.correct_answers as number[]).includes(optionNumber);
                const isSelected = selected.includes(optionNumber);
                const stateClass = isCorrect && isSelected ? styles.correct : isCorrect ? styles.correctMissed : isSelected ? styles.wrongSelected : '';
                return (
                  <li key={i} className={[styles.opt, stateClass].filter(Boolean).join(' ')}>
                    <span className={styles.optMark} />
                    {option}
                  </li>
                );
              })}
            </ul>
            <p className={styles.explanation}>{question.explanation}</p>
            <span className={styles.conceptTag}>{trimConcept(question.concept)}</span>
            <div className={styles.cardFooter}>page {question.page_number} in file.pdf</div>
          </div>
        </div>
      </div>
    </div>
  );
}
