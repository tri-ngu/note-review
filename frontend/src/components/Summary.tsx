import type { Question } from '../types/question';
import styles from './Summary.module.css';

interface SummaryProps {
  total: number;
  score: number;
  missed: Question[];
  onRestart: () => void;
  onExit: () => void;
}

export function Summary({ total, score, missed, onRestart, onExit }: SummaryProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.panel}>
        <p className={styles.score}>
          Score: {score}/{total}
        </p>
        {missed.length > 0 && (
          <>
            <p className={styles.missedHeading}>Missed Questions</p>
            <ul className={styles.missedList}>
              {missed.map((q, i) => (
                <li key={i} className={styles.missedItem}>
                  <p className={styles.missedQuestion}>{q.question_text}</p>
                  <p className={styles.missedExplanation}>{q.explanation}</p>
                </li>
              ))}
            </ul>
          </>
        )}
        <div className={styles.actions}>
          <button className={styles.actionBtn} onClick={onRestart}>
            Review Again
          </button>
          <button className={styles.actionBtnSecondary} onClick={onExit}>
            Back to Cards
          </button>
        </div>
      </div>
    </main>
  );
}
