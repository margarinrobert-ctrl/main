"""Finalize the EMA-cross search: pick the winner by a rule DECLARED BEFORE the
results were seen, patch the Pine defaults, lint, and log.

Selection rule (fixed now, not tuned after):
  Among NAS research-block cells with n >= 100 trades, take the one with the
  highest excess over the matched control SUBJECT TO exp > 0 (positive after
  costs) AND p < 0.05. If no cell meets that, there is NO SURVIVOR and the Pine
  keeps the plain-Donchian defaults with a note saying so.
  Walk-forward is reported alongside but is the OOS verdict, not the selector -
  selecting on it would make it in-sample.
"""
import pandas as pd, numpy as np, json, re, sys, subprocess
sys.path.insert(0, "/home/user/main/research")
import pine_lint as PL
sys.path.insert(0, "/home/user/main/research/donchian")
import ledger

R = pd.read_parquet("/home/user/main/data/donchian/emacross.parquet")
V = R.dropna(subset=["p"])
nas = V[(V.sym == "NAS") & (V.n >= 100)]
elig = nas[(nas.exp > 0) & (nas.p < 0.05)].sort_values("excess", ascending=False)

print("=" * 96)
print(f"FINALIZE - {len(R):,} configs searched, {len(nas):,} NAS cells with >=100 trades")
print(f"  eligible (exp>0 AND p<0.05): {len(elig)}   (chance at p<0.05 alone ~ {0.05*len(nas):.0f})")
print("=" * 96)

pine = "/home/user/main/pine/DonchianEmaCross.pine"
src = open(pine).read()

if len(elig) == 0:
    verdict = "NO SURVIVOR"
    win = None
    print("  No configuration is positive after costs at p<0.05. Pine keeps plain defaults.")
else:
    win = elig.iloc[0]
    verdict = "RESEARCH WINNER (unvalidated until walk-forward)"
    print(f"  winner: n={int(win.n_entry)} EMA {int(win.fast)}/{int(win.slow)} mode={win['mode']} "
          f"atr={win.atr} geom={win.stop}/{win.targ}")
    print(f"          trades={int(win.n)} exp={win.exp:+.2f} excess={win.excess:+.2f} "
          f"z={win.z:+.2f} p={win.p:.4f} sel={win.sel:.2f}")
    # patch defaults
    src = re.sub(r'lenEntry   = input\.int\(\d+,', f'lenEntry   = input.int({int(win.n_entry)},', src)
    src = re.sub(r'emaFast    = input\.int\(\d+,', f'emaFast    = input.int({int(win.fast)},', src)
    src = re.sub(r'emaSlow    = input\.int\(\d+,', f'emaSlow    = input.int({int(win.slow)},', src)
    src = re.sub(r'emaMode    = input\.string\("[^"]+"', f'emaMode    = input.string("{win["mode"]}"', src)
    src = re.sub(r'atrFilter  = input\.string\("[^"]+"', f'atrFilter  = input.string("{win.atr}"', src)
    src = re.sub(r'stopMult   = input\.float\([\d.]+,', f'stopMult   = input.float({win.stop},', src)
    src = re.sub(r'targMult   = input\.float\([\d.]+,', f'targMult   = input.float({win.targ},', src)

# write the results block into the header, replacing the placeholder box
def block():
    lines = ["// ┌───────────────────────────────────────────────────────────────────────────────────────────┐"]
    if win is None:
        lines += ["// │ SEARCH RESULT: NO SURVIVOR.                                                                │",
                  "// │ 2,160 configurations of Donchian x EMA-cross x ATR were searched on the research block.     │",
                  "// │ None was positive after costs at p<0.05 against the matched control. The defaults below   │",
                  "// │ are a plain Donchian breakout. The EMA cross adds nothing measurable here.                 │"]
    else:
        lines += [f"// │ SEARCH RESULT: research-block winner of 2,160 configurations. NOT yet out-of-sample.        │",
                  f"// │   n={int(win.n_entry)}  EMA {int(win.fast)}/{int(win.slow)}  {win['mode']:<8} atr={win.atr:<10} geom {win.stop}/{win.targ}"
                  f"{' '*(35-len(f'{win.atr}')-len(f'{win.stop}/{win.targ}'))}│",
                  f"// │   {int(win.n)} trades  exp {win.exp:+.2f}  excess {win.excess:+.2f}  z {win.z:+.2f}  p {win.p:.4f}"
                  f"{' '*(40-len(f'{win.exp:+.2f}{win.excess:+.2f}{win.z:+.2f}{win.p:.4f}'))}│",
                  "// │   Read the walk-forward verdict in docs/donchian/STUDY_DONCHIAN.md before believing it.       │"]
    lines += ["// └───────────────────────────────────────────────────────────────────────────────────────────┘"]
    return "\n".join(lines)

src = re.sub(r"// ┌─+┐\n(?:// │.*│\n)+// └─+┘", block(), src, count=1)
open(pine, "w").write(src)
probs = PL.check(src, "DonchianEmaCross")
print(f"\n  Pine: {'LINT CLEAN' if not probs else probs}")

json.dump({"verdict": verdict, "n_searched": int(len(R)), "n_eligible": int(len(elig)),
           "winner": None if win is None else {k: (float(v) if isinstance(v,(int,float,np.floating)) else str(v))
                                                for k, v in win.items()}},
          open("/home/user/main/docs/donchian/emacross_result.json", "w"), indent=2)
print("  written: docs/donchian/emacross_result.json")
