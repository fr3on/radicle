"""Export two Greeley 2010 treatments (T1 most irrigated, T6 driest) to radicle's CSV field format, so the maize
pipeline can be tested and demoed without the 16 MB raw download. Run from repo root after downloading
data/external/greeley-maize/ (public domain, see docs/DATA-SOURCES.md)."""
import csv
from pathlib import Path
from radicle.ingest.greeley import load_treatments, load_weather

ROOT, YEAR = "data/external/greeley-maize", 2010
weather, _ = load_weather(ROOT, YEAR)
for t in load_treatments(ROOT, YEAR):
    if t.trno not in (1, 6):
        continue
    out = Path(f"data/greeley-{YEAR}-t{t.trno}")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "weather.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "tmin", "tmax", "rh_mean", "wind_2m", "rs_mjm2", "rain_mm"])
        for d in sorted(weather):
            x = weather[d]
            w.writerow([d.isoformat(), round(x["tmin"], 2), round(x["tmax"], 2), round(x["rh"], 1), round(x["wind"], 2), round(x["rs"], 2), round(x["rain"], 2)])
    s = t.site
    (out / "soil.csv").write_text(f"key,value\nlat,{s.lat}\nelev_m,{s.elev_m}\nfc,{s.fc:.4f}\nwp,{s.wp:.4f}\nroot_depth_max_m,{s.root_depth_max_m}\ninitial_ece_dsm,{s.initial_ece}\n")
    lines = ["date,event,amount,ec_dsm", f"{t.mgmt.sow_date.isoformat()},sow,0,"]
    lines += [f"{d.isoformat()},irrigation,{mm},{ec}" for d, (mm, ec) in sorted(t.mgmt.irrigation.items())]
    (out / "management.csv").write_text("\n".join(lines) + "\n")
    (out / "observations.csv").write_text(
        "date,variable,value\n"
        f"2010-10-19,yield_t_ha,{t.obs_grain_t_ha:.3f}\n2010-10-19,biomass_g_m2,{t.obs_biomass_t_ha * 100:.0f}\n")
    (out / "README.md").write_text(
        f"Greeley CO limited-irrigation maize, {YEAR}, treatment {t.trno} (irrigation {t.obs_irrigation_mm:.0f} mm). "
        "USDA-ARS, public domain, DOI 10.15482/USDA.ADC/1254006. Weather gaps filled, assumptions listed in "
        "src/radicle/ingest/greeley.py. Observed values are dry grain yield and final biomass at harvest (2010-10-19). "
        "Run: radicle run <dir> --params maize_greeley\n")
    print("wrote", out)
