"""Every evaluation reported in the README and docs, as plain functions returning data (no printing, no plotting).

Scripts, the figure builder and `radicle reproduce` all call these, so a number quoted in the docs has exactly one
origin. Raw datasets are looked up under `data/external/` (see docs/DATA-SOURCES.md); each function raises
FileNotFoundError if its data is missing and `available()` tells you beforehand."""
import hashlib
import json
import platform
import statistics as st
from dataclasses import asdict
from datetime import date
from pathlib import Path

from . import __version__
from .calibrate import fit_grid
from .ingest import dssat, greeley
from .metrics import FitStats
from .models.crop import simulate
from .models.et0 import et0_daily
from .models.params import PARAMS_DIR, CropParams, load_params

EGYPT_ROOT = "data/external/egypt-nile-wheat/x"
GREELEY_ROOT = "data/external/greeley-maize"
SITE_NAMES = {"ASWN": "Aswan", "BSUF": "Beni Suef", "MNFY": "Menofya", "SARS": "Sakha"}
MAIZE_GRID = {"wp_g_m2": [14 + 2 * i for i in range(14)], "harvest_index": [0.40, 0.45, 0.50, 0.55, 0.60],
              "p_depletion": [0.40, 0.50, 0.60, 0.70]}


def available(root: str) -> bool:
    return Path(root).exists() and any(Path(root).iterdir())


# ------------------------------------------------------------------ wheat on the Nile trials
def egypt_wheat(params: CropParams, root: str = EGYPT_ROOT) -> dict:
    """22 fully irrigated treatments at 4 sites, season 2011/12. Timing columns ADAT/MDAT are days after planting
    as inferred from the file (docs/DATA-SOURCES.md)."""
    runs = []
    for t in dssat.load_all(root):
        s = simulate(t.weather, t.site, t.mgmt, params).summary
        if s.matured:
            runs.append((t, s, (date.fromisoformat(s.anthesis_date) - t.mgmt.sow_date).days,
                         (date.fromisoformat(s.harvest_date) - t.mgmt.sow_date).days))
    by_site = {}
    for site in sorted({r[0].exp[:4] for r in runs}):
        rr = [r for r in runs if r[0].exp.startswith(site)]
        by_site[site] = dict(name=SITE_NAMES.get(site, site), yield_sim=st.mean(r[1].yield_t_ha for r in rr),
                             yield_obs=st.mean(r[0].obs_yield_t_ha for r in rr),
                             maturity_sim_days=st.mean(r[3] for r in rr), maturity_obs_days=st.mean(r[0].obs_mdat for r in rr),
                             irrigation_mm=st.mean(r[1].irrigation_mm for r in rr))
    return dict(params=params.name, n_matured=len(runs),
                yield_fit=FitStats.from_pairs((r[0].obs_yield_t_ha, r[1].yield_t_ha) for r in runs),
                pairs=[(r[0].obs_yield_t_ha, r[1].yield_t_ha) for r in runs], sites=[r[0].exp[:4] for r in runs],
                anthesis_sim_days=st.mean(r[2] for r in runs), anthesis_obs_days=st.mean(r[0].obs_adat for r in runs),
                maturity_sim_days=st.mean(r[3] for r in runs), maturity_obs_days=st.mean(r[0].obs_mdat for r in runs),
                by_site=by_site)


# ------------------------------------------------------------------ maize at Greeley
def greeley_runs(params: CropParams, root: str = GREELEY_ROOT) -> list:
    """[(Treatment, Summary)] for the 24 treatments (4 years x 6 irrigation levels)."""
    return [(t, simulate(w, t.site, t.mgmt, params).summary) for t, w in greeley.load_all(root)]


def greeley_maize(params: CropParams, root: str = GREELEY_ROOT) -> dict:
    runs = greeley_runs(params, root)
    by_year = {}
    for y in sorted({t.year for t, _ in runs}):
        yr = sorted(((t.obs_irrigation_mm, s.yield_t_ha, t.obs_grain_t_ha) for t, s in runs if t.year == y))
        by_year[y] = dict(r=FitStats.from_pairs((o, p) for _, p, o in yr).r, sim_driest=yr[0][1], sim_wettest=yr[-1][1],
                          obs_driest=yr[0][2], obs_wettest=yr[-1][2])
    return dict(params=params.name, n=len(runs), n_completed=sum(s.matured for _, s in runs),
                yield_fit=FitStats.from_pairs((t.obs_grain_t_ha, s.yield_t_ha) for t, s in runs),
                biomass_fit=FitStats.from_pairs((t.obs_biomass_t_ha, s.biomass_g_m2 / 100) for t, s in runs),
                by_year=by_year)


def et0_check(root: str = GREELEY_ROOT, days: tuple = (130, 280)) -> FitStats:
    """radicle's FAO-56 ET0 against the station's published ASCE grass ETo on growing-season days.
    Pairs are (published, radicle), so bias = radicle - published."""
    pairs = []
    for y in greeley.YEARS:
        w, eto = greeley.load_weather(root, y)
        pairs += [(eto[k], et0_daily(x["tmin"], x["tmax"], x["rh"], x["wind"], x["rs"], greeley.LAT,
                                     k.timetuple().tm_yday, greeley.ELEV))
                  for k, x in w.items() if k in eto and days[0] <= k.timetuple().tm_yday <= days[1]]
    return FitStats.from_pairs(pairs)


