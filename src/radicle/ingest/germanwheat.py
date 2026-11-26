"""Loader for the German multi-environment winter wheat trials (Zenodo 10.5281/zenodo.8248543, CC BY 4.0).

Six locations (Kiel, Hannover, Quedlinburg, Kleine Altendorf, Rauischholzhausen, Gross Gerau), 2015-2017, about 220
cultivars, three treatments: high nitrogen with fungicide (HiN_HiF), high nitrogen without (HiN_NoF), low nitrogen
without (LoN_NoF). Rainfed. Files used: Yield_data.csv and climate_data.csv (latin-1, comma separated).

One Trial is one location x year x treatment, summarised over cultivars: median sowing date, mean heading date (BBCH 59),
median yield. Yield is thousand-kernel weight x spikes per m2 x kernels per spike, in dry t/ha; cultivars missing any
component are dropped.

Assumptions not in the data (all documented in docs/DATA-SOURCES.md): site coordinates and elevation (approximate,
from public maps); one generic soil (fc 0.30, wp 0.12, 1 m); wind 2 m/s; dew point equal to the daily minimum
temperature (humid climate); missing rain on a gap day is 0 and other gaps up to 2 days are interpolated; fungicide
sprays at heading plus the offsets below, efficacy 0.8, because spray dates are not recorded."""
import csv
import statistics as st
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..models.domain import Management, Site
from ..models.et0 import sat_vp

SITES = {  # (lat, elevation m): approximate
    "KAL": (50.62, 170), "GGE": (49.91, 90), "RHH": (50.77, 230),
    "HAN": (52.38, 55), "KIE": (54.32, 30), "QLB": (51.79, 120)}
NAMES = {"KAL": "Kleine Altendorf", "GGE": "Gross Gerau", "RHH": "Rauischholzhausen",
         "HAN": "Hannover", "KIE": "Kiel", "QLB": "Quedlinburg"}
FC, WP = 0.30, 0.12
WIND = 2.0
SPRAY_OFFSETS = (0,)          # days from heading
SPRAY_EFFICACY = 0.8
FUNGICIDE = "HiN_HiF"
MISSING = {"", "NA"}


@dataclass
class Trial:
    location: str
    year: int
    treatment: str
    site: Site
    mgmt: Management
    n_cultivars: int
    obs_yield_t_ha: float
    obs_heading: date

    @property
    def name(self):
        return f"{NAMES.get(self.location, self.location)} {self.year}"


def _num(s):
    s = (s or "").strip()
    return None if s in MISSING else float(s)


def _date(s):
    s = (s or "").strip()
    return None if s in MISSING else date.fromisoformat(s)


def _rows(path):
    with open(path, encoding="latin-1", newline="") as f:
        return list(csv.DictReader(f))


def load_weather(root):
    """{location: {date: weather}} in radicle units. Gaps of up to two days are interpolated (rain = 0)."""
    raw = {}
    for r in _rows(Path(root) / "climate_data.csv"):
        vals = [_num(r[k]) for k in ("Temperature.Air.Min_C", "Temperature.Air.Max_C", "Precipitation_mm_d",
                                     "Global.Radiation_MJ_m2_d")]
        if None in vals or vals[0] > vals[1]:
            continue
        raw.setdefault(r["Location"], {})[date.fromisoformat(r["Date"])] = vals
    out = {}
    for loc, days in raw.items():
        days = _fill(days)
        out[loc] = {d: dict(tmin=tmin, tmax=tmax, rh=_rh(tmin, tmax), wind=WIND, rs=rs, rain=rain)
                    for d, (tmin, tmax, rain, rs) in days.items()}
    return out


def _rh(tmin, tmax):
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2
    return max(5.0, min(100.0, 100 * sat_vp(tmin) / es))


def _fill(days, max_gap=2):
    ds = sorted(days)
    out = dict(days)
    for a, b in zip(ds, ds[1:]):
        gap = (b - a).days - 1
        if 0 < gap <= max_gap:
            for k in range(1, gap + 1):
                f = k / (gap + 1)
                va, vb = days[a], days[b]
                out[a + timedelta(days=k)] = [va[0] + f * (vb[0] - va[0]), va[1] + f * (vb[1] - va[1]), 0.0,
                                              va[3] + f * (vb[3] - va[3])]
    return out


def load_all(root, spray_offsets=SPRAY_OFFSETS):
    """[(Trial, weather)] for every location x year x treatment with a yield, heading and sowing date and weather
    covering the sowing date."""
    weather = load_weather(root)
    groups = {}
    for r in _rows(Path(root) / "Yield_data.csv"):
        groups.setdefault((r["Location"], int(r["Year"]), r["Treatment"]), []).append(r)
    out = []
    for (loc, year, tr), rows in sorted(groups.items()):
        if loc not in SITES or loc not in weather:
            continue
        sow = [_date(r["Sowing_date"]) for r in rows if _date(r["Sowing_date"])]
        head = [_date(r["Heading_date_BBCH59"]) for r in rows if _date(r["Heading_date_BBCH59"])]
        yields = []
        for r in rows:
            tkw, spikes, kps = (_num(r[k]) for k in ("Thousand_kernel_weight(g)", "Spike_number(m-2)", "Kernels_per_Spike"))
            if None not in (tkw, spikes, kps):
                yields.append(tkw * spikes * kps / 1e5)       # g/m2 -> t/ha
        if not (sow and head and yields):
            continue
        sow_d = sorted(sow)[len(sow) // 2]
        if sow_d not in weather[loc]:
            continue
        head_d = date.fromordinal(round(st.mean(d.toordinal() for d in head)))
        lat, elev = SITES[loc]
        site = Site(lat=lat, elev_m=elev, fc=FC, wp=WP, initial_depletion_frac=0.1, initial_ece=0.5)
        mgmt = Management(sow_date=sow_d)
        if tr == FUNGICIDE:
            mgmt.fungicide = {head_d + timedelta(days=o): SPRAY_EFFICACY for o in spray_offsets}
        out.append((Trial(loc, year, tr, site, mgmt, len(yields), st.median(yields), head_d), weather[loc]))
    return out
