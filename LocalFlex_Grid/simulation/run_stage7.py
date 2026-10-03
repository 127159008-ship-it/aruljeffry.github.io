"""Stage 7: rule-based control (Case B) vs no control (Case A = A1 inverter + natural devices). Two consecutive days, day 2 reported (cyclic carry-over)."""
import sys, os, json, time, copy, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from config.feeder_config import CFG, SEED, SCENARIOS, DEVICES, DEVICE_SEED
from network.feeder_generator import build
from profiles.scenarios import household_profiles, pv_availability
from devices.resources import *
from control.rule_based import RuleController, RULES
from run_stage6 import simulate6
from run_stage5 import metrics
R = os.path.join(ROOT, "results")
def next_day(groups):
    for g in groups:
        if isinstance(g, EVGroup):
            g.remA = g.remB.copy(); g.remB = g.need.copy(); g.rA0 = g.remA.copy(); g.departedA[:] = False; g.led = dict(grid=0.0, batt=0.0, unmetA=0.0)
        elif isinstance(g, WaterHeaterGroup): g.T0 = g.T; g.led = dict(e_in=0.0, e_loss=0.0, e_draw=0.0)
        elif isinstance(g, PumpTank): g.L0 = g.level; g.led = dict(v_in=0.0, v_served=0.0, unmet=0.0, spill=0.0, run_min=0)
        elif isinstance(g, SharedBattery): g.E0 = g.E; g.led = dict(grid_in=0.0, grid_out=0.0)
def run(case_ctl, m, dem, pv, days=2):
    groups = warm_start(make_all(DEVICES, DEVICE_SEED)); ctl = RuleController() if case_ctl == "B" else None
    for d in range(days):
        if d > 0: next_day(groups)
        df, dv, ex, ec, es = simulate6("A1", m, dem, pv, groups, controller=ctl)
    for g in groups:
        if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
    return df, dv, ex, ec, es, groups
def service(dv, groups, ec, es):
    S = {}; ev = [g for g in groups if isinstance(g, EVGroup)]; pu = [g for g in groups if isinstance(g, PumpTank)]; b = [g for g in groups if isinstance(g, SharedBattery)][0]
    S["ev_unmet_at_departure_kWh"] = round(sum(g.led["unmetA"] for g in ev), 2); S["unmet_water_m3"] = round(sum(g.led["unmet"] for g in pu), 3)
    T = dv[[c for c in dv if c.startswith("T_")]]; S["min_heater_T_C"] = round(float(T.min().min()), 1); S["heater_hours_below_45C"] = float((T < 45).any(axis=1).sum()/4)
    S["pump_min_level_pct"] = round(float(dv[[c for c in dv if c.startswith("level_")]].min().min()), 1)
    S["battery_throughput_kWh"] = round(b.led["grid_in"] + b.led["grid_out"], 1); S["battery_end_soc_pct"] = round(100*b.E/b.P["e_kwh"], 1); S["battery_soc_change_pct"] = round(100*(b.E-b.E0)/b.P["e_kwh"], 2)
    S["device_energy_commanded_kWh"] = round(sum(ec.values()), 1); S["device_energy_solved_kWh"] = round(sum(es.values()), 1)
    return S
