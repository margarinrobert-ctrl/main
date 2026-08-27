import { describe, expect, it } from "vitest";
import { ByteLru } from "./lru";

describe("ByteLru", () => {
  it("evicts least-recently-used until the new entry fits", () => {
    const c = new ByteLru<string>(100);
    c.set("a", "A", 40);
    c.set("b", "B", 40);
    c.set("c", "C", 40); // 120 > 100, so "a" goes
    expect(c.get("a")).toBeUndefined();
    expect(c.get("b")).toBe("B");
    expect(c.get("c")).toBe("C");
    expect(c.bytes).toBe(80);
  });

  it("counts a read as a use, so the survivor is the one being asked for", () => {
    const c = new ByteLru<string>(100);
    c.set("a", "A", 40);
    c.set("b", "B", 40);
    c.get("a"); // "a" is now the newest
    c.set("c", "C", 40);
    expect(c.get("a")).toBe("A");
    expect(c.get("b")).toBeUndefined();
  });

  it("replaces a key in place without double-counting its bytes", () => {
    const c = new ByteLru<string>(100);
    c.set("a", "A", 40);
    c.set("a", "AA", 60);
    expect(c.bytes).toBe(60);
    expect(c.size).toBe(1);
    expect(c.get("a")).toBe("AA");
  });

  it("stores an entry larger than the whole budget rather than silently not caching it", () => {
    const c = new ByteLru<string>(100);
    c.set("a", "A", 40);
    c.set("big", "B", 500);
    expect(c.get("big")).toBe("B");
    expect(c.get("a")).toBeUndefined();
  });

  it("builds once through take, and not again on a hit", () => {
    const c = new ByteLru<number>(100);
    let built = 0;
    const build = () => {
      built++;
      return { value: 7, bytes: 10 };
    };
    expect(c.take("k", build)).toBe(7);
    expect(c.take("k", build)).toBe(7);
    expect(built).toBe(1);
  });

  it("evicts immediately when the budget is lowered", () => {
    const c = new ByteLru<string>(100);
    c.set("a", "A", 40);
    c.set("b", "B", 40);
    c.reserve(50);
    expect(c.bytes).toBeLessThanOrEqual(50);
    expect(c.get("b")).toBe("B");
    expect(c.get("a")).toBeUndefined();
  });
});
