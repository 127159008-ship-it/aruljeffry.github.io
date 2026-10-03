"""Stage 9: C9 (bus x phase sensitivity MPC) vs frozen C8 (aggregate voltage MPC), plus A and B, identical scenarios/seeds/initial SoC."""
import sys, os, json, time, pickle
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from run_stage8 import *            # run_case (A, B, C8), calibrate, metrics, service, next_day ...
from sensitivity import build_H, monitored, resource_list
from control.mpc import make_forecast
from control.mpc9 import MPC9Controller
PV_RATED = CFG.get("pv_kw_each", 3.0)*40
def forecast_base(m, dem, pv, seed):
    """Forecast-driven OpenDSS run with natural devices: gives V_base (96 x monitored) and natural device power. Uses the forecast aggregate scaled onto the true per-home allocation."""
    fd, fp = make_forecast(dem.sum(axis=1), pv.sum(axis=1), seed); fd, fp = fd[:96], fp[:96]
    dem_f = dem*(fd/dem.sum(axis=1))[:, None]; pvs = pv.sum(axis=1); pv_f = pv*np.where(pvs > 0, fp/np.where(pvs > 0, pvs, 1), 0.0)[:, None]
    df, dv, *_ = simulate6("A1", m, dem_f, pv_f, warm_start(make_all(DEVICES, DEVICE_SEED))); mon = monitored(m)
    Vb = np.column_stack([df[f"V_{n}_{p}_pu"].values for n, p in mon]); Pn = {gid: dv[f"P_{gid}_kW"].values for gid in [r[0] for r in resource_list()] if f"P_{gid}_kW" in dv}; Pn["BATT"] = np.zeros(96)
    return Vb, Pn
def extra(df):
    vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]; a5 = df["V_a5_A_pu"]; night = df.hour < 6
    return dict(a5A_min_pu=round(float(a5.min()), 3), a5A_hours_below_0p94=float((a5 < 0.94).sum()/4), a5A_overnight_hours_below_0p94=float(((a5 < 0.94) & night).sum()/4), overnight_any_undervoltage_hours=float(((df[vc].min(axis=1) < 0.94) & night).sum()/4), overnight_vmin_pu=round(float(df[night][vc].min().min()), 3))
def run_case9(m, dem, pv, seed, cal, S_mid, S_ev, gate=True, trace=False):
    Vb, Pn = forecast_base(m, dem, pv, seed); groups = warm_start(make_all(DEVICES, DEVICE_SEED))
    ctl = MPC9Controller(cal, dem.sum(axis=1), pv.sum(axis=1), seed, S_mid["H"], S_ev["H"], [r for r in S_mid["resources"]], S_mid["monitored"], Vb, Pn, PV_RATED, gate=gate, trace_steps=((96+48, 96+76) if trace else ()))
    for d in range(2):
        if d > 0:
            next_day(groups); b = [g for g in groups if isinstance(g, SharedBattery)][0]; b.E = b.E0 = b.P["soc_init"]*b.P["e_kwh"]
        df, dv, ex, ec, es = simulate6("A1", m, dem, pv, groups, controller=ctl)
    for g in groups:
        if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
    return df, dv, ex, ec, es, groups, ctl
def main():
    t0 = time.time(); m = build(CFG, SEED); pvn = [m["homes"][i][0] for i in m["pv"]]; seeds = [7, 11, 23, 42] if "--full" in sys.argv else [7]
    cal = json.load(open(os.path.join(R, "stage8_voltage_model.json"))); S_mid = build_H(m, 48); S_ev = build_H(m, 76)
    rows = []; keep = {}; traces = None; pred_err = []
    for scn, (ds, sm, _) in SCENARIOS.items():
        for seed in seeds:
            dem = household_profiles(m["scale"], seed, ds); pv = pv_availability(sm, seed, pvn)
            variants = [("A", {}), ("B", {}), ("C8", {}), ("C9", {})] + ([("C9_nogate", dict(gate=False))] if seed == 7 else [])
            for name, kw in variants:
                if name.startswith("C9"): df, dv, ex, ec, es, groups, ctl = run_case9(m, dem, pv, seed, cal, S_mid, S_ev, trace=(name == "C9" and seed == 7), **kw)
                else: df, dv, ex, ec, es, groups, ctl = run_case(name[0], m, dem, pv, seed, cal)
                mm = metrics(df, ex, scn, seed, name); mm.update(service(dv, groups, ec, es)); mm.update(extra(df))
                if name in ("C8", "C9", "C9_nogate"): mm.update(gate_checks=ctl.n_gate, fallbacks_to_rules=ctl.n_fb, solver_failures=ctl.n_fail, simultaneous_batt_steps=ctl.n_sim, mean_solve_s=round(float(np.mean(ctl.solve_s)), 3))
                rows.append(mm)
                if seed == 7: keep[(scn, name)] = (df, dv); df.to_csv(os.path.join(R, f"stage9_{scn}_{name}_timeseries.csv"), index=False); dv.to_csv(os.path.join(R, f"stage9_{scn}_{name}_device_states.csv"), index=False)
                if name == "C9":
                    for (a, k, Vp, Vb_) in ctl.pred_log:
                        if a >= 96: pred_err.append(dict(scenario=scn, seed=seed, step=k, rmse=float(np.sqrt(np.mean((Vp - df[[f"V_{n}_{p}_pu" for n, p in S_mid["monitored"]]].values[k])**2))), maxabs=float(np.max(np.abs(Vp - df[[f"V_{n}_{p}_pu" for n, p in S_mid["monitored"]]].values[k]))), rmse_base_only=float(np.sqrt(np.mean((Vb_ - df[[f"V_{n}_{p}_pu" for n, p in S_mid["monitored"]]].values[k])**2)))))
                    if seed == 7 and scn == "clear": traces = (ctl.trace, df, dv)
            print(f"{scn} seed {seed} done ({time.time()-t0:.0f}s)", flush=True)
    out = pd.DataFrame(rows); out["curtailed_kWh_by_phase"] = out["curtailed_kWh_by_phase"].astype(str); out.to_csv(os.path.join(R, "stage9_summary.csv"), index=False)
    pe = pd.DataFrame(pred_err); pe.to_csv(os.path.join(R, "stage9_prediction_error.csv"), index=False)
    pickle.dump(dict(keep=keep, traces=traces, S_mid=S_mid, S_ev=S_ev), open(os.path.join(R, "_s9keep.pkl"), "wb"))
    print(out[["scenario", "seed", "case", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "a5A_min_pu", "a5A_overnight_hours_below_0p94", "overnight_any_undervoltage_hours", "ev_unmet_at_departure_kWh", "fallbacks_to_rules", "mean_solve_s"]].to_string(index=False))
if __name__ == "__main__": main()
