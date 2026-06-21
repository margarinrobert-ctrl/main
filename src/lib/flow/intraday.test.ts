import { describe, expect, it } from "vitest";
import type { GexSample } from "../gex-history";
import { intradayScan } from "./intraday";

function calmSeries(n: number): GexSample[] {
  const out: GexSample[] = [];
  let px = 100;
  for (let i = 0; i < n; i++) {
    px *= i % 2 === 0 ? 1.0005 : 0.9995;
    out.push({ t: i * 30000, spot: px, gex: 1e9 + (i % 2 === 0 ? 1e7 : -1e7), flip: 99, iv: 0.2 + (i % 2 === 0 ? 0.001 : -0.001) });
  }
  return out;
}

describe("intradayScan", () => {
  it("returns an empty/calm report with too few samples", () => {
    const r = intradayScan(calmSeries(1));
    expect(r.points.length).toBe(0);
    expect(r.current.state).toBe("calm");
  });

  it("stays calm on a quiet session and reports session range", () => {
    const r = intradayScan(calmSeries(15));
    expect(r.points.length).toBe(15);
    expect(r.current.state).toBe("calm");
    expect(r.rangePct).not.toBeNull();
  });

  it("flags a sudden intraday spot move as an anomaly", () => {
    const s = calmSeries(15);
    const last = s[s.length - 1];
    s.push({ t: last.t + 30000, spot: (last.spot as number) * 1.02, gex: 1e9, flip: 99, iv: 0.2 });
    const r = intradayScan(s);
    const move = r.current.flags.find((f) => f.metric === "Spot move");
    expect(move).toBeTruthy();
    expect(move!.direction).toBe("up");
    expect(r.current.state).toBe("anomalous");
    expect(r.points[r.points.length - 1].flagged).toBe(true);
  });
});
