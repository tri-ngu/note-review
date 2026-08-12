import styles from './PlayerBadge.module.css';

interface PlayerBadgeProps {
  nickname: string;
  score: number;
}

export function PlayerBadge({ nickname, score }: PlayerBadgeProps) {
  return (
    <div className={styles.badge}>
      <span className={styles.nickname}>{nickname}</span>
      <span className={styles.score}>Score: {score}</span>
    </div>
  );
}
