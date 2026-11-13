"""Synthetic Nile-Delta-like winter weather so the system runs before real data exists.
Numbers are invented for plumbing tests only. Never use outputs from synthetic data for farm decisions."""
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path


def make_field(outdir, seed=1, sow=date(2025, 11, 15), days=200):
    rnd = random.Random(seed)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "weather.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "tmin", "tmax", "rh_mean", "wind_2m", "rs_mjm2", "rain_mm"])
        for k in range(days):
            d = sow + timedelta(days=k)
            doy = d.timetuple().tm_yday
            season = math.cos(2 * math.pi * (doy - 200) / 365)  # peak summer ~ doy 200
            tmean = 20 + 8 * season + rnd.gauss(0, 1.5)
            tmax, tmin = tmean + 5, tmean - 5
            rain = rnd.expovariate(1 / 6) if rnd.random() < 0.06 and season < 0.2 else 0.0
            rs = max(4.0, 18 + 9 * season + rnd.gauss(0, 2) - (4 if rain else 0))
            rh = min(98, max(35, 65 - 10 * season + rnd.gauss(0, 8) + (10 if rain else 0)))
            w.writerow([d.isoformat(), round(tmin, 1), round(tmax, 1), round(rh, 0), round(abs(rnd.gauss(2.2, 0.7)), 1),
                        round(rs, 1), round(rain, 1)])
    (out / "soil.csv").write_text("key,value\nlat,31.1\nelev_m,10\nfc,0.38\nwp,0.18\nroot_depth_max_m,1.0\ninitial_ece_dsm,3.0\n")
    lines = ["date,event,amount,ec_dsm", f"{sow.isoformat()},sow,0,"]
    for k in range(20, days, 18):  # irrigate every 18 days, 60 mm, EC 1.5
        lines.append(f"{(sow + timedelta(days=k)).isoformat()},irrigation,60,1.5")
    (out / "management.csv").write_text("\n".join(lines) + "\n")
    (out / "observations.csv").write_text("date,variable,value\n")  # empty until real data arrives
    return out
