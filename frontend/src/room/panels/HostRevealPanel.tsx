import styles from './HostRevealPanel.module.css';

interface HostRevealPanelProps {
  round: number;
  totalRounds: number;
  questionText: string;
  options: string[];
  correctAnswers: number[];
  explanation: string;
  onShowLeaderboard: () => void;
}

export function HostRevealPanel({
  round,
  totalRounds,
  questionText,
  options,
  correctAnswers,
  explanation,
  onShowLeaderboard,
}: HostRevealPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {round} of {totalRounds}
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
        <button className={styles.primaryBtn} onClick={onShowLeaderboard}>
          Show Leaderboard
        </button>
      </div>
    </main>
  );
}
