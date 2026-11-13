"""Development: thermal time, crop coefficient curve, rooting depth."""
from .domain import Site
from .params import CropParams


def thermal_time(p: CropParams, tmin: float, tmax: float) -> float:
    """Degree days gained in one day."""
    if p.gdd_method == "clip":    # maize-style: Tmax capped, Tmin floored, then averaged
        return max(0.0, (min(tmax, p.tmax_cut) + max(tmin, p.tbase)) / 2 - p.tbase)
    tmean = (tmin + tmax) / 2
    return max(0.0, min(tmean, p.tmax_cut) - p.tbase)


def interpolate(x: float, points: list[tuple[float, float]]) -> float:
    """Piecewise linear through [(x, y), ...] (x ascending), flat outside the range."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def crop_coefficient(p: CropParams, gdd: float) -> float:
    """FAO-56 single Kc as a function of thermal time (initial, development, mid, late)."""
    return interpolate(gdd, [(0, p.kc_ini), (p.gdd_dev_end, p.kc_ini), (p.gdd_mid_start, p.kc_mid),
                             (p.gdd_late_start, p.kc_mid), (p.gdd_maturity, p.kc_end)])


def root_depth(p: CropParams, site: Site, gdd: float) -> float:
    """Rooting depth in m: linear from `root_depth_min_m` to the site maximum at anthesis."""
    frac = min(1.0, gdd / p.gdd_anthesis)
    return p.root_depth_min_m + (site.root_depth_max_m - p.root_depth_min_m) * frac


def killed_by_frost(p: CropParams, gdd: float, tmin: float) -> bool:
    return p.frost_kill_tmin is not None and gdd >= p.gdd_anthesis and tmin <= p.frost_kill_tmin
