"""Gold, 07:00-11:00 New York with an 11:00 flatten -- data admission and the clock, derived.

TWO FEEDS, and the difference between them decides which features are even legal.

  XAU_ISO_15m   494,235 bars 2004..2026, semicolon ISO export, REAL broker tick volume
                (mean 988, corr with the bar range +0.641). Registry clock New York + 7.
  XAUUSD15_MT   100,000 bars 2022-06-07..2026-08-28, tab-separated MT4 export, and its sixth
                column IS NOT VOLUME -- 99.62% of rows read exactly 15, sd 0.185, correlation
                with the bar's own range +0.0048 where real tick volume scores +0.641. It is the
                BAR'S LENGTH IN MINUTES. Confirmed again on this upload (sha256 fdd173af1c92a768,
                byte-identical to the registry copy).

  So on the MT feed every volume-derived feature is unavailable, not merely noisy, and a VWAP
  computed there is the unweighted mean of the typical price rather than a volume-weighted one.
  Volume features are therefore built on the ISO feed only and the MT feed is used for what it
  is genuinely good for: a SECOND PROVIDER over 2022-2026, which is the only way on this branch
  to ask whether a result is a property of gold or of one broker's tape.

THE CLOCK IS DERIVED HERE, NOT INHERITED. Gold does not key on the 09:30 equity open, so the
anchor has to come from gold's own activity: `derive_offset` finds the minute-of-day at which
mean |return| and mean range peak, separately in winter and in summer, and refuses a constant
shift if the two disagree. `STUDY_XAU` located gold's summer peak at raw 15:30 = 08:30 New York
to the minute; this re-derives it on both feeds rather than assuming it.

BLOCKS. Research = the first 65% of NY sessions on the ISO feed (the branch's standard split);
LOCKED = the remainder. The MT feed is treated as a single reserved read, because its span sits
inside the ISO feed's locked block and it is a different provider, not a different period.
"""
import numpy as np, pandas as pd

NY = "America/New_York"
ISO_PATH, MT_PATH = "data/XAU_ISO_15m.csv", "data/XAUUSD15_MT.csv"
NY_SHIFT_H = 7                     # registry value; re-derived in `derive_offset`
SPLIT = 0.65
START_ISO = "2010-01-01"           # pre-2010 excluded: 10.06% zero-range bars, median 5m volume 14
# gold's cost floor (research/xau/xau_core.py): USD/oz round turn and per-side slippage
COST_RT, SLIP = 0.30, 0.05


def load_iso(path=ISO_PATH, start=START_ISO, shift_h=NY_SHIFT_H):
    d = pd.read_csv(path, sep=";")
    d.columns = [c.strip().lower() for c in d.columns]
    ix = pd.to_datetime(d["date"], format="%Y.%m.%d %H:%M") - pd.Timedelta(hours=shift_h)
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")},
                     index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    return f[f.index >= start]


def load_mt(path=MT_PATH, shift_h=None):
    """THE MT FEED IS STAMPED IN UTC AND EVERY OTHER GOLD FEED HERE IS ON A BROKER SERVER.

    `derive_offset` settles it rather than the filename: on this feed winter prefers -5 and summer
    -4, which is EST and EDT, so the seasons DISAGREE and no fixed shift is correct. The ISO feed
    derives -7 in BOTH seasons, which is what a server that follows US daylight saving looks like.
    A fixed -7h here would put a 07:00 New York window at 09:00 or 10:00 -- a different session,
    not a slightly wrong one. Same trap the registry records for BTCUSDT. Pass `shift_h` only to
    reproduce a deliberately wrong reading; the default is a real tz conversion."""
    d = pd.read_csv(path, sep="\t", header=None,
                    names=["ts", "open", "high", "low", "close", "vol_is_minutes"])
    ts = pd.to_datetime(d["ts"])
    if shift_h is None:
        ix = ts.dt.tz_localize("UTC").dt.tz_convert(NY).dt.tz_localize(None)
    else:
        ix = ts - pd.Timedelta(hours=shift_h)
    f = pd.DataFrame({k: d[k].to_numpy(float) for k in ("open", "high", "low", "close")}, index=ix)
    f["volume"] = np.nan                     # NOT a typo: the column exists and is not volume
    return f[~f.index.duplicated(keep="first")].sort_index()


def volume_is_real(f):
    """The one check that must precede any volume rule (CLAUDE.md). Returns (verdict, rho)."""
    v = f["volume"].to_numpy(float)
    if not np.isfinite(v).any():
        return False, np.nan
    rho = float(np.corrcoef(v, (f["high"] - f["low"]).to_numpy())[0, 1])
    return bool(rho > 0.30), rho


def derive_offset(raw_ix, h, l, c, cand=range(0, 12)):
    """Gold's own anchor, winter and summer scored separately. Returns (best, winter, summer).

    A feed stamped on a broker server that FOLLOWS US daylight saving has ONE correct shift year
    round; a UTC-stamped feed does not, and the disagreement between the two seasons is what says
    which you have. Scored on mean |15m return| plus mean range, both normalised, at the
    minute-of-day the activity peaks -- gold's peak is its own, not the equity open.
    """
    r = np.abs(np.diff(np.log(c), prepend=np.nan))
    rng = (h - l) / c
    out = {}
    for season, mask in (("winter", np.isin(raw_ix.month, [12, 1, 2])),
                         ("summer", np.isin(raw_ix.month, [6, 7, 8]))):
        best = {}
        for s in cand:
            ix = raw_ix - pd.Timedelta(hours=s)
            mod = (ix.hour * 60 + ix.minute).to_numpy()
            g = pd.DataFrame({"m": mod[mask], "r": r[mask], "g": rng[mask]}).groupby("m").mean()
            z = (g.r / g.r.mean()) + (g.g / g.g.mean())
            best[s] = int(z.idxmax())
        # the shift that puts the peak nearest 08:30 New York, gold's documented anchor
        out[season] = min(best, key=lambda s: abs(best[s] - 510))
    agree = out["winter"] == out["summer"]
    return (out["winter"] if agree else None), out["winter"], out["summer"]


def assemble(f, win_start=420, win_end=660, split=SPLIT, atr_len=14):
    """Everything downstream needs, on a New York wall clock. Window default 07:00-11:00."""
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    v = f["volume"].to_numpy(float)
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy(np.int64)
    day = ix.normalize().values.astype("datetime64[D]").astype(np.int64)
    wd = ix.dayofweek.to_numpy()
    inw = (mod >= win_start) & (mod < win_end) & (wd < 5)

    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / atr_len, adjust=False).mean().to_numpy()

    D = dict(o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, day=day, wd=wd, inw=inw,
             atr=atr, tr=tr, n=len(c), win_start=win_start, win_end=win_end)
    us = np.unique(day[inw])
    D["cut_day"] = int(us[int(split * len(us))])
    D["blk"] = (day >= D["cut_day"]).astype(np.int64)
    D["cut_date"] = str(pd.Timestamp(D["cut_day"], unit="D").date())
    D["n_sessions"] = len(us)
    # the LAST in-window bar of each session: a flatten fills at the NEXT bar's open, so the order
    # must be submitted on the bar before the cutoff (STUDY_V63 / the `flat_open` engine change).
    lastw = np.zeros(len(c), bool)
    idx = np.flatnonzero(inw)
    if len(idx):
        dd = day[idx]
        lastw[idx[np.flatnonzero(np.diff(dd, append=dd[-1] + 1) != 0)]] = True
    D["last_win"] = lastw
    return D
