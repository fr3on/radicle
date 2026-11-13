import json
import re
from dataclasses import replace

import pytest

import radicle
from helpers import REPO, field
from radicle.calibrate import fit_grid
from radicle.cli import main
from radicle.experiments import reproduce
from radicle.models.crop import load_params, simulate


def test_version_is_consistent_everywhere():
    py = re.search(r'^version = "([^"]+)"', (REPO / "pyproject.toml").read_text(), re.M).group(1)
    cff = re.search(r"^version: (\S+)", (REPO / "CITATION.cff").read_text(), re.M).group(1)
    assert radicle.__version__ == py == cff
    assert f"## {py} " in (REPO / "CHANGELOG.md").read_text()


def test_release_files_exist_and_name_the_licence():
    assert "MIT License" in (REPO / "LICENSE").read_text()
    assert "license: MIT" in (REPO / "CITATION.cff").read_text()
    assert 'license = {text = "MIT"}' in (REPO / "pyproject.toml").read_text()


def test_reproduce_quick_writes_results_and_manifest(tmp_path):
    (tmp_path / "docs").mkdir()
    man = reproduce(tmp_path / "results", tmp_path / "docs", maize_loyo=False)
    assert man["radicle"] == radicle.__version__ and (tmp_path / "results/manifest.json").exists()
    assert "wheat_egypt.json" in man["written"] or "wheat_egypt" in man["skipped"]
    for f in man["written"]:
        json.loads((tmp_path / "results" / f).read_text())               # every result file is valid JSON
    if "wheat_egypt.json" in man["written"]:
        egypt = json.loads((tmp_path / "results/wheat_egypt.json").read_text())
        assert egypt["n_matured"] == 22 and 0 < egypt["yield_fit"]["rmse"] < 5
        assert set(man["params"]) >= {"wheat"} and len(next(iter(man["data"].values()))) == 16


def test_reproduce_is_deterministic(tmp_path):
    (tmp_path / "docs").mkdir()
    reproduce(tmp_path / "a", tmp_path / "docs", maize_loyo=False)
    reproduce(tmp_path / "b", tmp_path / "docs", maize_loyo=False)
    for f in (tmp_path / "a").glob("*.json"):
        assert f.read_text() == (tmp_path / "b" / f.name).read_text()


def test_committed_results_match_a_fresh_run_of_the_cheap_experiments(tmp_path):
    committed = REPO / "results" / "wheat_egypt.json"
    if not committed.exists():
        pytest.skip("no committed results yet")
    (tmp_path / "docs").mkdir()
    reproduce(tmp_path / "r", tmp_path / "docs", maize_loyo=False)
    assert json.loads(committed.read_text()) == json.loads((tmp_path / "r/wheat_egypt.json").read_text())


def test_fit_grid_picks_best_and_skips_invalid_combinations():
    base = load_params("wheat")
    # objective prefers harvest_index close to 0.35; the invalid value 1.5 is skipped rather than raising
    best = fit_grid(None, base, {"harvest_index": [0.2, 0.34, 0.5, 1.5]}, lambda p, _: abs(p.harvest_index - 0.35))
    assert best.harvest_index == 0.34
    with pytest.raises(ValueError, match="no valid"):
        fit_grid(None, base, {"harvest_index": [1.5, 2.0]}, lambda p, _: 0.0)


def test_cli_calibrate_records_provenance_of_what_it_changed(tmp_path):
    w, s, m, _ = field(tmp_path)
    d = tmp_path / "f"
    target = simulate(w, s, m, load_params())["summary"]["yield_t_ha"] * 0.8
    (d / "observations.csv").write_text(f"date,variable,value\n2026-05-01,yield_t_ha,{target}\n")
    out = tmp_path / "cal.json"
    assert main(["calibrate", str(d), "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    changed = [k for k, v in data["_provenance"].items() if v.startswith("calibrated:")]
    assert changed and all(data[k] != getattr(load_params(), k) for k in changed)
    assert data["_provenance"]["tbase"] == "placeholder"                  # untouched values keep their label


def test_readme_documents_the_reproduce_command():
    assert "radicle reproduce" in (REPO / "README.md").read_text()
