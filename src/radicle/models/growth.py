"""Biomass growth by normalised water productivity (AquaCrop-style): dB = WP * Ta/ET0, reduced by disease and heat."""
from .params import CropParams


def transpiration_ratio(p: CropParams, kc: float, ks_w: float, ks_s: float, gdd: float) -> float:
    """Ta/ET0: zero before emergence."""
    return (kc * min(ks_w, 1.0) * ks_s) if gdd > p.gdd_emergence else 0.0


def heat_factor(p: CropParams, tmax: float, gdd: float) -> float:
    hot = tmax > p.heat_tmax and p.gdd_mid_start < gdd < p.gdd_late_start
    return 1.0 - (0.1 if hot else 0.0)


def daily_biomass(p: CropParams, ta_over_et0: float, severity: float, heat: float) -> float:
    return p.wp_g_m2 * ta_over_et0 * (1 - p.dis_yield_loss * severity) * heat


def grain_yield_t_ha(p: CropParams, biomass_g_m2: float) -> float:
    return biomass_g_m2 * p.harvest_index / 100.0   # g/m2 -> t/ha
