# demo_assets — manifest

What is in git and what is not (decisions 2026-11-17):

- **In git:** the v3 `traindev` RUL weights and scalers (`models/`) and the synthetic demo data
  (`synthetic/`). Anyone with the repo can run the demo.
- **Internal only, on request from Yuhan:** the real C9 data (`data/`). Sharing method still to
  be decided. `c9_window.npz` is an internal, locally built cut of it (not needed).

| file | target path | size (bytes) | sha256 | source version | in git |
|---|---|---|---|---|---|
| pipe_rul_v3_traindev.weights.h5 | demo_assets/models/pipe_rul_v3_traindev.weights.h5 | 95,376 | 57c2d40414fd00697720be2e83785f7842ed972695ca5a808cfd3fd979cd726e | AI_for_Renze/09-RUL Model/, v3 traindev (2026-06-30) | yes |
| pipe_rul_v3_traindev_scaler.pkl | demo_assets/models/pipe_rul_v3_traindev_scaler.pkl | 899 | 5e978c4dc6cb81a35dc366ad709f174291bdb1120d800bad9ed56568bc62c698 | AI_for_Renze/09-RUL Model/, v3 traindev (2026-06-30) | yes |
| hxg_rul_v3_traindev.weights.h5 | demo_assets/models/hxg_rul_v3_traindev.weights.h5 | 45,640 | 37206308eb8d8a1b0bc7ce0d88c8b3067988e438e89b5c24ded25e1930ed2350 | AI_for_Renze/09-B-HXG_RUL_Model/, v3 traindev (2026-10-15) | yes |
| hxg_rul_v3_traindev_scaler.pkl | demo_assets/models/hxg_rul_v3_traindev_scaler.pkl | 899 | 3028a81cee087159a1b124124ec1dc640a18b2b9a1688b6a453333594c4f9ee4 | AI_for_Renze/09-B-HXG_RUL_Model/, v3 traindev (2026-10-15) | yes |
| renze_synth_c456_v1.npz | demo_assets/synthetic/renze_synth_c456_v1.npz | 9,177,245 | cb1bddbf58d6ac14b8786d72beb65c786eee276c905e218615be8c2bd8b262fc | synthetic, built by an internal generator, not in this repo (seed 0, 2026-11-18) | yes |
| series6_cycle_9_converted.npy | demo_assets/data/series6_cycle_9_converted.npy | 414,720,128 | e6afb753d403a3f5e582b8f8f4869189a2caf7d7af9a5e6119eca7b35f24fab6 | AI_for_Renze/08-Data/, cycle 9 converted (2026-07-30) | no: internal, request from Yuhan |

Built locally, not listed: `demo_assets/c9_window.npz` (internal).

Note: the series6 clock is Taiwan local time labelled UTC (checked 2026-11-17); it is not shifted.

## Check

```bash
shasum -a 256 demo_assets/models/* demo_assets/synthetic/*.npz demo_assets/data/*   # compare with the table
```
