"""Parameter fitting: a dependency-free random search for one field, and a generic grid search for many.

With one season of data both are under-determined: treat results as a sanity check, and record where they came from
in the parameter file's provenance (see CropParams.save)."""
import itertools
import random
from dataclasses import replace
from typing import Callable, Iterable

from .models.crop import simulate
from .models.params import CropParams

TUNABLE = {"wp_g_m2": (8, 25), "harvest_index": (0.3, 0.55), "salt_threshold_dsm": (3, 10),
           "salt_slope_per_dsm": (0.03, 0.15), "dis_yield_loss": (0.1, 0.7), "p_depletion": (0.4, 0.7)}


def loss(result, obs) -> float | None:
    """Mean squared relative error over the usable observations; None if there are none or the run was truncated."""
    if not result["summary"]["matured"]:
        return None  # truncated run (weather ended early): its yield/biomass are not comparable to observations
    err, n = 0.0, 0
    by_date = {r["date"]: r for r in result["daily"]}
    for d, var, val in obs:
        if var == "yield_t_ha":
            err += ((result["summary"]["yield_t_ha"] - val) / max(val, 0.1)) ** 2
            n += 1
        elif var == "ece_dsm" and d.isoformat() in by_date:
            err += ((by_date[d.isoformat()]["ece"] - val) / max(val, 0.5)) ** 2
            n += 1
        elif var == "disease_severity" and d.isoformat() in by_date:
            err += (by_date[d.isoformat()]["disease"] - val) ** 2 * 4
            n += 1
        elif var == "biomass_g_m2" and d.isoformat() in by_date:
            err += ((by_date[d.isoformat()]["biomass_g_m2"] - val) / max(val, 10)) ** 2
            n += 1
    return err / n if n else None


def calibrate(weather, site, mgmt, params: CropParams, obs, iters: int = 300, seed: int = 0, keys=None):
    """Random-search hill climbing on `keys` (default TUNABLE). Returns (best CropParams, best loss)."""
    rnd = random.Random(seed)
    keys = keys or list(TUNABLE)
    best = params
    best_loss = loss(simulate(weather, site, mgmt, best), obs)
    if best_loss is None:
        raise ValueError("No usable observations: need yield_t_ha, ece_dsm, disease_severity or biomass_g_m2 dated inside the "
                         "simulated season, and weather long enough for the crop to mature.")
    for _ in range(iters):
        changes = {}
        for k in rnd.sample(keys, k=min(2, len(keys))):
            lo, hi = TUNABLE[k]
            changes[k] = min(hi, max(lo, getattr(best, k) + rnd.gauss(0, (hi - lo) * 0.1)))
        try:
            cand = replace(best, **changes)
        except ValueError:      # e.g. stage thresholds out of order
            continue
        l = loss(simulate(weather, site, mgmt, cand), obs)
        if l is not None and l < best_loss:
            best, best_loss = cand, l
    return best, best_loss


def fit_grid(items, base: CropParams, grid: dict[str, Iterable[float]], objective: Callable[[CropParams, list], float]):
    """Exhaustive search over the cartesian product of `grid` (name -> values). Returns the CropParams with the lowest
    `objective(params, items)`; invalid combinations are skipped."""
    names = list(grid)
    best, best_val = None, float("inf")
    for combo in itertools.product(*(list(grid[n]) for n in names)):
        try:
            cand = replace(base, **dict(zip(names, combo)))
        except ValueError:
            continue
        val = objective(cand, items)
        if val < best_val:
            best, best_val = cand, val
    if best is None:
        raise ValueError("no valid parameter combination in the grid")
    return best
