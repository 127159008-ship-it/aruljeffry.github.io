import sys, os, json, pickle, csv
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); R = os.path.join(ROOT, "results"); sys.path.insert(0, ROOT)
d = pickle.load(open(os.path.join(R, "_s10keep.pkl"), "rb")); keep, logs = d["keep"], d["logs"]; out = pd.read_csv(os.path.join(R, "stage10_summary.csv")); bur = pd.read_csv(os.path.join(R, "stage10_burden_by_group.csv"))
core = ["A", "B", "C8", "C9raw", "C", "D"]; main = out[out.variant.isin(core)].copy(); tests = {}
C, D = main[main.variant == "C"], main[main.variant == "D"]
tests["battery_exclusivity: simultaneous charge+discharge steps anywhere in C / D plans (C9raw for comparison)"] = [int(C.simultaneous_batt_steps_anywhere_in_plans.sum()), int(D.simultaneous_batt_steps_anywhere_in_plans.sum()), int(main[main.variant == "C9raw"].simultaneous_batt_steps_anywhere_in_plans.sum())]
tests["plans solved C / D"] = [int(C.plans.sum()), int(D.plans.sum())]; tests["MILP plans stopped at 1 s limit (feasible incumbent, gap<=2% not proven) C / D"] = [int(C.mip_time_limited_plans.sum()), int(D.mip_time_limited_plans.sum())]
tests["initial battery SoC (%) all runs"] = sorted(set(out.batt_initial_soc_pct.round(1))); tests["all_runs_convergence_failures"] = int(out.convergence_failures.sum()); tests["max_power_balance_residual_kW"] = float(out.max_power_balance_residual_kW.max())
tests["solver_failures C / D"] = [int(C.solver_failures.sum()), int(D.solver_failures.sum())]; tests["C battery final SoC min / D battery final SoC min (%)"] = [float(C.batt_final_soc_pct.min()), float(D.batt_final_soc_pct.min())]
tests["EV unmet at departure: max over runs C / D (kWh)"] = [float(C.ev_unmet_at_departure_kWh.max()), float(D.ev_unmet_at_departure_kWh.max())]; tests["unmet water max (m3)"] = float(main.unmet_water_m3.max())
# burden aggregates
def agg(g):
    b = g.B_plan.values; return pd.Series(dict(worst_B=b.max(), mean_B=b.mean(), max_over_mean=b.max()/max(b.mean(), 1e-9), jain=(b.sum()**2)/(len(b)*(b**2).sum()) if (b**2).sum() > 0 else 1.0, worst_B_incl_curtail=(g.B_plan+g.B_curt).max()))
