import { Link } from 'react-router-dom';
import type { LeaderboardStanding } from '../../types/room';
import styles from './FinishedPanel.module.css';

interface FinishedPanelProps {
  standings: LeaderboardStanding[];
  reason: 'natural_end' | 'host_ended' | 'host_disconnected';
  currentPlayerId?: string;
}

const REASON_LABEL: Record<FinishedPanelProps['reason'], string> = {
  natural_end: 'Game complete!',
  host_ended: 'Host ended the game.',
  host_disconnected: 'Host disconnected — game ended.',
};

export function FinishedPanel({ standings, reason, currentPlayerId }: FinishedPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <h1 className={styles.title}>{REASON_LABEL[reason]}</h1>
        <ol className={styles.standings}>
          {standings.map((s) => (
            <li key={s.player_id} className={s.player_id === currentPlayerId ? styles.ownRow : styles.row}>
              <span className={styles.rank}>#{s.rank}</span>
              <span className={styles.nickname}>{s.nickname}</span>
              <span className={styles.score}>{s.score}</span>
            </li>
          ))}
        </ol>
        <Link className={styles.homeLink} to="/">
          Back to Home
        </Link>
      </div>
    </main>
  );
}
