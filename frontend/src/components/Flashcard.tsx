import { useState, type KeyboardEvent } from 'react';
import type { Question } from '../types/question';
import { trimConcept } from '../lib/trimConcept';
import { QuestionEditForm } from './QuestionEditForm';
import styles from './Flashcard.module.css';

interface FlashcardProps {
  question: Question;
  otherConcepts: string[];
  onSave: (updated: Question, renameFrom?: string) => void;
  onEditingChange: (isEditing: boolean) => void;
}

export function Flashcard({ question, otherConcepts, onSave, onEditingChange }: FlashcardProps) {
  const [isFlipped, setIsFlipped] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const toggleFlip = () => {
    if (isEditing) return;
    setIsFlipped((f) => !f);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (isEditing) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleFlip();
    }
  };

  const startEditing = () => {
    setIsEditing(true);
    onEditingChange(true);
  };

  const handleSave = (updated: Question, renameFrom?: string) => {
    onSave(updated, renameFrom);
    setIsEditing(false);
    onEditingChange(false);
  };

  const handleCancel = () => {
    setIsEditing(false);
    onEditingChange(false);
  };

  const cardClass = [styles.card, isFlipped ? styles.isFlipped : '', question.is_select_all ? styles.isSa : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={cardClass}
      tabIndex={isEditing ? undefined : 0}
      role={isEditing ? undefined : 'button'}
      aria-label={isEditing ? undefined : 'Flip card'}
      onClick={isEditing ? undefined : toggleFlip}
      onKeyDown={isEditing ? undefined : handleKeyDown}
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
            {isEditing ? (
              <QuestionEditForm question={question} otherConcepts={otherConcepts} onSave={handleSave} onCancel={handleCancel} />
            ) : (
              <>
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
                <button
                  className={styles.editBtn}
                  onClick={(e) => {
                    e.stopPropagation();
                    startEditing();
                  }}
                >
                  revise plate
                </button>
                <div className={styles.cardFooter}>page {question.page_number}</div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
