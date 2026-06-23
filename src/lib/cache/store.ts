export interface CacheStore {
  get<T>(key: string): Promise<T | undefined>;
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>;
}

interface Entry {
  value: unknown;
  expiresAt: number;
}

class InMemoryCache implements CacheStore {
  private store = new Map<string, Entry>();

  async get<T>(key: string): Promise<T | undefined> {
    const e = this.store.get(key);
    if (!e) return undefined;
    if (Date.now() > e.expiresAt) {
      this.store.delete(key);
      return undefined;
    }
    return e.value as T;
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    this.store.set(key, { value, expiresAt: Date.now() + ttlSeconds * 1000 });
  }
}

// Swap for a Redis-backed implementation later — same interface, no call-site changes.
export const cache: CacheStore = new InMemoryCache();

/** Cache-aside helper: return the cached value or compute, store, and return it. */
export async function cached<T>(key: string, ttlSeconds: number, fn: () => Promise<T>): Promise<T> {
  const hit = await cache.get<T>(key);
  if (hit !== undefined) return hit;
  const value = await fn();
  await cache.set(key, value, ttlSeconds);
  return value;
}
