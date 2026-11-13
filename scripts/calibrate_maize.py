"""Leave-one-year-out calibration of maize wp_g_m2, harvest_index and p_depletion on the Greeley trials, then a fit on all
24 treatments saved to params/maize_greeley_calibrated.json. Usage (repo root): python scripts/calibrate_maize.py"""
import json
from pathlib import Path

from radicle import experiments as ex
from radicle.models.params import load_params

base = load_params("maize_greeley")
r = ex.maize_leave_one_year_out(base)
for y, f in r["folds"].items():
    print(y, "fitted", f)
for label, s in r["summary"].items():
    print(f"{label}: yield bias {s['bias']:+.2f} RMSE {s['rmse']} r {s['r']} | biomass bias {s['biomass_bias']:+.1f} t/ha")
Path("docs/maize_calibration.json").write_text(json.dumps(dict(summary=r["summary"], records=r["records"]), indent=1) + "\n")
src = "calibrated:greeley-maize 24 treatments, grid search on yield+biomass (leave-one-year-out in docs/maize_calibration.json)"
final = r["final"].save("params/maize_greeley_calibrated.json", calibrated={k: src for k in ex.MAIZE_GRID},
                        note="maize_greeley.json with wp_g_m2, harvest_index and p_depletion fitted to ALL 24 Greeley treatments "
                             "(grid search, yield+biomass). Leave-one-year-out error is in docs/maize_calibration.json. One site, "
                             "4 seasons, drip-irrigated, no N or salinity data: do not extrapolate.")
print("saved", {k: getattr(final, k) for k in ex.MAIZE_GRID})
