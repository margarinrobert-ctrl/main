/**
 * A least-recently-used cache with a BYTE budget rather than an entry count.
 *
 * The tuner's caches hold typed arrays whose sizes differ by four orders of magnitude — a trigger
 * list is a few kilobytes, an exit tensor over a million bars is hundreds of megabytes — so "keep
 * the last 50" is not a budget, it is a coin flip on whether the tab survives. Counting bytes is.
 *
 * This exists because the caches it replaces were unbounded `Map`s, and that is the tuner's single
 * biggest freeze: every keystroke in the stop field builds a fresh tensor keyed on the new
 * geometry list, and nothing ever dropped the old one. Typing `1,1.5,2,2.5` one character at a
 * time allocated ten tensors and freed none.
 */
export class ByteLru<V> {
  private readonly map = new Map<string, { value: V; bytes: number }>();
  private used = 0;
  private hits = 0;
  private misses = 0;
  private evictions = 0;

  constructor(private budget: number) {}

  get size(): number {
    return this.map.size;
  }

  get bytes(): number {
    return this.used;
  }

  stats(): { entries: number; bytes: number; budget: number; hits: number; misses: number; evictions: number } {
    return { entries: this.map.size, bytes: this.used, budget: this.budget, hits: this.hits, misses: this.misses, evictions: this.evictions };
  }

  get(key: string): V | undefined {
    const hit = this.map.get(key);
    if (!hit) {
      this.misses++;
      return undefined;
    }
    // Re-inserting moves the key to the end of Map's insertion order, which is the recency list.
    this.map.delete(key);
    this.map.set(key, hit);
    this.hits++;
    return hit.value;
  }

  set(key: string, value: V, bytes: number): V {
    const prev = this.map.get(key);
    if (prev) {
      this.used -= prev.bytes;
      this.map.delete(key);
    }
    // An entry larger than the whole budget is still stored — refusing it would mean the caller
    // silently got no caching on the one thing most worth caching — but it evicts everything else.
    while (this.used + bytes > this.budget && this.map.size) {
      const oldest = this.map.keys().next();
      if (oldest.done) break;
      const e = this.map.get(oldest.value)!;
      this.map.delete(oldest.value);
      this.used -= e.bytes;
      this.evictions++;
    }
    this.map.set(key, { value, bytes });
    this.used += bytes;
    return value;
  }

  /** Fetch or build. The builder also reports the entry's size, since only it knows. */
  take(key: string, build: () => { value: V; bytes: number }): V {
    const hit = this.get(key);
    if (hit !== undefined) return hit;
    const made = build();
    return this.set(key, made.value, made.bytes);
  }

  clear(): void {
    this.map.clear();
    this.used = 0;
  }

  /** Raise or lower the budget, evicting immediately if it shrank. */
  reserve(budget: number): void {
    this.budget = budget;
    while (this.used > this.budget && this.map.size) {
      const oldest = this.map.keys().next();
      if (oldest.done) break;
      const e = this.map.get(oldest.value)!;
      this.map.delete(oldest.value);
      this.used -= e.bytes;
      this.evictions++;
    }
  }
}