def main():
    t0 = time.time(); m = build(CFG, SEED); pv_nodes = [m["homes"][i][0] for i in m["pv"]]; rows = []; keep = {}
    seeds = [7, 11, 23, 42] if "--full" in sys.argv else [7]
    for scn, (dscale, smode, desc) in SCENARIOS.items():
        for seed in seeds:
            dem = household_profiles(m["scale"], seed, dscale); pv = pv_availability(smode, seed, pv_nodes)
            for case in ("A", "B"):
                df, dv, ex, ec, es, groups = run(case, m, dem, pv); mm = metrics(df, ex, scn, seed, case); mm.update(service(dv, groups, ec, es)); rows.append(mm)
                if seed == 7: keep[(scn, case)] = (df, dv); df.to_csv(os.path.join(R, f"stage7_{scn}_{case}_timeseries.csv"), index=False); dv.to_csv(os.path.join(R, f"stage7_{scn}_{case}_device_states.csv"), index=False)
            print(f"{scn} seed {seed} done ({time.time()-t0:.0f}s)", flush=True)
    out = pd.DataFrame(rows); out["curtailed_kWh_by_phase"] = out["curtailed_kWh_by_phase"].astype(str); out.to_csv(os.path.join(R, "stage7_summary.csv"), index=False)
    import pickle; pickle.dump(keep, open(os.path.join(R, "_s7keep.pkl"), "wb"))
    cols = ["scenario", "seed", "case", "v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "peak_phase_loading_pct", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "unmet_water_m3", "min_heater_T_C", "battery_throughput_kWh", "battery_soc_change_pct", "convergence_failures"]
    print(out[cols].to_string(index=False))
def finish():
    import pickle, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from config.feeder_config import REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, REGISTER_S6, SUPERSEDED_S2
    keep = pickle.load(open(os.path.join(R, "_s7keep.pkl"), "rb")); out = pd.read_csv(os.path.join(R, "stage7_summary.csv")); nodes = [c[2:-5] for c in keep[("clear","A")][0] if c.startswith("V_") and c.endswith("_A_pu")]
    fig, ax = plt.subplots(3, 2, figsize=(14, 12))
    for j, scn in enumerate(("clear", "high_demand")):
        for case, st, col in (("A", ":", "#888"), ("B", "-", "#1F7A7A")):
            df, dv = keep[(scn, case)]; vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]
            ax[0, j].plot(df.hour, df[vc].max(axis=1), ls=st, c=col, label=f"{case} highest"); ax[0, j].plot(df.hour, df[vc].min(axis=1), ls=st, c=col, alpha=.6, label=f"{case} lowest")
            ax[1, j].plot(df.hour, df.trafo_kW, ls=st, c=col, label=f"{case}")
        ax[0, j].axhline(CFG["v_hi"], c="k", lw=1, ls="--"); ax[0, j].axhline(CFG["v_lo"], c="k", lw=1, ls="--"); ax[0, j].set_title(f"{scn}: network voltage extremes, A=no control (dotted) vs B=rules"); ax[0, j].legend(fontsize=7); ax[1, j].set_title(f"{scn}: transformer net kW"); ax[1, j].axhline(0, c="k", lw=1); ax[1, j].legend()
        dv = keep[(scn, "B")][1]; ax[2, j].plot(dv.hour, dv[[c for c in dv if c.startswith("P_EV")]].sum(axis=1), label="EV"); ax[2, j].plot(dv.hour, dv[[c for c in dv if c.startswith("P_WH")]].sum(axis=1), label="heaters"); ax[2, j].plot(dv.hour, dv[[c for c in dv if c.startswith("P_PUMP")]].sum(axis=1), label="pumps"); ax[2, j].plot(dv.hour, dv.P_BATT_kW, label="battery (+charge)", c="k"); ax[2, j].legend(fontsize=7); ax[2, j].set_title(f"{scn}: device power under rules (kW)")
    for a in ax.flat: a.grid(alpha=.3); a.set_xlabel("hour of day")
    fig.suptitle("LocalFlex Grid - Stage 7: rule-based control (Case B) vs no control (Case A), day 2 of a 2-day cyclic run, seed 7", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage7_rules_vs_nocontrol.png"), dpi=130)
    RS7 = [("Rule voltage thresholds (act / full / low)", "1.04 / 1.07 / 0.96", "pu", "Assumption", "Placeholder", "Local droop trigger", "+-0.02"),
           ("Rule time windows", "shed 18-22; battery discharge 17-23; EV charge 22-06; pump hold 17-21", "h", "Assumption", "Placeholder", "Typical evening peak", "+-1 h"),
           ("EV latest-start margin / low-voltage block", "1.0 h / 0.95 pu", "-", "Assumption", "Placeholder", "Keep departure service", "0.5-2 h"),
           ("Rule inputs", "previous-step local voltage only; no forecast, no network model", "-", "Design", "Stage 7", "Case B definition", "-")]
    import csv
    with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter", "Value", "Unit", "Source type", "Source", "Reason", "Sensitivity range", "Version"])
        for r in REGISTER: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)" if r[0] in SUPERSEDED_S2 else "stage1-v0.1"])
        for L, v in ((REGISTER_S2, "stage2-v0.2"), (REGISTER_S3, "stage3-v0.3"), (REGISTER_S5, "stage5-v0.5"), (REGISTER_S6, "stage6-v0.6"), (RS7, "stage7-v0.7")):
            for r in L: w.writerow(list(r)+[v])
    g = out.groupby(["scenario", "case"])[["hours_any_overvoltage", "hours_any_undervoltage", "v_min_pu", "peak_trafo_loading_pct", "peak_neutral_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh"]].mean().round(2); print(g.to_string())
    out.groupby(["scenario", "case"]).mean(numeric_only=True).round(3).to_csv(os.path.join(R, "stage7_summary_mean_over_seeds.csv"))
if __name__ == "__main__":
    main()
    if "--full" in sys.argv: finish()
