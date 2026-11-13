"""Single root-zone water balance (FAO-56 depletion bookkeeping)."""
from dataclasses import dataclass

from .domain import Site
from .params import CropParams


@dataclass(frozen=True)
class RootZone:
    zr: float      # rooting depth, m
    taw: float     # total available water, mm
    raw: float     # readily available water, mm
    wfc: float     # water held at field capacity, mm


def root_zone(p: CropParams, site: Site, zr: float) -> RootZone:
    taw = 1000 * (site.fc - site.wp) * zr
    return RootZone(zr=zr, taw=taw, raw=p.p_depletion * taw, wfc=1000 * site.fc * zr)


def initial_depletion(site: Site, rz: RootZone) -> float:
    return site.initial_depletion_frac * rz.taw


def water_stress(depletion: float, rz: RootZone) -> float:
    """Ks: 1 while depletion is within RAW, then falls linearly to 0 at TAW."""
    return 1.0 if depletion <= rz.raw else max(0.0, (rz.taw - depletion) / (rz.taw - rz.raw))


def actual_et(p: CropParams, kc: float, et0: float, ks_w: float, ks_s: float, gdd: float) -> float:
    """ETc adjusted for stress; before emergence only soil evaporation (0.3 of Kc*ET0)."""
    if gdd > p.gdd_emergence:
        return kc * et0 * min(ks_w, 1.0) * ks_s
    return kc * et0 * 0.3


def effective_rain(rain: float) -> float:
    """Rain above 2 mm, 80 % of it infiltrating (crude runoff/interception)."""
    return max(0.0, rain - 2.0) * 0.8 if rain > 2.0 else 0.0


def balance_step(depletion: float, etc: float, rain_eff: float, irrigation: float, rz: RootZone) -> tuple[float, float]:
    """One day: returns (new depletion capped at TAW, drainage). Water above field capacity drains."""
    dr = depletion + etc - rain_eff - irrigation
    drain = 0.0
    if dr < 0:
        drain = -dr
        dr = 0.0
    return min(dr, rz.taw), drain
