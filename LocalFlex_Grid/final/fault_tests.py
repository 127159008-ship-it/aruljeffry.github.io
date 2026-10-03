"""Explicit fault-injection tests of the fallback ladder (clear scenario, seed 7, Case D controller, fault window 16:00-19:00).
Safety criterion (documented): hard equipment limits respected (transformer <=100 %, phase <=200 A, neutral <=100 A, all solves converged)
AND voltage violation magnitude inside the window not worse than the worse of the no-control (A) and rule-based (B) cases."""
import sys, os, json
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from multiprocessing import Pool
import run_stage10 as r
from final.supervisor import FAULTS
W0, W1 = 64, 76
def window_metrics(df, a=W0, b=92):
    d = df.iloc[a:b]; vc = [c for c in d if c.startswith("V_") and c.endswith("_pu")]; V = d[vc].values
    ic = [c for c in d if c.startswith("I_") and c.endswith("_A") and not c.endswith("_N_A")]; nc = [c for c in d if c.endswith("_N_A") and c.startswith("I_")]
    return dict(win_under_pu_h=float(np.clip(0.94-V, 0, None).sum()*.25), win_over_pu_h=float(np.clip(V-1.06, 0, None).sum()*.25), win_trafo_max_pct=float(d.trafo_loading_pct.max()),
                win_phase_max_A=float(d[ic].values.max()), win_neutral_max_A=float(d[nc].values.max()), win_all_converged=bool(d.converged.all()))
def variants():
    cm = dict(comm=dict(discom=dict(cap_kw=150.0, window=(18.0, 22.0), lead_h=1.0), outages=[(16.5, 19.5)]))
    ex = {"D": dict(supervise=True)}
    for f in FAULTS:
        kw = dict(faults=[(f, 72, 88) if f == "battery_unavailable" else (f, W0, W1)]);
        if f == "communication_lost": kw.update(cm)
        ex["D@F_"+f] = kw
    return ex
def main():
    ex = variants(); names = ["A", "B"] + list(ex)
    half = [names[:6], ["A"] + names[6:]]
    res = []
    with Pool(2) as p: res = p.map(r.task, [("clear", 7, h, {k: v for k, v in ex.items() if k in h}) for h in half], chunksize=1)
    rows = [x for rr in res for x in rr[0] if not (x["variant"] == "A" and any(y["variant"] == "A" for y in [])) ]
    seen = set(); rows = [x for x in rows if not (x["variant"] in seen or seen.add(x["variant"]))]; keep = {}; logs = {}
    for rr in res: keep.update(rr[2]); logs.update(rr[3])
    out = pd.DataFrame(rows).set_index("variant"); wm = {n: window_metrics(keep[("clear", n)][0]) for n in names}; ref = max(wm["A"]["win_under_pu_h"]+wm["A"]["win_over_pu_h"], wm["B"]["win_under_pu_h"]+wm["B"]["win_over_pu_h"])
    tab = []
    for n in names:
        w = wm[n]; ev = logs.get(n+"_sup", []); hard = w["win_trafo_max_pct"] <= 100 and w["win_phase_max_A"] <= 200 and w["win_neutral_max_A"] <= 100 and w["win_all_converged"]
        safe = hard and (w["win_under_pu_h"]+w["win_over_pu_h"] <= ref + 1e-9)
        tab.append(dict(variant=n, **{k: round(v, 3) if isinstance(v, float) else v for k, v in w.items()}, events=len(ev), event_summary="; ".join(f"{e['cause']}->{e['action']} {e['duration_min']}min" for e in ev[:6]),
                        fallbacks_to_rules=out.loc[n, "fallbacks_to_rules"] if "fallbacks_to_rules" in out else None, ev_unmet_kWh=out.loc[n, "ev_unmet_at_departure_kWh"], hard_limits_ok=hard, safety_maintained=safe))
    T = pd.DataFrame(tab); T.to_csv(os.path.join(ROOT, "results", "final_fault_tests.csv"), index=False)
    json.dump({k: v for k, v in logs.items() if k.endswith("_sup")}, open(os.path.join(ROOT, "results", "final_fault_event_log.json"), "w"), indent=1, default=str)
    print(T.drop(columns=["event_summary"]).to_string()); print(T[["variant", "event_summary"]].to_string())
if __name__ == "__main__": main()
