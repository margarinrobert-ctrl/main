/**
 * Deterministic RNG. Every bootstrap, permutation and Monte Carlo path in this stack is seeded,
 * so a reported p-value is reproducible to the digit rather than "about 0.03 last time I ran it".
 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Box-Muller standard normal from a uniform generator. */
export function normal(rand: () => number): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = rand();
  while (v === 0) v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** Student-t draw with `df` degrees of freedom — fat tails, which real intraday returns have. */
export function studentT(rand: () => number, df: number): number {
  let chi = 0;
  for (let i = 0; i < df; i++) {
    const z = normal(rand);
    chi += z * z;
  }
  return normal(rand) / Math.sqrt(chi / df);
}
