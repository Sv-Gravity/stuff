// Seeded RNG (mulberry32). The RNG state lives inside the game state as {r: uint32}
// so the whole simulation is deterministic and serialisable (needed for multiplayer).
export function rand(s) {
  let t = (s.r = (s.r + 0x6D2B79F5) >>> 0);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
export const range = (s, a, b) => a + (b - a) * rand(s);
export const pick = (s, arr) => arr[Math.floor(rand(s) * arr.length)];
