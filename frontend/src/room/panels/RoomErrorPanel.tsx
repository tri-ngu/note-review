import { Link } from 'react-router-dom';
import styles from './RoomErrorPanel.module.css';

interface RoomErrorPanelProps {
  title: string;
  message: string;
}

export function RoomErrorPanel({ title, message }: RoomErrorPanelProps) {
  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.message}>{message}</p>
        <Link className={styles.homeLink} to="/">
          Back to Home
        </Link>
      </div>
    </main>
  );
}
