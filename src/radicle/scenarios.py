"""'Digital replanting': rerun the same field with changed sowing date, irrigation water quality, or irrigation depth."""
import copy
from datetime import timedelta

from .models.crop import simulate


def run_scenario(weather, site, mgmt, params, sow_shift_days=0, irrigation_ec=None, irrigation_scale=1.0, **kw):
    m = copy.deepcopy(mgmt)
    m.sow_date = mgmt.sow_date + timedelta(days=sow_shift_days)
    m.irrigation = {d + timedelta(days=sow_shift_days): (mm * irrigation_scale, ec if irrigation_ec is None else irrigation_ec)
                    for d, (mm, ec) in mgmt.irrigation.items()}
    return simulate(weather, site, m, params, **kw)["summary"]


def sweep(weather, site, mgmt, params, skipped=None):
    """Rows only for runs that matured. Skipped combinations are appended to `skipped` as (shift, ec, scale, reason)."""
    rows = []
    skip = skipped if skipped is not None else []
    for shift in (-14, -7, 0, 7, 14):
        for ec in (None, 0.5, 3.0, 5.0):
            for scale in (0.7, 1.0, 1.3):
                try:
                    s = run_scenario(weather, site, mgmt, params, shift, ec, scale)
                except ValueError as e:
                    skip.append((shift, ec, scale, str(e)))
                    continue  # do not report a fake 0
                if not s["matured"]:
                    skip.append((shift, ec, scale, "crop did not mature before weather record ends"))
                    continue
                rows.append(dict(sow_shift_days=shift, irrigation_ec=ec if ec is not None else "as-recorded",
                                 irrigation_scale=scale, **s))
    return rows
