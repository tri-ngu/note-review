import { useCountdown } from '../lib/useCountdown';
import styles from './CountdownTimer.module.css';

interface CountdownTimerProps {
  startedAt: number | null;
  durationSeconds: number;
}

export function CountdownTimer({ startedAt, durationSeconds }: CountdownTimerProps) {
  const remaining = useCountdown(startedAt, durationSeconds);
  const seconds = Math.ceil(remaining);

  return (
    <p className={seconds <= 5 ? styles.urgent : styles.timer}>
      {seconds}s remaining
    </p>
  );
}
