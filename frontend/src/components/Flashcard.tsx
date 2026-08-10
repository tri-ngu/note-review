import { useState, type KeyboardEvent } from 'react';
import type { Question } from '../types/question';
import { trimConcept } from '../lib/trimConcept';
import styles from './Flashcard.module.css';

interface FlashcardProps {
  question: Question;
}

export function Flashcard({ question }: FlashcardProps) {
  const [isFlipped, setIsFlipped] = useState(false);

  const toggleFlip = () => setIsFlipped((f) => !f);

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleFlip();
    }
  };

  const cardClass = [styles.card, isFlipped ? styles.isFlipped : '', question.is_select_all ? styles.isSa : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={cardClass}
      tabIndex={0}
      role="button"
      aria-label="Flip card"
      onClick={toggleFlip}
      onKeyDown={handleKeyDown}
    >
      <div className={styles.cardInner}>
        <div className={`${styles.cardFace} ${styles.cardFront}`}>
          <div className={styles.qBody}>
            <p className={styles.qText}>{question.question_text}</p>
            <ul className={styles.options}>
              {question.options.map((option, i) => (
                <li key={i} className={styles.opt}>
                  <span className={styles.optMark} />
                  {option}
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className={`${styles.cardFace} ${styles.cardBack}`}>
          <div className={styles.qBody}>
            <p className={styles.qText}>{question.question_text}</p>
            <ul className={styles.options}>
              {question.options.map((option, i) => {
                const optionNumber = i + 1;
                const isCorrect = (question.correct_answers as number[]).includes(optionNumber);
                return (
                  <li key={i} className={isCorrect ? `${styles.opt} ${styles.correct}` : styles.opt}>
                    <span className={styles.optMark} />
                    {option}
                  </li>
                );
              })}
            </ul>
            <p className={styles.explanation}>{question.explanation}</p>
            <span className={styles.conceptTag}>{trimConcept(question.concept)}</span>
            <button className={styles.editBtn} disabled>
              revise plate
            </button>
            <div className={styles.cardFooter}>page {question.page_number}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
