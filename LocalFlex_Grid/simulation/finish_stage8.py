import sys, os, json, pickle, csv
import numpy as np, pandas as pd
from run_stage8 import *
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from config.feeder_config import REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, REGISTER_S6, SUPERSEDED_S2
from control.mpc import W, PLAN, make_forecast
keep = pickle.load(open(os.path.join(R, "_s8keep.pkl"), "rb")); out = pd.read_csv(os.path.join(R, "stage8_summary.csv")); cal = json.load(open(os.path.join(R, "stage8_voltage_model.json")))
m = build(CFG, SEED); pvn = [m["homes"][i][0] for i in m["pv"]]; tests = {}
# tests
g = warm_start(make_all(DEVICES, DEVICE_SEED)); dem = household_profiles(m["scale"], 7, 1.0); pv = pv_availability("clear", 7, pvn); df, *_ = simulate6("A1", m, dem, pv, g); ref = pd.read_csv(os.path.join(R, "stage6_clear_A1_baseline_timeseries.csv")); cols = [c for c in ref.columns if c in df.columns]
tests["engine_regression_vs_stage6_max_abs_diff"] = float(np.abs(ref[cols].values - df[cols].values).max())
fd, fp = make_forecast(dem.sum(axis=1), pv.sum(axis=1), 7); td, tp = np.tile(dem.sum(axis=1), 4), np.tile(pv.sum(axis=1), 4); mask = tp > 1
tests["forecast_differs_from_actual: demand MAPE %"] = round(float(100*np.mean(np.abs(fd-td)/td)), 1); tests["forecast_differs_from_actual: PV MAPE % (daylight)"] = round(float(100*np.mean(np.abs(fp[mask]-tp[mask])/tp[mask])), 1)
tests["common_start_SoC_all_cases_pct"] = sorted({round(float(keep[(s, c)][1].SoC_BATT_pct.iloc[0]), 1) for s in SCENARIOS for c in ("A", "B", "C", "C_nogate", "C_perfect") if (s, c) in keep})
C = out[out.case == "C"]; tests["C_battery_end_SoC_min_pct"] = float(C.battery_end_soc_pct.min()); tests["C_ev_unmet_max_kWh"] = float(C.ev_unmet_at_departure_kWh.max()); tests["C_unmet_water_max_m3"] = float(C.unmet_water_m3.max())
tests["C_solver_failures_total"] = int(C.solver_failures.sum()); tests["C_simultaneous_battery_charge_discharge_steps"] = int(C.simultaneous_batt_steps.sum()); tests["all_runs_convergence_failures"] = int(out.convergence_failures.sum())
tests["C_fallback_steps_share_pct"] = round(float(100*C.fallbacks_to_rules.sum()/C.gate_checks.sum()), 1); tests["C_mean_solve_s"] = float(C.mean_solve_s.mean())
tests["voltage_model"] = {k: round(v, 5) for k, v in cal.items()}
json.dump(tests, open(os.path.join(R, "stage8_tests.json"), "w"), indent=1, default=str); print(json.dumps(tests, indent=1, default=str))
# plots
fig, ax = plt.subplots(3, 2, figsize=(14, 13)); col = {"A": "#888", "B": "#B84A4A", "C": "#1F7A7A"}
for j, scn in enumerate(("clear", "high_demand")):
    for c in ("A", "B", "C"):
        df, dv = keep[(scn, c)]; vc = [x for x in df if x.startswith("V_") and x.endswith("_pu")]
        ax[0, j].plot(df.hour, df[vc].max(axis=1), c=col[c], label=f"{c} highest"); ax[0, j].plot(df.hour, df[vc].min(axis=1), c=col[c], ls="--", label=f"{c} lowest"); ax[1, j].plot(df.hour, dv.SoC_BATT_pct, c=col[c], label=f"{c} battery SoC")
    ax[0, j].axhline(1.06, c="k", lw=1, ls=":"); ax[0, j].axhline(0.94, c="k", lw=1, ls=":"); ax[0, j].set_title(f"{scn}: highest / lowest node-phase voltage (pu)"); ax[0, j].legend(fontsize=7, ncol=2); ax[1, j].set_title(f"{scn}: battery SoC (%)"); ax[1, j].legend(fontsize=7)
    df, dv = keep[(scn, "C")]; ax[2, j].plot(dv.hour, dv[[x for x in dv if x.startswith("P_EV")]].sum(axis=1), label="EV"); ax[2, j].plot(dv.hour, dv[[x for x in dv if x.startswith("P_WH")]].sum(axis=1), label="heaters"); ax[2, j].plot(dv.hour, dv[[x for x in dv if x.startswith("P_PUMP")]].sum(axis=1), label="pumps"); ax[2, j].plot(dv.hour, dv.P_BATT_kW, c="k", label="battery (+charge)"); ax[2, j].legend(fontsize=7); ax[2, j].set_title(f"{scn}: device power under MPC (Case C), kW")
