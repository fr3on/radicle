import json
import tempfile
from datetime import timedelta
from pathlib import Path

from helpers import field
from radicle.models.crop import load_params
from radicle.synthetic import make_field


def test_sweep_reports_skipped_and_drops_unmatured():
    from radicle.scenarios import sweep
    with tempfile.TemporaryDirectory() as t:
        w, s, m, _ = field(t)
        skipped = []
        rows = sweep(w, s, m, load_params(), skipped)
        assert {r["sow_shift_days"] for r in rows} == {0, 7, 14}
        assert {k[0] for k in skipped} == {-14, -7} and all(r["matured"] for r in rows)
        short = {d: x for d, x in w.items() if d < m.sow_date + timedelta(days=60)}
        skipped = []
        assert sweep(short, s, m, load_params(), skipped) == []
        assert any("did not mature" in k[3] for k in skipped)


def test_cli_warns_on_truncated_run(capsys):
    from radicle.cli import main
    with tempfile.TemporaryDirectory() as t:
        d = make_field(Path(t) / "f")
        lines = (d / "weather.csv").read_text().splitlines()[:61]
        (d / "weather.csv").write_text("\n".join(lines) + "\n")
        assert main(["run", str(d)]) == 0
        assert "WARNING" in capsys.readouterr().err


def test_cli_run_writes_a_csv_with_one_row_per_day(tmp_path, capsys):
    import csv
    from radicle.cli import main
    d = make_field(tmp_path / "f")
    out = tmp_path / "run.csv"
    assert main(["run", str(d), "--out", str(out)]) == 0
    rows = list(csv.DictReader(open(out)))
    days = json.loads(capsys.readouterr().out)["days"]
    assert len(rows) == days and {"date", "gdd", "biomass_g_m2"} <= set(rows[0])


def test_cli_scenarios_writes_a_csv(tmp_path):
    import csv
    from radicle.cli import main
    d = make_field(tmp_path / "f")
    out = tmp_path / "sweep.csv"
    assert main(["scenarios", str(d), "--out", str(out)]) == 0
    assert len(list(csv.DictReader(open(out)))) == 36


def test_cli_reports_data_errors_with_exit_code_2(tmp_path, capsys):
    from radicle.cli import main
    assert main(["validate", str(tmp_path / "missing")]) == 2
    assert "DATA ERROR" in capsys.readouterr().err
