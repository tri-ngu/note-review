import { describe, expect, it } from 'vitest';
import { initialRoomSocketState, roomSocketReducer } from './roomSocketReducer';

describe('roomSocketReducer', () => {
  it('adds a new player to the roster on player_joined', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    expect(state.roster).toEqual([{ player_id: 'p1', nickname: 'Alice' }]);
  });

  it('updates nickname if player_joined fires again for the same player_id', () => {
    const joined = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    const renamed = roomSocketReducer(joined, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice (1)',
    });
    expect(renamed.roster).toEqual([{ player_id: 'p1', nickname: 'Alice (1)' }]);
  });

  it('removes a player from the roster on player_left', () => {
    const joined = roomSocketReducer(initialRoomSocketState, {
      type: 'player_joined',
      player_id: 'p1',
      nickname: 'Alice',
    });
    const left = roomSocketReducer(joined, { type: 'player_left', player_id: 'p1' });
    expect(left.roster).toEqual([]);
  });

  it('enters question_active phase and clears prior round data on question_start', () => {
    const withPriorRound = {
      ...initialRoomSocketState,
      lastReveal: {
        type: 'answer_reveal' as const,
        round: 1,
        correct_answers: [1],
        explanation: 'because',
        results: {},
      },
      answeredCount: { answered: 2, total_connected: 3 },
    };
    const state = roomSocketReducer(withPriorRound, {
      type: 'question_start',
      round: 2,
      total_rounds: 8,
      question_text: 'What is water made of?',
      options: ['H2O', 'CO2', 'O2', 'N2'],
      is_select_all: false,
      page_number: 1,
      concept: 'Water cycle',
      server_time: 100,
    });
    expect(state.phase).toBe('question_active');
    expect(state.currentQuestion?.question_text).toBe('What is water made of?');
    expect(state.answeredCount).toBeNull();
    expect(state.lastReveal).toBeNull();
  });

  it('records answered_count', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'answered_count',
      answered: 1,
      total_connected: 4,
    });
    expect(state.answeredCount).toEqual({ answered: 1, total_connected: 4 });
  });

  it('enters reveal phase and stores the reveal payload on answer_reveal', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'answer_reveal',
      round: 1,
      correct_answers: [1, 3],
      explanation: 'because',
      results: { p1: { correct: true, points: 90 } },
    });
    expect(state.phase).toBe('reveal');
    expect(state.lastReveal?.correct_answers).toEqual([1, 3]);
  });

  it('enters leaderboard phase and stores standings on leaderboard', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'leaderboard',
      round: 1,
      total_rounds: 8,
      standings: [{ player_id: 'p1', nickname: 'Alice', score: 90, rank: 1 }],
      is_final: false,
    });
    expect(state.phase).toBe('leaderboard');
    expect(state.standings).toHaveLength(1);
    expect(state.isFinalRound).toBe(false);
  });

  it('enters finished phase and stores final standings on game_over', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'game_over',
      reason: 'natural_end',
      final_standings: [{ player_id: 'p1', nickname: 'Alice', score: 90, rank: 1 }],
    });
    expect(state.phase).toBe('finished');
    expect(state.gameOver?.reason).toBe('natural_end');
  });

  it('stores the last error on error without changing phase', () => {
    const state = roomSocketReducer(initialRoomSocketState, {
      type: 'error',
      code: 'late_answer',
      message: 'Answer rejected: too late.',
    });
    expect(state.phase).toBe('lobby');
    expect(state.lastError).toEqual({ code: 'late_answer', message: 'Answer rejected: too late.' });
  });

  it('tracks connection open/closed transitions', () => {
    const open = roomSocketReducer(initialRoomSocketState, { type: 'connection_open' });
    expect(open.connection).toBe('open');
    const closed = roomSocketReducer(open, { type: 'connection_closed' });
    expect(closed.connection).toBe('closed');
  });
});
