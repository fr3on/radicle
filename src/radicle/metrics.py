"""Goodness-of-fit statistics shared by the experiments, scripts and figures. Convention: error = simulated - observed."""
import statistics as st
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FitStats:
    n: int
    obs_mean: float
    sim_mean: float
    bias: float
    rmse: float
    r: float

    @classmethod
    def from_pairs(cls, pairs) -> "FitStats":
        """pairs: [(observed, simulated), ...]. r is nan with fewer than 3 points or no spread."""
        pairs = list(pairs)
        if not pairs:
            raise ValueError("no (observed, simulated) pairs")
        o, s = [p[0] for p in pairs], [p[1] for p in pairs]
        try:
            r = st.correlation(o, s) if len(pairs) >= 3 else float("nan")
        except st.StatisticsError:       # constant input
            r = float("nan")
        return cls(n=len(pairs), obs_mean=st.mean(o), sim_mean=st.mean(s), bias=st.mean(s) - st.mean(o),
                   rmse=st.mean((a - b) ** 2 for a, b in pairs) ** 0.5, r=r)

    def rounded(self, digits: int = 2) -> dict:
        return {k: (round(v, digits) if isinstance(v, float) else v) for k, v in asdict(self).items()}

    def lines(self, unit: str = "t/ha") -> list[str]:
        return [f"n = {self.n}", f"bias = {self.bias:+.2f} {unit}", f"RMSE = {self.rmse:.2f} {unit}", f"r = {self.r:.2f}"]

    def __str__(self) -> str:
        return (f"n={self.n} obs {self.obs_mean:.2f} sim {self.sim_mean:.2f} "
                f"bias {self.bias:+.2f} rmse {self.rmse:.2f} r {self.r:.2f}")
