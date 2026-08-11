import { CountdownTimer } from './CountdownTimer';
import styles from './QuestionActivePanel.module.css';

const QUESTION_TIMEOUT_SECONDS = 30;

interface QuestionActivePanelProps {
  round: number;
  totalRounds: number;
  answeredCount: { answered: number; total_connected: number } | null;
  questionStartedAt: number | null;
}

export function QuestionActivePanel({ round, totalRounds, answeredCount, questionStartedAt }: QuestionActivePanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Round {round} of {totalRounds}
        </p>
        <h1 className={styles.status}>Question in progress…</h1>
        <CountdownTimer startedAt={questionStartedAt} durationSeconds={QUESTION_TIMEOUT_SECONDS} />
        <p className={styles.answeredCount}>
          {answeredCount ? `${answeredCount.answered} of ${answeredCount.total_connected} answered` : 'Waiting for answers…'}
        </p>
      </div>
    </main>
  );
}
