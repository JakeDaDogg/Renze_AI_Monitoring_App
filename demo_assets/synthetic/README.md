# Synthetic demo data — `renze_synth_c456_v1.npz`

**This is synthetic data, not plant data.** Every row is a random weighted average of three
cleaned operating cycles (C4, C5, C6) of the Renze plant. No real plant row is in this file.
It exists only so that anyone with the repo can run the demo; production reads real 5-s plant
data with all 49 sensors (`full49`).

Built by `backend/tools/make_synthetic_demo.py` (seed 0) on 2026-11-18.

## Contents

| key | value |
|---|---|
| `ts` | int64 epoch seconds, `2000-01-01T00:00:00Z` every 5 s, no gaps (an obviously synthetic clock) |
| `X` | float32, 173,520 rows × 15 sensors |
| `columns` | `VCB1-Power, VCB2-Power, PT100, PT101, PV101, TT203, LIT101, LV101, TT101, FT102, LV102, FT103, PT106, PT105, ENV-0` (the `synth15` schema) |
| `seed` | 0 |
| `weights` | `Dirichlet(1,1,1) per 5-s row` |
| `source_cycles`, `cleaning_dates` | 4, 5, 6; C4 2025-04-21 00:00, C5 2025-05-20 00:00, C6 2025-06-17 00:00 |
| `build_date` | build day |

Sensors: the 11 RUL model sensors plus TT203, PT105, PT106, LV102 for the daily maintenance
decision (PT100 and LIT101 are already among the 11). PV101 is 0 throughout in all three source
cycles, so it is 0 here too.

## How it was built

1. **Source:** `series6_cycle_{4,5,6}_raw.npy` (cleaned, sampled every 60 s, downtime and rows
   below 300 kW removed). The source files are internal and are not in the repo.
2. **Cleaning dates** from the training config (`05-RUL_Pipe_Model_TrainDev.ipynb`, shared by
   pipe and HXG). C4 and C5 files run about 8 h past the notebook date; the notebook date was
   used and the later samples (485 and 508) were dropped. C6 ends 10 s before its date.
3. **Operating time** counted backwards from the cleaning date; gaps longer than 5 min count 0.
   The 15 sensors go on a 1-min grid of operating minutes; the last 10 operating days
   (14,400 minutes) are kept.
4. **Aligned** on operating minutes-before-cleaning: `C4[m], C5[m], C6[m]`.
5. **Random weighted average** per 5-s row: each of the 12 rows of minute `m` gets its own
   weights `w ~ Dirichlet(1, 1, 1)` (three non-negative weights summing to 1) and
   `row = w4·C4[m] + w5·C5[m] + w6·C6[m]`, with the same `w` for all 15 sensors of the row.
   The random weights are the only noise; values stay within the three cycles' range.
6. **Shutdown tail**, 60 min (720 rows): VCB1-Power and VCB2-Power of each cycle replaced by
   0–5 kW, the other sensors held at each cycle's last-minute value, then the same weighting.
   The demo therefore ends with the plant offline.

The 1-min means the models see (mean of 12 rows) sit close to the equal-weight mean of the three
cycles, so they are smoother than the 5-s rows.
