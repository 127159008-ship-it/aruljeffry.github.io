"""Builds the evidence directory from the run outputs (nothing typed by hand): tables, plots, automatic factual conclusions, final_summary.json, FINAL_REPORT.md."""
import sys, os, json, pickle, shutil, glob
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "results", "final"); SC = ["clear", "cloudy", "high_solar", "high_demand"]; V4 = ["A", "B", "C", "D"]
COL = dict(A="#2a78d6", B="#eb6834", C="#1baf7a", D="#eda100"); LAB = dict(A="A no control", B="B rules", C="C MPC", D="D MPC + fairness")
plt.rcParams.update({"axes.facecolor": "#fcfcfb", "figure.facecolor": "#fcfcfb", "axes.edgecolor": "#c9c8c3", "axes.grid": True, "grid.color": "#ecebe7", "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
def sub(n): d = os.path.join(OUT, n); os.makedirs(d, exist_ok=True); return d
def groupbar(ax, T, col, title, ylab):
    w = 0.2
    for i, v in enumerate(V4):
        y = [T.loc[(s, v), col] if (s, v) in T.index else np.nan for s in SC]; ax.bar(np.arange(4)+i*w-0.3, y, w-0.02, color=COL[v], label=LAB[v])
    ax.set_xticks(range(4)); ax.set_xticklabels(SC); ax.set_title(title, loc="left", fontsize=10); ax.set_ylabel(ylab)
def tab(S, cols, name, folder):
    T = S.groupby(["scenario", "variant"])[[c for c in cols if c in S]].mean().round(3); T.to_csv(os.path.join(sub(folder), name+".csv")); return T
def fairness(bur):
    def agg(g):
        b = g.B_plan.values; return pd.Series(dict(worst_burden=b.max(), mean_burden=b.mean(), fairness_index_jain=(b.sum()**2)/(len(b)*(b**2).sum()) if (b**2).sum() > 0 else 1.0))
    return bur.groupby(["scenario", "seed", "variant"]).apply(agg).reset_index()
def pct(a, b): return None if b is None or abs(b) < 1e-9 else 100*(a-b)/abs(b)
def build_report():
    S = pd.read_csv(os.path.join(OUT, "final_summary.csv")); S = S[S.variant.isin(V4)]; keep = pickle.load(open(os.path.join(OUT, "_keep.pkl"), "rb")); K, LG = keep["keep"], keep["logs"]
    S["voltage_pu_h_total"] = S.under_pu_h + S.over_pu_h
    cols_all = ["v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "over_pu_h", "under_pu_h", "phase_voltage_unbalance_pct_max", "peak_phase_current_A", "peak_phase_loading_pct", "peak_neutral_current_A", "peak_neutral_loading_pct", "neutral_to_earth_V_max",
                "peak_trafo_kVA", "peak_trafo_loading_pct", "pv_available_kWh", "pv_delivered_kWh", "pv_curtailed_kWh", "pv_utilisation_pct", "curtailment_pct", "reverse_flow_hours", "reverse_flow_energy_kWh", "peak_import_kW", "peak_export_kW", "feeder_losses_kWh", "import_energy_kWh", "export_energy_kWh",
                "ev_delivered_kWh_incl_tail", "ev_unmet_at_departure_kWh", "heater_energy_kWh", "min_heater_T_C", "heater_hours_below_45C", "pump_energy_kWh", "water_delivered_m3", "unmet_water_m3", "tank_min_pct", "tank_max_pct",
                "batt_initial_soc_pct", "batt_final_soc_pct", "batt_soc_min_pct", "batt_soc_max_pct", "batt_charge_kWh", "batt_discharge_kWh", "batt_throughput_kWh", "plans", "mip_time_limited_plans", "solver_failures", "gate_checks", "fallbacks_to_rules", "convergence_failures", "msgs_lost_to_discom"]
    comp = tab(S, cols_all, "A_B_C_D_comparison_mean_over_seeds", "."); comp.to_csv(os.path.join(OUT, "A_B_C_D_comparison.csv")); os.remove(os.path.join(OUT, "A_B_C_D_comparison_mean_over_seeds.csv")) if os.path.exists(os.path.join(OUT, "A_B_C_D_comparison_mean_over_seeds.csv")) else None
    S.groupby(["scenario", "seed", "variant"])[[c for c in cols_all if c in S]].first().round(3).to_csv(os.path.join(OUT, "final_per_run.csv"))
    # --- category tables
    tab(S, ["v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "over_pu_h", "under_pu_h", "phase_voltage_unbalance_pct_max"], "voltage", "voltage")
    wv = S.groupby(["scenario", "variant"])[["v_max_where", "v_min_where"]].agg(lambda x: x.mode().iloc[0]); wv.to_csv(os.path.join(sub("voltage"), "worst_bus_phase_most_common.csv"))
    tab(S, ["peak_trafo_kVA", "peak_trafo_loading_pct", "peak_import_kW", "import_energy_kWh", "feeder_losses_kWh"], "transformer", "transformer"); tab(S, ["peak_phase_current_A", "peak_phase_loading_pct", "peak_neutral_current_A", "peak_neutral_loading_pct", "neutral_to_earth_V_max"], "neutral_and_phase_current", "neutral")
    tab(S, ["reverse_flow_hours", "reverse_flow_energy_kWh", "peak_export_kW", "export_energy_kWh"], "reverse_flow", "reverse_flow"); tab(S, ["pv_available_kWh", "pv_delivered_kWh", "pv_curtailed_kWh", "pv_utilisation_pct", "curtailment_pct"], "pv", "pv_curtailment")
    tab(S, ["batt_initial_soc_pct", "batt_final_soc_pct", "batt_soc_min_pct", "batt_soc_max_pct", "batt_charge_kWh", "batt_discharge_kWh", "batt_throughput_kWh"], "battery", "battery")
    tab(S, ["ev_delivered_kWh_incl_tail", "ev_unmet_at_departure_kWh", "heater_energy_kWh", "min_heater_T_C", "heater_hours_below_45C", "pump_energy_kWh", "water_delivered_m3", "unmet_water_m3", "tank_min_pct", "tank_max_pct"], "flexible_loads", "flexible_loads")
    tab(S, ["plans", "mip_time_limited_plans", "solver_failures", "gate_checks", "fallbacks_to_rules", "convergence_failures", "sup_events"], "controller", "controller")
    # --- fairness
    bur = pd.read_csv(os.path.join(OUT, "final_burden_by_group.csv")); bur = bur[bur.variant.isin(V4)]; bur.to_csv(os.path.join(sub("fairness"), "burden_by_group_all_runs.csv"), index=False); fa = fairness(bur); fa.to_csv(os.path.join(sub("fairness"), "burden_aggregate_per_run.csv"), index=False)
    fm = fa.groupby(["scenario", "variant"])[["worst_burden", "mean_burden", "fairness_index_jain"]].mean().round(3); fm.to_csv(os.path.join(sub("fairness"), "burden_mean_over_seeds.csv"))
    # --- main figure
    T = comp; fig, ax = plt.subplots(2, 4, figsize=(18, 8))
    for a, (c, t, y) in zip(ax.flat, [("voltage_pu_h_total", "Voltage violation magnitude (under+over)", "pu-hours"), ("hours_any_undervoltage", "Hours with any under-voltage", "h"), ("hours_any_overvoltage", "Hours with any over-voltage", "h"), ("peak_trafo_loading_pct", "Transformer peak loading", "%"),
                                     ("reverse_flow_energy_kWh", "Reverse-flow energy", "kWh"), ("curtailment_pct", "PV curtailed", "% of available"), ("ev_unmet_at_departure_kWh", "EV energy unmet at departure", "kWh"), ("worst_burden", "Worst-group burden (households)", "normalised")]):
        if c == "voltage_pu_h_total": T[c] = T.under_pu_h + T.over_pu_h
        if c == "worst_burden": groupbar(a, fm, c, t, y)
        else: groupbar(a, T, c, t, y)
    ax[0, 0].legend(fontsize=8, frameon=False); fig.suptitle("LocalFlex Grid final A/B/C/D comparison - mean of 4 seeds, identical initial state, 32 h scoring window (synthetic profiles)", fontsize=11, x=0.01, ha="left"); fig.tight_layout(); fig.savefig(os.path.join(OUT, "A_B_C_D_comparison.png"), dpi=130); plt.close(fig)
    # --- time series (seed 7)
    for scn in ("clear", "high_demand"):
        if (scn, "A") not in K: continue
        fig, ax = plt.subplots(2, 3, figsize=(17, 8)); 
        for v in V4:
            if (scn, v) not in K: continue
            df, dv = K[(scn, v)]; vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]; t = df.t_h
            ax[0, 0].plot(t, df[vc].min(axis=1), c=COL[v], label=LAB[v], lw=1.6); ax[0, 1].plot(t, df[vc].max(axis=1), c=COL[v], lw=1.6); ax[0, 2].plot(t, df.trafo_kW, c=COL[v], lw=1.6)
            nc = [c for c in df if c.endswith("_N_A") and c.startswith("I_")]; ax[1, 0].plot(t, df[nc].max(axis=1), c=COL[v], lw=1.6); ax[1, 1].plot(t, df.pv_curtailed_kW.clip(lower=0), c=COL[v], lw=1.6); ax[1, 2].plot(dv.t_h, dv.SoC_BATT_pct, c=COL[v], lw=1.6)
        for a, tt in zip(ax.flat, ["Lowest phase voltage (pu)", "Highest phase voltage (pu)", "Transformer net power (kW, + import)", "Highest neutral current (A)", "PV curtailed (kW)", "Battery SoC (%)"]): a.set_title(tt, loc="left", fontsize=10); a.set_xlabel("hours from 00:00 of reported day (32 h window)")
        ax[0, 0].axhline(0.94, c="#52514e", ls="--", lw=1); ax[0, 1].axhline(1.06, c="#52514e", ls="--", lw=1); ax[1, 0].axhline(100, c="#52514e", ls="--", lw=1); ax[0, 0].legend(frameon=False, fontsize=8); fig.suptitle(f"Scenario {scn}, seed 7 (synthetic)", x=0.01, ha="left"); fig.tight_layout()
        fig.savefig(os.path.join(sub("voltage"), f"timeseries_{scn}.png"), dpi=120); plt.close(fig)
    # --- fairness plot
    fig, ax = plt.subplots(1, 3, figsize=(15, 4)); 
    for a, (c, t) in zip(ax, [("worst_burden", "Worst-group burden"), ("mean_burden", "Mean burden"), ("fairness_index_jain", "Jain fairness index (1 = equal)")]): groupbar(a, fm, c, t, "")
    ax[0].legend(frameon=False, fontsize=8); fig.tight_layout(); fig.savefig(os.path.join(sub("fairness"), "fairness_summary.png"), dpi=120); plt.close(fig)
    # --- decision traces
    trs = {k: v for k, v in LG.items() if k.endswith("_trace")}; pls = {k: v for k, v in LG.items() if k.endswith("_predlog")}; dtr = sub("decision_traces"); rows = []; rm = []
    for k, tr in trs.items():
        if not k.startswith("clear_7_"): continue
        var = k.split("_")[2]; df = K[("clear", var)][0]
        for t in tr:
            col = f"V_{t['node_phase'].split('/')[0]}_{t['node_phase'].split('/')[1]}_pu"; t = dict(t); t["V_OpenDSS_after_execution"] = float(df[col][t["step"]]); t["V_OpenDSS_no_control_A"] = float(K[("clear", "A")][0][col][t["step"]]); t["validator"] = "executed command was gated by the OpenDSS trial solve; per-step verdict not logged (run-level fallback count in final_summary.csv)"; t["controller"] = var; rows.append(t)
    json.dump(rows, open(os.path.join(dtr, "decision_traces.json"), "w"), indent=1, default=str)
    for k, pl in pls.items():                                  # RMSE(V_pred, V_OpenDSS) at executed step
        if not k.startswith("clear_7_"): continue
        var = k.split("_")[2]; df = K[("clear", var)][0]; vc = [f"V_{n}_{p}_pu" for n in ["a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3", "b4", "b5"] for p in "ABC"]
        e = [np.array(vp) - df[vc].values[kk] for aa, kk, vp, vb in pl if aa >= 96 and kk < 96]; e0 = [np.array(vb) - df[vc].values[kk] for aa, kk, vp, vb in pl if aa >= 96 and kk < 96]
        rm.append(dict(controller=var, rmse_pred_vs_opendss_pu=float(np.sqrt(np.mean(np.square(e)))), rmse_forecast_base_no_action_pu=float(np.sqrt(np.mean(np.square(e0)))), steps=len(e)))
    pd.DataFrame(rm).to_csv(os.path.join(sub("decision_traces"), "sensitivity_prediction_rmse.csv"), index=False)
    # --- conclusions (facts only)
    L = []; C = comp
    for s in SC:
        def g(v, c): return float(C.loc[(s, v), c]) if (s, v) in C.index else None
        a_, b_, c_, d_ = [g(v, "under_pu_h") for v in V4]; ao, bo, co, do = [g(v, "over_pu_h") for v in V4]
        L.append(f"[{s}] voltage violation magnitude (pu-h, under+over): A {a_+ao:.3f}, B {b_+bo:.3f}, C {c_+co:.3f}, D {d_+do:.3f}; C vs A {pct(c_+co, a_+ao):+.0f}%, D vs C {pct(d_+do, c_+co):+.0f}%.")
        L.append(f"[{s}] hours with any under-voltage: A {g('A','hours_any_undervoltage'):.2f}, B {g('B','hours_any_undervoltage'):.2f}, C {g('C','hours_any_undervoltage'):.2f}, D {g('D','hours_any_undervoltage'):.2f}.")
        L.append(f"[{s}] transformer peak loading %: A {g('A','peak_trafo_loading_pct'):.1f}, B {g('B','peak_trafo_loading_pct'):.1f}, C {g('C','peak_trafo_loading_pct'):.1f}, D {g('D','peak_trafo_loading_pct'):.1f}; reverse-flow energy kWh: A {g('A','reverse_flow_energy_kWh'):.1f}, C {g('C','reverse_flow_energy_kWh'):.1f}, D {g('D','reverse_flow_energy_kWh'):.1f}; PV curtailed %: A {g('A','curtailment_pct'):.2f}, C {g('C','curtailment_pct'):.2f}, D {g('D','curtailment_pct'):.2f}.")
        L.append(f"[{s}] EV unmet kWh: A {g('A','ev_unmet_at_departure_kWh'):.2f}, B {g('B','ev_unmet_at_departure_kWh'):.2f}, C {g('C','ev_unmet_at_departure_kWh'):.2f}, D {g('D','ev_unmet_at_departure_kWh'):.2f}; D vs C worst-group burden {fm.loc[(s,'C'),'worst_burden']:.2f} -> {fm.loc[(s,'D'),'worst_burden']:.2f}, fairness index {fm.loc[(s,'C'),'fairness_index_jain']:.2f} -> {fm.loc[(s,'D'),'fairness_index_jain']:.2f}.")
    open(os.path.join(OUT, "conclusions_auto.txt"), "w").write("\n".join(L))
    # --- machine-readable summary + checks
    ok = dict(energy_balance_all=bool(S.energy_balance_ok.all()), max_abs_energy_residual_kWh=float(S.energy_balance_residual_kWh.abs().max()), convergence_failures=int(S.convergence_failures.sum()), solver_failures_CD=int(S[S.variant.isin(["C", "D"])].solver_failures.sum()),
              simultaneous_batt_plan_steps_CD=int(S[S.variant.isin(["C", "D"])].simultaneous_batt_steps_anywhere_in_plans.sum()), min_raw_pv_curtail_kW=float(S.pv_raw_curtail_min_kW.min()), runs=int(len(S)), initial_soc_values=sorted(set(S.batt_initial_soc_pct.round(1))))
    summ = dict(final_reference="localflex-final-v1", checks=ok, comparison={f"{a}|{b}": r.to_dict() for (a, b), r in comp.iterrows()}, fairness={f"{a}|{b}": r.to_dict() for (a, b), r in fm.iterrows()}, decision_trace_rmse=rm, conclusions=L)
    json.dump(summ, open(os.path.join(OUT, "final_summary.json"), "w"), indent=1, default=str); S.to_csv(os.path.join(OUT, "final_summary_core.csv"), index=False)
    # --- studies aggregation (whatever exists)
    study_tables(); copy_misc(); print("report built"); return summ
def study_tables():
    key = ["variant", "tag"]; keepc = ["hours_any_undervoltage", "hours_any_overvoltage", "under_pu_h", "over_pu_h", "peak_trafo_loading_pct", "peak_neutral_loading_pct", "reverse_flow_energy_kWh", "curtailment_pct", "ev_unmet_at_departure_kWh", "unmet_water_m3", "batt_throughput_kWh", "batt_final_soc_pct", "fallbacks_to_rules", "solver_failures", "convergence_failures", "mip_time_limited_plans"]
    for n, folder in (("participation", "robustness"), ("forecast_error", "robustness"), ("comm_delay", "robustness"), ("assumption_sensitivity", "robustness"), ("battery_size", "battery_sizing"), ("battery_location", "battery_sizing"), ("scalability", "scalability")):
        p = os.path.join(OUT, f"{n}.csv")
        if not os.path.exists(p): continue
        d = pd.read_csv(p); d = d[d.ok == True] if "ok" in d else d; extra = [c for c in d if c in ("participation", "pv_sigma_pct", "meas_delay_steps", "cmd_delay_steps", "batt_kwh", "batt_kw", "batt_node", "battery_only", "assumption", "homes", "run_s", "mean_solve_s", "planner_vars", "planner_cons", "batt_dV_per_kW_mean", "batt_dV_per_kW_far_ends", "scenario", "wall_s")]
        d[["tag", "variant"]+extra+[c for c in keepc if c in d]].to_csv(os.path.join(sub(folder), f"{n}.csv"), index=False)
def copy_misc():
    for f, dst in (("final_fault_tests.csv", "robustness"), ("final_fault_event_log.json", "robustness"), ("final_forecast_metrics.csv", "robustness"), ("final_openplc_equivalence.json", "openplc")):
        p = os.path.join(ROOT, "results", f)
        if os.path.exists(p): shutil.copy(p, sub(dst))
    d = os.path.join(ROOT, "openplc"); 
    for f in ("localflex_rules.st",):
        if os.path.exists(os.path.join(d, f)): shutil.copy(os.path.join(d, f), sub("openplc"))
    if os.path.exists(os.path.join(OUT, "standards_audit.csv")): shutil.copy(os.path.join(OUT, "standards_audit.csv"), sub("standards"))
if __name__ == "__main__": build_report()
