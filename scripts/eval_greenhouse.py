"""Fit the greenhouse model on 5 compartments and predict the 6th (leave-one-compartment-out), 4 harvest dates each.
Baseline: mean of the other compartments' observations at the same date index."""
import itertools, statistics as st
from dataclasses import replace
from radicle.ingest.agc import TEAMS, load_daily, load_density, load_harvest
from radicle.models.greenhouse import GHParams, simulate

ROOT = "data/external/agc4-dwarf-tomato/x/autonomous_greenhouse_challenge4_timeseries"
daily = {t: load_daily(ROOT, t) for t in TEAMS}
dens = {t: load_density(ROOT, t) for t in TEAMS}
harv = load_harvest(ROOT, daily)
import sys
if "--exclude-final" in sys.argv:   # ripe fruit was picked before the final harvest (no removal record): drop it
    harv = {t: {d: v for d, v in dd.items() if d != max(dd)} for t, dd in harv.items()}
print("harvest dates per team:", {t: sorted(str(d) for d in harv[t]) for t in TEAMS})

def predict(team, p):
    sim = simulate(daily[team], dens[team], p)
    return {d: sim[d] for d in harv[team] if d in sim}

def err(teams, p):
    e = []
    for t in teams:
        pr = predict(t, p)
        for d, (fw, n) in harv[t].items():
            if d in pr: e.append((pr[d] - fw) / fw)
    return st.mean(x * x for x in e) ** .5 if e else 9

grid = [replace(GHParams(), lue_g_mol=l, tt_flower=f) for l, f in itertools.product([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], [150, 250, 350, 450, 550])]
print("\nObserved mean fruit FW per plant (g):")
for t in TEAMS: print(f"  {t:11}", {str(d): round(v[0]) for d, v in sorted(harv[t].items())}, "PAR mean", round(st.mean(x['par_mol'] for x in daily[t].values()), 1), "mol/m2/d")
tot_m, tot_b, n = [], [], 0
print("\nLeave-one-compartment-out (relative RMSE of fruit FW per plant):")
for held in TEAMS:
    train = [t for t in TEAMS if t != held]
    best = min(grid, key=lambda p: err(train, p))
    pr = predict(held, best)
    em = [(pr[d] - v[0]) / v[0] for d, v in harv[held].items() if d in pr]
    # baseline: mean observed FW of the other compartments at the same ordinal harvest
    base = []
    for i, (d, v) in enumerate(sorted(harv[held].items())):
        others = [sorted(harv[t].items())[i][1][0] for t in train if len(harv[t]) > i]
        base.append((st.mean(others) - v[0]) / v[0])
    tot_m += em; tot_b += base
    print(f"  {held:11} fitted lue={best.lue_g_mol} tt_flower={best.tt_flower} | model rel.err {[round(x,2) for x in em]} | baseline {[round(x,2) for x in base]}")
rm = lambda e: (st.mean(x * x for x in e)) ** .5
print(f"\nOverall relative RMSE: model {rm(tot_m):.2f} vs baseline (mean of others) {rm(tot_b):.2f}; n={len(tot_m)}")
