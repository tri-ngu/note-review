export function buildJoinUrl(origin: string, pin: string): string {
  return `${origin}/join/${pin}`;
}
