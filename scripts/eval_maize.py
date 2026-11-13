"""Maize on the Greeley limited-irrigation trials. Usage: python scripts/eval_maize.py [params-name ...]"""
import sys

from radicle import experiments as ex
from radicle.models.params import load_params

for name in sys.argv[1:] or ["maize", "maize_greeley", "maize_greeley_calibrated"]:
    g = ex.greeley_maize(load_params(name))
    print(f"## {name}: completed {g['n_completed']}/{g['n']}\n  grain yield t/ha: {g['yield_fit']}\n  biomass t/ha:     {g['biomass_fit']}")
    for y, v in g["by_year"].items():
        print(f"  {y}: r {v['r']:.2f} | sim driest {v['sim_driest']:.1f} wettest {v['sim_wettest']:.1f} | obs {v['obs_driest']:.1f} / {v['obs_wettest']:.1f}")
print(f"ET0 vs published ASCE grass ETo (mm/d, bias = radicle - published): {ex.et0_check()}")
