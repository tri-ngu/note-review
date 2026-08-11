import { useEffect, useReducer, useRef } from 'react';
import type { ClientMessage, ServerMessage } from '../types/room';
import { initialRoomSocketState, roomSocketReducer } from './lib/roomSocketReducer';

interface UseRoomSocketArgs {
  pin: string;
  role: 'host' | 'player';
  playerId?: string;
}

export function useRoomSocket({ pin, role, playerId }: UseRoomSocketArgs) {
  const [state, dispatch] = useReducer(roomSocketReducer, initialRoomSocketState);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!pin) return;
    const query = role === 'player' && playerId ? `?player_id=${encodeURIComponent(playerId)}` : '';
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/room/${pin}${query}`);
    socketRef.current = socket;

    socket.onopen = () => dispatch({ type: 'connection_open' });
    socket.onclose = () => dispatch({ type: 'connection_closed' });
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data as string) as ServerMessage;
      dispatch(message);
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [pin, role, playerId]);

  const send = (message: ClientMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  };

  return { state, send };
}
