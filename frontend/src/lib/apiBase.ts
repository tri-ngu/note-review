// Frontend and backend share an origin (FastAPI serves the built frontend), so
// paths are always relative — no cross-origin base URL to configure.
export function apiUrl(path: string): string {
  return path;
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init);
}

export function wsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}${path}`;
}
