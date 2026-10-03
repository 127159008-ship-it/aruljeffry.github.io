# LocalFlex Grid: Final Integration Report (`localflex-final-v1`)

Pure simulation: OpenDSS feeder + Python controllers. **No hardware. All profiles are synthetic.** Nothing here is a real-world result. Every number below comes from a run in `results/final/` and can be reproduced with the commands at the end.

## 1. What was built

One closed-loop master simulator (`run_final.py`) around the frozen Stage 1–10 core:

| Layer | What it does |
|---|---|
| Feeder | 11/0.415 kV, 250 kVA, 100 homes, 2 feeders, explicit neutral, 40 PV × 3 kW (22/12/6 by phase) |
| Cases | **A** no control, **B** Stage-7 rules, **C** network-aware MILP MPC (Stage 9 bus×phase sensitivity), **D** C + household fairness |
| Safety supervisor | OpenDSS check is the final authority; ladder: repair → previous approved plan (max 1 h) → Stage-7 rules → hard-limit override |
| DISCOM interface | Two-way, aggregated only (no household data); reply accepted / partial / rejected / no_response with a reason |
| Environment | synthetic (default), CSV irradiance, NASA POWER-format reader |
| OpenPLC | IEC 61131-3 Structured Text for the per-group rule logic, checked against the Python rules |
| Dashboard | engineering view, DISCOM view, decision-trace screen (`results/final/dashboard.html`) |

No new control algorithm was added at this stage and nothing was re-tuned to favour D.

## 2. Headline A/B/C/D result

Identical initial state (battery 50 % SoC), 4 scenarios × 4 seeds, scoring window 32 h (day + 8 h tail). Means of 4 seeds, "clear" scenario (full table: `A_B_C_D_comparison.csv`, plot `A_B_C_D_comparison.png`):

| Metric (clear) | A | B | C | D |
|---|---|---|---|---|
| Voltage violation magnitude, pu·h | 1.237 | 0.970 | 0.463 | 0.484 |
| Hours with any under-voltage | 7.9 | 11.4 | 11.9 | 11.1 |
| Transformer peak loading % | 72.6 | 66.2 | 58.5 | 58.5 |
| Reverse-flow energy kWh | 349 | 303 | 301 | 300 |
| PV curtailed % | 3.08 | 2.7 | 2.40 | 2.43 |
| EV energy unmet at departure kWh | 0.00 | 1.21 | 0.00 | 1.28 |

Across the four scenarios C and D cut voltage-violation magnitude by 54–66 % against no control and lower transformer peak by 12–15 points.

**Trade-offs (not hidden):**
- **Under-voltage hours go up** with B, C and D relative to A (e.g. 7.9 → 11–12 h clear; 11.2 → 16 h high-demand). Magnitude falls but duration rises, mainly overnight when EV and heater load is shifted to late hours (overnight under-voltage hours: A 0.1, C 5.2, D 4.1 on average).
- **Fairness (D) is not a free win.** It helped on high demand (worst-group burden 1.49 → 1.08, EV unmet 0.66 → 0.21 kWh) but on clear and cloudy days the worst-group burden and the fairness index got *worse* than C (clear: index 0.94 → 0.78; EV unmet 0 → 1.28 kWh).
- EV unmet energy in D varies from run to run (0 to ~3 kWh in the stress studies). The MILP has a 1 s limit per plan, so plans depend slightly on machine load.
- The Stage 8/9 voltage model is linear; its error against OpenDSS is lower than a no-action forecast (RMSE 0.008 vs 0.010 pu) but not small.

## 3. Safety supervisor and fault tests

