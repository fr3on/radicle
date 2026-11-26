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


GERMAN = Path(__file__).resolve().parents[1] / "data/external/zenodo-wheat-gxe"
needs_german = pytest.mark.skipif(not (GERMAN / "Yield_data.csv").exists(), reason="German wheat dataset not downloaded")


def _write_german_tables(root):
    """Two cultivars, two treatments, one site, a six-day weather record with one two-day gap and one bad day."""
    from datetime import timedelta
    (Path(root) / "Yield_data.csv").write_text(
        '"genotype","Year","Location","Treatment","Sowing_date","Heading_date_BBCH59","Thousand_kernel_weight(g)",'
        '"Spike_number(m-2)","Kernels_per_Spike"\n'
        '"A",2015,"KIE","HiN_HiF","2014-10-01","2015-06-01",50,400,40\n'
        '"B",2015,"KIE","HiN_HiF","2014-10-03","2015-06-03",50,500,40\n'
        '"C",2015,"KIE","HiN_HiF","2014-10-02","2015-06-02",NA,500,40\n'
        '"A",2015,"KIE","HiN_NoF","2014-10-01","2015-06-01",50,300,40\n', encoding="latin-1")
    days = [date(2014, 10, 1) + timedelta(days=i) for i in range(6)]
    rows = ['"Location","Date","Temperature.Air.Mean_C","Temperature.Air.Min_C","Temperature.Air.Max_C",'
            '"Precipitation_mm_d","Global.Radiation_MJ_m2_d"']
    for i, d in enumerate(days):
        if i in (2, 3):
            continue                                        # a two-day gap: interpolated, rain 0
        tmin, tmax = (8.0 + i, 14.0 + i) if i != 5 else (20.0, 10.0)   # last day is physically impossible: dropped
        rows.append(f'"KIE",{d},{(tmin + tmax) / 2},{tmin},{tmax},2.0,8.0')
    (Path(root) / "climate_data.csv").write_text("\n".join(rows) + "\n")


def test_german_loader_summarises_cultivars_and_sprays(tmp_path):
    from radicle.ingest import germanwheat
    _write_german_tables(tmp_path)
    trials = {t.treatment: (t, w) for t, w in germanwheat.load_all(tmp_path)}
    t, w = trials["HiN_HiF"]
    assert t.n_cultivars == 2 and t.obs_yield_t_ha == pytest.approx((8.0 + 10.0) / 2)   # 50*400*40/1e5 = 8.0 t/ha
    assert t.mgmt.sow_date == date(2014, 10, 2) and t.obs_heading == date(2015, 6, 2)
    assert t.mgmt.fungicide == {date(2015, 6, 2): germanwheat.SPRAY_EFFICACY}
    assert trials["HiN_NoF"][0].mgmt.fungicide == {}
    assert sorted(w) == [date(2014, 10, d) for d in range(1, 6)]   # two-day gap filled, impossible day dropped
    assert w[date(2014, 10, 2)]["rain"] == 2.0 and w[date(2014, 10, 3)]["rain"] == 0.0


@needs_german
def test_german_dataset_loads_and_shows_fungicide_gain():
    from radicle.experiments import german_wheat
    from radicle.models.params import load_params
    r = german_wheat(load_params("wheat"), str(GERMAN))
    assert r["n"] >= 35 and r["fungicide_gain_obs"] > 1.0       # observed gain is about 1.5 t/ha


def test_german_weather_uses_dwd_humidity_and_wind(tmp_path):
    from radicle.ingest import germanwheat
    _write_german_tables(tmp_path)
    (tmp_path / "dwd").mkdir()
    (tmp_path / "dwd" / "produkt_klima_tag_02564.txt").write_text(
        "STATIONS_ID;MESS_DATUM;QN_3;  FX;  FM;QN_4; RSK;RSKF; SDK;SHK_TAG;  NM; VPM;  PM; TMK; UPM; TXK; TNK; TGK;eor\n"
        "2564;20141001;5;6.0;4.0;-999;-999;-999;-999;-999;-999;-999;-999;-999;90.0;-999;-999;-999;eor\n"
        "2564;20141002;5;6.0;-999;-999;-999;-999;-999;-999;-999;-999;-999;-999;-999;-999;-999;-999;eor\n")
    w = germanwheat.load_weather(tmp_path)["KIE"]
    d1, d2 = w[date(2014, 10, 1)], w[date(2014, 10, 2)]
    assert d1["rh"] == 90.0 and d1["wind"] == pytest.approx(4.0 * germanwheat.WIND_10M_TO_2M)
    assert d2["wind"] == germanwheat.WIND and d2["rh"] != 90.0     # -999 falls back to the assumptions
