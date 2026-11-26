"""Loader for the German multi-environment winter wheat trials (Zenodo 10.5281/zenodo.8248543, CC BY 4.0).

Six locations (Kiel, Hannover, Quedlinburg, Kleine Altendorf, Rauischholzhausen, Gross Gerau), 2015-2017, about 220
cultivars, three treatments: high nitrogen with fungicide (HiN_HiF), high nitrogen without (HiN_NoF), low nitrogen
without (LoN_NoF). Rainfed. Files used: Yield_data.csv and climate_data.csv (latin-1, comma separated).

One Trial is one location x year x treatment, summarised over cultivars: median sowing date, mean heading date (BBCH 59),
median yield. Yield is thousand-kernel weight x spikes per m2 x kernels per spike, in dry t/ha; cultivars missing any
component are dropped.

Humidity and wind come from the nearest German Weather Service (DWD) stations when their daily files are in
`<root>/dwd/produkt_klima_tag_<station>.txt` (open data, free use with attribution; see DWD_STATIONS). Without them,
humidity is estimated from Tmin (dew point = Tmin) and wind is 2 m/s, both assumptions.

Other assumptions (documented in docs/DATA-SOURCES.md): site coordinates and elevation (approximate, from public maps);
one generic soil (fc 0.30, wp 0.12, 1 m); missing rain on a gap day is 0 and other gaps up to 2 days are interpolated;
fungicide sprays at heading plus the offsets below, efficacy 0.8, because spray dates are not recorded."""
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
DWD_STATIONS = {"KAL": "00603", "GGE": "01420", "RHH": "07410", "HAN": "02014", "KIE": "02564", "QLB": "04032"}
WIND_10M_TO_2M = 0.748         # FAO-56 eq. 47 for a 10 m anemometer over grass
FC, WP = 0.30, 0.12
WIND = 2.0                     # m/s, used only without DWD wind
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


def load_dwd(root):
    """{location: {date: (relative humidity %, wind m/s at 2 m)}} from the DWD daily files that are present.
    Missing values (-999) are left out."""
    out = {}
    for loc, station in DWD_STATIONS.items():
        path = Path(root) / "dwd" / f"produkt_klima_tag_{station}.txt"
        if not path.exists():
            continue
        with open(path, encoding="latin-1", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        head = [c.strip() for c in rows[0]]
        i_date, i_rh, i_wind = head.index("MESS_DATUM"), head.index("UPM"), head.index("FM")
        days = {}
        for r in rows[1:]:
            ds = r[i_date].strip()
            rh, wind = float(r[i_rh]), float(r[i_wind])
            days[date(int(ds[:4]), int(ds[4:6]), int(ds[6:]))] = (
                rh if rh > -99 else None, wind * WIND_10M_TO_2M if wind > -99 else None)
        out[loc] = days
    return out


def load_weather(root):
    """{location: {date: weather}} in radicle units. Gaps of up to two days are interpolated (rain = 0). Humidity
    and wind come from DWD where available, else from the Tmin and 2 m/s assumptions."""
    dwd = load_dwd(root)
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
        obs = dwd.get(loc, {})
        out[loc] = {}
        for d, (tmin, tmax, rain, rs) in days.items():
            rh, wind = obs.get(d, (None, None))
            out[loc][d] = dict(tmin=tmin, tmax=tmax, rh=max(5.0, min(100.0, rh)) if rh is not None else _rh(tmin, tmax),
                               wind=max(0.1, wind) if wind is not None else WIND, rs=rs, rain=rain)
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
