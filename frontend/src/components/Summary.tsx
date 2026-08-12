import { useState } from 'react';
import type { Question } from '../types/question';
import { trimConcept } from '../lib/trimConcept';
import styles from './Summary.module.css';

interface QuestionResult {
  question: Question;
  selected: number[];
  correct: boolean;
}

interface SummaryProps {
  total: number;
  score: number;
  results: QuestionResult[];
  onRestart: () => void;
  onExit: () => void;
}

export function Summary({ total, score, results, onRestart, onExit }: SummaryProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const current = results[selectedIndex];

  return (
    <main className={styles.theme}>
      <div className={styles.layout}>
        <div className={styles.detailPanel}>
          <span className={styles.typeTag}>{current.question.is_select_all ? 'Select All' : 'Multiple Choice'}</span>
          <p className={styles.qText}>{current.question.question_text}</p>
          <ul className={styles.options}>
            {current.question.options.map((option, i) => {
              const optionNumber = i + 1;
              const isCorrect = (current.question.correct_answers as number[]).includes(optionNumber);
              const isSelected = current.selected.includes(optionNumber);
              const stateClass = isCorrect && isSelected ? styles.correct : isCorrect ? styles.correctMissed : isSelected ? styles.wrongSelected : '';
              return (
                <li key={i} className={[styles.opt, stateClass].filter(Boolean).join(' ')}>
                  <span className={styles.optMark} />
                  {option}
                </li>
              );
            })}
          </ul>
          <p className={styles.explanation}>{current.question.explanation}</p>
          <span className={styles.conceptTag}>{trimConcept(current.question.concept)}</span>
          <div className={styles.cardFooter}>page {current.question.page_number} in file.pdf</div>
        </div>
        <div className={styles.sidebar}>
          <p className={styles.score}>
            Score: {score}/{total}
          </p>
          <ul className={styles.questionList}>
            {results.map((r, i) => (
              <li key={i}>
                <button
                  type="button"
                  className={[styles.questionBtn, i === selectedIndex ? styles.active : '', r.correct ? styles.right : styles.wrong]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setSelectedIndex(i)}
                >
                  <span className={styles.resultMark}>{r.correct ? '✓' : '✗'}</span>
                  Question {i + 1}
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.actions}>
            <button className={styles.actionBtn} onClick={onRestart}>
              Review Again
            </button>
            <button className={styles.actionBtnSecondary} onClick={onExit}>
              Back to Cards
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
