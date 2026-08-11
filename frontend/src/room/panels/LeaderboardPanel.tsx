import type { LeaderboardStanding } from '../../types/room';
import styles from './LeaderboardPanel.module.css';

interface LeaderboardPanelProps {
  standings: LeaderboardStanding[];
  round: number;
  totalRounds: number;
  isFinal: boolean;
  currentPlayerId?: string;
  hostControls?: { onNext: () => void; onEndGame: () => void };
}

export function LeaderboardPanel({
  standings,
  round,
  totalRounds,
  isFinal,
  currentPlayerId,
  hostControls,
}: LeaderboardPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.round}>
          Leaderboard — Round {round} of {totalRounds}
        </p>
        <ol className={styles.standings}>
          {standings.map((s) => (
            <li key={s.player_id} className={s.player_id === currentPlayerId ? styles.ownRow : styles.row}>
              <span className={styles.rank}>#{s.rank}</span>
              <span className={styles.nickname}>{s.nickname}</span>
              <span className={styles.score}>{s.score}</span>
            </li>
          ))}
        </ol>
        {hostControls && (
          <div className={styles.hostActions}>
            <button className={styles.primaryBtn} onClick={hostControls.onNext}>
              {isFinal ? 'Finish' : 'Next Question'}
            </button>
            {!isFinal && (
              <button className={styles.secondaryBtn} onClick={hostControls.onEndGame}>
                End Game
              </button>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
