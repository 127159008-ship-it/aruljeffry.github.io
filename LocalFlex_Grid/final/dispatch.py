"""DISCOM dispatch suite: simulated utility requests -> LocalFlex feasibility check (from the planner's own slack variables) -> accepted / partial / rejected with reason ->
execution through MPC + validator + devices -> measured result. Aggregated data only. Used by run_demo.py (live) and run_final.py (suite)."""
import sys, os, json
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
def hhmm(h): return f"{int(h):02d}:{int(round((h-int(h))*60)):02d}"
def parse_request(req):
    """req: {'request': 'reduce_import'|'import_cap'|'export_cap', 'target_kw' | 'cap_kw', 'start': 'HH:MM', 'duration_min': int, 'priority': 'normal'|'high'} -> SimDISCOM kwargs"""
    h, m = req["start"].split(":"); w0 = int(h) + int(m)/60.0; w1 = w0 + req["duration_min"]/60.0; kind = req["request"]
    kw = dict(window=(w0, w1), lead_h=1.0, kind=kind, priority=req.get("priority", "normal"))
    if kind == "reduce_import": kw["target_kw"] = float(req["target_kw"])
    elif kind == "import_cap": kw["cap_kw"] = float(req["cap_kw"])
    elif kind == "export_cap": kw["export_cap_kw"] = float(req["cap_kw"])
    else: raise ValueError(kind)
    return kw
def respond(req, caplog, comm_log):
    """LocalFlex response issued at the first plan after reception: from planner slack. Rejected when the request never arrived (no ack)."""
    received = any(isinstance(e["msg"], dict) and e["dir"] == "DISCOM->LocalFlex" for e in comm_log)
    if not received: return dict(status="no_response", reason="request lost: link down at issue time; DISCOM receives no acknowledgement and must time out", requested=req)
    first = next((c for c in caplog if c["kind"] in ("import", "export")), None)
    if first is None: return dict(status="rejected", reason="no plan with an active window", requested=req)
    tgt = req.get("target_kw")
    if req["request"] == "reduce_import": need = tgt; slack = first["slack_max_kW"]; feasible = max(need - slack, 0.0)
    else:
        need = None; slack = first["slack_max_kW"]; feasible = None
    if slack <= 0.5: st, why = "accepted", "plan meets the request within validator limits"
    elif need is not None and feasible > 0.5: st, why = "partial", f"planner can deliver about {feasible:.0f} kW of the {need:.0f} kW requested; remaining shortfall {slack:.0f} kW (EV deadlines, tank/heater service floors, battery reserve/limits)"
    elif need is None: st, why = "partial", f"cap exceeded by about {slack:.0f} kW in the plan: remaining demand is uncontrollable base load / service constraints"
    else: st, why = "rejected", "no feasible reduction without violating service or battery limits"
    return dict(status=st, reason=why, requested=req, plan_predicted_slack_kW=round(slack, 1), plan_feasible_reduction_kW=None if feasible is None else round(feasible, 1))
SUITE = {
  "R1 reduce import 20 kW, 18:30-19:30": dict(req=dict(request="reduce_import", target_kw=20, start="18:30", duration_min=60), outage=None),
  "R2 reduce import 60 kW, 18:30-19:30": dict(req=dict(request="reduce_import", target_kw=60, start="18:30", duration_min=60), outage=None),
  "R3 reduce import 150 kW, 18:30-19:30": dict(req=dict(request="reduce_import", target_kw=150, start="18:30", duration_min=60), outage=None),
  "R4 import cap 120 kW, 18:00-22:00": dict(req=dict(request="import_cap", cap_kw=120, start="18:00", duration_min=240), outage=None),
  "R5 export cap 5 kW, 11:00-14:00": dict(req=dict(request="export_cap", cap_kw=5, start="11:00", duration_min=180), outage=None),
  "R6 = R1 with link lost before request (17:00-18:00)": dict(req=dict(request="reduce_import", target_kw=20, start="18:30", duration_min=60), outage=[(17.0, 18.0)]),
  "R7 = R1 with link lost after request (17:45-20:00)": dict(req=dict(request="reduce_import", target_kw=20, start="18:30", duration_min=60), outage=[(17.75, 20.0)]),
}
def comm_kw(item): return dict(supervise=True, comm=dict(discom=parse_request(item["req"]), outages=item["outage"] or []))
def job(args):
    import run_stage10 as r
    name, item, scn, seed = args; variants = {"D": dict(supervise=True)}; nm = "D@disp"; variants[nm] = comm_kw(item)
    rows, brows, keep, logs = r.task((scn, seed, ["A", "D", nm] if True else [nm], variants))
    return name, item, rows, keep, logs
