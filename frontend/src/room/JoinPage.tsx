import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { RoomPrecheck } from '../types/room';
import { RoomErrorPanel } from './panels/RoomErrorPanel';
import styles from './JoinPage.module.css';

export function JoinPage() {
  const { pin } = useParams<{ pin: string }>();
  const navigate = useNavigate();
  const [precheck, setPrecheck] = useState<RoomPrecheck | 'not_found' | 'loading'>('loading');
  const [nickname, setNickname] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!pin) return;
    let cancelled = false;
    fetch(`/rooms/${pin}`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: RoomPrecheck) => {
        if (!cancelled) setPrecheck(data);
      })
      .catch(() => {
        if (!cancelled) setPrecheck('not_found');
      });
    return () => {
      cancelled = true;
    };
  }, [pin]);

  if (!pin) {
    return <RoomErrorPanel title="Room not found" message="No room PIN was given." />;
  }

  if (precheck === 'loading') {
    return null;
  }

  if (precheck === 'not_found') {
    return <RoomErrorPanel title="Room not found" message={`No room with PIN ${pin} exists.`} />;
  }

  if (precheck.status === 'finished') {
    return <RoomErrorPanel title="Game over" message="This room's game has already finished." />;
  }

  if (precheck.status === 'in_progress') {
    return <RoomErrorPanel title="Already started" message="This room's game is already in progress." />;
  }

  if (precheck.player_count >= 10) {
    return <RoomErrorPanel title="Room full" message="This room already has 10 players." />;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    const response = await fetch(`/rooms/${pin}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname }),
    });
    setSubmitting(false);
    if (!response.ok) {
      setSubmitError(response.status === 409 ? 'This room is full or already started.' : 'Room not found.');
      return;
    }
    const data = (await response.json()) as { player_id: string };
    navigate(`/play/${pin}?player_id=${data.player_id}`);
  };

  return (
    <main className={styles.theme}>
      <form className={styles.stage} onSubmit={handleSubmit}>
        <p className={styles.pinLabel}>Joining Room {pin}</p>
        <input
          className={styles.nicknameInput}
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          placeholder="Your nickname"
          required
        />
        {submitError && <p className={styles.error}>{submitError}</p>}
        <button className={styles.joinBtn} type="submit" disabled={submitting || nickname.trim() === ''}>
          Join Room
        </button>
      </form>
    </main>
  );
}
