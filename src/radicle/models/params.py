"""Crop parameters as a validated, immutable dataclass with a provenance label for every value.

Provenance vocabulary (the part before the first ':' is checked by a test):
  placeholder  typed from memory of typical literature values; NOT verified
  literature   copied from a cited source (say which after the colon)
  calibrated   fitted to data (say which dataset after the colon)
  derived      computed from other parameters (say how after the colon)
"""
import json
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

PARAMS_DIR = Path(__file__).resolve().parents[3] / "params"
PROVENANCE_STATUSES = ("placeholder", "literature", "calibrated", "derived")


@dataclass(frozen=True)
class CropParams:
    # thermal time (degree days, base `tbase`)
    tbase: float
    tmax_cut: float
    gdd_emergence: float
    gdd_dev_end: float          # end of initial stage (Kc starts rising); disease active after this
    gdd_mid_start: float        # full cover: Kc reaches kc_mid
    gdd_anthesis: float         # silking/anthesis: roots reach full depth; frost can end the season after this
    gdd_late_start: float       # Kc starts falling
    gdd_maturity: float
    # FAO-56 crop coefficient and root zone
    kc_ini: float
    kc_mid: float
    kc_end: float
    root_depth_min_m: float
    p_depletion: float          # fraction of total available water usable before stress
    # salinity (threshold-slope response)
    salt_threshold_dsm: float
    salt_slope_per_dsm: float
    # growth
    wp_g_m2: float              # normalised water productivity: dB = WP * Ta/ET0
    harvest_index: float
    heat_tmax: float            # tmax above this between mid_start and late_start costs 10 % growth/day
    # disease
    dis_rh_min: float
    dis_t_lo: float
    dis_t_hi: float
    dis_rate: float
    dis_yield_loss: float
    # optional behaviour
    gdd_method: str = "mean"                 # "mean": clip(mean temp) | "clip": (min(tmax,cut)+max(tmin,tbase))/2
    frost_kill_tmin: float | None = None     # deg C; after anthesis a tmin at or below this ends the season
    fungicide_days: float = 14               # protection window of one spray
    # metadata (not part of equality: two parameter sets with the same numbers are the same model)
    name: str = field(default="", compare=False)
    note: str = field(default="", compare=False)
    provenance: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        stages = [self.gdd_dev_end, self.gdd_mid_start, self.gdd_anthesis, self.gdd_late_start, self.gdd_maturity]
        if not all(a < b for a, b in zip(stages, stages[1:])):
            raise ValueError("need gdd_dev_end < gdd_mid_start < gdd_anthesis < gdd_late_start < gdd_maturity, got "
                             f"{stages}")
        if not 0 < self.harvest_index <= 1:
            raise ValueError(f"harvest_index must be in (0, 1], got {self.harvest_index}")
        if not 0 < self.p_depletion < 1:
            raise ValueError(f"p_depletion must be in (0, 1), got {self.p_depletion}")
        if self.tmax_cut <= self.tbase:
            raise ValueError("tmax_cut must exceed tbase")
        if self.gdd_method not in ("mean", "clip"):
            raise ValueError(f"gdd_method must be 'mean' or 'clip', got {self.gdd_method!r}")
        if self.fungicide_days <= 0:
            raise ValueError("fungicide_days must be positive")

    # ------------------------------------------------------------------ io
    @classmethod
    def numeric_fields(cls) -> list[str]:
        return [f.name for f in fields(cls) if f.name not in ("name", "note", "provenance")]

    @classmethod
    def from_json(cls, path) -> "CropParams":
        path = Path(path)
        data = json.loads(path.read_text())
        note, prov = data.pop("_note", ""), data.pop("_provenance", {})
        unknown = sorted(set(data) - set(cls.numeric_fields()))
        if unknown:
            raise ValueError(f"{path}: unknown parameter(s) {unknown}")
        return cls(**data, name=path.stem, note=note, provenance=prov)

    def to_json(self) -> str:
        d = {"_note": self.note, "_provenance": self.provenance}
        d.update({k: v for k, v in asdict(self).items() if k in self.numeric_fields()
                  and not (k == "frost_kill_tmin" and v is None)})
        return json.dumps(d, indent=2)

    def save(self, path, calibrated: dict | None = None, note: str | None = None) -> "CropParams":
        """Write to `path`. `calibrated` maps parameter name -> provenance label to record for values just fitted."""
        out = replace(self, provenance={**self.provenance, **(calibrated or {})}, note=note if note is not None else self.note)
        Path(path).write_text(out.to_json() + "\n")
        return out

    def provenance_problems(self, written_keys=None) -> list[str]:
        """Parameters without a provenance label, or with an unknown status."""
        optional = {"gdd_method": "mean", "frost_kill_tmin": None, "fungicide_days": 14}   # only need a label if changed
        keys = written_keys or [k for k in self.numeric_fields() if k not in optional or getattr(self, k) != optional[k]]
        bad = [f"{k}: no provenance" for k in keys if k not in self.provenance]
        bad += [f"{k}: unknown status {v!r}" for k, v in self.provenance.items()
                if v.split(":")[0].split(" ")[0] not in PROVENANCE_STATUSES]
        return bad


def load_params(name: str = "wheat") -> CropParams:
    return CropParams.from_json(PARAMS_DIR / f"{name}.json")
