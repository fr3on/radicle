"""Loader for the USDA-ARS Limited Irrigation Research Farm (Greeley, Colorado) drip-irrigated maize, 2008-2011.
Public domain (US government work); DOI 10.15482/USDA.ADC/1254006 (data listed on catalog.data.gov and figshare).
Files expected in `root`: LIRF_Maize_<year>.xlsx, LIRF_Weather_<year>.xlsx, LIRF_Soils.xlsx.

Six irrigation treatments (about 40 to 100 % of ET) x 4 years = 24 treatments. ASSUMPTIONS made here, not in the data:
irrigation water EC 0.5 dS/m, initial root-zone ECe 1.0 dS/m, initial depletion 20 %, soil water limits are the
site mean of pressure-plate theta(33 kPa) and theta(1500 kPa) over 0-100 cm (one soil for all plots), rooting depth 1.05 m
(the depth of the profile the authors monitored). One impossible solar radiation value (2010-06-12) is capped at clear-sky Rso. Rain is the authors' best-estimate 'Precip' column when present."""
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..models.crop import Management, Site
from ..models.et0 import extraterrestrial_radiation, sat_vp
from .xlsx_min import read_xlsx

LAT, ELEV = 40.45, 1425.0       # from the dataset's own description
IRRIGATION_EC = 0.5             # ASSUMPTION
YEARS = (2008, 2009, 2010, 2011)
EXCEL0 = date(1899, 12, 30)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _date(serial):
    return EXCEL0 + timedelta(days=int(float(serial)))


def load_weather(root, year):
    """-> (model weather dict date -> tmin,tmax,rh,wind,rs,rain ; dict date -> published ASCE grass ETo mm/day)."""
    rows = read_xlsx(Path(root) / f"LIRF_Weather_{year}.xlsx")["Daily"]
    out, eto = {}, {}
    for r in rows:
        if _f(r.get("A")) is None or _f(r.get("B")) is None:
            continue
        tmax, tmin, vp, rs, run = (_f(r.get(k)) for k in ("D", "E", "F", "I", "J"))
        rain = _f(r.get("P"))
        if rain is None:
            rain = _f(r.get("K"))
        if None in (tmax, tmin, vp, rs, run) or rain is None:
            continue
        if not (-45 <= tmin <= tmax <= 50 and 0 <= vp <= 7 and 0 <= rs and 0 <= run <= 1500 and rain <= 300):
            continue            # corrupt sensor row (e.g. tmin -231 C in 2010): treated as missing, then gap-filled
        es = (sat_vp(tmax) + sat_vp(tmin)) / 2
        d = _date(r["A"])
        rso = (0.75 + 2e-5 * ELEV) * extraterrestrial_radiation(LAT, d.timetuple().tm_yday)
        rs = min(rs, rso)   # 2010-06-12 reports 45 MJ/m2/d (impossible; the file's own ETo is normal): cap at clear-sky Rso
        out[d] = dict(tmin=tmin, tmax=tmax, rh=max(1.0, min(100.0, 100 * vp / es)), wind=run / 86.4, rs=rs, rain=max(0.0, rain))
        if _f(r.get("R")) is not None:
            eto[d] = _f(r["R"])
    return _fill_gaps(out), eto


def _fill_gaps(w, max_gap=2):
    """Days dropped for missing values (the 2009 and 2011 files each lose one day) are filled by linear interpolation
    between the neighbouring days, rain 0; longer gaps are left so that simulate() raises instead of guessing."""
    days = sorted(w)
    for a, b in zip(days, days[1:]):
        n = (b - a).days - 1
        if 0 < n <= max_gap:
            for i in range(1, n + 1):
                f = i / (n + 1)
                w[a + timedelta(days=i)] = {k: (w[a][k] + (w[b][k] - w[a][k]) * f if k != "rain" else 0.0) for k in w[a]}
    return w


def load_site(root):
    rows = read_xlsx(Path(root) / "LIRF_Soils.xlsx")["Moisture Release"]
    fc = wp = wsum = 0.0
    for r in rows:
        top, bot, t33, t1500 = (_f(r.get(k)) for k in ("C", "D", "AD", "AG"))
        if None in (top, bot, t33, t1500) or top >= 100:
            continue
        thick = min(bot, 100) - top
        if thick > 0:
            fc += t33 * thick; wp += t1500 * thick; wsum += thick
    if wsum < 100:
        raise ValueError("soil moisture release table not understood: too little data in the top 100 cm")
    return Site(lat=LAT, elev_m=ELEV, fc=fc / wsum, wp=wp / wsum, root_depth_max_m=1.05,
                initial_depletion_frac=0.2, initial_ece=1.0)


@dataclass
class Treatment:
    year: int
    trno: int
    site: Site
    mgmt: Management
    obs_grain_t_ha: float        # dry grain yield (the 'Grain Yield' column that is about 85 % of the other one)
    obs_biomass_t_ha: float
    obs_harvest_index: float
    obs_silking: date | None     # first R1 note in the crop log
    obs_irrigation_mm: float


def _first_block(rows):
    """The 6 treatment-mean rows of the Seasonal sheet."""
    i = next(k for k, r in enumerate(rows) if r.get("A") == "Tmnt")
    out = []
    for r in rows[i + 1:]:
        if (r.get("A") or "").isdigit():
            out.append(r)
            if len(out) == 6:
                break
    return out


def load_treatments(root, year, site=None):
    book = read_xlsx(Path(root) / f"LIRF_Maize_{year}.xlsx")
    site = site or load_site(root)
    log = book["CropLog"]
    plant = next(_date(r["A"]) for r in log if "plant" in (r.get("B", "") + " " + r.get("C", "")).lower()
                 and r.get("B") in ("Planting", "Plant") or r.get("C") in ("Plant Corn", "Plant"))
    silk = next((_date(r["A"]) for r in log if r.get("B") == "Growth Stage" and (r.get("C") or "").strip() == "R1"), None)
    seasonal = _first_block(book["Seasonal"])
    out = []
    for k, srow in enumerate(seasonal, start=1):
        sheet = book[f"Tmnt{k}"]
        start = next(i for i, r in enumerate(sheet) if r.get("A") == "DOY")
        irr = {}
        for r in sheet[start + 2:]:
            doy, mm = _f(r.get("A")), _f(r.get("C"))
            if doy is not None and mm and mm > 0:
                irr[date(year, 1, 1) + timedelta(days=int(doy) - 1)] = (mm, IRRIGATION_EC)
        m = Management(sow_date=plant, irrigation={d: v for d, v in irr.items() if d >= plant}, irrigation_ec_default=IRRIGATION_EC)
        out.append(Treatment(year, k, site, m, float(srow["I"]) / 1000.0, float(srow["F"]) / 1000.0, float(srow["G"]), silk,
                             sum(mm for mm, _ in m.irrigation.values())))
    return out


def load_all(root):
    """-> list of (Treatment, weather dict) for every year that has files."""
    site, res = load_site(root), []
    for y in YEARS:
        if not (Path(root) / f"LIRF_Maize_{y}.xlsx").exists():
            continue
        weather, _ = load_weather(root, y)
        res += [(t, weather) for t in load_treatments(root, y, site)]
    return res