Seven faults injected into D (`results/final_fault_tests.csv`, event log `final_fault_event_log.json`): solver unavailable, OpenDSS convergence failure, communication lost, stale measurement, invalid command, battery unavailable, forecast missing.
**Result:** in all 7, hard equipment limits held (transformer ≤ 100 %, phase ≤ 200 A, neutral ≤ 100 A, all solves converged) and voltage violation in the window was no worse than the worse of A/B. Cost of the fallback: EV unmet energy rose in some cases (up to ~1.9 kWh), and the transformer peak in the window rose from 59 % to 61–68 %. Communication-lost had no effect in this run because the 150 kW cap never binds.

## 4. DISCOM two-way interface (`results/final/discom/`)

Seven requests (`dispatch_suite.csv`, outcome check `dispatch_verified.csv`).

| Request | LocalFlex planner reply | Simulated outcome (OpenDSS) | Verified status |
|---|---|---|---|
| R1 reduce import 20 kW 18:30–19:30 | accepted | 6.3 kW reduction | **partial** |
| R2 reduce 60 kW | partial (~37 kW) | 39.4 kW | partial |
| R3 reduce 150 kW | partial (~49 kW) | 40.4 kW | partial |
| R4 import cap 120 kW 18–22 | accepted | peak 132 kW | **partial** |
| R5 export cap 5 kW 11–14 | accepted | peak 57 kW (baseline 58) | **partial** |
| R6 link lost before request | no_response | unchanged | no_response |
| R7 link lost after request | accepted | 6.3 kW | **partial** |

**Known defect, reported not fixed:** the planner's "accepted" replies were too optimistic for R1, R4, R5 and R7. The MPC models PV curtailment as a free variable, but the plant has no PV-curtailment actuator (curtailment only comes from the local volt-watt rule), and the planner's linear prediction is not exact. An export cap therefore cannot be honoured. After each run the simulated result is checked against the request, and the dashboard and `dispatch_verified.csv` show the verified status next to the planner's reply. Real-time acceptance would need either an actuator for curtailment or a stricter feasibility test; both are future work.

## 5. Robustness studies (clear unless stated; `results/final/*.csv`)

- **Participation 30 / 60 / 100 %:** voltage benefit scales with participation (clear under+over pu·h at 30 %: A 1.06, C 0.64; at 60 %: C 0.52; at 100 %: ~0.46). At 30 % the high-demand case barely improves (1.82 → 1.52).
- **Forecast error (σ scale 0 – 4/3):** voltage metrics stay in a narrow band (C 0.34–0.36, D 0.35–0.38). EV unmet energy is noisy (D 0–2.5 kWh) with no clean trend in σ.
- **Communication delay (measurement/command 0–4 steps):** benefit survives; with a 1-step command delay the transformer peak rises to ~66–70 % vs 59 %.
- **Battery size and power:** 20 → 150 kWh at 50 kW cuts clear-day voltage magnitude from 0.46 to 0.34 pu·h with diminishing returns after ~80 kWh. Results are not strictly monotone (EV unmet jumps around, see the MILP-limit note). A battery-only controller (C@bo, no flexible loads) never met the pre-declared voltage requirement at 40–200 kWh (0.74–1.0 pu·h vs 1.22 for A), which supports the flexible-load part of the concept.
- **Battery location (6 buses):** best clear-day voltage at b5/b3 (0.27/0.32 pu·h) vs a1 0.41; location effect is real but one seed only.
- **Assumption sensitivity (9 variants incl. neutral resistance ×2, feeder R ×0.7/×1.3, transformer 160/400 kVA, limits ±5 %, PV placement/size):** C and D beat A in voltage magnitude in every variant. Caveat: in the `vlim_0.95_1.05` variant only the planner limit changes; the reported metrics still use 0.94–1.06, so its A row equals the baseline. A 160 kVA transformer is overloaded in all cases (A 113 %, D 102 %).
- **Scalability:** 100 homes: run time 140 s per D run. 300 homes on the same cable network: the feeder is overloaded (A voltage magnitude 8.3 pu·h), so this tests the controller under stress, not a realistic larger feeder. 500 homes on unchanged cables: OpenDSS does not converge, a network limit, not a controller limit. Realistic scale-up would replicate feeders and transformers; not done.

