import sys, os, json, pickle, csv
import numpy as np, pandas as pd
from run_stage9 import *
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from config.feeder_config import REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, REGISTER_S6, SUPERSEDED_S2
d = pickle.load(open(os.path.join(R, "_s9keep.pkl"), "rb")); keep = d["keep"]; tr, dfc, dvc = d["traces"]; out = pd.read_csv(os.path.join(R, "stage9_summary.csv")); pe = pd.read_csv(os.path.join(R, "stage9_prediction_error.csv"))
m = build(CFG, SEED); tests = {}; mon = monitored(m); res = resource_list()
S1 = build_H(m, 48); S1b = build_H(m, 48); S2 = build_H(m, 76)
tests["matrix_shape_midday / evening (monitored x resources)"] = [list(S1["H"].shape), list(S2["H"].shape), f"{len(mon)} node-phases x {len(res)} resources"]
tests["reproducible_build_max_abs_diff"] = float(np.abs(S1["H"] - S1b["H"]).max())
own = []; 
for q, (gid, node, ph) in enumerate(res):
    if ph is not None: own.append(S1["H"][mon.index((node, "ABC"[ph-1])), q]); own.append(S2["H"][mon.index((node, "ABC"[ph-1])), q])
tests["own_node_phase_sensitivity_all_negative (load up -> own voltage down)"] = bool(all(o < 0 for o in own)); tests["own_node_phase_H_range_pu_per_kW"] = [round(min(own), 5), round(max(own), 5)]
tests["battery_H_all_negative"] = bool((S1["H"][:, -1] < 0).all() and (S2["H"][:, -1] < 0).all())
tests["offphase_positive_entries_share_pct (neutral-shift coupling; physical)"] = [round(float(100*(S["H"] > 1e-6).mean()), 1) for S in (S1, S2)]
# linearity: single-group perturbation, linear vs nonlinear
lin = []
for nm, S in (("midday", S1), ("evening", S2)):
    solve = build_H(m, S["ref_step"])["solve"]; V0 = solve()
    for q, (gid, node, ph) in enumerate(res):
        for dp in (1.0, 5.0, 10.0):
            tot = dp*(3 if gid == "BATT" else 1) if False else dp; Vn = solve({gid: tot}); Vl = V0 + S["H"][:, q]*tot; lin.append(dict(regime=nm, resource=gid, dP_kW=tot, max_abs_err_pu=float(np.abs(Vn - Vl).max()), max_abs_dV_pu=float(np.abs(Vn - V0).max())))
lin = pd.DataFrame(lin); lin.to_csv(os.path.join(R, "stage9_linearity_test.csv"), index=False); tests["linearity_max_abs_err_pu_by_dP"] = {str(k): round(float(v), 5) for k, v in lin.groupby("dP_kW").max_abs_err_pu.max().items()}
# C8 unchanged
c8_old = pd.read_csv(os.path.join(R, "stage8_clear_C_timeseries.csv")); c8_new = pd.read_csv(os.path.join(R, "stage9_clear_C8_timeseries.csv")); cols = [c for c in c8_old.columns if c in c8_new.columns]; tests["C8_unchanged_vs_stage8_max_abs_diff"] = float(np.abs(c8_old[cols].values - c8_new[cols].values).max())
tests["all_runs_convergence_failures"] = int(out.convergence_failures.sum()); tests["max_power_balance_residual_kW"] = float(out.max_power_balance_residual_kW.max())
C9 = out[out.case == "C9"]; tests["C9_solver_failures"] = int(C9.solver_failures.sum()); tests["C9_simultaneous_battery_steps"] = int(C9.simultaneous_batt_steps.sum()); tests["C9_battery_end_SoC_min_pct"] = float(C9.battery_end_soc_pct.min()); tests["C9_fallback_steps_share_pct"] = round(float(100*C9.fallbacks_to_rules.sum()/C9.gate_checks.sum()), 1)
tests["prediction_error_V_pred_vs_OpenDSS (all node-phases, day 2, executed first step): rmse / max (pu)"] = [round(float(pe.rmse.mean()), 4), round(float(pe.maxabs.max()), 4)]; tests["prediction_error_forecast_base_only (no H action term) rmse (pu)"] = round(float(pe.rmse_base_only.mean()), 4)
json.dump(tests, open(os.path.join(R, "stage9_tests.json"), "w"), indent=1, default=str); print(json.dumps(tests, indent=1, default=str))
# decision trace with executed + nonlinear result
A = keep[("clear", "A")][0]; trace = []
for t in tr:
    k = t["step"]; col = f"V_{t['node_phase'].replace('/', '_')}_pu"; ex = {gid: float(dvc[f"P_{gid}_kW"][k]) for gid, _, _ in res if f"P_{gid}_kW" in dvc}; ex["BATT"] = float(dvc["P_BATT_kW"][k])
    for c in t["candidates"]: c["executed_kW"] = ex[c["resource"]]
    t["V_nonlinear_OpenDSS_after_execution"] = float(dfc[col][k]); t["V_nonlinear_OpenDSS_no_control_A"] = float(A[col][k]); trace.append(t)