for a in ax.flat: a.grid(alpha=.3); a.set_xlabel("hour of day")
fig.suptitle("LocalFlex Grid - Stage 8: A no control / B rules / C predictive (no fairness), day 2, seed 7, common start SoC 50%", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage8_A_B_C.png"), dpi=130)
# register
RS8 = [("MPC horizon / step / replan", "24 h / 15 min / every step", "-", "Design", "Stage 8", "Rolling horizon", "12-36 h"),
       ("Forecast error (PV / demand), AR(1) rho", "15% / 8%, rho 0.9; PV forecast smoothed 5 steps", "-", "Assumption", "Placeholder", "Forecast != actual", "5-25%"),
       ("Voltage model used by planner", "Vmax=%.4f%+.5f*P, Vmin=%.4f%+.5f*P (P=net transformer kW)" % (cal["a_hi"], cal["b_hi"], cal["a_lo"], cal["b_lo"]), "pu", "Identified", "OpenDSS runs, profile seeds 11 and 23", "Basic aggregate voltage awareness (no bus/phase)", "R2 about 0.6"),
       ("Planner weights", json.dumps(W), "-", "Assumption", "Placeholder", "Soft constraints", "x0.5-x2"),
       ("Planner limits", "heater floor 47 C, ceiling 64.5 C; pump floor 20%; EV deadline margin 1.0 h; transformer cap 200 kW; evening reserve 40 kWh at 17:00; day-end SoC >= 50%", "-", "Assumption", "Placeholder", "Service and reserve", "-"),
       ("Common initial state", "battery SoC 50% at start of every reported day, all cases", "%", "Design", "Stage 8", "Fair A/B/C/D comparison", "-"),
       ("Gate", "predicted-step severity (voltage excursion + transformer overload) of MPC command vs Stage 7 rule command; fall back if MPC is worse", "-", "Design", "Stage 8", "Validator gate with fallback", "-")]
with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Parameter", "Value", "Unit", "Source type", "Source", "Reason", "Sensitivity range", "Version"])
    for r in REGISTER: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)" if r[0] in SUPERSEDED_S2 else "stage1-v0.1"])
    for L, v in ((REGISTER_S2, "stage2-v0.2"), (REGISTER_S3, "stage3-v0.3"), (REGISTER_S5, "stage5-v0.5"), (REGISTER_S6, "stage6-v0.6")):
        for r in L: w.writerow(list(r)+[v])
    old = pd.read_csv(os.path.join(R, "..", "config", "parameter_register_stage7_rows.csv")) if os.path.exists(os.path.join(R, "..", "config", "parameter_register_stage7_rows.csv")) else None
    for r in [("Rule voltage thresholds (act / full / low)", "1.04 / 1.07 / 0.96", "pu", "Assumption", "Placeholder", "Local droop trigger", "+-0.02"), ("Rule time windows", "shed 18-22; battery discharge 17-23; EV charge 22-06; pump hold 17-21", "h", "Assumption", "Placeholder", "Typical evening peak", "+-1 h"), ("EV latest-start margin / low-voltage block", "1.0 h / 0.95 pu", "-", "Assumption", "Placeholder", "Keep departure service", "0.5-2 h"), ("Rule inputs", "previous-step local voltage only; no forecast, no network model", "-", "Design", "Stage 7", "Case B definition", "-")]: w.writerow(list(r)+["stage7-v0.7"])
    for r in RS8: w.writerow(list(r)+["stage8-v0.8"])
g = out.groupby(["scenario", "case"]); keepc = ["hours_any_overvoltage", "hours_any_undervoltage", "v_min_pu", "v_max_pu", "peak_trafo_loading_pct", "peak_neutral_loading_pct", "peak_phase_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "min_heater_T_C", "battery_throughput_kWh", "battery_end_soc_pct"]
mean = g[keepc].mean().round(2); mean.to_csv(os.path.join(R, "stage8_summary_mean_over_seeds.csv")); print(mean.to_string())
