import { parseSseBuffer } from './sseParse';
import type { GenerationEvent } from './generationProgress';

interface RunGenerationArgs {
  endpoint: '/generate' | '/generate/retry';
  body?: unknown;
  onEvent: (evt: GenerationEvent) => void;
}

export async function runGeneration({ endpoint, body, onEvent }: RunGenerationArgs): Promise<void> {
  let res: Response;
  try {
    res = await fetch(endpoint, {
      method: 'POST',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    onEvent({ stage: 'error', message: 'Could not reach the backend. Please try again.' });
    return;
  }

  if (!res.ok || !res.body) {
    onEvent({ stage: 'error', message: 'Could not start generation. Please try again.' });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = parseSseBuffer<GenerationEvent>(buffer);
    buffer = remainder;
    for (const evt of events) onEvent(evt);
  }
}
