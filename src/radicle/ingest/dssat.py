"""Loader for the Nile-gradient wheat dataset (Kheir et al., ODJAR 2020, DOI 10.18174/odjar.v6i0.16318, CC BY 4.0).
DSSAT text formats: .WHX management, .WHA observed means, .WTH weather (DATE=YYDDD), .SOL soil.
Weather has only SRAD, TMAX, TMIN, RAIN: wind and humidity are ASSUMED (FAO-56 arid-region defaults) below."""
import re
import statistics as st
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..models.crop import Management, Site
from ..models.et0 import sat_vp

WIND_DEFAULT = 2.0   # m/s assumption (FAO-56 default when wind missing)


def yyddd(v):
    v = int(v)
    return date(2000 + v // 1000, 1, 1) + timedelta(days=v % 1000 - 1)


def read_weather(path):
    out, on = {}, False
    for line in open(path, errors="replace"):
        if line.startswith("@DATE"):
            on = True
            continue
        if on and line.strip():
            p = line.split()
            srad, tmax, tmin, rain = (float(x) for x in p[1:5])
            es = (sat_vp(tmax) + sat_vp(tmin)) / 2
            ea = sat_vp(tmin - 2.0)  # FAO-56: Tdew ~ Tmin - 2 C in arid regions (assumption)
            out[yyddd(p[0])] = dict(tmin=tmin, tmax=tmax, rh=min(100.0, 100 * ea / es), wind=WIND_DEFAULT, rs=srad, rain=rain)
    return out


def read_soils(folder):
    prof = {}
    for f in Path(folder).iterdir():
        cur = None
        for line in open(f, errors="replace"):
            m = re.match(r"\*(\w+)\s", line)
            if m:
                cur = m.group(1)
                prof[cur] = dict(layers=[], lat=None)
            elif cur and re.match(r"\s+[A-Za-z]", line) and "Egypt" in line:
                m2 = re.search(r"Egypt\s+(-?[\d.]+)", line)
                prof[cur]["lat"] = float(m2.group(1)) if m2 else None
            elif cur and re.match(r"\s+\d+\s", line) and len(line.split()) >= 5:
                p = line.split()
                try:
                    prof[cur]["layers"].append((float(p[0]), float(p[2]), float(p[3])))
                except ValueError:
                    pass
    return prof


def soil_site(profile, depth=100):
    prev, fc, wp, w = 0.0, 0.0, 0.0, 0.0
    for bot, ll, dul in profile["layers"]:
        thick = min(bot, depth) - prev
        if thick > 0:
            fc += dul * thick; wp += ll * thick; w += thick
        prev = bot
        if bot >= depth: break
    return Site(lat=profile["lat"] or 30.0, fc=fc / w, wp=wp / w, root_depth_max_m=min(1.0, w / 100),
                initial_depletion_frac=0.1, initial_ece=2.0)


@dataclass
class Treatment:
    exp: str
    trno: int
    name: str
    site: Site
    mgmt: Management
    weather_key: str
    obs_yield_t_ha: float
    obs_adat: float
    obs_mdat: float


def load_experiment(root, code, soils):
    d = Path(root) / "Dataset"
    whx = open(d / "Experimental_data_4locations_3seasons" / f"{code}.WHX.txt", errors="replace").read().splitlines()
    wha = open(d / "Experimental_data_4locations_3seasons" / f"{code}.WHA.txt", errors="replace").read().splitlines()
    trts, plant, irr, soil_id, sec = [], {}, {}, None, None
    for line in whx:
        if line.startswith("*"):
            sec = line[1:12]
            continue
        if line.startswith("@") or not line.strip():
            sub = line
            continue
        p = line.split()
        if sec.startswith("TREATMENTS"):
            trts.append(dict(n=int(p[0]), name=p[4], mp=int(p[9]), mi=int(p[10])))
        elif sec.startswith("FIELDS") and sub.startswith("@L ID_FIELD"):
            soil_id = p[-2]
        elif sec.startswith("PLANTING"):
            plant[int(p[0])] = yyddd(p[1])
        elif sec.startswith("IRRIGATION") and sub.startswith("@I IDATE"):
            irr.setdefault(int(p[0]), {})[yyddd(p[1])] = float(p[3])
    obs = {}
    for line in wha:
        p = line.split()
        if p and p[0].isdigit():
            obs[int(p[0])] = (float(p[1].rstrip(".")) / 1000.0, float(p[6]), float(p[7]))
    site = soil_site(soils[soil_id])
    out = []
    for t in trts:
        if t["n"] not in obs:
            continue
        m = Management(sow_date=plant[t["mp"]])
        m.irrigation = {dt: (mm, 1.0) for dt, mm in irr.get(t["mi"], {}).items()}
        out.append(Treatment(code, t["n"], t["name"], site, m, code, *obs[t["n"]]))
    return out


def load_all(root):
    soils = read_soils(Path(root) / "Dataset" / "Soil _data_4locations")
    res = []
    for f in sorted((Path(root) / "Dataset" / "Experimental_data_4locations_3seasons").glob("*.WHX.txt")):
        code = f.name.split(".")[0]
        wf = Path(root) / "Dataset" / "Weather data_four locations_3seasons" / f"{code}.WTH"
        weather = read_weather(wf)
        nxt = wf.with_name(f"{code[:4]}{int(code[4:6]) + 1}{code[6:]}.WTH")  # season crosses the calendar year
        if nxt.exists():
            weather.update(read_weather(nxt))
        for t in load_experiment(root, code, soils):
            t.weather = weather
            res.append(t)
    return res
