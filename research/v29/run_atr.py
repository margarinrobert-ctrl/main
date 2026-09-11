import sys, pandas as pd
sys.path.insert(0, "research"); sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21"); sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v27"); sys.path.insert(0, "research/v28")
sys.path.insert(0, "research/v29")
import v24ma as V, v29chop as Q
if __name__ == "__main__":
    out = pd.concat([Q.part2_atr_grid(m, 30) for m in ("NQ", "US30")], ignore_index=True)
    out.to_csv("results/v29/v29_atr_grid.csv", index=False)
    V.hdr("C. THE ATR REGIME GRID -- every declared cell against a same-selectivity control")
    for mkt in ("NQ", "US30"):
        for blk in ("research", "locked"):
            d = out[(out.market == mkt) & (out.block == blk)]
            base = d[d.family == "baseline"].iloc[0]
            print(f"\n   {mkt} {blk}: baseline {base.R:+.4f} R, PF {base.pf:.3f}, n {int(base.n)}")
            g = d[~d.family.isin(["baseline", "CHOP<=40 (shipped)"])]
            print(f"      cells {len(g)}   beating baseline R: {(g.R > base.R).mean():.0%}"
                  f"   clearing control at p<=0.05: {(g.p <= 0.05).mean():.0%}"
                  f"   (chance 5%)   mean excess {g.excess.mean():+.4f}")
            fam = g.groupby("family").agg(n=("R", "size"), R=("R", "mean"), pf=("pf", "mean"),
                                          exc=("excess", "mean"),
                                          hit=("p", lambda x: float((x <= 0.05).mean())))
            for k, r in fam.sort_values("exc", ascending=False).iterrows():
                print(f"      {k:<14}{int(r.n):>5} cells   R {r.R:>+8.4f}   PF {r.pf:>6.3f}"
                      f"   excess {r.exc:>+8.4f}   p<=0.05 in {r.hit:>4.0%}")
    V.hdr("   THE TOP 12 ATR CELLS BY RESEARCH EXCESS, with the locked read attached")
    r_ = out[(out.block == "research") & (~out.family.isin(["baseline", "CHOP<=40 (shipped)"]))]
    l_ = out[out.block == "locked"].set_index(["market", "family", "param"])
    top = r_.sort_values("excess", ascending=False).head(12)
    print(f"   {'market':<7}{'family':<12}{'param':<16}{'res n':>7}{'res R':>9}{'res p':>7}"
          f"{'|':>3}{'lk n':>6}{'lk R':>9}{'lk PF':>8}{'lk p':>7}")
    for _, r in top.iterrows():
        try:
            L = l_.loc[(r.market, r.family, r.param)]
        except KeyError:
            continue
        print(f"   {r.market:<7}{r.family:<12}{r.param:<16}{int(r.n):>7}{r.R:>+9.4f}{r.p:>7.3f}"
              f"{'|':>3}{int(L.n):>6}{L.R:>+9.4f}{L.pf:>8.3f}{L.p:>7.3f}")
