// Empty in dev (Vite proxy handles same-origin relative paths, see vite.config.ts).
// Set to the deployed Render backend URL in prod via VITE_API_BASE_URL.
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '';

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), { ...init, credentials: 'include' });
}

export function wsUrl(path: string): string {
  if (API_BASE_URL) {
    return `${API_BASE_URL.replace(/^http/, 'ws')}${path}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}${path}`;
}
