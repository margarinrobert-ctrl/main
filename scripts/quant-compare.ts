/**
 * Summarise several study reports side by side.
 *
 *   npx tsx scripts/quant-compare.ts docs/STUDY_NQ.md docs/r2/*.md --out docs/r2/COMPARISON.md
 *
 * A research cycle produces one study per configuration, and the interesting signal lives in the
 * DIFFERENCES between them — what changed when execution got cheaper, when the session narrowed,
 * when the timeframe halved. Reading that off four separate reports invites cherry-picking, so it
 * is extracted mechanically here instead.
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

interface StudyRow {
  file: string;
  title: string;
  session: string;
  fill: string;
  costTicks: string;
  budget: string;
  best: { id: string; sharpe: string; net: string; t: string; trades: string } | null;
  gatesBest: string;
  cleared: string;
}

/** Pull the cells out of a markdown table row. */
const cells = (line: string): string[] => line.split("|").slice(1, -1).map((c) => c.trim());

function parseStudy(file: string): StudyRow {
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  const field = (label: string): string => {
    const row = lines.find((l) => l.startsWith(`| ${label} |`));
    return row ? cells(row)[1] : "—";
  };

  // Walk-forward table: the out-of-sample record, which is the only comparable number.
  const wfStart = lines.findIndex((l) => l.includes("Walk-forward out-of-sample"));
  let best: StudyRow["best"] = null;
  if (wfStart >= 0) {
    for (let i = wfStart; i < Math.min(lines.length, wfStart + 40); i++) {
      const c = cells(lines[i]);
      if (c.length < 10 || c[0] === "strategy" || c[0].startsWith("---")) continue;
      const sharpe = Number(c[5]);
      if (!Number.isFinite(sharpe)) continue;
      if (!best || sharpe > Number(best.sharpe)) best = { id: c[0], trades: c[2], net: c[3], sharpe: c[5], t: c[6] };
    }
  }

  const verdictStart = lines.findIndex((l) => l.startsWith("## 12. Verdict"));
  let gatesBest = "—";
  let cleared = "0";
  if (verdictStart >= 0) {
    let bestGates = -1;
    let clearedCount = 0;
    for (let i = verdictStart; i < lines.length; i++) {
      const c = cells(lines[i]);
      if (c.length !== 3 || c[0] === "strategy" || c[0].startsWith("---")) continue;
      const passed = Number(String(c[1]).split("/")[0]);
      if (Number.isFinite(passed) && passed > bestGates) { bestGates = passed; gatesBest = `${c[0]} ${c[1]}`; }
      if (c[2].includes("cleared all")) clearedCount++;
    }
    cleared = String(clearedCount);
  }

  const budgetRow = lines.find((l) => l.includes("largest credible conditional edge"));
  const title = (lines.find((l) => l.startsWith("# ")) ?? "# study").slice(2).trim();

  return {
    file,
    title,
    session: field("session studied"),
    fill: field("fill model"),
    costTicks: (text.match(/\*\*([\d.]+) ticks \(\$[\d.]+\) per round turn\*\*/) ?? [])[1] ?? "—",
    budget: budgetRow ? cells(budgetRow)[1] : "—",
    best,
    gatesBest,
    cleared,
  };
}

function main() {
  const args = process.argv.slice(2);
  const outIdx = args.indexOf("--out");
  const out = outIdx >= 0 ? args[outIdx + 1] : "";
  const files = (outIdx >= 0 ? args.slice(0, outIdx) : args).filter((f) => f.endsWith(".md"));
  if (!files.length) {
    console.error("usage: quant-compare <study.md> [study.md ...] [--out comparison.md]");
    process.exit(1);
  }

  const rows = files.map(parseStudy);
  const md: string[] = [];
  md.push("# Study comparison");
  md.push("");
  md.push("Extracted mechanically from each study's own tables — the walk-forward line is the only");
  md.push("comparable number, since it is the sole out-of-sample record every configuration produces.");
  md.push("");
  md.push("| study | session | fill | cost (ticks) | alpha budget | best OOS strategy | OOS trades | net (ticks) | OOS Sharpe | t (HAC) | best gates | cleared all |");
  md.push("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |");
  for (const r of rows) {
    md.push(
      `| ${r.title} | ${r.session} | ${r.fill} | ${r.costTicks} | ${r.budget} | ${r.best?.id ?? "—"} | ${r.best?.trades ?? "—"} | ` +
        `${r.best?.net ?? "—"} | ${r.best?.sharpe ?? "—"} | ${r.best?.t ?? "—"} | ${r.gatesBest} | ${r.cleared} |`,
    );
  }
  md.push("");
  const anyCleared = rows.some((r) => Number(r.cleared) > 0);
  md.push(
    anyCleared
      ? `**${rows.filter((r) => Number(r.cleared) > 0).map((r) => r.title).join(", ")}** produced at least one strategy clearing every gate.`
      : `**No configuration produced a strategy clearing every gate.** Changing execution, session and timeframe moved the numbers without changing the conclusion.`,
  );
  md.push("");

  const text = md.join("\n") + "\n";
  console.log(text);
  if (out) {
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, text);
    console.error(`wrote ${out}`);
  }
}

main();
