import tempfile
from datetime import date
from pathlib import Path

import pytest

from helpers import GREELEY, needs_greeley
from radicle.ingest.loaders import DataError, load_field, load_weather
from radicle.synthetic import make_field


def test_validation_rejects_bad_rows():
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "weather.csv"
        p.write_text("date,tmin,tmax,rh_mean,wind_2m,rs_mjm2,rain_mm\n2025-01-01,30,20,50,2,15,0\n")
        try:
            load_weather(p)
            assert False
        except DataError as e:
            assert "tmin > tmax" in str(e)


@pytest.mark.parametrize("fname,content,msg", [
    ("soil.csv", "key,value\nlatitude,25\nfc,0.3\nwp,0.1\n", "unknown soil key"),
    ("soil.csv", "key,value\nlat,abc\nfc,0.3\nwp,0.1\n", "not a number"),
    ("soil.csv", "key,value\nlat,25\n", "missing required soil keys"),
    ("management.csv", "date,event,amount,ec_dsm\n2025-12-01,irrigation,60,1.5\n", "no 'sow' event"),
    ("management.csv", "date,event,amount,ec_dsm\n2025-11-15,sow,0,\n2025-12-01,irrigation,60,abc\n", "not a number"),
    ("observations.csv", "date,variable,value\n2026-05-01,yeild_t_ha,7\n", "unknown variable"),
    ("observations.csv", "date,variable,value\n2026-05-01,yield_t_ha,x\n", "not a number"),
])
def test_loaders_reject_bad_input(fname, content, msg):
    with tempfile.TemporaryDirectory() as t:
        d = make_field(Path(t) / "f")
        (d / fname).write_text(content)
        with pytest.raises(DataError, match=msg):
            load_field(d)


@needs_greeley
def test_greeley_loader_and_weather_cleaning():
    from radicle.ingest import greeley
    T = greeley.load_all(str(GREELEY))
    assert len(T) == 24 and {t.year for t, _ in T} == {2008, 2009, 2010, 2011}
    for y in (2008, 2009, 2010, 2011):
        yt = [t for t, _ in T if t.year == y]
        assert [t.trno for t in yt] == [1, 2, 3, 4, 5, 6]
        irr = [t.obs_irrigation_mm for t in yt]
        assert irr[0] > irr[-1]                          # treatment 1 is the wettest
        assert yt[0].obs_grain_t_ha > yt[-1].obs_grain_t_ha
    w2010, _ = greeley.load_weather(str(GREELEY), 2010)
    assert all(-45 <= x["tmin"] <= x["tmax"] <= 50 and x["rs"] < 35 for x in w2010.values())   # corrupt rows removed/capped
    assert len(w2010) == 365                                                                    # and the gap was filled
    w2009, _ = greeley.load_weather(str(GREELEY), 2009)
    assert date(2009, 10, 2) in w2009                    # single missing day filled by interpolation
