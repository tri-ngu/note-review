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
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!pin) return;

    // StrictMode double-invokes this effect (mount -> cleanup -> mount) synchronously
    // in dev. If a close from the phantom cleanup is still pending, cancel it and
    // reuse the still-open socket below instead of opening a second real connection
    // — otherwise the phantom socket's real disconnect reaches the server (e.g. the
    // Host disconnect short-circuit would end the Room before the real socket ever opens).
    if (closeTimerRef.current !== null) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }

    let socket = socketRef.current;
    const reusable = socket !== null && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING);

    if (!reusable) {
      const query = role === 'player' && playerId ? `?player_id=${encodeURIComponent(playerId)}` : '';
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      socket = new WebSocket(`${protocol}://${window.location.host}/ws/room/${pin}${query}`);
      socketRef.current = socket;

      socket.onopen = () => {
        if (socketRef.current === socket) dispatch({ type: 'connection_open' });
      };
      socket.onclose = () => {
        if (socketRef.current === socket) dispatch({ type: 'connection_closed' });
      };
      socket.onmessage = (event) => {
        if (socketRef.current !== socket) return;
        const message = JSON.parse(event.data as string) as ServerMessage;
        dispatch(message);
      };
    }

    // non-null: either reused from the readyState check above, or freshly assigned
    const socketForCleanup = socket!;
    return () => {
      closeTimerRef.current = setTimeout(() => {
        closeTimerRef.current = null;
        if (socketRef.current === socketForCleanup) {
          socketForCleanup.close();
          socketRef.current = null;
        }
      }, 0);
    };
  }, [pin, role, playerId]);

  const send = (message: ClientMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  };

  return { state, send };
}
