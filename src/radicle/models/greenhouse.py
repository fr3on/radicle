"""Greenhouse dwarf tomato (pot/substrate) growth model, driven by measured compartment climate.

Light-use-efficiency growth: dDM = LUE * intercepted PAR * f(T) * f(CO2) * f(salt); a fraction of new dry matter goes to
fruit after the flowering thermal time. Salinity enters only through `ec` when given; with the AGC4 data it is NOT
validated (see docs/DATA-SOURCES.md). All defaults are placeholders from memory of tomato literature."""
import math
from dataclasses import dataclass


@dataclass
class GHParams:
    lue_g_mol: float = 2.5          # g dry matter per mol intercepted PAR (placeholder)
    k_ext: float = 0.7              # light extinction coefficient
    lai0: float = 0.6
    lai_max: float = 3.0
    lai_per_tt: float = 0.004       # LAI increase per degree-day
    tbase: float = 6.0
    tt_flower: float = 300.0        # degree-days from start until fruit set begins (fitted)
    tt_fruit_full: float = 250.0    # degree-days to reach fmax after tt_flower
    fmax: float = 0.7
    dm_frac_fruit: float = 0.07     # fruit dry matter fraction (placeholder)
    co2_gain: float = 0.25          # relative gain at 800 vs 400 ppm
    topt_lo: float = 18.0
    topt_hi: float = 26.0
    tmin: float = 8.0
    tmax: float = 35.0
    salt_threshold: float = 2.5     # dS/m, FAO-29 tomato (from memory, unverified mapping to substrate EC)
    salt_slope: float = 0.099
    w0_veg: float = 20.0            # initial vegetative dry matter, g/m2


def f_temp(t, p):
    if t <= p.tmin or t >= p.tmax:
        return 0.0
    if t < p.topt_lo:
        return (t - p.tmin) / (p.topt_lo - p.tmin)
    if t <= p.topt_hi:
        return 1.0
    return (p.tmax - t) / (p.tmax - p.topt_hi)


def simulate(daily, density_plants_m2, p, ec_by_day=None):
    """daily: {date: dict(par_mol, t, co2)}. Returns {date: fruit fresh weight per plant, g} and totals."""
    tt = 0.0
    lai = p.lai0
    w_veg, w_fruit = p.w0_veg, 0.0
    out = {}
    for d in sorted(daily):
        x = daily[d]
        if x["t"] is None or x["par_mol"] is None:
            continue
        tt += max(0.0, x["t"] - p.tbase)
        lai = min(p.lai_max, p.lai0 + p.lai_per_tt * tt)
        fi = 1 - math.exp(-p.k_ext * lai)
        fco2 = 1 + p.co2_gain * max(-0.5, min(1.0, ((x["co2"] or 400.0) - 400.0) / 400.0))
        ec = (ec_by_day or {}).get(d)
        fsalt = 1.0 if ec is None else max(0.0, 1 - p.salt_slope * max(0.0, ec - p.salt_threshold))
        dm = p.lue_g_mol * fi * x["par_mol"] * f_temp(x["t"], p) * fco2 * fsalt
        frac = 0.0 if tt < p.tt_flower else min(1.0, (tt - p.tt_flower) / p.tt_fruit_full) * p.fmax
        w_fruit += dm * frac
        w_veg += dm * (1 - frac)
        out[d] = w_fruit / p.dm_frac_fruit / density_plants_m2   # g fresh fruit per plant
    return out
