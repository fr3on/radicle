"""Root-zone salt balance. Salt is stored as (solution EC in dS/m) x (mm of soil water), so that
concentration = salt / water-at-field-capacity and irrigation adds `mm * EC` directly."""
from .domain import Site
from .params import CropParams


def initial_concentration(site: Site) -> float:
    """Soil-solution EC of unexplored soil, from the saturated-paste ECe."""
    return site.initial_ece / site.ece_per_conc


def salt_from_new_soil(site: Site, extra_wfc: float) -> float:
    """Roots reaching new soil bring that soil's initial salt into the root zone."""
    return initial_concentration(site) * extra_wfc


def irrigation_salt(mm: float, ec: float) -> float:
    return mm * ec


def leach(salt: float, wfc: float, drain: float) -> float:
    """Salt after `drain` mm leaves with water at the mixed concentration."""
    return salt - (salt / (wfc + drain)) * drain


def ece(salt: float, wfc: float, site: Site) -> float:
    return salt / wfc * site.ece_per_conc


def salt_stress(p: CropParams, ece_dsm: float) -> float:
    """Maas-Hoffman threshold-slope relative yield (1 = no stress)."""
    return max(0.0, 1.0 - p.salt_slope_per_dsm * max(0.0, ece_dsm - p.salt_threshold_dsm))
