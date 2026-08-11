import { useParams, useSearchParams } from 'react-router-dom';
import { useRoomSocket } from './useRoomSocket';
import { WaitingPanel } from './panels/WaitingPanel';
import { QuestionPanel } from './panels/QuestionPanel';
import { RevealPanel } from './panels/RevealPanel';
import { LeaderboardPanel } from './panels/LeaderboardPanel';
import { FinishedPanel } from './panels/FinishedPanel';
import { RoomErrorPanel } from './panels/RoomErrorPanel';

export function PlayerPage() {
  const { pin } = useParams<{ pin: string }>();
  const [searchParams] = useSearchParams();
  const playerId = searchParams.get('player_id');

  const { state, send } = useRoomSocket({ pin: pin ?? '', role: 'player', playerId: playerId ?? undefined });

  if (!pin || !playerId) {
    return <RoomErrorPanel title="Missing player info" message="Join the room again to get a valid player link." />;
  }

  if (state.connection === 'closed') {
    return <RoomErrorPanel title="Disconnected" message="Lost connection to the room." />;
  }

  switch (state.phase) {
    case 'lobby':
      return <WaitingPanel pin={pin} />;
    case 'question_active':
      return state.currentQuestion ? (
        <QuestionPanel
          key={state.currentQuestion.round}
          question={state.currentQuestion}
          onSubmit={(selected) => send({ type: 'submit_answer', round: state.currentQuestion!.round, selected })}
        />
      ) : null;
    case 'reveal':
      return state.currentQuestion && state.lastReveal ? (
        <RevealPanel
          questionText={state.currentQuestion.question_text}
          options={state.currentQuestion.options}
          correctAnswers={state.lastReveal.correct_answers}
          explanation={state.lastReveal.explanation}
          result={state.lastReveal.results[playerId]}
        />
      ) : null;
    case 'leaderboard':
      return (
        <LeaderboardPanel
          standings={state.standings}
          round={state.currentQuestion?.round ?? 0}
          totalRounds={state.currentQuestion?.total_rounds ?? 0}
          isFinal={state.isFinalRound}
          currentPlayerId={playerId}
        />
      );
    case 'finished':
      return (
        <FinishedPanel
          standings={state.gameOver?.final_standings ?? []}
          reason={state.gameOver?.reason ?? 'natural_end'}
          currentPlayerId={playerId}
        />
      );
  }
  return null;
}
