"""Command line interface: `radicle <command>`. One small function per command; `main` only parses and dispatches."""
import argparse
import csv
import json
import sys
from pathlib import Path

from .calibrate import calibrate
from .ingest.loaders import DataError, load_field
from .models.crop import load_params, simulate
from .plot import season_svg
from .scenarios import sweep
from .synthetic import make_field


def _write_csv(path, rows, fieldnames) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# ---- commands that do not need a field directory
def cmd_synth(a) -> int:
    print("wrote synthetic field to", make_field(a.dir), "(invented numbers, not for decisions)")
    return 0


def cmd_reproduce(a) -> int:
    from .experiments import reproduce
    man = reproduce(a.out, a.docs, maize_loyo=not a.quick)
    print("wrote", ", ".join(man["written"]) or "nothing", "->", a.out)
    for name, why in man["skipped"].items():
        print("skipped", name, "-", why)
    return 0


# ---- commands on a field directory: (args, weather, site, mgmt, obs) -> exit code
def cmd_validate(a, weather, site, mgmt, obs) -> int:
    print(f"ok: {len(weather)} weather days, {len(mgmt.irrigation)} irrigations, {len(obs)} observations")
    return 0


def cmd_run(a, weather, site, mgmt, obs) -> int:
    r = simulate(weather, site, mgmt, load_params(a.params))
    if not r.summary.matured:
        print(f"WARNING: weather ends after {r.summary.days} days before the crop matures; "
              "yield is truncated and not meaningful", file=sys.stderr)
    print(json.dumps(r.summary.as_dict(), indent=2))
    if a.out:
        _write_csv(a.out, r.daily, r.daily[0].keys())
    return 0


def cmd_plot(a, weather, site, mgmt, obs) -> int:
    r = simulate(weather, site, mgmt, load_params(a.params))
    out = a.out or "season.svg"
    Path(out).write_text(season_svg(r, f"radicle: {a.dir} (yield {r.summary.yield_t_ha} t/ha)"))
    print("wrote", out)
    return 0


def cmd_scenarios(a, weather, site, mgmt, obs) -> int:
    skipped = []
    rows = sweep(weather, site, mgmt, load_params(a.params), skipped)
    if skipped:
        shifts = sorted({k[0] for k in skipped})
        print(f"WARNING: {len(skipped)} of {len(skipped) + len(rows)} scenarios skipped "
              f"(sow shifts affected: {shifts}); first reason: {skipped[0][3]}", file=sys.stderr)
    if not rows:
        print("no scenario produced a matured crop", file=sys.stderr)
        return 2
    rows.sort(key=lambda x: -x["yield_t_ha"])
    for x in rows[:5] + rows[-3:]:
        print(x["sow_shift_days"], x["irrigation_ec"], x["irrigation_scale"], x["yield_t_ha"], "t/ha")
    if a.out:
        _write_csv(a.out, rows, rows[0].keys())
    return 0


def cmd_calibrate(a, weather, site, mgmt, obs) -> int:
    params = load_params(a.params)
    best, l = calibrate(weather, site, mgmt, params, obs)
    print("loss", l)
    out = a.out or "params-calibrated.json"
    changed = [k for k in best.numeric_fields() if getattr(best, k) != getattr(params, k)]
    best.save(out, calibrated={k: f"calibrated:{a.dir} (random search, loss {l:.4f})" for k in changed},
              note=f"{params.name} parameters re-fitted to {a.dir}/observations.csv: {', '.join(changed) or 'nothing changed'}")
    print("wrote", out)
    return 0


FIELD_COMMANDS = {"validate": cmd_validate, "run": cmd_run, "plot": cmd_plot, "scenarios": cmd_scenarios,
                  "calibrate": cmd_calibrate}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="radicle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("synth", help="write SYNTHETIC demo data (plumbing test only)").add_argument("dir")
    for name in FIELD_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("dir", help="field directory with weather.csv, soil.csv, management.csv[, observations.csv]")
        if name != "validate":
            p.add_argument("--params", default="wheat", help="parameter set in params/ (default: wheat)")
            p.add_argument("--out", default=None)
    rp = sub.add_parser("reproduce", help="recompute every reported number into results/*.json (skips missing datasets)")
    rp.add_argument("--out", default="results")
    rp.add_argument("--docs", default="docs")
    rp.add_argument("--quick", action="store_true", help="skip the slow leave-one-year-out maize calibration (~1 min)")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd == "synth":
        return cmd_synth(a)
    if a.cmd == "reproduce":
        return cmd_reproduce(a)
    try:
        field = load_field(a.dir)
    except (DataError, FileNotFoundError) as e:
        print("DATA ERROR:", e, file=sys.stderr)
        return 2
    return FIELD_COMMANDS[a.cmd](a, *field)


if __name__ == "__main__":
    sys.exit(main())
