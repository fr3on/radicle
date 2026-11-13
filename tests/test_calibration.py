import json
import tempfile
from datetime import date, timedelta

import pytest

from helpers import REPO, field
from radicle.calibrate import calibrate
from radicle.ingest.loaders import load_field
from radicle.models.crop import load_params, simulate


def test_calibration_recovers_yield():
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        P = load_params()
        target = simulate(w, s, m, P)["summary"]["yield_t_ha"] * 0.8
        best, l = calibrate(w, s, m, P, [(date(2026, 6, 1), "yield_t_ha", target)], iters=150)
        assert simulate(w, s, m, best)["summary"]["yield_t_ha"] == pytest_approx(target)


def pytest_approx(x):
    class A:
        def __eq__(self, o): return abs(o - x) / x < 0.1
    return A()


def test_calibration_ignores_truncated_runs():
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        short = {d: x for d, x in w.items() if d < m.sow_date + timedelta(days=60)}
        with pytest.raises(ValueError, match="No usable observations"):
            calibrate(short, s, m, load_params(), [(date(2026, 6, 1), "yield_t_ha", 7.0)], iters=5)


def test_calibrated_maize_params_match_committed_real_fields():
    # NOTE in-sample: 2010 is part of the fit. The honest out-of-sample numbers are in docs/maize_calibration.json.
    P = load_params("maize_greeley_calibrated")
    for t in (1, 6):
        w, s, m, obs = load_field(REPO / f"data/greeley-2010-t{t}")
        sim = simulate(w, s, m, P)["summary"]["yield_t_ha"]
        o = {v: x for _, v, x in obs}["yield_t_ha"]
        assert abs(sim - o) / o < 0.15, (t, sim, o)


def test_recorded_heldout_calibration_beats_placeholders():
    d = json.loads((REPO / "docs/maize_calibration.json").read_text())
    s = d["summary"]
    assert abs(s["calibrated (held-out year)"]["bias"]) < 1.0 < abs(s["uncalibrated"]["bias"])
    assert s["calibrated (held-out year)"]["rmse"] < 0.3 * s["uncalibrated"]["rmse"]
    assert len(d["records"]) == 24
