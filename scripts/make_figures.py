"""Regenerate docs/figures/*.svg (run from the repo root). Maize figures need docs/maize_calibration.json,
which `radicle reproduce` or scripts/calibrate_maize.py writes."""
from radicle.figures import build

print("wrote", build())
