"""Wheat on the Nile-gradient trials (4 sites, season 2011/12, fully irrigated). Usage: python scripts/eval_egypt.py"""
from radicle import experiments as ex
from radicle.models.params import load_params

for name in ("wheat", "wheat_eu_calibrated"):
    e = ex.egypt_wheat(load_params(name))
    print(f"{name}: matured {e['n_matured']} | yield {e['yield_fit']}")
    print(f"  days to anthesis sim {e['anthesis_sim_days']:.0f} obs {e['anthesis_obs_days']:.0f} | "
          f"days to maturity sim {e['maturity_sim_days']:.0f} obs {e['maturity_obs_days']:.0f}")
    for site, v in e["by_site"].items():
        print(f"   {v['name']:9} yield sim {v['yield_sim']:.1f} obs {v['yield_obs']:.1f} | maturity day sim {v['maturity_sim_days']:.0f} "
              f"obs {v['maturity_obs_days']:.0f} | irrigation {v['irrigation_mm']:.0f} mm")
