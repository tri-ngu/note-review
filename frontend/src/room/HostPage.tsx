import { useParams } from 'react-router-dom';
import { useRoomSocket } from './useRoomSocket';
import { LobbyPanel } from './panels/LobbyPanel';
import { QuestionActivePanel } from './panels/QuestionActivePanel';
import { LeaderboardPanel } from './panels/LeaderboardPanel';
import { FinishedPanel } from './panels/FinishedPanel';
import { RoomErrorPanel } from './panels/RoomErrorPanel';

export function HostPage() {
  const { pin } = useParams<{ pin: string }>();
  const { state, send } = useRoomSocket({ pin: pin ?? '', role: 'host' });

  if (!pin) {
    return <RoomErrorPanel title="Room not found" message="No room PIN was given." />;
  }

  if (state.connection === 'closed') {
    return <RoomErrorPanel title="Disconnected" message="Lost connection to the room." />;
  }

  switch (state.phase) {
    case 'lobby':
      return <LobbyPanel pin={pin} roster={state.roster} onStart={() => send({ type: 'advance' })} />;
    case 'question_active':
    case 'reveal':
      return (
        <QuestionActivePanel
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          answeredCount={state.answeredCount}
        />
      );
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
