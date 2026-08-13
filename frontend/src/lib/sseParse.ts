export interface ParsedSseChunk<T> {
  events: T[];
  remainder: string;
}

export function parseSseBuffer<T>(buffer: string): ParsedSseChunk<T> {
  const parts = buffer.split('\n\n');
  const remainder = parts.pop() ?? '';
  const events: T[] = [];

  for (const part of parts) {
    const dataLine = part.split('\n').find((line) => line.startsWith('data: '));
    if (!dataLine) continue;
    events.push(JSON.parse(dataLine.slice('data: '.length)) as T);
  }

  return { events, remainder };
}
