import type { RoomSocketAction, RoomSocketState } from '../../types/room';

export const initialRoomSocketState: RoomSocketState = {
  connection: 'connecting',
  phase: 'lobby',
  roster: [],
  currentQuestion: null,
  questionStartedAt: null,
  answeredCount: null,
  lastReveal: null,
  standings: [],
  isFinalRound: false,
  gameOver: null,
  lastError: null,
};

export function roomSocketReducer(state: RoomSocketState, action: RoomSocketAction): RoomSocketState {
  switch (action.type) {
    case 'connection_open':
      return { ...state, connection: 'open' };
    case 'connection_closed':
      return { ...state, connection: 'closed' };
    case 'player_joined': {
      const alreadyPresent = state.roster.some((p) => p.player_id === action.player_id);
      const roster = alreadyPresent
        ? state.roster.map((p) =>
            p.player_id === action.player_id ? { player_id: action.player_id, nickname: action.nickname } : p,
          )
        : [...state.roster, { player_id: action.player_id, nickname: action.nickname }];
      return { ...state, roster };
    }
    case 'player_left':
      return { ...state, roster: state.roster.filter((p) => p.player_id !== action.player_id) };
    case 'question_start':
      return {
        ...state,
        phase: 'question_active',
        currentQuestion: action,
        questionStartedAt: Date.now(),
        answeredCount: null,
        lastReveal: null,
      };
    case 'answered_count':
      return { ...state, answeredCount: { answered: action.answered, total_connected: action.total_connected } };
    case 'answer_reveal':
      return { ...state, phase: 'reveal', lastReveal: action };
    case 'leaderboard':
      return { ...state, phase: 'leaderboard', standings: action.standings, isFinalRound: action.is_final };
    case 'game_over':
      return { ...state, phase: 'finished', gameOver: action };
    case 'room_closed':
      return { ...state, phase: 'closed' };
    case 'error':
      return { ...state, lastError: { code: action.code, message: action.message } };
    default:
      return state;
  }
}
