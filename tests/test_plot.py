import xml.etree.ElementTree as ET

import pytest

from helpers import REPO
from radicle.ingest.loaders import load_field
from radicle.models.crop import load_params, simulate


def test_run_svg_is_valid_xml_with_four_panels():
    from radicle.plot import run_svg
    w, s, m, _ = load_field(REPO / "data/demo")
    svg = run_svg(simulate(w, s, m, load_params())["daily"], "t <&> title")
    root = ET.fromstring(svg)                                   # parses -> well-formed, text escaped
    assert root.tag.endswith("svg")
    assert svg.count("<polyline") == 5 and "t &lt;&amp;&gt; title" in svg and "days after sowing" in svg


def test_scatter_svg_points_and_empty_input():
    from radicle.plot import scatter_svg
    svg = scatter_svg([(5.0, 6.0), (7.0, 6.5)], "obs", "sim", "title")
    assert svg.count("<circle") == 2 and ET.fromstring(svg) is not None
    with pytest.raises(ValueError):
        scatter_svg([], "a", "b", "c")


def test_plot_cli_writes_file(tmp_path):
    from radicle.cli import main
    out = tmp_path / "s.svg"
    assert main(["plot", str(REPO / "data/demo"), "--out", str(out)]) == 0
    assert ET.fromstring(out.read_text()).tag.endswith("svg")


def test_committed_figures_are_current():
    # regenerate demo figure and compare: catches model/plot changes without re-running scripts/make_figures.py
    from radicle.plot import season_svg
    w, s, m, _ = load_field(REPO / "data/demo")
    r = simulate(w, s, m, load_params())
    fresh = season_svg(r, f"Synthetic demo field (yield {r['summary']['yield_t_ha']} t/ha)")
    assert (REPO / "docs/figures/demo_season.svg").read_text() == fresh, "run: python scripts/make_figures.py"


def test_scatter_with_legend_notes_and_rings_is_valid_and_complete():
    from radicle.plot import scatter_svg
    svg = scatter_svg([(5, 6), (7, 6.5), (9, 9)], "obs", "sim", "T", labels=[0, 1, 1], legend=["a", "b"],
                      notes=["bias = +1"], hollow=[(5, 9), (7, 12), (9, 14)], hollow_label="before")
    ET.fromstring(svg)
    assert svg.count("<circle") == 3 + 3 + 3          # 3 points + 3 rings + 3 legend markers (a, b, before)
    assert all(t in svg for t in (">a<", ">b<", ">before<", "bias = +1", "Statistics", "1:1 line"))


def test_lines_svg_series_legend_and_empty():
    from radicle.plot import lines_svg
    svg = lines_svg([("obs", [(100, 5), (300, 9)], 0, False), ("sim", [(100, 6), (300, 8)], 0, True)], "x", "y", "T", notes=["n"])
    ET.fromstring(svg)
    assert svg.count("<polyline") == 2 and "stroke-dasharray" in svg and ">obs<" in svg and ">sim<" in svg
    with pytest.raises(ValueError):
        lines_svg([], "x", "y", "T")


def test_axis_limits_are_round_and_cover_data():
    from radicle.plot import _axis
    for lo, hi in [(0, 7.3), (0, 23.4), (0, 0.0007), (3, 97)]:
        a, b, ticks = _axis(lo, hi)
        assert a <= lo and b >= hi and ticks[0] == a and ticks[-1] == b and 3 <= len(ticks) <= 12
