import styles from './QuestionActivePanel.module.css';

interface QuestionActivePanelProps {
  round: number;
  totalRounds: number;
  answeredCount: { answered: number; total_connected: number } | null;
}

export function QuestionActivePanel({ round, totalRounds, answeredCount }: QuestionActivePanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {round} of {totalRounds}
        </p>
        <h1 className={styles.status}>Question in progress…</h1>
        <p className={styles.answeredCount}>
          {answeredCount ? `${answeredCount.answered} of ${answeredCount.total_connected} answered` : 'Waiting for answers…'}
        </p>
      </div>
    </main>
  );
}
