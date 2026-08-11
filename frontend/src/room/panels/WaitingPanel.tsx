import styles from './WaitingPanel.module.css';

interface WaitingPanelProps {
  pin: string;
}

export function WaitingPanel({ pin }: WaitingPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.pinLabel}>Room {pin}</p>
        <h1 className={styles.message}>Waiting for the host to start the game…</h1>
      </div>
    </main>
  );
}
