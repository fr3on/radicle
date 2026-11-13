import statistics as st

from helpers import EGYPT, GREELEY, REPO, needs_egypt, needs_greeley
from radicle.ingest.loaders import load_field
from radicle.models.crop import load_params, simulate
from radicle.models.et0 import et0_daily


@needs_egypt
def test_egypt_trials_load_and_simulate():
    from radicle.ingest.dssat import load_all
    T = load_all(str(EGYPT))
    assert len(T) == 22 and {t.exp for t in T} == {"ASWN1101", "BSUF1101", "MNFY1101", "SARS1101"}
    P = load_params()
    pred, obs = [], []
    for t in T:
        s_ = simulate(t.weather, t.site, t.mgmt, P)["summary"]
        assert s_["matured"]
        pred.append(s_["yield_t_ha"]); obs.append(t.obs_yield_t_ha)
    import statistics as st
    assert 3 < st.mean(pred) < 9 and 5 < st.mean(obs) < 9
    assert st.correlation(pred, obs) > 0.2          # weak skill documented in docs/DATA-SOURCES.md; guards regressions


@needs_egypt
def test_egypt_hotter_site_matures_earlier():
    from radicle.ingest.dssat import load_all
    days = {}
    for t in load_all(str(EGYPT)):
        days.setdefault(t.exp[:4], []).append(simulate(t.weather, t.site, t.mgmt, load_params())["summary"]["days"])
    import statistics as st
    assert st.mean(days["ASWN"]) < st.mean(days["BSUF"])     # Aswan (south) is hotter than Beni Suef


def test_committed_real_maize_fields_follow_irrigation():
    P = load_params("maize_greeley")
    res = {}
    for t in (1, 6):
        w, s, m, obs = load_field(REPO / f"data/greeley-2010-t{t}")
        r = simulate(w, s, m, P)["summary"]
        assert r["matured"] and r["ended_by"] == "frost" and r["days"] > 120
        res[t] = (r["yield_t_ha"], {v: x for _, v, x in obs}["yield_t_ha"], r["irrigation_mm"])
    assert res[1][2] > 3 * res[6][2]                 # T1 gets far more water than T6
    assert res[1][0] > res[6][0] and res[1][1] > res[6][1]   # model and observations agree on the direction
    assert 0.5 < res[1][0] / res[1][1] < 2.5          # same order of magnitude (placeholder WP overestimates; see docs)


@needs_greeley
def test_greeley_et0_matches_published_eto():
    import statistics as st
    from radicle.ingest import greeley
    pairs = []
    for y in greeley.YEARS:
        w, eto = greeley.load_weather(str(GREELEY), y)
        pairs += [(et0_daily(x["tmin"], x["tmax"], x["rh"], x["wind"], x["rs"], greeley.LAT, k.timetuple().tm_yday, greeley.ELEV), eto[k])
                  for k, x in w.items() if k in eto and 130 <= k.timetuple().tm_yday <= 280]
    a, b = zip(*pairs)
    assert abs(st.mean(x - y for x, y in pairs)) < 0.4 and st.correlation(a, b) > 0.95


@needs_greeley
def test_greeley_model_ranks_irrigation_treatments():
    import statistics as st
    from radicle.ingest import greeley
    P = load_params("maize_greeley")
    sim, obs, by_year = [], [], {}
    for t, w in greeley.load_all(str(GREELEY)):
        s = simulate(w, t.site, t.mgmt, P)["summary"]
        assert s["matured"]
        sim.append(s["yield_t_ha"]); obs.append(t.obs_grain_t_ha)
        by_year.setdefault(t.year, []).append((s["yield_t_ha"], t.obs_grain_t_ha))
    assert st.correlation(sim, obs) > 0.85                                   # measured 0.94
    assert all(st.correlation(*zip(*v)) > 0.9 for v in by_year.values())     # irrigation response within each year
    assert st.mean(sim) > 1.2 * st.mean(obs)                                 # documents the known overestimate; update when calibrated
