"""Loader for the New Zealand winter wheat potential-yield experiments (Plant & Food Research; AgMIP-Wheat format).

Source: Harvard Dataverse doi:10.7910/DVN/XA4VA2, six site-years (Leeston 2013-2015, Wakanui 2016-2018), 50 treatments
of sowing date x sowing density. The Dataverse record is labelled CC0, but the dataset's own description says use is
restricted by a consortium agreement, so the data is not redistributed with radicle. See docs/DATA-SOURCES.md.

Layout under `root` (the unzipped download): Experimental_observation-Model_input/NZ_AgMIP_tab_delimited/*.txt and
Weather/*.wth. Tables are tab separated with three header rows (names, units, codes); dates are YYYY.MM.DD or
YYYY-MM-DD; missing is blank, -99 or -999. Weather is DSSAT .wth with wind (m/s at 2 m) and mean relative humidity.

Assumptions: initial depletion 10 % (winter-wet soil) and initial ECe 0.5 dS/m (no salinity); both are placeholders
because the dataset records neither. Density is not modelled, so treatments differing only in density share a
simulation."""
import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..models.domain import Management, Site
from .icasa import _apply_soil

TABLES = "Experimental_observation-Model_input/NZ_AgMIP_tab_delimited"
MISSING = {"", "NA", "-99", "-999", "-99.0", "-999.0"}
INITIAL_DEPLETION = 0.1
INITIAL_ECE = 0.5
IRRIGATION_EC = 0.5


@dataclass
class Treatment:
    tid: str
    eid: str
    site_name: str
    year: int                      # harvest year
    site: Site
    mgmt: Management
    weather_file: str
    density: float | None = None
    obs_grain_t_ha: float | None = None       # dry grain yield
    obs_biomass_t_ha: float | None = None     # dry tops at maturity
    obs_anthesis: date | None = None
    obs_maturity: date | None = None
    obs_harvest: date | None = None
    obs_lai: list = field(default_factory=list)       # [(date, m2/m2)]
    obs_tops: list = field(default_factory=list)      # [(date, g/m2)]


def parse_date(s):
    s = (s or "").strip()
    if s in MISSING:
        return None
    try:
        return date.fromisoformat(s.replace(".", "-"))
    except ValueError:
        return None


def num(s):
    s = (s or "").strip()
    if s in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def read_table(path):
    """Rows keyed by the third header line (the short codes)."""
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    codes = rows[2]
    return [dict(zip(codes, r)) for r in rows[3:] if any(c.strip() for c in r)]


def read_wth(path):
    """Daily weather in radicle's units, plus (lat, elev). Rows with any missing value are dropped."""
    out, meta, mode = {}, {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("@ INSI"):
            mode = "meta"
        elif line.startswith("@DATE"):
            mode = "data"
        elif not line.strip() or line[0] in "*!$":
            continue
        elif mode == "meta":
            p = line.split()
            meta = dict(lat=float(p[1]), elev=float(p[3]))
            mode = None
        elif mode == "data":
            p = line.split()
            ds = p[0]
            d = date(int(ds[:4]), 1, 1) + timedelta(days=int(ds[4:]) - 1)
            srad, tmax, tmin, rain, wind, _vp, rh = (float(x) for x in p[4:11])
            if min(srad, tmax, tmin, rain, wind, rh) <= -99 or tmin > tmax:
                continue
            out[d] = dict(tmin=tmin, tmax=tmax, rh=max(5.0, min(100.0, rh)), wind=wind, rs=srad, rain=rain)
    return out, meta


def load_weather(root, weather_file):
    return read_wth(Path(root) / "Weather" / f"{weather_file}.wth")


def load_all(root):
    """[(Treatment, weather)] for every treatment with a sowing date, soil, weather file and weather covering
    the sowing date. Observed series are attached where present."""
    base = Path(root) / TABLES
    table = lambda name: read_table(base / f"NZ_AgMIP_{name}.txt")
    stations = {r["WST_ID"]: r for r in table("Weather_stations")}
    layers = {}
    for r in table("Soil_profile_layers"):
        layers.setdefault(r["SOIL_ID"], []).append(r)
    planting = {r["TREAT_ID"]: r for r in table("Planting_events")}
    irrigation = {}
    for r in table("Irrigation_events"):
        d, mm = parse_date(r["IDATE"]), num(r["IRVAL"])
        if d and mm:
            irrigation.setdefault(r["EID"], {})[d] = mm
    summary = {r["TREAT_ID"]: r for r in table("Obs_crop_summary_means")}
    daily = {}
    for r in table("Obs_crop_daily_means"):
        daily.setdefault(r["TREAT_ID"], []).append(r)
    experiments = {r["EID"]: r for r in table("Experiment_description")}

    out, weather_cache = [], {}
    for t in table("Treatments"):
        tid, eid = t["TREAT_ID"], t["EID"]
        plant = planting.get(tid)
        sow = parse_date(plant["PDATE"]) if plant else None
        st, wf = stations.get(t["wst_id"]), t["WST_DATASET"]
        if sow is None or st is None or t["SOIL_ID"] not in layers:
            continue
        if wf not in weather_cache:
            path = Path(root) / "Weather" / f"{wf}.wth"
            weather_cache[wf] = read_wth(path)[0] if path.exists() else {}
        weather = weather_cache[wf]
        if sow not in weather:
            continue
        site = Site(lat=float(st["WST_LAT"]), elev_m=float(st["WST_ELEV"] or 0),
                    initial_depletion_frac=INITIAL_DEPLETION, initial_ece=INITIAL_ECE)
        _apply_soil(site, layers[t["SOIL_ID"]])
        mgmt = Management(sow_date=sow)
        if t["IRRIG"].strip() == "Y":
            mgmt.irrigation = {d: (mm, IRRIGATION_EC) for d, mm in irrigation.get(eid, {}).items()}
        s = summary.get(tid, {})
        grain, tops = num(s.get("GWAM")), num(s.get("CWAM"))
        harvest_year = int(experiments[eid]["HAYR"]) if eid in experiments else sow.year + 1
        tr = Treatment(tid, eid, t["TRT_NAME"].split("_")[1] if "_" in t["TRT_NAME"] else st["WST_SITE"],
                       harvest_year, site, mgmt, wf, density=num(plant.get("PLPOP")),
                       obs_grain_t_ha=grain / 1000 if grain else None,
                       obs_biomass_t_ha=tops / 1000 if tops else None,
                       obs_anthesis=parse_date(s.get("ADAT")), obs_maturity=parse_date(s.get("MDAT")),
                       obs_harvest=parse_date(s.get("HDATE")))
        for r in daily.get(tid, []):
            d = parse_date(r["date"])
            if d is None:
                continue
            if (lai := num(r.get("LAID"))) is not None:
                tr.obs_lai.append((d, lai))
            if (cw := num(r.get("CWAD"))) is not None:
                tr.obs_tops.append((d, cw / 10))
        out.append((tr, weather))
    return out
