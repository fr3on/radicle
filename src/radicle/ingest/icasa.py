"""Loader for the INVITE wheat registration trials (ICASA format, Zenodo 10.5281 record 20786880, CC BY 4.0).

Format quirks handled here: .csv files are TAB separated with 3 header rows (names, units, codes); dates are Excel
serial numbers; missing is -999 / NA; weather is ICASA .wht (DATE=YYYYDDD). VPRSD units are not trustworthy as labelled
(kPa), see _rh_from_vp: the scale is checked empirically and reported by check_vp_scale()."""
import csv
import math
import statistics as st
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..models.crop import Management, Site
from ..models.et0 import sat_vp

EXCEL0 = date(1899, 12, 30)
MISSING = {"", "NA", "-99", "-999", "-999.0", "-99.0"}
VP_TO_KPA = 0.01  # ASSUMPTION inferred from data (values ~10-40 on freezing days); verified by check_vp_scale()


def excel_date(v):
    try:
        return EXCEL0 + timedelta(days=int(float(v)))
    except (TypeError, ValueError):
        return None


def read_table(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    codes = rows[2]
    return [dict(zip(codes, r)) for r in rows[3:] if any(r)]


def _f(x):
    return None if x is None or x.strip() in MISSING else float(x)


_wcache = {}


def read_wht(path):
    path = str(path)
    if path in _wcache:
        return _wcache[path]
    out, meta, mode = {}, {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        if line.startswith("@ DATE"):
            mode = "data"
            continue
        if line.startswith("@ INSI"):
            mode = "meta"
            continue
        if line.startswith("!") or line.startswith("$") or not line.strip():
            continue
        parts = line.split()
        if mode == "meta":
            try:
                meta = dict(lat=float(parts[1]), elev=float(parts[3]))
            except (ValueError, IndexError):
                meta = {}
        elif mode == "data":
            ds = parts[0]
            d = date(int(ds[:4]), 1, 1) + timedelta(days=int(ds[4:]) - 1)
            tmin, tmax, rain, srad, wind, vp = (float(x) for x in parts[1:7])
            if -900 in (tmin, tmax, srad, wind, vp, rain) or min(tmin, tmax, rain, srad, wind, vp) <= -99:
                continue
            out[d] = dict(tmin=tmin, tmax=tmax, rain=rain, rs=srad, wind=wind, vp=vp)
    _wcache[path] = (out, meta)
    return out, meta


def _rh_from_vp(w):
    es = (sat_vp(w["tmax"]) + sat_vp(w["tmin"])) / 2
    return max(5.0, min(100.0, 100 * w["vp"] * VP_TO_KPA / es))


def check_vp_scale(weather):
    """Mean relative humidity implied by the assumed vapour-pressure unit. Sane for Europe: roughly 65-85 %."""
    return st.mean(_rh_from_vp(w) for w in weather.values())


def to_model_weather(raw):
    return {d: dict(tmin=w["tmin"], tmax=w["tmax"], rh=_rh_from_vp(w), wind=w["wind"], rs=w["rs"], rain=w["rain"])
            for d, w in raw.items()}


@dataclass
class Trial:
    eid: str
    country: str
    year: int
    site: Site
    mgmt: Management
    weather_path: Path
    n_obs: int = 0
    yield_t_ha: float | None = None       # mean over cultivars of dry grain yield
    heading_date: date | None = None      # mean ear emergence date
    maturity_date: date | None = None
    disease: dict = field(default_factory=dict)


def load_country(root, country):
    base = Path(root) / "csv" / country
    pick = lambda frag: next(base.glob(f"*{frag}*.csv"))
    fields = {r["EID"]: r for r in read_table(pick("_Fields"))}
    treat = {r["EID"]: r for r in read_table(pick("_Treatments"))}
    planting = {}
    for r in read_table(pick("Planting_events")):
        d = excel_date(r["PDATE"])
        if d:
            planting.setdefault(r["EID"], []).append(d)
    soils = {}
    for r in read_table(pick("Soil_profile_layers")):
        soils.setdefault(r["SOIL_ID"], []).append(r)
    obs = {}
    for r in read_table(pick("Obs_crop_summary_means")):
        obs.setdefault(r["EID"], []).append(r)
    trials = []
    for eid, rows in obs.items():
        t, fl = treat.get(eid), fields.get(eid)
        if not t or not fl or eid not in planting:
            continue
        wp = Path(root) / "WeatherData" / country / (t["WST_DATASET"] + ".wht")
        if not wp.exists():
            continue
        site = Site(lat=float(fl["FL_LAT"]), elev_m=float(fl["FLELE"] or 0), initial_depletion_frac=0.1, initial_ece=0.5)
        layers = soils.get(t["SOIL_ID"], [])
        _apply_soil(site, layers)
        pd = sorted(planting[eid])[len(planting[eid]) // 2]
        yields = [_f(r.get("GWAM")) for r in rows]
        yields = [y for y in yields if y]
        heads = [excel_date(r["EEMD"]) for r in rows if _f(r.get("EEMD"))]
        mats = [excel_date(r["MDAT"]) for r in rows if _f(r.get("MDAT"))]
        dis = {}
        for k in ("MILDEW", "SEPTO", "BRUST", "YRUST", "FHB"):
            v = [_f(r.get(k)) for r in rows]
            v = [x for x in v if x is not None]
            if v:
                dis[k] = st.mean(v)
        mean_date = lambda ds: EXCEL0 + timedelta(days=round(st.mean([(x - EXCEL0).days for x in ds]))) if ds else None
        trials.append(Trial(eid, country, pd.year + 1, site, Management(sow_date=pd), wp, len(rows),
                            st.mean(yields) / 1000.0 if yields else None, mean_date(heads), mean_date(mats), dis))
    return trials


def _apply_soil(site, layers, depth_cm=100):
    fcs, wps, w = [], [], 0.0
    for r in layers:
        top, bot = _f(r["SLLT"]), _f(r["SLLB"])
        dul, ll = _f(r["SLDUL"]), _f(r["SLLL"])
        if None in (top, bot, dul, ll) or top >= depth_cm:
            continue
        thick = min(bot, depth_cm) - top
        fcs.append(dul * thick)
        wps.append(ll * thick)
        w += thick
    if w > 20:
        site.fc, site.wp = sum(fcs) / w, sum(wps) / w
        site.root_depth_max_m = min(1.0, w / 100)
