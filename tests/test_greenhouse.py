from datetime import date, timedelta


def test_greenhouse_more_light_more_fruit():
    from datetime import timedelta
    from radicle.models.greenhouse import GHParams, simulate as gh
    d0 = date(2024, 9, 4)
    mk = lambda par: {d0 + timedelta(days=i): dict(par_mol=par, t=21.0, co2=700.0) for i in range(70)}
    lo, hi = gh(mk(8.0), 40.0, GHParams()), gh(mk(16.0), 40.0, GHParams())
    last = d0 + timedelta(days=69)
    assert 0 < lo[last] < hi[last]
    assert all(a <= b for a, b in zip(list(hi.values()), list(hi.values())[1:]))
