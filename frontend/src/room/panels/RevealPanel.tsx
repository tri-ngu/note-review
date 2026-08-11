import type { AnswerResult } from '../../types/room';
import styles from './RevealPanel.module.css';

interface RevealPanelProps {
  questionText: string;
  options: string[];
  correctAnswers: number[];
  explanation: string;
  result: AnswerResult | undefined;
}

export function RevealPanel({ questionText, options, correctAnswers, explanation, result }: RevealPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={result?.correct ? styles.correct : styles.incorrect}>
          {result?.correct ? 'Correct!' : 'Incorrect'}
          {result ? ` +${result.points} pts` : ''}
        </p>
        <h1 className={styles.questionText}>{questionText}</h1>
        <ul className={styles.optionList}>
          {options.map((option, i) => {
            const position = i + 1;
            const isCorrect = correctAnswers.includes(position);
            return (
              <li key={position} className={isCorrect ? styles.correctOption : styles.option}>
                {option}
              </li>
            );
          })}
        </ul>
        <p className={styles.explanation}>{explanation}</p>
      </div>
    </main>
  );
}