json.dump(trace, open(os.path.join(R, "stage9_decision_trace.json"), "w"), indent=1)
# tables
g = out.groupby(["scenario", "case"]); keepc = ["hours_any_overvoltage", "hours_any_undervoltage", "v_max_pu", "v_min_pu", "a5A_min_pu", "a5A_overnight_hours_below_0p94", "overnight_any_undervoltage_hours", "overnight_vmin_pu", "peak_phase_loading_pct", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "battery_throughput_kWh", "battery_end_soc_pct", "fallbacks_to_rules"]
mean = g[keepc].mean().round(2); mean.to_csv(os.path.join(R, "stage9_summary_mean_over_seeds.csv")); print(mean.to_string())
# plots
S = d; fig, ax = plt.subplots(3, 2, figsize=(14, 13)); lab = [f"{n}/{p}" for n, p in mon]; rl = [r[0] for r in res]
for j, (nm, Sx) in enumerate((("H_midday (12:00 ref)", S1), ("H_evening (19:00 ref)", S2))):
    im = ax[0, j].imshow(Sx["H"], aspect="auto", cmap="RdBu", vmin=-0.009, vmax=0.009); ax[0, j].set_xticks(range(len(rl))); ax[0, j].set_xticklabels(rl, rotation=45, fontsize=7); ax[0, j].set_yticks(range(len(lab))); ax[0, j].set_yticklabels(lab, fontsize=5); ax[0, j].set_title(f"{nm}: dV/dP (pu per kW)"); plt.colorbar(im, ax=ax[0, j])
col = {"A": "#888", "C8": "#B84A4A", "C9": "#1F7A7A"}
for c in ("A", "C8", "C9"):
    df, dv = keep[("clear", c)]; ax[1, 0].plot(df.hour, df.V_a5_A_pu, c=col[c], label=c); ax[1, 1].plot(dv.hour, dv.P_EV1_kW, c=col[c], label=c); ax[2, 0].plot(dv.hour, dv.SoC_BATT_pct, c=col[c], label=c)
    ax[2, 1].plot(df.hour, df[[x for x in df if x.startswith("V_") and x.endswith("_pu")]].max(axis=1), c=col[c], label=f"{c} highest"); ax[2, 1].plot(df.hour, df[[x for x in df if x.startswith("V_") and x.endswith("_pu")]].min(axis=1), c=col[c], ls="--", label=f"{c} lowest")
ax[1, 0].axhline(0.94, c="k", ls=":"); ax[1, 0].set_title("clear: voltage at a5/A (weakest point), day 2"); ax[1, 1].set_title("clear: EV1 charging power at a5/A (kW)"); ax[2, 0].set_title("clear: battery SoC (%)"); ax[2, 1].set_title("clear: highest / lowest voltage anywhere")
for a in ax.flat[2:]: a.grid(alpha=.3); a.legend(fontsize=7); a.set_xlabel("hour of day")
fig.suptitle("LocalFlex Grid - Stage 9: bus x phase sensitivity (C9) vs aggregate model (C8) vs no control (A)", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage9_C8_vs_C9.png"), dpi=130)
# register
RS9 = [("Sensitivity H (bus x phase)", f"{len(mon)} node-phases x {len(res)} resources, perturbation 1 kW per single-phase group (3 kW total for battery, 1 kW per phase), finite difference in OpenDSS", "pu/kW", "Identified", "OpenDSS runs", "Network-aware planner", "linear to ~10 kW (see stage9_linearity_test.csv)"),
       ("Reference states for H", "midday = clear-sky seed 7 at 12:00; evening = clear seed 7 at 19:00; natural devices, A1 inverter", "-", "Design", "Stage 9", "Operating-point linearisation", "other regimes not built"),
       ("Regime selection", "midday H when forecast PV >= 20% of rated PV, else evening H", "-", "Assumption", "Placeholder", "Pick matrix by regime", "10-30%"),
       ("Base voltage for planner", "OpenDSS run driven by FORECAST demand/PV with natural devices (day-0 forecast, periodic)", "pu", "Design", "Stage 9", "V_base without flexibility actions", "-"),
       ("Planner objective / weights / battery / forecast", "unchanged from Stage 8", "-", "Design", "Stage 9", "Single change: voltage model", "-")]
import csv
with open(os.path.join(ROOT, "config", "parameter_register.csv"), newline="") as f: rows = list(csv.reader(f))
rows = [r for r in rows if not (len(r) >= 8 and r[7] == "stage9-v0.9")]
with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
    w = csv.writer(f); [w.writerow(r) for r in rows]; [w.writerow(list(r)+["stage9-v0.9"]) for r in RS9]
