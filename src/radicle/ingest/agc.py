"""Loader for the 4th Autonomous Greenhouse Challenge dwarf tomato data (4TU, CC BY 4.0, 2024).
Daily aggregates of the 5-minute compartment series plus manual fruit harvests per compartment."""
import csv
import re
import statistics as st
from datetime import date
from pathlib import Path

from .xlsx_min import read_xlsx

TEAM_BY_GH = {"301": "tomatonuts", "302": "mugrow", "303": "agrifusion", "306": "reference", "307": "ideas", "308": "trigger"}
TEAMS = list(TEAM_BY_GH.values())
SAMPLE_S = 300.0  # data are 5-minute: ASSUMPTION from row counts (about 288 rows/day)


def _fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_daily(root, team):
    path = Path(root) / "timeseries" / f"{team}.csv"
    byday = {}
    for r in csv.DictReader(open(path)):
        d = date.fromisoformat(r["time"][:10])
        b = byday.setdefault(d, dict(par=[], t=[], co2=[], vpd=[], drain_ec=[], drain_l=[], n=0))
        b["n"] += 1
        for k, c in [("par", "compartment/par"), ("t", "compartment/air_temperature"), ("co2", "compartment/co2_concentration"),
                     ("vpd", "compartment/humidity_deficit"), ("drain_ec", "compartment/water_drain/ec"),
                     ("drain_l", "compartment/water_drain/water_volume")]:
            v = _fnum(r.get(c))
            if v is not None:
                b[k].append(v)
    out = {}
    for d, b in sorted(byday.items()):
        if b["n"] < 200 or not b["par"]:   # skip partial days (first/last)
            continue
        mean = lambda v: st.mean(v) if v else None
        out[d] = dict(par_mol=st.mean(b["par"]) * 86400 / 1e6, t=mean(b["t"]), co2=mean(b["co2"]), vpd=mean(b["vpd"]),
                      drain_ec=mean(b["drain_ec"]), drain_l_m2=sum(b["drain_l"]) if b["drain_l"] else None)
    return out


def load_density(root, team):
    vals = [_fnum(r.get("dwarf_tomato/plant_density")) for r in csv.DictReader(open(Path(root) / "timeseries" / f"{team}.csv"))]
    vals = [v for v in vals if v]
    return st.mean(vals)


def load_harvest(root, daily_by_team):
    """Mean fruit fresh weight per plant (g) per compartment: {team: {date: (mean_fw_g, mean_count)}}.
    Destructive harvests 2024-10-07, 10-22, 11-05 (dates from sheet names); final harvest date is NOT given in the
    file: ASSUMED to be the last full day of that compartment's series."""
    book = read_xlsx(Path(root) / "Harvest.xlsx")
    dates = {"Destructive harvest 7-10-24": date(2024, 10, 7), "Destructive harvest 22-10-24": date(2024, 10, 22),
             "Destructive harvest 05-11-24": date(2024, 11, 5)}
    res = {}
    for name, rows in book.items():
        if name == "Information":
            continue
        fw_col, n_col = ("B", "D") if name == "Destructive harvest 7-10-24" else ("C", "D")
        for r in rows:
            pid = r.get("A") if name == "Destructive harvest 7-10-24" else r.get("B")
            if not pid or not re.fullmatch(r"\d{3}-\d", pid):
                continue
            team = TEAM_BY_GH[pid[:3]]
            if name in dates:
                dt = dates[name]
            else:
                dt = max(daily_by_team[team])
            fw, n = _fnum(r.get(fw_col)), _fnum(r.get(n_col))
            if fw:
                res.setdefault(team, {}).setdefault(dt, []).append((fw, n))
    return {t: {d: (st.mean(x[0] for x in v), st.mean(x[1] for x in v if x[1])) for d, v in dd.items()} for t, dd in res.items()}
