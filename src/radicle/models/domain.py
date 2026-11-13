"""Plain data types shared by the model, the loaders and the experiments.

Results are frozen dataclasses (`DayRecord`, `Summary`, `SimulationResult`) that also behave like read-only mappings
(`result["summary"]["yield_t_ha"]`), so older dict-style code keeps working while new code can use attributes.
"""
from dataclasses import dataclass, field, fields
from datetime import date
from typing import Iterator, Mapping, TypedDict


class DayWeather(TypedDict):
    """One day of model-ready weather. Units: deg C, % (mean RH), m/s at 2 m, MJ/m2/day, mm."""
    tmin: float
    tmax: float
    rh: float
    wind: float
    rs: float
    rain: float


Weather = Mapping[date, DayWeather]


@dataclass
class Site:
    lat: float = 31.1
    elev_m: float = 10.0
    fc: float = 0.35               # volumetric water content at field capacity
    wp: float = 0.15               # wilting point
    root_depth_max_m: float = 1.0
    initial_depletion_frac: float = 0.3
    initial_ece: float = 2.0       # dS/m, saturated paste extract of the root zone
    ece_per_conc: float = 0.5      # crude: ECe ~ ECsw * 0.5


@dataclass
class Management:
    sow_date: date = date(2025, 11, 15)
    irrigation: dict = field(default_factory=dict)   # date -> (mm, EC of the water in dS/m)
    irrigation_ec_default: float = 1.0
    fungicide: dict = field(default_factory=dict)    # date -> efficacy 0..1


class Record:
    """Read-only mapping view of a dataclass, so `rec["field"]`, `rec.get`, `dict(rec.items())` work."""

    def __getitem__(self, key: str):
        if key not in self._names():
            raise KeyError(key)
        return getattr(self, key)

    @classmethod
    def _names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def keys(self):
        return self.as_dict().keys()      # a real keys view: set-like, as csv.DictWriter and `**record` expect

    def items(self):
        return self.as_dict().items()

    def get(self, key: str, default=None):
        return getattr(self, key) if key in self._names() else default

    def __iter__(self) -> Iterator[str]:
        return iter(self._names())

    def __contains__(self, key) -> bool:
        return key in self._names()

    def __len__(self) -> int:
        return len(self._names())

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self._names()}


@dataclass(frozen=True)
class DayRecord(Record):
    date: str
    gdd: float
    et0: float
    kc: float
    ks_water: float
    ks_salt: float
    ece: float
    depletion_mm: float
    taw_mm: float
    disease: float
    biomass_g_m2: float
    rain: float
    irrigation: float


@dataclass(frozen=True)
class Summary(Record):
    matured: bool            # True when the season completed: physiological maturity or a killing frost
    ended_by: str            # "maturity" | "frost" | "weather_end"
    days: int
    yield_t_ha: float
    biomass_g_m2: float
    irrigation_mm: float
    drainage_mm: float
    stress_days: int
    final_ece: float | None
    final_disease: float | None
    harvest_date: str | None
    anthesis_date: str | None


@dataclass(frozen=True)
class SimulationResult:
    daily: list
    summary: Summary

    def __getitem__(self, key: str):
        if key not in ("daily", "summary"):
            raise KeyError(key)
        return getattr(self, key)
