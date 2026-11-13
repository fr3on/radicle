"""Builds the figures in docs/figures/ from experiment results. Run via `python scripts/make_figures.py`."""
import json
from pathlib import Path

from . import experiments as ex
from .ingest.loaders import load_field
from .models.crop import simulate
from .models.params import load_params
from .plot import lines_svg, scatter_svg, season_svg


def build(figures_dir="docs/figures", calibration="docs/maize_calibration.json", demo="data/demo") -> list[str]:
    out = Path(figures_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, s, m, _ = load_field(demo)
    r = simulate(w, s, m, load_params())
    (out / "demo_season.svg").write_text(season_svg(r, f"Synthetic demo field (yield {r.summary.yield_t_ha} t/ha)"))

    if ex.available(ex.EGYPT_ROOT):
        e = ex.egypt_wheat(load_params("wheat"))
        names = sorted(ex.SITE_NAMES)
        (out / "egypt_yield.svg").write_text(scatter_svg(
            e["pairs"], "observed yield (t/ha)", "simulated yield (t/ha)", "Wheat, Nile trials: placeholder parameters",
            labels=[names.index(x) for x in e["sites"]], legend=[ex.SITE_NAMES[n] for n in names],
            notes=e["yield_fit"].lines() + ["season 2011/12, fully irrigated"]))

    if Path(calibration).exists():
        d = json.loads(Path(calibration).read_text())
        rec, sm = d["records"], d["summary"]
        u, c = sm["uncalibrated"], sm["calibrated (held-out year)"]
        years = sorted({x["year"] for x in rec})
        (out / "maize_yield.svg").write_text(scatter_svg(
            [(x["obs"], x["heldout"]) for x in rec], "observed dry grain yield (t/ha)", "simulated yield (t/ha)",
            "Maize, Greeley CO: before and after calibration", labels=[years.index(x["year"]) for x in rec],
            legend=[str(y) for y in years], hollow=[(x["obs"], x["uncalibrated"]) for x in rec], hollow_label="placeholder params",
            notes=[f"n = {len(rec)} (4 yr x 6 irrigation)", "Filled = calibrated, each year", "predicted from the other 3 yrs:",
                   f"  bias {c['bias']:+.1f}, RMSE {c['rmse']}, r {c['r']}", "Rings = placeholder parameters:",
                   f"  bias {u['bias']:+.1f}, RMSE {u['rmse']}, r {u['r']}"]))
        series = []
        for i, y in enumerate(years):
            ry = sorted((x for x in rec if x["year"] == y), key=lambda x: x["irrigation_mm"])
            series.append((f"{y} observed", [(x["irrigation_mm"], x["obs"]) for x in ry], i, False))
            series.append((f"{y} simulated", [(x["irrigation_mm"], x["heldout"]) for x in ry], i, True))
        (out / "maize_irrigation_response.svg").write_text(lines_svg(
            series, "seasonal irrigation applied (mm)", "dry grain yield (t/ha)", "Maize yield response to irrigation",
            notes=["Solid = observed means", "Dashed = calibrated model,", "year held out of the fit", "Trend and ranking follow;",
                   "driest 2011 plot is missed", "(3.4 obs vs 5.3 sim)."]))
    return sorted(p.name for p in out.glob("*.svg"))
