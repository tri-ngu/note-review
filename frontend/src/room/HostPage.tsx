import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useRoomSocket } from './useRoomSocket';
import type { RoomPrecheck } from '../types/room';
import { LobbyPanel } from './panels/LobbyPanel';
import { QuestionActivePanel } from './panels/QuestionActivePanel';
import { HostRevealPanel } from './panels/HostRevealPanel';
import { LeaderboardPanel } from './panels/LeaderboardPanel';
import { FinishedPanel } from './panels/FinishedPanel';
import { RoomErrorPanel } from './panels/RoomErrorPanel';

export function HostPage() {
  const { pin } = useParams<{ pin: string }>();
  const [precheck, setPrecheck] = useState<RoomPrecheck | 'not_found' | 'loading'>('loading');

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

  const { state, send } = useRoomSocket({ pin: pin ?? '', role: 'host' });

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

  if (state.phase === 'closed') {
    return <RoomErrorPanel title="Room closed" message="This room was closed due to inactivity." />;
  }

  if (state.connection === 'closed') {
    return <RoomErrorPanel title="Disconnected" message="Lost connection to the room." />;
  }

  switch (state.phase) {
    case 'lobby':
      return <LobbyPanel pin={pin} roster={state.roster} onStart={() => send({ type: 'advance' })} />;
    case 'question_active':
      return (
        <QuestionActivePanel
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          isSelectAll={state.currentQuestion?.is_select_all ?? false}
          answeredCount={state.answeredCount}
          questionStartedAt={state.questionStartedAt}
        />
      );
    case 'reveal':
      return state.currentQuestion && state.lastReveal ? (
        <HostRevealPanel
          round={state.currentQuestion.round}
          totalRounds={state.currentQuestion.total_rounds}
          isSelectAll={state.currentQuestion.is_select_all}
          questionText={state.currentQuestion.question_text}
          options={state.currentQuestion.options}
          correctAnswers={state.lastReveal.correct_answers}
          explanation={state.lastReveal.explanation}
          onShowLeaderboard={() => send({ type: 'advance' })}
        />
      ) : null;
    case 'leaderboard':
      return (
        <LeaderboardPanel
          standings={state.standings}
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          isFinal={state.isFinalRound}
          hostControls={{
            onNext: () => send({ type: 'advance' }),
            onEndGame: () => send({ type: 'end_game' }),
          }}
        />
      );
    case 'finished':
      return (
        <FinishedPanel standings={state.gameOver?.final_standings ?? []} reason={state.gameOver?.reason ?? 'natural_end'} />
      );
  }
  return null;
}
