"""Unit tests of the individual process modules and result types."""
import pytest

from helpers import field
from radicle.metrics import FitStats
from radicle.models import disease, growth, phenology, salinity, water
from radicle.models.crop import Management, Site, load_params, simulate
from radicle.models.params import load_params as lp


def test_interpolate_is_flat_outside_and_linear_inside():
    pts = [(0, 1.0), (10, 3.0), (20, 3.0)]
    assert phenology.interpolate(-5, pts) == 1.0 and phenology.interpolate(5, pts) == 2.0
    assert phenology.interpolate(15, pts) == 3.0 and phenology.interpolate(99, pts) == 3.0


def test_kc_curve_hits_its_plateaus():
    P = lp("wheat")
    assert phenology.crop_coefficient(P, 0) == P.kc_ini
    assert phenology.crop_coefficient(P, P.gdd_mid_start) == pytest.approx(P.kc_mid)
    assert phenology.crop_coefficient(P, P.gdd_maturity) == pytest.approx(P.kc_end)


def test_root_depth_grows_to_site_maximum_at_anthesis():
    P, S = lp("wheat"), Site(root_depth_max_m=1.2)
    assert phenology.root_depth(P, S, 0) == P.root_depth_min_m
    assert phenology.root_depth(P, S, P.gdd_anthesis) == pytest.approx(1.2)
    assert phenology.root_depth(P, S, 10 * P.gdd_anthesis) == pytest.approx(1.2)


def test_water_balance_conserves_water_and_drains_above_field_capacity():
    P, S = lp("wheat"), Site()
    rz = water.root_zone(P, S, 1.0)
    # no drainage case: depletion changes by ET - rain - irrigation
    dr, drain = water.balance_step(50.0, 5.0, 2.0, 1.0, rz)
    assert drain == 0 and dr == pytest.approx(50 + 5 - 2 - 1)
    # drainage case: 10 mm of depletion, 30 mm irrigation -> 20 mm drains, depletion floors at 0
    dr, drain = water.balance_step(10.0, 0.0, 0.0, 30.0, rz)
    assert dr == 0.0 and drain == pytest.approx(20.0)
    # depletion never exceeds TAW
    assert water.balance_step(rz.taw - 1, 50.0, 0.0, 0.0, rz)[0] == rz.taw


def test_water_stress_is_one_within_raw_and_zero_at_taw():
    rz = water.root_zone(lp("wheat"), Site(), 1.0)
    assert water.water_stress(rz.raw, rz) == 1.0 and water.water_stress(rz.taw, rz) == 0.0
    assert 0 < water.water_stress((rz.raw + rz.taw) / 2, rz) < 1


def test_effective_rain_ignores_small_events():
    assert water.effective_rain(1.5) == 0 and water.effective_rain(12.0) == pytest.approx(8.0)


def test_leaching_removes_salt_in_proportion_to_drainage():
    assert salinity.leach(100.0, 300.0, 100.0) == pytest.approx(75.0)
    assert salinity.leach(100.0, 300.0, 0.0) == 100.0


def test_salt_stress_follows_threshold_slope():
    P = lp("wheat")
    assert salinity.salt_stress(P, P.salt_threshold_dsm) == 1.0
    assert salinity.salt_stress(P, P.salt_threshold_dsm + 1) == pytest.approx(1 - P.salt_slope_per_dsm)
    assert salinity.salt_stress(P, 1000) == 0.0


def test_fungicide_factor_window_edges():
    from datetime import date, timedelta
    P, d0 = lp("wheat"), date(2026, 3, 1)
    m = Management(fungicide={d0: 0.7})
    assert disease.fungicide_factor(P, m, d0 - timedelta(days=1)) == 1.0           # before the spray
    assert disease.fungicide_factor(P, m, d0) == pytest.approx(0.3)
    assert disease.fungicide_factor(P, m, d0 + timedelta(days=13)) == pytest.approx(0.3)
    assert disease.fungicide_factor(P, m, d0 + timedelta(days=14)) == 1.0          # window is 14 days


def test_disease_needs_warm_humid_days_and_the_active_stage():
    P = lp("wheat")
    wet = dict(tmin=8, tmax=18, rh=95, wind=2, rs=15, rain=0)
    dry = dict(wet, rh=40)
    mid = (P.gdd_dev_end + P.gdd_maturity) / 2
    assert disease.step(P, 0.01, mid, wet, 13.0, 1.0) > 0.01
    assert disease.step(P, 0.01, mid, dry, 13.0, 1.0) == 0.01
    assert disease.step(P, 0.01, P.gdd_dev_end - 1, wet, 13.0, 1.0) == 0.01        # not active yet
    assert disease.step(P, 0.01, mid, wet, 13.0, 0.0) == 0.01                       # fully protected


def test_growth_pieces():
    P = lp("wheat")
    assert growth.transpiration_ratio(P, 1.0, 1.0, 1.0, P.gdd_emergence) == 0.0
    assert growth.heat_factor(P, P.heat_tmax + 1, (P.gdd_mid_start + P.gdd_late_start) / 2) == pytest.approx(0.9)
    assert growth.heat_factor(P, P.heat_tmax + 1, 10) == 1.0
    assert growth.grain_yield_t_ha(P, 1000.0) == pytest.approx(1000 * P.harvest_index / 100)


def test_results_behave_like_dataclasses_and_read_only_mappings(tmp_path):
    w, s, m, _ = field(tmp_path)
    r = simulate(w, s, m, load_params())
    assert r["summary"] is r.summary and r["daily"] is r.daily
    assert r.summary["yield_t_ha"] == r.summary.yield_t_ha and r.summary.get("nope", 1) == 1
    assert list(r.daily[0].keys())[:3] == ["date", "gdd", "et0"] and "kc" in r.daily[0] and len(r.daily[0]) == 13
    assert r.summary.as_dict()["ended_by"] == r.summary.ended_by
    with pytest.raises(KeyError):
        r.daily[0]["nope"]
    with pytest.raises(Exception):
        r.summary.yield_t_ha = 99          # frozen


def test_fitstats_values_and_edge_cases():
    f = FitStats.from_pairs([(1, 2), (2, 4), (3, 6)])
    assert f.n == 3 and f.bias == pytest.approx(2.0) and f.rmse == pytest.approx((14 / 3) ** 0.5)
    assert f.r == pytest.approx(1.0) and "n = 3" in f.lines()[0]
    assert FitStats.from_pairs([(1, 1), (2, 2)]).r != FitStats.from_pairs([(1, 1), (2, 2)]).r      # nan with n < 3
    assert FitStats.from_pairs([(1, 5), (1, 6), (1, 7)]).r != FitStats.from_pairs([(1, 5), (1, 6), (1, 7)]).r   # no spread
    with pytest.raises(ValueError):
        FitStats.from_pairs([])
