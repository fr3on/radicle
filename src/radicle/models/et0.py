"""FAO-56 Penman-Monteith reference evapotranspiration (daily). Equations from FAO Irrigation and Drainage Paper 56."""
import math


def sat_vp(t):  # kPa
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def extraterrestrial_radiation(lat_deg, doy):  # MJ/m2/day
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    dec = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))


def et0_daily(tmin, tmax, rh_mean, u2, rs, lat_deg, doy, elev_m=0.0):
    """mm/day. rs in MJ/m2/day, u2 wind at 2 m in m/s, rh_mean in %."""
    tmean = (tmin + tmax) / 2
    es = (sat_vp(tmax) + sat_vp(tmin)) / 2
    ea = es * rh_mean / 100
    delta = 4098 * sat_vp(tmean) / (tmean + 237.3) ** 2
    p = 101.3 * ((293 - 0.0065 * elev_m) / 293) ** 5.26
    gamma = 0.000665 * p
    ra = extraterrestrial_radiation(lat_deg, doy)
    rso = (0.75 + 2e-5 * elev_m) * ra
    rns = 0.77 * rs
    ratio = min(rs / rso, 1.0) if rso > 0 else 0.5
    sigma = 4.903e-9
    rnl = sigma * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * math.sqrt(max(ea, 0))) * (1.35 * ratio - 0.35)
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)
    return max(0.0, num / (delta + gamma * (1 + 0.34 * u2)))
