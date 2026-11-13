"""Field-scale crop simulation: composes the process modules day by day.

Processes: phenology (thermal time, Kc, roots) -> water balance -> salt balance -> disease -> growth.
Every numeric default lives in params/<crop>.json with a provenance label; most are PLACEHOLDERS, not calibrated.

Order of operations each day (kept fixed because results depend on it): ET0, thermal time, root zone, salt from newly
explored soil, Kc, stresses from yesterday's depletion and salt, ETc, irrigation salt, water balance and leaching,
disease, growth.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from . import disease, growth, phenology, salinity, water
from .domain import (DayRecord, DayWeather, Management, SimulationResult, Site, Summary, Weather)  # noqa: F401 (re-exported)
from .et0 import et0_daily
from .params import PARAMS_DIR, CropParams, load_params  # noqa: F401 (re-exported)


@dataclass
class SeasonState:
    gdd: float = 0.0
    biomass: float = 0.0
    severity: float = 0.0
    depletion: float = 0.0
    salt: float = 0.0
    wfc_prev: float = 0.0


def simulate(weather: Weather, site: Site, mgmt: Management, params: CropParams, seed_disease: float = 1e-4) -> SimulationResult:
    """Run from the sowing date until maturity, a killing frost (if configured) or the end of the weather record.

    Raises ValueError if the sowing date is outside the weather record or the record has a gap inside the season."""
    P = params
    if mgmt.sow_date not in weather:
        raise ValueError(f"No weather data for sowing date {mgmt.sow_date}; weather covers "
                         f"{min(weather)} to {max(weather)}")
    s = SeasonState(severity=seed_disease)
    daily: list[DayRecord] = []
    d = mgmt.sow_date
    first = True
    anthesis_date: date | None = None
    stress_days = 0
    drain_total = irr_total = 0.0
    last_day = max(weather)
    ended_by = "weather_end"
    while d <= last_day and s.gdd < P.gdd_maturity:
        if d not in weather:
            raise ValueError(f"Weather gap: no data for {d} (record runs {min(weather)} to {last_day}); fill or remove the gap")
        w = weather[d]
        et0 = et0_daily(w["tmin"], w["tmax"], w["rh"], w["wind"], w["rs"], site.lat, d.timetuple().tm_yday, site.elev_m)
        tmean = (w["tmin"] + w["tmax"]) / 2
        s.gdd += phenology.thermal_time(P, w["tmin"], w["tmax"])
        rz = water.root_zone(P, site, phenology.root_depth(P, site, s.gdd))
        if first:
            s.depletion = water.initial_depletion(site, rz)
            s.salt = salinity.initial_concentration(site) * rz.wfc
            first = False
        elif rz.wfc > s.wfc_prev:
            s.salt += salinity.salt_from_new_soil(site, rz.wfc - s.wfc_prev)
        s.wfc_prev = rz.wfc
        kc = phenology.crop_coefficient(P, s.gdd)
        ks_w = water.water_stress(s.depletion, rz)
        ece = salinity.ece(s.salt, rz.wfc, site)
        ks_s = salinity.salt_stress(P, ece)
        etc = water.actual_et(P, kc, et0, ks_w, ks_s, s.gdd)
        irr_mm, irr_ec = mgmt.irrigation.get(d, (0.0, mgmt.irrigation_ec_default))
        irr_total += irr_mm
        s.salt += salinity.irrigation_salt(irr_mm, irr_ec)
        s.depletion, drain = water.balance_step(s.depletion, etc, water.effective_rain(w["rain"]), irr_mm, rz)
        if drain > 0:
            s.salt = salinity.leach(s.salt, rz.wfc, drain)
            drain_total += drain
        s.severity = disease.step(P, s.severity, s.gdd, w, tmean, disease.fungicide_factor(P, mgmt, d))
        s.biomass += growth.daily_biomass(P, growth.transpiration_ratio(P, kc, ks_w, ks_s, s.gdd), s.severity,
                                          growth.heat_factor(P, w["tmax"], s.gdd))
        if anthesis_date is None and s.gdd >= P.gdd_anthesis:
            anthesis_date = d
        stress_days += ks_w < 0.95 or ks_s < 0.95
        daily.append(DayRecord(date=d.isoformat(), gdd=round(s.gdd, 1), et0=round(et0, 2), kc=round(kc, 2),
                               ks_water=round(ks_w, 3), ks_salt=round(ks_s, 3), ece=round(ece, 2),
                               depletion_mm=round(s.depletion, 1), taw_mm=round(rz.taw, 1), disease=round(s.severity, 4),
                               biomass_g_m2=round(s.biomass, 1), rain=w["rain"], irrigation=irr_mm))
        if phenology.killed_by_frost(P, s.gdd, w["tmin"]):
            ended_by = "frost"
            break
        d += timedelta(days=1)
    if s.gdd >= P.gdd_maturity:
        ended_by = "maturity"
    summary = Summary(
        matured=ended_by in ("maturity", "frost"), ended_by=ended_by, days=len(daily),
        yield_t_ha=round(growth.grain_yield_t_ha(P, s.biomass), 2), biomass_g_m2=round(s.biomass, 1),
        irrigation_mm=round(irr_total, 1), drainage_mm=round(drain_total, 1), stress_days=int(stress_days),
        final_ece=daily[-1].ece if daily else None, final_disease=daily[-1].disease if daily else None,
        harvest_date=daily[-1].date if daily else None,
        anthesis_date=anthesis_date.isoformat() if anthesis_date else None)
    return SimulationResult(daily=daily, summary=summary)
