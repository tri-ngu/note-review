import { useState } from 'react';
import type { Question, QuestionSet } from '../types/question';
import { distinctConcepts } from '../lib/renameConcept';
import { Flashcard } from './Flashcard';
import styles from './FlashcardView.module.css';

interface FlashcardViewProps {
  questionSet: QuestionSet;
  onStartReview: () => void;
  onUpdateQuestion: (index: number, updated: Question, renameFrom?: string) => void;
}

export function FlashcardView({ questionSet, onStartReview, onUpdateQuestion }: FlashcardViewProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isEditing, setIsEditing] = useState(false);
  const total = questionSet.questions.length;
  const current = questionSet.questions[currentIndex];

  const goPrev = () => setCurrentIndex((i) => Math.max(0, i - 1));
  const goNext = () => setCurrentIndex((i) => Math.min(total - 1, i + 1));

  return (
    <main className={styles.theme}>
      <div className={styles.cardStage}>
        <Flashcard
          key={currentIndex}
          question={current}
          otherConcepts={distinctConcepts(questionSet.questions, current.concept)}
          onSave={(updated, renameFrom) => onUpdateQuestion(currentIndex, updated, renameFrom)}
          onEditingChange={setIsEditing}
        />
        <p className={styles.flipHint}>Click to flip card</p>
        <div className={styles.cardNav}>
          <button className={styles.navBtn} onClick={goPrev} disabled={isEditing || currentIndex === 0}>
            ‹ prior
          </button>
          <span className={styles.progress}>
            Card {currentIndex + 1} of {total}
          </span>
          <button className={styles.navBtn} onClick={goNext} disabled={isEditing || currentIndex === total - 1}>
            next ›
          </button>
        </div>
        <button className={styles.startReviewBtn} onClick={onStartReview} disabled={isEditing}>
          Start Review
        </button>
      </div>
    </main>
  );
}
