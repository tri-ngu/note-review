import { QRCodeSVG } from 'qrcode.react';
import type { RosterPlayer } from '../../types/room';
import { buildJoinUrl } from '../lib/joinUrl';
import styles from './LobbyPanel.module.css';

interface LobbyPanelProps {
  pin: string;
  roster: RosterPlayer[];
  onStart: () => void;
}

export function LobbyPanel({ pin, roster, onStart }: LobbyPanelProps) {
  const joinUrl = buildJoinUrl(window.location.origin, pin);

  return (
    <main className={styles.theme}>
      <div className={styles.stage}>
        <p className={styles.pinLabel}>Room PIN</p>
        <h1 className={styles.pin}>{pin}</h1>
        <QRCodeSVG value={joinUrl} size={180} />
        <p className={styles.joinUrl}>{joinUrl}</p>
        <h2 className={styles.rosterHeading}>Players ({roster.length}/10)</h2>
        <ul className={styles.roster}>
          {roster.map((player) => (
            <li key={player.player_id} className={styles.rosterItem}>
              {player.nickname}
            </li>
          ))}
        </ul>
        <button className={styles.startBtn} onClick={onStart}>
          Start Game
        </button>
      </div>
    </main>
  );
}
