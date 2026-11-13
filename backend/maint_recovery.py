"""
maint_recovery.py — recovered energy (kWh) from cleaning tomorrow, Renze maintenance scheme v0.

Coefficients come from `maint_recovery_v0.json` (exported by 01-Maintenance_Recovery_v0.ipynb):
    recovered = intercept + sum_f coef_f * (x_f - mean_f) / std_f
    f_rul1 = RUL - D,  f_rul2 = RUL * (RUL - D);  sensors = previous operating day's means.
Returns 0 when RUL <= D.

Usage (s = dict of TT203, PT100, PT105, LIT101, PT106, LV102):
    joint = recovery_kwh(min(rul_pipe, rul_hx), s)
    pipe  = recovery_kwh(rul_pipe, s, SHARE_PIPE)
    hx    = recovery_kwh(rul_hx, s, SHARE_HX)

SHARE_PIPE / SHARE_HX = 0.8 are user-chosen assumptions (v0 measured shares were inconsistent).
"""
import json
from pathlib import Path

SHARE_PIPE = 0.8
SHARE_HX = 0.8


def load(path=Path(__file__).with_name("maint_recovery_v0.json")):
    with open(path) as f:
        return json.load(f)


_SPEC = load()


def recovery_kwh(rul_days, sensors, share=1.0, spec=None):
    spec = spec or _SPEC
    D, m = float(spec["D_days"]), spec["model"]
    rul = float(rul_days)
    if rul <= D:
        return 0.0
    x = dict(sensors, f_rul1=rul - D, f_rul2=rul * (rul - D))
    y = m["intercept"] + sum(m["coef"][f] * (float(x[f]) - m["mean"][f]) / m["std"][f] for f in m["features"])
    return share * y