def main(scn="clear", seed=7, names=None):
    from multiprocessing import Pool
    names = names or list(SUITE); out = []; tasks = [(n, SUITE[n], scn, seed) for n in names]
    with Pool(2) as p: res = p.map(job, tasks, chunksize=1)
    rows = []; story = {}
    for name, item, rr, keep, logs in res:
        base = next(x for x in rr if x["variant"] == "D"); run = next(x for x in rr if x["variant"] == "D@disp")
        dfb = keep[(scn, "D")][0]; dfr = keep[(scn, "D@disp")][0]; req = item["req"]; w0, w1 = (lambda h, m: (int(h)+int(m)/60.0, int(h)+int(m)/60.0+req["duration_min"]/60.0))(*req["start"].split(":")); sel = (dfb.hour >= w0) & (dfb.hour < w1)
        resp = respond(req, logs.get("D@disp_caplog", []), logs.get("D@disp", []))
        ib = dfb.trafo_kW[sel].clip(lower=0).values; ir = dfr.trafo_kW[sel].clip(lower=0).values; eb = (-dfb.trafo_kW[sel]).clip(lower=0).values; er = (-dfr.trafo_kW[sel]).clip(lower=0).values
        rows.append(dict(request=name, status=resp["status"], reason=resp["reason"], baseline_mean_import_kW=round(float(ib.mean()), 1), actual_mean_import_kW=round(float(ir.mean()), 1), mean_import_reduction_kW=round(float((ib-ir).mean()), 1), min_step_reduction_kW=round(float((ib-ir).min()), 1),
                         baseline_peak_export_kW=round(float(eb.max()), 1), actual_peak_export_kW=round(float(er.max()), 1), ev_unmet_kWh=run["ev_unmet_at_departure_kWh"], ev_unmet_baseline_kWh=base["ev_unmet_at_departure_kWh"], undervolt_pu_h=run["under_pu_h"], undervolt_pu_h_baseline=base["under_pu_h"],
                         fallbacks=run.get("fallbacks_to_rules"), solver_failures=run.get("solver_failures"), convergence_failures=run["convergence_failures"], msgs_lost_up=run.get("msgs_lost_to_discom"), requests_lost=run.get("requests_lost_from_discom")))
        story[name] = dict(response=resp, comm_log=logs.get("D@disp", [])[:60], hour=dfr.hour[::1].tolist() if False else None, import_baseline=dfb.trafo_kW.tolist(), import_run=dfr.trafo_kW.tolist(), window=[w0, w1])
    T = pd.DataFrame(rows); od = os.path.join(ROOT, "results", "final", "discom"); os.makedirs(od, exist_ok=True); T.to_csv(os.path.join(od, "dispatch_suite.csv"), index=False); json.dump(story, open(os.path.join(od, "dispatch_suite_detail.json"), "w"), indent=1, default=str)
    print(T.to_string()); return T
if __name__ == "__main__": main()

def verify(req, trafo_base, trafo_run, window):
    """Outcome check against the simulated (OpenDSS) result, independent of the planner's own prediction. trafo_kW > 0 = import.
    Record = scored day (96 steps) + 8 h tail; window is evaluated in the day part only."""
    import numpy as np
    w0, w1 = window; n = len(trafo_run); hr = (np.arange(n) % 96) * 0.25; sel = (hr >= w0) & (hr < w1) & (np.arange(n) < 96)
    b = np.array(trafo_base)[sel]; r_ = np.array(trafo_run)[sel]
    if req["request"] == "reduce_import":
        ach = float((np.clip(b, 0, None) - np.clip(r_, 0, None)).mean()); tgt = float(req["target_kw"]); ok = ach >= 0.9*tgt
        return dict(metric="mean import reduction kW", requested=tgt, achieved=round(ach, 1), met=bool(ok))
    if req["request"] == "import_cap":
        pk = float(np.clip(r_, 0, None).max()); cap = float(req["cap_kw"]); return dict(metric="peak import kW", requested=cap, achieved=round(pk, 1), met=bool(pk <= cap*1.05))
    pk = float(np.clip(-r_, 0, None).max()); cap = float(req["cap_kw"]); return dict(metric="peak export kW", requested=cap, achieved=round(pk, 1), met=bool(pk <= max(cap*1.05, cap+1.0)))
def verified_table():
    import numpy as np
    od = os.path.join(ROOT, "results", "final", "discom"); T = pd.read_csv(os.path.join(od, "dispatch_suite.csv")); det = json.load(open(os.path.join(od, "dispatch_suite_detail.json"))); rows = []
    for _, t in T.iterrows():
        d = det[t["request"]]; req = d["response"]["requested"]; v = verify(req, d["import_baseline"], d["import_run"], tuple(d["window"]))
        st, why = t["status"], t["reason"]
        if st == "accepted" and not v["met"]:
            st = "partial"
            why = f"planner predicted compliance but the OpenDSS-simulated outcome missed the request ({v['metric']}: requested {v['requested']}, achieved {v['achieved']}). " + ("The planner's PV-curtailment variable is not an actuator in this prototype (curtailment comes only from the local volt-watt rule), so an export cap cannot be honoured by curtailment." if req["request"] == "export_cap" else "")
        rows.append(dict(request=t["request"], planner_status=t["status"], verified_status=st, verified_reason=why, **{"check_"+k: val for k, val in v.items()}))
    V = pd.DataFrame(rows); V.to_csv(os.path.join(od, "dispatch_verified.csv"), index=False); return V
