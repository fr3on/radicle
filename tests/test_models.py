import copy
import tempfile
from dataclasses import replace
from datetime import timedelta

import pytest

from helpers import REPO, field, tiny_weather
from radicle.ingest.loaders import load_field
from radicle.models.crop import Management, Site, load_params, simulate
from radicle.models.et0 import et0_daily


def test_et0_fao56_example():
    # FAO-56 Example 18 (Uccle, Belgium, 6 July): ET0 about 3.9 mm/day. Inputs: tmin 12.3, tmax 21.5,
    # RH mean ~ 73.5% (derived from ea=1.409/es=1.997), u2 ~2.078 m/s, Rs 22.07, lat 50.8N, elev 100 m, doy 187.
    v = et0_daily(12.3, 21.5, 70.5, 2.078, 22.07, 50.8, 187, 100)
    assert 3.4 < v < 4.4, v


def test_et0_tight():
    # FAO-56 Example 18 published ET0 = 3.88 mm/day (ea=1.409 kPa -> RH 70.5 %)
    assert abs(et0_daily(12.3, 21.5, 70.5, 2.078, 22.07, 50.8, 187, 100) - 3.88) < 0.05


def test_end_to_end_and_salinity_effect():
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        P = load_params()
        good = simulate(w, s, m, P)["summary"]
        assert good["matured"] and 0 < good["yield_t_ha"] < 15
        m.irrigation = {d: (mm, 30.0) for d, (mm, ec) in m.irrigation.items()}
        salty = simulate(w, s, m, P)["summary"]
        assert salty["yield_t_ha"] < good["yield_t_ha"]


def test_sowing_outside_weather_raises():
    from radicle.scenarios import run_scenario
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        try:
            run_scenario(w, s, m, load_params(), sow_shift_days=-30)
            assert False
        except ValueError as e:
            assert "No weather data" in str(e)


def test_initial_salinity_not_diluted_by_root_growth():
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        m.irrigation = {}
        w = {d: dict(x, rain=0.0) for d, x in w.items()}
        r = simulate(w, s, m, load_params())["daily"]
        assert r[-1]["ece"] == pytest.approx(s.initial_ece, rel=0.15)   # no inputs, no drainage -> ECe ~ constant


def test_irrigation_salt_units():
    # with no drainage, ECe rise from irrigation must be bounded by pure evapo-concentration of the water's own EC
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        s.initial_ece = 0.0
        w = {d: dict(x, rain=0.0) for d, x in w.items()}
        m.irrigation = {m.sow_date + timedelta(days=30): (50.0, 4.0)}
        r = simulate(w, s, m, load_params())["daily"]
        day = r[31]
        # salt = 50*4 = 200 (ECsw*mm) over wfc = 1000*fc*zr; ECe = 0.5*salt/wfc
        zr_mm = day["taw_mm"] / (1000 * (s.fc - s.wp)) * 1000 * s.fc
        assert day["ece"] == pytest.approx(0.5 * 200 / zr_mm, rel=0.1)


def test_fungicide_protects_for_a_window():
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        P = load_params()
        w = {d: dict(x, rh=95.0, tmin=8.0, tmax=18.0) for d, x in w.items()}
        base = simulate(w, s, m, P)
        mf = copy.deepcopy(m)
        day = m.sow_date + timedelta(days=90)
        mf.fungicide = {day: 1.0}
        sp = simulate(w, s, mf, P)["daily"]
        i = 90
        assert sp[i + 10]["disease"] == sp[i]["disease"]               # frozen for the whole window
        assert sp[i + 20]["disease"] > sp[i]["disease"]                # resumes afterwards
        assert sp[-1]["disease"] <= base["daily"][-1]["disease"]


def test_clip_gdd_caps_tmax_and_floors_tmin():
    d0, w = tiny_weather(3, {0: dict(tmin=0.0, tmax=40.0)})
    P = replace(load_params("maize"), frost_kill_tmin=None)
    r = simulate(w, Site(), Management(sow_date=d0), P)["daily"]
    assert r[0]["gdd"] == pytest.approx((30 + 10) / 2 - 10)       # tmax capped at 30, tmin floored at 10


def test_frost_after_anthesis_ends_season():
    d0, w = tiny_weather(60, {30: dict(tmin=-5.0, tmax=8.0)})
    P = replace(load_params("maize"), gdd_dev_end=20.0, gdd_mid_start=30.0, gdd_anthesis=50.0, gdd_late_start=60.0, gdd_maturity=5000.0)
    s = simulate(w, Site(), Management(sow_date=d0), P)["summary"]
    assert s["ended_by"] == "frost" and s["matured"] and s["days"] == 31
    # same frost before anthesis does not end the season
    P2 = replace(P, gdd_dev_end=2000.0, gdd_mid_start=3000.0, gdd_anthesis=4000.0, gdd_late_start=4500.0)
    assert simulate(w, Site(), Management(sow_date=d0), P2)["summary"]["ended_by"] == "weather_end"


def test_weather_gap_raises_instead_of_truncating():
    d0, w = tiny_weather(40)
    del w[d0 + timedelta(days=20)]
    with pytest.raises(ValueError, match="Weather gap"):
        simulate(w, Site(), Management(sow_date=d0), load_params("maize"))


def test_water_stress_appears_when_underirrigated():
    w, s, m, _ = load_field(REPO / "data/demo")
    w = {d: dict(x, rain=0.0) for d, x in w.items()}
    m.irrigation = {d: (mm * 0.2, ec) for d, (mm, ec) in m.irrigation.items()}
    r = simulate(w, s, m, load_params())
    assert min(d["ks_water"] for d in r["daily"]) < 0.9
    assert r["summary"]["yield_t_ha"] < simulate(*load_field(REPO / "data/demo")[:3], load_params())["summary"]["yield_t_ha"]


def test_committed_demo_data_runs():
    w, s, m, obs = load_field(REPO / "data/demo")
    r = simulate(w, s, m, load_params())
    assert r["summary"]["matured"] and 4 < r["summary"]["yield_t_ha"] < 12
    assert r["summary"]["drainage_mm"] >= 0 and all(0 <= d["disease"] <= 1 for d in r["daily"])
