"""One loader per data type. Each validates ranges and units, reports row-level errors, returns normalised objects.

Expected CSV files per field directory (data/<field>/):
  weather.csv      date,tmin,tmax,rh_mean,wind_2m,rs_mjm2,rain_mm      (rs may be replaced by sunshine_h later)
  soil.csv         key,value   keys: lat, elev_m, fc, wp, root_depth_max_m, initial_ece_dsm
  management.csv   date,event,amount,ec_dsm   events: sow | irrigation | fungicide(amount=efficacy 0..1)
  observations.csv date,variable,value   variables: yield_t_ha, ece_dsm, ndvi, disease_severity, biomass_g_m2, lai
"""
import csv
from datetime import date
from pathlib import Path

from ..models.crop import Management, Site


class DataError(ValueError):
    pass


def _rows(path, required):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        missing = [c for c in required if c not in (r.fieldnames or [])]
        if missing:
            raise DataError(f"{path}: missing columns {missing}")
        for i, row in enumerate(r, start=2):
            yield i, row


def _num(path, i, row, col, lo, hi):
    try:
        v = float(row[col])
    except (TypeError, ValueError):
        raise DataError(f"{path} line {i}: '{col}' is not a number: {row[col]!r}")
    if not lo <= v <= hi:
        raise DataError(f"{path} line {i}: '{col}'={v} outside plausible range [{lo}, {hi}]")
    return v


def _date(path, i, row):
    try:
        return date.fromisoformat(row["date"])
    except ValueError:
        raise DataError(f"{path} line {i}: date must be YYYY-MM-DD, got {row['date']!r}")


def load_weather(path):
    out = {}
    for i, row in _rows(path, ["date", "tmin", "tmax", "rh_mean", "wind_2m", "rs_mjm2", "rain_mm"]):
        d = _date(path, i, row)
        w = dict(tmin=_num(path, i, row, "tmin", -30, 55), tmax=_num(path, i, row, "tmax", -30, 60),
                 rh=_num(path, i, row, "rh_mean", 0, 100), wind=_num(path, i, row, "wind_2m", 0, 40),
                 rs=_num(path, i, row, "rs_mjm2", 0, 40), rain=_num(path, i, row, "rain_mm", 0, 500))
        if w["tmin"] > w["tmax"]:
            raise DataError(f"{path} line {i}: tmin > tmax")
        if d in out:
            raise DataError(f"{path} line {i}: duplicate date {d}")
        out[d] = w
    return out


def load_soil(path):
    keys = {"lat": ("lat", -90, 90), "elev_m": ("elev_m", -500, 6000), "fc": ("fc", 0, 1), "wp": ("wp", 0, 1),
            "root_depth_max_m": ("root_depth_max_m", 0.1, 5), "initial_ece_dsm": ("initial_ece", 0, 50)}
    kv = {}
    for i, row in _rows(path, ["key", "value"]):
        k = (row["key"] or "").strip()
        if k not in keys:
            raise DataError(f"{path} line {i}: unknown soil key {k!r}; allowed: {sorted(keys)}")
        kv[k] = _num(path, i, row, "value", keys[k][1], keys[k][2])
    missing = [k for k in ("lat", "fc", "wp") if k not in kv]
    if missing:
        raise DataError(f"{path}: missing required soil keys {missing}")
    s = Site()
    for key, (attr, _, _) in keys.items():
        if key in kv:
            setattr(s, attr, kv[key])
    if not 0 < s.wp < s.fc < 0.7:
        raise DataError(f"{path}: need 0 < wp < fc < 0.7 (got wp={s.wp}, fc={s.fc})")
    return s


def load_management(path):
    m = Management()
    sown = False
    for i, row in _rows(path, ["date", "event", "amount"]):
        d = _date(path, i, row)
        ev = (row["event"] or "").strip().lower()
        if ev == "sow":
            m.sow_date, sown = d, True
        elif ev == "irrigation":
            ec = (row.get("ec_dsm") or "").strip() or m.irrigation_ec_default
            m.irrigation[d] = (_num(path, i, row, "amount", 0, 500), _num(path, i, {"ec_dsm": ec}, "ec_dsm", 0, 30))
        elif ev == "fungicide":
            m.fungicide[d] = _num(path, i, row, "amount", 0, 1)
        else:
            raise DataError(f"{path} line {i}: unknown event {ev!r}")
    if not sown:
        raise DataError(f"{path}: no 'sow' event")
    return m


def load_observations(path):
    known = {"yield_t_ha", "ece_dsm", "ndvi", "disease_severity", "biomass_g_m2", "lai"}
    obs = []
    for i, row in _rows(path, ["date", "variable", "value"]):
        var = (row["variable"] or "").strip()
        if var not in known:
            raise DataError(f"{path} line {i}: unknown variable {var!r}; allowed: {sorted(known)}")
        obs.append((_date(path, i, row), var, _num(path, i, row, "value", -1e9, 1e9)))
    return obs


def load_field(dirpath):
    p = Path(dirpath)
    weather = load_weather(p / "weather.csv")
    site = load_soil(p / "soil.csv")
    mgmt = load_management(p / "management.csv")
    obs = load_observations(p / "observations.csv") if (p / "observations.csv").exists() else []
    return weather, site, mgmt, obs
