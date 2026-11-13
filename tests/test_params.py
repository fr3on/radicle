import json
from dataclasses import replace

import pytest

from radicle.models.params import PARAMS_DIR, CropParams, load_params

ALL = sorted(p.stem for p in PARAMS_DIR.glob("*.json"))


@pytest.mark.parametrize("name", ALL)
def test_every_committed_parameter_has_provenance(name):
    p = load_params(name)
    written = [k for k in json.loads((PARAMS_DIR / f"{name}.json").read_text()) if not k.startswith("_")]
    assert p.provenance_problems(written) == []


@pytest.mark.parametrize("name", ["wheat_eu_calibrated", "maize_greeley", "maize_greeley_calibrated"])
def test_calibrated_files_say_what_was_calibrated(name):
    labels = load_params(name).provenance.values()
    assert any(v.startswith("calibrated") for v in labels)


def test_placeholder_files_are_labelled_honestly():
    assert set(load_params("wheat").provenance.values()) == {"placeholder"}
    assert set(load_params("maize").provenance.values()) == {"placeholder"}


def test_unknown_parameter_name_is_rejected(tmp_path):
    d = json.loads((PARAMS_DIR / "wheat.json").read_text())
    d["wp_g_m"] = 15.0                                   # typo must not be silently ignored
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="unknown parameter"):
        CropParams.from_json(f)


@pytest.mark.parametrize("changes,msg", [
    (dict(gdd_anthesis=2500.0), "gdd_dev_end < gdd_mid_start"),
    (dict(harvest_index=1.5), "harvest_index"),
    (dict(p_depletion=1.0), "p_depletion"),
    (dict(tmax_cut=0.0), "tmax_cut"),
    (dict(gdd_method="average"), "gdd_method"),
    (dict(fungicide_days=0), "fungicide_days"),
])
def test_invalid_parameters_are_rejected(changes, msg):
    with pytest.raises(ValueError, match=msg):
        replace(load_params("wheat"), **changes)


def test_save_roundtrip_keeps_values_and_updates_provenance(tmp_path):
    p = replace(load_params("wheat"), wp_g_m2=18.5)
    out = p.save(tmp_path / "x.json", calibrated={"wp_g_m2": "calibrated:test"}, note="n")
    back = CropParams.from_json(tmp_path / "x.json")
    assert back == p and back.provenance["wp_g_m2"] == "calibrated:test" and back.provenance["tbase"] == "placeholder"
    assert out.note == back.note == "n"


def test_parameter_sets_with_same_numbers_are_equal_regardless_of_metadata():
    a = load_params("wheat")
    assert a == replace(a, name="other", note="x", provenance={})


def test_bad_provenance_status_is_reported():
    p = replace(load_params("wheat"), provenance={**load_params("wheat").provenance, "tbase": "guess"})
    assert any("tbase" in m for m in p.provenance_problems())
