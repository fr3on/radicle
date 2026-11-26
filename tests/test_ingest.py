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


NZ = REPO_NZ = Path(__file__).resolve().parents[1] / "data/external/nz-wheat"
needs_nz = pytest.mark.skipif(not (NZ / "Weather").exists(), reason="NZ wheat dataset not downloaded")


def _write_nz_tables(root):
    """Smallest valid NZ-format tree: one site, one treatment, three weather days."""
    base = Path(root) / "Experimental_observation-Model_input/NZ_AgMIP_tab_delimited"
    base.mkdir(parents=True)
    (Path(root) / "Weather").mkdir()

    def table(name, header, rows):
        lines = ["\t".join(header)] * 3 + ["\t".join(r) for r in rows]
        (base / f"NZ_AgMIP_{name}.txt").write_text("\n".join(lines) + "\n")
    table("Weather_stations", ["WST_ID", "WST_SITE", "WST_LAT", "WST_ELEV"], [["TST", "Testville", "-43.7", "10"]])
    table("Soil_profile_layers", ["SOIL_ID", "SLLT", "SLLB", "SLDUL", "SLLL"], [["S1", "0", "100", "0.30", "0.10"]])
    table("Planting_events", ["TREAT_ID", "PDATE", "PLPOP"], [["T1", "2012.02.27", "150"]])
    table("Irrigation_events", ["EID", "IDATE", "IRVAL"], [["E1", "2012-03-05", "30"]])
    table("Obs_crop_summary_means", ["TREAT_ID", "GWAM", "CWAM", "ADAT", "MDAT", "HDATE"],
          [["T1", "12000", "26000", "2012.12.01", "", "2013.02.10"]])
    table("Obs_crop_daily_means", ["TREAT_ID", "date", "LAID", "CWAD"],
          [["T1", "2012.10.01", "3.5", "-99"], ["T1", "2012.10.15", "", "5000"]])
    table("Experiment_description", ["EID", "HAYR"], [["E1", "2013"]])
    table("Treatments", ["TREAT_ID", "EID", "SOIL_ID", "wst_id", "WST_DATASET", "TRT_NAME", "IRRIG"],
          [["T1", "E1", "S1", "TST", "TSTW", "2013_Testville_FebruarySowing_150", "Y"]])
    (Path(root) / "Weather/TSTW.wth").write_text(
        "*WEATHER DATA: test\n\n@ INSI LAT LONG ELEV TAV AMP REFHT WNDHT\nTEST -43.7 172.3 10 -99 2 2\n"
        "@DATE YYYY MM DD SRAD TMAX TMIN RAIN WIND VPRS RHUM\n"
        "2012058 2012 2 27 15 20 8 0 2 9 70\n2012059 2012 2 28 14 21 9 1 2 9 -99\n2012060 2012 2 29 16 22 7 0 2 9 65\n")


def test_nz_loader_parses_tables_and_drops_bad_weather(tmp_path):
    from radicle.ingest import nzwheat
    _write_nz_tables(tmp_path)
    [(t, w)] = nzwheat.load_all(tmp_path)
    assert t.mgmt.sow_date == date(2012, 2, 27) and t.year == 2013 and t.site_name == "Testville"
    assert t.obs_grain_t_ha == 12.0 and t.obs_biomass_t_ha == 26.0 and t.density == 150
    assert t.obs_anthesis == date(2012, 12, 1) and t.obs_maturity is None
    assert t.mgmt.irrigation == {date(2012, 3, 5): (30.0, nzwheat.IRRIGATION_EC)}
    assert t.obs_lai == [(date(2012, 10, 1), 3.5)] and t.obs_tops == [(date(2012, 10, 15), 500.0)]
    assert sorted(w) == [date(2012, 2, 27), date(2012, 2, 29)]   # the -99 humidity day is dropped
    assert (t.site.fc, t.site.wp) == (0.30, 0.10)


@needs_nz
def test_nz_dataset_loads_and_simulates():
    from radicle.experiments import nz_wheat
    from radicle.models.params import load_params
    r = nz_wheat(load_params("wheat"), str(NZ))
    assert r["n"] == 50 and set(r["by_year"]) >= {"Leeston 2013", "Wakanui 2018"}
    assert 7 < min(o for o, _ in r["pairs"]) and max(o for o, _ in r["pairs"]) < 17   # observed dry yields, t/ha
