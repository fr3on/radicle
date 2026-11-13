"""Compare radicle with the INVITE wheat trials. Usage: python scripts/eval_trials.py [--calibrate]"""
import json, random, statistics as st, sys
from dataclasses import replace
from radicle.ingest.icasa import load_country, read_wht, to_model_weather, check_vp_scale
from radicle.models.crop import load_params, simulate
from radicle.calibrate import TUNABLE

ROOT = "data/external/eu-wheat-vct/x"
COUNTRIES = ["Czech_Republic", "Hungary", "Switzerland"]


def corr(a, b):
    if len(a) < 3: return float("nan")
    return st.correlation(a, b)


def run(trials, P):
    rows = []
    for t in trials:
        raw, _ = read_wht(t.weather_path)
        w = to_model_weather(raw)
        try:
            r = simulate(w, t.site, t.mgmt, P)
        except ValueError:
            continue
        s = r["summary"]
        if not s["matured"]:
            continue
        rows.append((t, s))
    return rows


def metrics(rows):
    out = {}
    y = [(s["yield_t_ha"], t.yield_t_ha) for t, s in rows if t.yield_t_ha]
    if y:
        p, o = zip(*y)
        out["yield"] = dict(n=len(y), obs_mean=round(st.mean(o), 2), sim_mean=round(st.mean(p), 2),
                            rmse=round((st.mean([(a - b) ** 2 for a, b in y])) ** .5, 2), r=round(corr(p, o), 2))
    from datetime import date
    h = [((date.fromisoformat(s["anthesis_date"]) - t.heading_date).days) for t, s in rows if t.heading_date and s["anthesis_date"]]
    if h:
        out["anthesis_minus_ear_emergence_days"] = dict(n=len(h), mean=round(st.mean(h), 1), sd=round(st.pstdev(h), 1))
    m = [((date.fromisoformat(s["harvest_date"]) - t.maturity_date).days) for t, s in rows if t.maturity_date]
    if m:
        out["sim_maturity_minus_obs_days"] = dict(n=len(m), mean=round(st.mean(m), 1), sd=round(st.pstdev(m), 1))
    return out


def loss(rows):
    from datetime import date
    e, n = 0.0, 0
    for t, s in rows:
        if t.yield_t_ha:
            e += ((s["yield_t_ha"] - t.yield_t_ha) / t.yield_t_ha) ** 2; n += 1
        if t.maturity_date:
            e += ((date.fromisoformat(s["harvest_date"]) - t.maturity_date).days / 15) ** 2; n += 1
        if t.heading_date and s["anthesis_date"]:
            e += ((date.fromisoformat(s["anthesis_date"]) - t.heading_date).days / 10) ** 2; n += 1
    return e / n if n else 1e9


if __name__ == "__main__":
    trials = []
    for c in COUNTRIES:
        try:
            trials += load_country(ROOT, c)
        except Exception as ex:
            print("skip", c, repr(ex))
    P = load_params()
    print("trials loaded:", len(trials), "years", min(t.year for t in trials), max(t.year for t in trials))
    rows = run(trials, P)
    print("simulated and matured:", len(rows))
    print("DEFAULT (placeholder) params:", json.dumps(metrics(rows), indent=1))
    if "--calibrate" in sys.argv:
        train = [t for t in trials if t.year <= 2012]
        test = [t for t in trials if t.year > 2012]
        rnd = random.Random(0)
        rnd.shuffle(train)
        sub = train[:50]
        keys = dict(TUNABLE)
        keys.update(gdd_anthesis=(700, 1500), gdd_maturity=(1500, 2600), gdd_late_start=(1100, 2000))
        best, bl = P, loss(run(sub, P))
        print("start loss", round(bl, 3))
        for it in range(250):
            changes = {}
            for k in rnd.sample(list(keys), 2):
                lo, hi = keys[k]
                changes[k] = min(hi, max(lo, getattr(best, k) + rnd.gauss(0, (hi - lo) * 0.1)))
            try:
                c = replace(best, **changes)
            except ValueError:          # stage thresholds out of order
                continue
            l = loss(run(sub, c))
            if l < bl: best, bl = c, l
        print("calibrated on", len(sub), "train trials (<=2012); loss", round(bl, 3))
        timing = ("gdd_anthesis", "gdd_late_start", "gdd_maturity")
        best.save("params/wheat_eu_calibrated.json", calibrated={k: ("calibrated:eu-wheat-vct (timing only; trusted)" if k in timing else "calibrated:eu-wheat-vct (unconstrained by the data, do not use)") for k in keys}, note="Wheat placeholders with growth-stage timing calibrated on INVITE trials; use for timing only (see _provenance).")
        print("HOLDOUT (years > 2012), default params:", json.dumps(metrics(run(test, P))))
        print("HOLDOUT (years > 2012), calibrated params:", json.dumps(metrics(run(test, best)), indent=1))