ba = bur.groupby(["scenario", "seed", "variant"]).apply(agg).reset_index(); ba.to_csv(os.path.join(R, "stage10_burden_aggregate.csv"), index=False)
bm = ba[ba.variant.isin(core)].groupby(["scenario", "variant"])[["worst_B", "mean_B", "max_over_mean", "jain", "worst_B_incl_curtail"]].mean().round(3); bm.to_csv(os.path.join(R, "stage10_burden_mean_over_seeds.csv"))
# main table
cols = ["hours_any_overvoltage", "hours_any_undervoltage", "under_pu_h", "over_pu_h", "v_max_pu", "v_min_pu", "peak_phase_loading_pct", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "curtailment_pct", "ev_unmet_at_departure_kWh", "min_heater_T_C", "batt_final_soc_pct", "batt_throughput_kWh", "batt_charge_kWh", "batt_discharge_kWh", "fallbacks_to_rules", "a5A_min_pu", "overnight_vmin_pu"]
mean = main.groupby(["scenario", "variant"])[cols].mean().round(3); mean = mean.reindex(pd.MultiIndex.from_product([["clear", "cloudy", "high_solar", "high_demand"], core]), ); mean.to_csv(os.path.join(R, "stage10_summary_mean_over_seeds.csv"))
pd.set_option("display.width", 250); print(mean[["hours_any_overvoltage", "hours_any_undervoltage", "under_pu_h", "over_pu_h", "v_min_pu", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "batt_final_soc_pct", "batt_throughput_kWh", "fallbacks_to_rules"]].to_string()); print(bm.to_string())
# lambda sweep + comm
sw = out[out.variant.str.contains("@lam") | ((out.variant == "D") & (out.seed == 7) & (out.scenario == "clear")) | ((out.variant == "C") & (out.seed == 7) & (out.scenario == "clear"))].copy()
sw["lam"] = sw.variant.map(lambda v: float(v.split("lam")[1]) if "lam" in v else (500.0 if v == "D" else 0.0))
swb = ba[(ba.scenario == "clear") & (ba.seed == 7)].set_index("variant"); sw["worst_B"] = sw.variant.map(lambda v: swb.worst_B.get(v)); sw = sw.sort_values("lam"); sw[["variant", "lam", "worst_B", "under_pu_h", "over_pu_h", "hours_any_undervoltage", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "batt_throughput_kWh", "fallbacks_to_rules"]].to_csv(os.path.join(R, "stage10_lambda_sweep.csv"), index=False); print(sw[["variant", "lam", "worst_B", "under_pu_h", "hours_any_undervoltage", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "fallbacks_to_rules"]].to_string(index=False))
cm = out[out.variant.str.contains("dispatch") | ((out.variant == "D") & (out.seed == 7) & (out.scenario == "clear"))]; cmc = ["variant", "import_peak_18_22_kW", "peak_trafo_loading_pct", "peak_phase_loading_pct", "v_min_pu", "under_pu_h", "ev_unmet_at_departure_kWh", "batt_final_soc_pct", "msgs_lost_to_discom", "requests_lost_from_discom", "steps_with_dispatch_cap", "solver_failures", "convergence_failures"]; cm[cmc].to_csv(os.path.join(R, "stage10_comm_test.csv"), index=False); print(cm[cmc].to_string(index=False))
json.dump({k: v[:60] for k, v in logs.items()}, open(os.path.join(R, "stage10_discom_message_log_sample.json"), "w"), indent=1, default=str)
tests["comm: every comm variant had 0 solver failures and 0 convergence failures"] = bool((cm.solver_failures.fillna(0) == 0).all() and (cm.convergence_failures == 0).all())
tests["comm: dispatch_up peak import 18-22 vs D (kW)"] = [float(cm[cm.variant == "D@dispatch_up"].import_peak_18_22_kW.iloc[0]), float(cm[cm.variant == "D"].import_peak_18_22_kW.iloc[0])]
json.dump(tests, open(os.path.join(R, "stage10_tests.json"), "w"), indent=1, default=str); print(json.dumps(tests, indent=1, default=str))
# plots
fig, ax = plt.subplots(3, 2, figsize=(14, 13)); col = {"A": "#888", "B": "#B84A4A", "C": "#1F7A7A", "D": "#E8A33D"}
for j, scn in enumerate(("clear", "high_demand")):
    for v in ("A", "B", "C", "D"):
        df, dv = keep[(scn, v)]; vc = [x for x in df if x.startswith("V_") and x.endswith("_pu")]; ax[0, j].plot(df.t_h, df[vc].max(axis=1), c=col[v], label=f"{v} highest"); ax[0, j].plot(df.t_h, df[vc].min(axis=1), c=col[v], ls="--", label=f"{v} lowest"); ax[1, j].plot(dv.t_h, dv.SoC_BATT_pct, c=col[v], label=v)
    ax[0, j].axhline(1.06, c="k", ls=":"); ax[0, j].axhline(0.94, c="k", ls=":"); ax[0, j].set_title(f"{scn}: highest / lowest voltage (seed 7)"); ax[0, j].legend(fontsize=6, ncol=2); ax[1, j].set_title(f"{scn}: battery SoC (%)"); ax[1, j].legend(fontsize=7)
