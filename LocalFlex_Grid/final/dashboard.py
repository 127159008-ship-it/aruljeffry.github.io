"""Builds results/final/dashboard.html (self-contained) from the run outputs. Data are replayed from real simulation runs (seed 7 time series, decision traces, dispatch suite); nothing is invented."""
import sys, os, json, pickle
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "results", "final"); NODES = ["a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3", "b4", "b5"]; SC = ["clear", "cloudy", "high_solar", "high_demand"]; V4 = ["A", "B", "C", "D"]
def r(x, n=3): return [round(float(v), n) for v in x]
def table(path, cols=None, n=3):
    if not os.path.exists(path): return None
    d = pd.read_csv(path)
    if cols: d = d[[c for c in cols if c in d]]
    return json.loads(d.round(n).to_json(orient="records"))
def build():
    K = pickle.load(open(os.path.join(OUT, "_keep.pkl"), "rb"))["keep"]; data = dict(ts={}, nodes=NODES)
    for s in SC:
        for v in V4:
            if (s, v) not in K: continue
            df, dv = K[(s, v)]; d = dict(t=r(df.t_h, 2), V=[[r(df[f"V_{n}_{p}_pu"], 4) for p in "ABC"] for n in NODES], trafo_kW=r(df.trafo_kW, 1), trafo_pct=r(df.trafo_loading_pct, 1), pv_avail=r(df.pv_avail_kW, 1), pv=r(df.pv_kW, 1), pv_curt=r(df.pv_curtailed_kW.clip(lower=0), 1), demand=r(df.demand_kW, 1), losses=r(df.losses_kW, 2),
                 In=r(df[[c for c in df if c.startswith("I_") and c.endswith("_N_A")]].max(axis=1), 1), Iph=r(df[[c for c in df if c.startswith("I_") and c.endswith("_A") and not c.endswith("_N_A")]].max(axis=1), 1), soc=r(dv.SoC_BATT_pct, 1), dev={c[2:-3]: r(dv[c], 2) for c in dv if c.startswith("P_") and c.endswith("_kW")},
                 T={c[2:-2]: r(dv[c], 1) for c in dv if c.startswith("T_")}, lvl={c[6:-4]: r(dv[c], 1) for c in dv if c.startswith("level_")}, ev_rem={c[4:-4]: r(dv[c], 2) for c in dv if c.startswith("rem_")})
            data["ts"][f"{s}|{v}"] = d
    comp = pd.read_csv(os.path.join(OUT, "A_B_C_D_comparison.csv")); data["comp"] = json.loads(comp.round(3).to_json(orient="records"))
    fp = os.path.join(OUT, "fairness", "burden_mean_over_seeds.csv"); data["fair"] = table(fp)
    tp = os.path.join(OUT, "decision_traces", "decision_traces.json"); data["traces"] = json.load(open(tp)) if os.path.exists(tp) else []; data["rmse"] = table(os.path.join(OUT, "decision_traces", "sensitivity_prediction_rmse.csv"), n=4)
    dp = os.path.join(OUT, "discom", "dispatch_suite_detail.json"); data["dispatch"] = json.load(open(dp)) if os.path.exists(dp) else {}; from final.dispatch import verified_table
    try: verified_table()
    except Exception as e: print("verify skipped", e)
    data["dispatch_tab"] = table(os.path.join(OUT, "discom", "dispatch_verified.csv"))
    st = {}
    for k, p in (("participation", "robustness/participation.csv"), ("forecast_error", "robustness/forecast_error.csv"), ("comm_delay", "robustness/comm_delay.csv"), ("assumptions", "robustness/assumption_sensitivity.csv"), ("faults", "robustness/final_fault_tests.csv"), ("battery_req", "battery_sizing/requirement_check.csv"), ("battery_loc", "battery_sizing/battery_location.csv"), ("scale", "scalability/scalability.csv")):
        st[k] = table(os.path.join(OUT, p))
    data["studies"] = st; data["audit"] = json.load(open(os.path.join(OUT, "standards_audit.json"))); vp = os.path.join(OUT, "final_validation.json"); data["validation"] = json.load(open(vp)) if os.path.exists(vp) else []
    cp = os.path.join(OUT, "cost_emissions.json"); data["cost"] = json.load(open(cp)) if os.path.exists(cp) else None; ap = os.path.join(OUT, "conclusions_auto.txt"); data["conclusions"] = open(ap).read().splitlines() if os.path.exists(ap) else []
    data["manifest"] = json.load(open(os.path.join(OUT, "manifest.json"))) if os.path.exists(os.path.join(OUT, "manifest.json")) else {}
    html = open(os.path.join(ROOT, "final", "dashboard_template.html")).read().replace("__DATA__", json.dumps(data, separators=(",", ":"), default=str))
    open(os.path.join(OUT, "dashboard.html"), "w").write(html); print("dashboard bytes", len(html)); return html
if __name__ == "__main__": build()
