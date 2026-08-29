import sys, warnings, numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, "research"); sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v27"); sys.path.insert(0, "research/v30")
import optuna, v30opt as O
optuna.logging.set_verbosity(optuna.logging.WARNING)

N_TRIALS = 400
COST = {"NQ": 1.72, "US30": 2.50}


def space(t):
    return dict(
        entry1  = t.suggest_int("entry1", 10, 80),
        exit1   = t.suggest_int("exit1", 5, 40),
        atr_len = t.suggest_int("atr_len", 10, 30),
        atr_mult= t.suggest_float("atr_mult", 1.0, 5.0, step=0.1),
        pyr_step= t.suggest_float("pyr_step", 0.0, 1.5, step=0.1),
        max_units=t.suggest_int("max_units", 1, 4),
        adx_max = t.suggest_categorical("adx_max", [0.0, 18.0, 22.0, 26.0, 30.0, 35.0, 45.0]),
        ext_max = t.suggest_categorical("ext_max", [0.0, 1.5, 2.5, 3.5, 5.0, 8.0]),
        ao_min  = t.suggest_categorical("ao_min", [-999.0, -0.5, 0.0, 0.25, 0.5, 1.0]),
        skip_win= t.suggest_categorical("skip_win", [True, False]))


if __name__ == "__main__":
    rows = []
    for mkt in ("NQ", "US30"):
        b = O.load(mkt, 30)
        u = np.unique(b["sess"]); cut = u[int(len(u) * 0.65)]
        res, lk = b["sess"] < cut, b["sess"] >= cut
        for side in (1, -1):
            def obj(t, b=b, res=res, side=side, mkt=mkt):
                p = space(t)
                s = O.score(b, p, side, res, COST[mkt])
                if s is None:
                    return -10.0
                t.set_user_attr("res", s)
                return s["sharpe"]
            st = optuna.create_study(direction="maximize",
                                     sampler=optuna.samplers.TPESampler(seed=7, n_startup_trials=60))
            st.optimize(obj, n_trials=N_TRIALS, show_progress_bar=False)
            for t in st.trials:
                if t.value is None or t.value <= -9.9:
                    continue
                p = dict(t.params)
                r = t.user_attrs.get("res")
                l = O.score(b, p, side, lk, COST[mkt])          # recorded, NEVER optimised on
                rows.append(dict(market=mkt, side=("long" if side > 0 else "short"),
                                 **p, res_sharpe=r["sharpe"], res_pf=r["pf"], res_n=r["n"],
                                 res_R=r["R"], res_dd=r["dd"],
                                 lk_sharpe=(l["sharpe"] if l else np.nan),
                                 lk_pf=(l["pf"] if l else np.nan),
                                 lk_n=(l["n"] if l else 0), lk_R=(l["R"] if l else np.nan),
                                 lk_dd=(l["dd"] if l else np.nan)))
            print(f"   {mkt} {'long' if side>0 else 'short':<5} done: "
                  f"{len(st.trials)} trials, best research Sharpe {st.best_value:+.3f}", flush=True)
    pd.DataFrame(rows).to_csv("results/v30/v30_trials.csv", index=False)
    print(f"   wrote {len(rows)} scorable trials")
