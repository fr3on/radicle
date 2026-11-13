"""Weather-driven logistic disease epidemic with fungicide protection."""
from datetime import date

from .domain import DayWeather, Management
from .params import CropParams


def fungicide_factor(p: CropParams, mgmt: Management, day: date) -> float:
    """1 - efficacy of the best spray applied within the last `fungicide_days` days (1.0 = unprotected)."""
    best = max((e for sd, e in mgmt.fungicide.items() if 0 <= (day - sd).days < p.fungicide_days), default=0.0)
    return 1.0 - best


def step(p: CropParams, severity: float, gdd: float, w: DayWeather, tmean: float, protection: float) -> float:
    """Next severity (0..1). Active between the end of the initial stage and maturity, on warm humid days."""
    favourable = 1.0 if (w["rh"] >= p.dis_rh_min and p.dis_t_lo <= tmean <= p.dis_t_hi) else 0.0
    if p.gdd_dev_end < gdd < p.gdd_maturity:
        return min(1.0, severity + p.dis_rate * favourable * protection * severity * (1 - severity))
    return severity
