import { describe, expect, it } from "vitest";
import { clockFor, inWindow, localToUtc, minutesSinceOpen, nyOffsetMinutes, sessionIndex } from "./clock";
import type { Bar } from "./types";

// The DST rule is hand-rolled for speed, so it is checked against the platform's own tz database
// across the whole span the research data covers. If ICU and the rule ever disagree, this fails.
describe("nyOffsetMinutes", () => {
  const icuOffset = (utcMs: number): number => {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour12: false,
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
    const p = Object.fromEntries(fmt.formatToParts(new Date(utcMs)).map((x) => [x.type, x.value]));
    const local = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute);
    return Math.round((local - utcMs) / 60_000);
  };

  it("matches the platform timezone database every 6 hours from 2020 to 2027", () => {
    let checked = 0;
    for (let t = Date.UTC(2020, 0, 1); t < Date.UTC(2027, 0, 1); t += 6 * 3_600_000) {
      expect(nyOffsetMinutes(t)).toBe(icuOffset(t));
      checked++;
    }
    expect(checked).toBeGreaterThan(10_000);
  });

  it("switches on the correct instants in 2025", () => {
    // 2025 spring forward: 09 March 07:00 UTC. Fall back: 02 November 06:00 UTC.
    expect(nyOffsetMinutes(Date.UTC(2025, 2, 9, 6, 59))).toBe(-300);
    expect(nyOffsetMinutes(Date.UTC(2025, 2, 9, 7, 0))).toBe(-240);
    expect(nyOffsetMinutes(Date.UTC(2025, 10, 2, 5, 59))).toBe(-240);
    expect(nyOffsetMinutes(Date.UTC(2025, 10, 2, 6, 0))).toBe(-300);
  });
});

describe("localToUtc", () => {
  it("maps the 09:30 ET open to 13:30 UTC in summer and 14:30 UTC in winter", () => {
    expect(new Date(localToUtc(2023, 6, 1, 9, 30, "America/New_York")).toISOString()).toBe("2023-06-01T13:30:00.000Z");
    expect(new Date(localToUtc(2023, 1, 3, 9, 30, "America/New_York")).toISOString()).toBe("2023-01-03T14:30:00.000Z");
  });

  it("round-trips through nyOffsetMinutes", () => {
    for (const [mo, d] of [[1, 15], [3, 20], [7, 4], [11, 20]] as const) {
      const utc = localToUtc(2024, mo, d, 10, 5, "America/New_York");
      const local = new Date(utc + nyOffsetMinutes(utc) * 60_000);
      expect(local.getUTCHours()).toBe(10);
      expect(local.getUTCMinutes()).toBe(5);
    }
  });
});

describe("clockFor", () => {
  const bars: Bar[] = [
    { t: Date.UTC(2023, 5, 1, 13, 30), o: 1, h: 1, l: 1, c: 1, v: 1 },
    { t: Date.UTC(2023, 0, 3, 14, 30), o: 1, h: 1, l: 1, c: 1, v: 1 },
  ];

  it("reports exchange-local fields, not UTC ones", () => {
    const c = clockFor(bars, "America/New_York");
    expect([...c.hour]).toEqual([9, 9]);
    expect([...c.minute]).toEqual([30, 30]);
    expect([...c.minuteOfDay]).toEqual([570, 570]);
  });

  it("memoises per series and timezone", () => {
    expect(clockFor(bars, "America/New_York")).toBe(clockFor(bars, "America/New_York"));
    expect(clockFor(bars, "UTC")).not.toBe(clockFor(bars, "America/New_York"));
  });
});

describe("inWindow", () => {
  it("handles ordinary and midnight-wrapping windows", () => {
    expect(inWindow(600, 570, 960)).toBe(true);
    expect(inWindow(960, 570, 960)).toBe(false);
    expect(inWindow(30, 1320, 120)).toBe(true);
    expect(inWindow(600, 1320, 120)).toBe(false);
  });
});

describe("minutesSinceOpen", () => {
  it("counts forward from a session that stays inside one day", () => {
    expect(minutesSinceOpen(570, 570)).toBe(0);
    expect(minutesSinceOpen(630, 570)).toBe(60);
    expect(minutesSinceOpen(960, 570)).toBe(390);
  });

  it("counts forward across midnight for an overnight session", () => {
    // 18:00 open. 18:30 is 30 minutes in; 00:30 is 390; 03:00 is 540.
    expect(minutesSinceOpen(1080, 1080)).toBe(0);
    expect(minutesSinceOpen(1110, 1080)).toBe(30);
    expect(minutesSinceOpen(30, 1080)).toBe(390);
    expect(minutesSinceOpen(180, 1080)).toBe(540);
  });

  it("is what makes an IB window test correct past midnight", () => {
    // A 120-minute IB from 23:00 ends at 01:00. Raw arithmetic (1380 + 120 = 1500) would put every
    // post-midnight bar outside the window.
    const start = 1380;
    expect(minutesSinceOpen(1380, start) < 120).toBe(true); // 23:00 in
    expect(minutesSinceOpen(30, start) < 120).toBe(true);   // 00:30 in
    expect(minutesSinceOpen(90, start) < 120).toBe(false);  // 01:30 out
  });
});

describe("sessionIndex", () => {
  const mk = (times: string[]): Bar[] => times.map((t) => ({ t: Date.parse(t), o: 1, h: 1, l: 1, c: 1, v: 1 }));

  it("keeps an overnight session together across the midnight boundary", () => {
    // 18:00, 20:00, 23:00 ET Monday and 00:30, 02:00 ET Tuesday are ONE session.
    const bars = mk([
      "2024-03-04T23:00:00Z", // 18:00 ET Mon
      "2024-03-05T01:00:00Z", // 20:00 ET Mon
      "2024-03-05T04:00:00Z", // 23:00 ET Mon
      "2024-03-05T05:30:00Z", // 00:30 ET Tue
      "2024-03-05T07:00:00Z", // 02:00 ET Tue
    ]);
    const clock = clockFor(bars, "America/New_York");
    const sess = sessionIndex(clock, 1080);
    expect(new Set([...sess]).size).toBe(1);
    // dayIndex, by contrast, splits them.
    expect(new Set([...clock.dayIndex]).size).toBe(2);
  });

  it("starts a new session at the next open", () => {
    const bars = mk([
      "2024-03-05T01:00:00Z", // 20:00 ET Mon
      "2024-03-05T05:30:00Z", // 00:30 ET Tue — same session
      "2024-03-05T23:30:00Z", // 18:30 ET Tue — next session
    ]);
    const sess = sessionIndex(clockFor(bars, "America/New_York"), 1080);
    expect(sess[0]).toBe(sess[1]);
    expect(sess[2]).toBe(sess[0] + 1);
  });

  it("is identical to dayIndex for a session already filtered to a non-wrapping window", () => {
    const bars = mk(["2024-03-05T14:30:00Z", "2024-03-05T18:00:00Z", "2024-03-05T20:59:00Z"]); // 09:30-15:59 ET
    const clock = clockFor(bars, "America/New_York");
    expect([...sessionIndex(clock, 570)]).toEqual([...clock.dayIndex]);
  });
});
