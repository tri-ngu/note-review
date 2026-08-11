export type RoomPublicStatus = 'lobby' | 'in_progress' | 'finished';

export interface RoomPrecheck {
  status: RoomPublicStatus;
  player_count: number;
}

export interface RosterPlayer {
  player_id: string;
  nickname: string;
}

export interface LeaderboardStanding {
  player_id: string;
  nickname: string;
  score: number;
  rank: number;
}

export interface AnswerResult {
  correct: boolean;
  points: number;
}

export interface QuestionStartMessage {
  type: 'question_start';
  round: number;
  total_rounds: number;
  question_text: string;
  options: [string, string, string, string];
  is_select_all: boolean;
  page_number: number;
  concept: string;
  server_time: number;
}

export interface AnswerRevealMessage {
  type: 'answer_reveal';
  round: number;
  correct_answers: number[];
  explanation: string;
  results: Record<string, AnswerResult>;
}

export interface LeaderboardMessage {
  type: 'leaderboard';
  round: number;
  total_rounds: number;
  standings: LeaderboardStanding[];
  is_final: boolean;
}

export interface GameOverMessage {
  type: 'game_over';
  reason: 'natural_end' | 'host_ended' | 'host_disconnected';
  final_standings: LeaderboardStanding[];
}

export type ServerMessage =
  | { type: 'player_joined'; player_id: string; nickname: string }
  | { type: 'player_left'; player_id: string }
  | QuestionStartMessage
  | { type: 'answered_count'; answered: number; total_connected: number }
  | AnswerRevealMessage
  | LeaderboardMessage
  | GameOverMessage
  | { type: 'error'; code: string; message: string };

export type ClientMessage =
  | { type: 'advance' }
  | { type: 'end_game' }
  | { type: 'submit_answer'; round: number; selected: number[] };

export type ConnectionState = 'connecting' | 'open' | 'closed';

export type RoomSocketAction =
  | ServerMessage
  | { type: 'connection_open' }
  | { type: 'connection_closed' };

export type RoomPhase = 'lobby' | 'question_active' | 'reveal' | 'leaderboard' | 'finished';

export interface RoomSocketState {
  connection: ConnectionState;
  phase: RoomPhase;
  roster: RosterPlayer[];
  currentQuestion: QuestionStartMessage | null;
  questionStartedAt: number | null;
  answeredCount: { answered: number; total_connected: number } | null;
  lastReveal: AnswerRevealMessage | null;
  standings: LeaderboardStanding[];
  isFinalRound: boolean;
  gameOver: GameOverMessage | null;
  lastError: { code: string; message: string } | null;
}