def _maize_loss(params: CropParams, items: list) -> float:
    errs = []
    for t, w in items:
        s = simulate(w, t.site, t.mgmt, params).summary
        errs.append(((s.yield_t_ha - t.obs_grain_t_ha) / t.obs_grain_t_ha) ** 2
                    + ((s.biomass_g_m2 / 100 - t.obs_biomass_t_ha) / t.obs_biomass_t_ha) ** 2)
    return st.mean(errs)


def maize_leave_one_year_out(base: CropParams, root: str = GREELEY_ROOT, grid: dict = MAIZE_GRID) -> dict:
    """Fit wp_g_m2, harvest_index and p_depletion on three years, predict the fourth; repeat for each year, then fit
    on everything. Returns per-treatment records, summary statistics and the all-data fit (`final`, a CropParams)."""
    data = greeley.load_all(root)
    records, folds = [], {}
    for y in sorted({t.year for t, _ in data}):
        train, test = [d for d in data if d[0].year != y], [d for d in data if d[0].year == y]
        fitted = fit_grid(train, base, grid, _maize_loss)
        folds[y] = {k: getattr(fitted, k) for k in grid}
        for t, w in test:
            records.append(dict(year=t.year, trno=t.trno, irrigation_mm=t.obs_irrigation_mm, obs=t.obs_grain_t_ha,
                                uncalibrated=simulate(w, t.site, t.mgmt, base).summary.yield_t_ha,
                                heldout=simulate(w, t.site, t.mgmt, fitted).summary.yield_t_ha,
                                obs_biomass=t.obs_biomass_t_ha,
                                uncalibrated_biomass=simulate(w, t.site, t.mgmt, base).summary.biomass_g_m2 / 100,
                                heldout_biomass=simulate(w, t.site, t.mgmt, fitted).summary.biomass_g_m2 / 100))
    summary = {}
    for label, key in (("uncalibrated", "uncalibrated"), ("calibrated (held-out year)", "heldout")):
        f = FitStats.from_pairs((x["obs"], x[key]) for x in records)
        summary[label] = dict(bias=round(f.bias, 2), rmse=round(f.rmse, 2), r=round(f.r, 2),
                              biomass_bias=round(st.mean(x[key + "_biomass"] - x["obs_biomass"] for x in records), 1))
    return dict(summary=summary, records=records, folds=folds, final=fit_grid(data, base, grid, _maize_loss))


# ------------------------------------------------------------------ reproduce everything
def _tree_hash(path) -> str:
    h = hashlib.sha256()
    p = Path(path)
    for f in sorted(x for x in (p.rglob("*") if p.is_dir() else [p]) if x.is_file() and x.name != ".DS_Store"):
        h.update(f.relative_to(p if p.is_dir() else p.parent).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _dump(obj, path: Path):
    def enc(o):
        if isinstance(o, FitStats):
            return o.rounded()
        if isinstance(o, CropParams):
            return o.name
        raise TypeError(type(o))
    path.write_text(json.dumps(obj, indent=2, default=enc, sort_keys=False) + "\n")


def reproduce(results_dir="results", docs_dir="docs", maize_loyo: bool = True) -> dict:
    """Recompute every reported number and write results/*.json plus a manifest with versions and data/parameter hashes.
    Experiments whose data is missing are listed under `skipped`. Writes docs/maize_calibration.json for the figures."""
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(radicle=__version__, python=platform.python_version(), written=[], skipped={}, params={}, data={})
    wheat, maize_pl, maize_gr = load_params("wheat"), load_params("maize_greeley"), load_params("maize_greeley_calibrated")

    def stash(name, obj, params=(), data=()):
        _dump(obj, out / f"{name}.json")
        manifest["written"].append(f"{name}.json")
        for p in params:
            manifest["params"][p.name] = _tree_hash(PARAMS_DIR / f"{p.name}.json")
        for d in data:
            manifest["data"][d] = _tree_hash(d)

    if available(EGYPT_ROOT):
        stash("wheat_egypt", egypt_wheat(wheat), [wheat], [EGYPT_ROOT])
    else:
        manifest["skipped"]["wheat_egypt"] = f"{EGYPT_ROOT} missing"
    if available(GREELEY_ROOT) and (Path(GREELEY_ROOT) / "LIRF_Soils.xlsx").exists():
        stash("maize_greeley_placeholder", greeley_maize(maize_pl), [maize_pl], [GREELEY_ROOT])
        stash("maize_greeley_calibrated_insample", greeley_maize(maize_gr), [maize_gr], [GREELEY_ROOT])
        stash("et0_greeley", dict(fit=et0_check(), note="pairs are (published ASCE grass ETo, radicle FAO-56 ET0)"), [], [GREELEY_ROOT])
        if maize_loyo:
            r = maize_leave_one_year_out(maize_pl)
            stash("maize_leave_one_year_out", dict(summary=r["summary"], folds=r["folds"], records=r["records"]), [maize_pl], [GREELEY_ROOT])
            (Path(docs_dir) / "maize_calibration.json").write_text(
                json.dumps(dict(summary=r["summary"], records=r["records"]), indent=1) + "\n")
    else:
        manifest["skipped"]["maize_greeley"] = f"{GREELEY_ROOT} missing (download, see docs/DATA-SOURCES.md)"
    _dump(manifest, out / "manifest.json")
    return manifest