b7 = bur[(bur.scenario == "clear") & bur.variant.isin(["A", "B", "C", "D"])].groupby(["variant", "group"]).B_plan.mean().unstack(0)[["B", "C", "D"]]; b7.plot.bar(ax=ax[2, 0], color=[col["B"], col["C"], col["D"]]); ax[2, 0].set_title("clear: burden B_plan per household-facing group (mean over seeds)"); ax[2, 0].set_ylabel("normalised burden")
s2 = pd.read_csv(os.path.join(R, "stage10_lambda_sweep.csv")); ax[2, 1].plot(s2.lam, s2.worst_B, "o-", c=col["D"], label="worst group burden"); ax[2, 1].set_xscale("symlog", linthresh=50); ax[2, 1].set_xlabel("fairness weight lambda (0 = C)"); a2 = ax[2, 1].twinx(); a2.plot(s2.lam, s2.under_pu_h, "s--", c="k", label="under-voltage pu-h"); ax[2, 1].set_title("clear seed 7: fairness weight sweep"); ax[2, 1].legend(loc="upper left", fontsize=7); a2.legend(loc="upper right", fontsize=7)
for a in ax.flat[:4]: a.grid(alpha=.3); a.set_xlabel("hours from midnight of the reported day (96-128 = next morning tail)")
fig.suptitle("LocalFlex Grid - Stage 10: A no control / B rules / C = C9-fixed / D = C9-fixed + fairness (identical initial state)", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage10_final_comparison.png"), dpi=130)
fig, ax = plt.subplots(1, 1, figsize=(10, 4.5))
for v, c in (("A", "#888"), ("D", "#E8A33D"), ("D@dispatch_up", "#1F7A7A"), ("D@dispatch_lost_before", "#B84A4A"), ("D@dispatch_lost_after", "#2B6CA0")):
    df, dv = keep[("clear", v)]; ax.plot(df.t_h, df.trafo_kW, c=c, label=v)
ax.axhline(150, c="k", ls=":"); ax.axvspan(18, 22, alpha=.08); ax.set_title("DISCOM dispatch test (import cap 150 kW 18-22 h, issued 17:00): link up vs lost before vs lost after"); ax.set_xlabel("hour"); ax.set_ylabel("transformer net kW"); ax.legend(fontsize=7); ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(os.path.join(R, "stage10_comm_test.png"), dpi=130)
# register
from config.feeder_config import REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, REGISTER_S6
RS10 = [("Battery exclusivity", "binary mode variable per step (MILP), HiGHS limit 1 s, rel gap 2%", "-", "Design", "Stage 10", "No simultaneous charge/discharge (C9-fixed)", "-"),
        ("Fairness burden B_g", "delay energy-hours/(4 h x natural daily energy) + 10 x unmet/natural daily energy; groups WH1-4, EV1-2; pumps excluded (shared service)", "-", "Assumption", "Placeholder", "Household-facing groups only", "weights x0.5-x2"),
        ("Fairness term", "lambda x worst-group burden (day-so-far realised + planned), lambda=500; sweep 100/500/2000 reported", "cost units", "Assumption", "Placeholder", "Case D = C + fairness only", "100-2000"),
        ("Curtailment burden", "reported ex-post only: phase-level PV curtailment shared among household-facing groups on that phase; NOT optimised (curtailment is set by the inverter, not commanded)", "kWh", "Design", "Stage 10", "Transparency", "-"),
        ("DISCOM request / link", "import cap 150 kW 18-22 h issued 17:00; validity 3 h + window; outage windows applied daily; default envelope = transformer cap 200 kW", "kW", "Assumption", "Placeholder", "Simulated aggregated interface", "-"),
        ("Evaluation protocol", "reported day = day 2 from IDENTICAL snapshot (battery 50%, device states, EV carry-over) + 8 h tail for next-morning EV/heater/pump service", "-", "Design", "Stage 10", "Identical initial conditions A/B/C/D", "-")]
with open(os.path.join(ROOT, "config", "parameter_register.csv"), newline="") as f: rows = list(csv.reader(f))
rows = [r for r in rows if not (len(r) >= 8 and r[7] == "stage10-v1.0")]
with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
    w = csv.writer(f); [w.writerow(r) for r in rows]; [w.writerow(list(r)+["stage10-v1.0"]) for r in RS10]
