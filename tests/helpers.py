"""Shared test helpers: repo paths, dataset skip markers, small builders."""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from radicle.ingest.loaders import load_field
from radicle.synthetic import make_field

REPO = Path(__file__).resolve().parents[1]
EGYPT = REPO / "data/external/egypt-nile-wheat/x"
GREELEY = REPO / "data/external/greeley-maize"
needs_egypt = pytest.mark.skipif(not EGYPT.exists(), reason="Egypt dataset not present")
needs_greeley = pytest.mark.skipif(not (GREELEY / "LIRF_Soils.xlsx").exists(), reason="Greeley dataset not downloaded")


def field(tmp):
    """Load a fresh synthetic demo field written under `tmp`."""
    return load_field(make_field(Path(tmp) / "f"))


def tiny_weather(days, overrides=None):
    """(start date, weather dict) of constant mild weather with per-day overrides {index: {key: value}}."""
    d0 = date(2025, 5, 1)
    base = dict(tmin=10.0, tmax=25.0, rh=60.0, wind=2.0, rs=20.0, rain=0.0)
    return d0, {d0 + timedelta(days=i): dict(base, **(overrides or {}).get(i, {})) for i in range(days)}
