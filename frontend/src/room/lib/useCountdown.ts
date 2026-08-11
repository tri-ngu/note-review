import { useEffect, useState } from 'react';

export function useCountdown(startedAt: number | null, durationSeconds: number): number {
  const [remaining, setRemaining] = useState(durationSeconds);

  useEffect(() => {
    if (startedAt === null) {
      setRemaining(durationSeconds);
      return;
    }
    const tick = () => {
      const elapsed = (Date.now() - startedAt) / 1000;
      setRemaining(Math.max(0, durationSeconds - elapsed));
    };
    tick();
    const interval = setInterval(tick, 250);
    return () => clearInterval(interval);
  }, [startedAt, durationSeconds]);

  return remaining;
}
