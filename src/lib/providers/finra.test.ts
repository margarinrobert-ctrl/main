import { describe, expect, it } from "vitest";
import { parseFinraDaily } from "./finra";

describe("parseFinraDaily", () => {
  const file = [
    "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market",
    "20260619|SPY|18000000|50000|40000000|Q",
    "20260619|AAPL|9000000|0|20000000|Q",
    "20260619|QQQ|6000000|10000|15000000|B",
    "Records: 3", // trailing footer FINRA appends
    "",
  ].join("\n");

  it("parses pipe-delimited rows into a per-symbol off-exchange map", () => {
    const m = parseFinraDaily(file);
    expect(m.size).toBe(3);
    expect(m.get("SPY")).toEqual({ short: 18000000, shortExempt: 50000, total: 40000000 });
    expect(m.get("AAPL")?.total).toBe(20000000);
  });

  it("skips the header, the record-count footer and blank lines", () => {
    const m = parseFinraDaily(file);
    expect(m.has("SYMBOL")).toBe(false);
    expect([...m.keys()].some((k) => /record/i.test(k))).toBe(false);
  });

  it("tolerates CRLF line endings and is empty for junk input", () => {
    expect(parseFinraDaily("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\r\n20260619|TSLA|1|0|2|Q\r\n").get("TSLA")?.total).toBe(2);
    expect(parseFinraDaily("not a finra file").size).toBe(0);
  });
});