## 6. Sizing, cost, emissions (`cost_emissions.json`, `battery_sizing/`)

**All unit costs are placeholders (INR), not market quotes.** At 10 % discount rate with capital-recovery-factor annualisation:
- New 100 kWh / 50 kW LocalFlex: ≈ ₹4,970 per household per year; second-life battery variant ≈ ₹4,670.
- Transformer 250 → 400 kVA: ≈ ₹540 per household per year.

Under these placeholders the **battery is the dominant cost and a transformer upgrade is much cheaper.** The case for LocalFlex has to rest on what an upgrade does not give (voltage and reverse-flow support, deferral, and measured cost inputs that are still unverified). The CO₂ factor 0.710 tCO₂/MWh is taken from the submission (CEA baseline FY2024-25). A pre-declared sizing rule (Q1–Q5) found no battery size that met it reliably across scenarios, because the pass pattern is non-monotone.

## 7. OpenPLC

`openplc/localflex_rules.st` compiled with matiec to C and compared with the Python rules on ~20,000 random vectors per block: 0 mismatches (max difference 2.4e-8, battery 1.8e-4 kW). Scope: per-group rule logic only. Not run on a PLC.

## 8. Standards and assumptions audit (`standards_audit.csv`)

Verified or partly verified: IE Rules 1956 Rule 54 (LV ±6 %), IS 1180 transformer ratings incl. 250 kVA. **Not verified:** the volt-watt curve (IEEE 1547-style placeholder, v1 1.06 → v2 1.10 pu, 20 % at v2), cable and neutral parameters, all costs. **Not modelled:** protection, harmonics, unbalance limits. The CEA draft 2026 regulations apply at ≥ 33 kV, so they do not directly apply to this 415 V feeder. No placeholder is presented as an Indian standard.

## 9. Acceptance suite

`python run_validation.py` writes `results/final/final_validation.json` (feeder, neutral, frozen A0/A1, ledgers, battery exclusivity, MPC feasibility, validator, convergence, energy balance, PV accounting, fairness, sensitivity, fault ladder, DISCOM replies, communication loss, OpenPLC, reproducibility). Reproducibility: the no-control case reruns bit-identical; D reruns are not bit-for-bit: a repeat run differed by up to 13 % on a headline metric (under-voltage pu·h 0.395 vs 0.343), so the suite records this as a measured known limitation (pass band 25 %, no convergence failures), not as exact reproducibility, because the 1 s MILP limit is load-dependent. The DISCOM check requires a reply and a reason for every request; it is **not** a claim that every request was met (0 of 7 met the 90 % outcome test).

## 10. Limits to state in any presentation

1. Synthetic profiles and an assumed forecast-error model; no field data.
2. NASA POWER reader written but not tested live (no network access from the build environment). CSV mode works.
3. Cost, volt-watt curve and cable parameters are unverified placeholders.
4. MILP plans often reach the 1 s limit; results differ slightly between runs.
5. DISCOM caps are soft in the planner and the prototype cannot guarantee them (section 4).
6. Fairness weight (λ = 500) trades EV service for equity on some days.
7. Single transformer, 100 homes; larger feeders not validated.

## 11. Reproduce

```
python run_final.py --profile full --stage core      # A/B/C/D, 4 scenarios × 4 seeds (~40 min on 2 CPUs)
python final/fault_tests.py && python final/dispatch.py
python final/studies.py participation forecast_error battery_size battery_location assumption_sensitivity comm_delay scalability
python -c "import final.sizing_cost as s; s.economics()"
python -c "import final.report as r; r.build_report(); r.study_tables(); r.copy_misc()"
python -c "import final.dashboard as d; d.build()"
python run_validation.py
python run_demo.py --request reduce_import --target 40 --start 18:30 --duration 60   # live DISCOM request
```
Manifest with file hashes and versions: `results/final/manifest.json`.
