"""Stage 8: predictive control (Case C) vs A (no control) and B (rules). Common initial battery SoC (50%) for every case on the reported day; forecast != actual; validator gate + Stage 7 fallback."""
import sys, os, json, time, pickle, csv
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from run_stage7 import *
from run_stage7 import next_day, service
from control.mpc import MPCController, make_forecast, W, PLAN
from control.rule_based import RuleController
R = os.path.join(ROOT, "results")
def calibrate(m):
    """Identify Vmax = a + b*P_net and Vmin = a + b*P_net from natural-device A1 runs on profile seeds 11 and 23 (NOT the reported seed 7)."""
    pvn = [m["homes"][i][0] for i in m["pv"]]; X = []; Vh = []; Vl = []
    for seed in (11, 23):
        for scn, (ds, sm, _) in SCENARIOS.items():
            dem = household_profiles(m["scale"], seed, ds); pv = pv_availability(sm, seed, pvn)
            df, *_ = simulate6("A1", m, dem, pv, warm_start(make_all(DEVICES, DEVICE_SEED)))
            vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]; X += list(df.trafo_kW); Vh += list(df[vc].max(axis=1)); Vl += list(df[vc].min(axis=1))
    X = np.array(X); out = {}
    for nm, y in (("hi", np.array(Vh)), ("lo", np.array(Vl))):
        b, a = np.polyfit(X, y, 1); res = y - (a + b*X); out[f"a_{nm}"] = float(a); out[f"b_{nm}"] = float(b); out[f"r2_{nm}"] = float(1 - res.var()/y.var()); out[f"rmse_{nm}"] = float(np.sqrt((res**2).mean()))
    return out
def run_case(case, m, dem, pv, seed, cal, gate=True, perfect=False):
    groups = warm_start(make_all(DEVICES, DEVICE_SEED)); ctl = None
    if case == "B": ctl = RuleController()
    if case == "C": ctl = MPCController(cal, dem.sum(axis=1), pv.sum(axis=1), seed, gate=gate, perfect=perfect)
    for d in range(2):
        if d > 0:
            next_day(groups); b = [g for g in groups if isinstance(g, SharedBattery)][0]; b.E = b.E0 = b.P["soc_init"]*b.P["e_kwh"]   # common initial state for the reported day
        df, dv, ex, ec, es = simulate6("A1", m, dem, pv, groups, controller=ctl)
    for g in groups:
        if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
    return df, dv, ex, ec, es, groups, ctl
def main():
    t0 = time.time(); m = build(CFG, SEED); pvn = [m["homes"][i][0] for i in m["pv"]]; seeds = [7, 11, 23, 42] if "--full" in sys.argv else [7]
    cal = calibrate(m); print("calibration:", {k: round(v, 5) for k, v in cal.items()}, flush=True); json.dump(cal, open(os.path.join(R, "stage8_voltage_model.json"), "w"), indent=1)
    rows = []; keep = {}
    variants = [("A", {}), ("B", {}), ("C", {})]
    for scn, (ds, sm, _) in SCENARIOS.items():
        for seed in seeds:
            dem = household_profiles(m["scale"], seed, ds); pv = pv_availability(sm, seed, pvn)
            vs = variants + ([("C_nogate", dict(gate=False)), ("C_perfect", dict(perfect=True))] if seed == 7 else [])
            for name, kw in vs:
                case = name.split("_")[0]; df, dv, ex, ec, es, groups, ctl = run_case(case, m, dem, pv, seed, cal, **kw)
                mm = metrics(df, ex, scn, seed, name); mm.update(service(dv, groups, ec, es))
                if ctl is not None and case == "C": mm.update(gate_checks=ctl.n_gate, fallbacks_to_rules=ctl.n_fb, solver_failures=ctl.n_fail, simultaneous_batt_steps=ctl.n_sim, mean_solve_s=round(float(np.mean(ctl.solve_s)), 3))
                rows.append(mm)
                if seed == 7: keep[(scn, name)] = (df, dv); df.to_csv(os.path.join(R, f"stage8_{scn}_{name}_timeseries.csv"), index=False); dv.to_csv(os.path.join(R, f"stage8_{scn}_{name}_device_states.csv"), index=False)
            print(f"{scn} seed {seed} done ({time.time()-t0:.0f}s)", flush=True)
    out = pd.DataFrame(rows); out["curtailed_kWh_by_phase"] = out["curtailed_kWh_by_phase"].astype(str); out.to_csv(os.path.join(R, "stage8_summary.csv"), index=False)
    pickle.dump(keep, open(os.path.join(R, "_s8keep.pkl"), "wb"))
    cols = ["scenario", "seed", "case", "v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "peak_phase_loading_pct", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "ev_unmet_at_departure_kWh", "min_heater_T_C", "battery_throughput_kWh", "battery_end_soc_pct", "fallbacks_to_rules", "simultaneous_batt_steps"]
    print(out[[c for c in cols if c in out]].to_string(index=False))
if __name__ == "__main__": main()
