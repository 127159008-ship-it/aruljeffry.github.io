"""Live demo: send a simulated DISCOM request to the running LocalFlex engine (scenario day, full MPC + validator + OpenDSS) and print the story.
  python run_demo.py --request reduce_import --target 20 --start 18:30 --duration 60
  python run_demo.py --request import_cap --target 120 --start 18:00 --duration 240 --comm-off 17:00-20:00
Runs two simulations (baseline D, and D with the request); about 5 minutes. All numbers come from those runs."""
import sys, os, json, argparse
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--request", default="reduce_import", choices=["reduce_import", "import_cap", "export_cap"]); ap.add_argument("--target", type=float, default=20.0, help="kW reduction (reduce_import) or cap (import_cap/export_cap)")
    ap.add_argument("--start", default="18:30"); ap.add_argument("--duration", type=int, default=60); ap.add_argument("--scenario", default="clear"); ap.add_argument("--seed", type=int, default=7); ap.add_argument("--comm-off", default=None, help="HH:MM-HH:MM link outage"); a = ap.parse_args()
    from final.dispatch import job
    req = dict(request=a.request, start=a.start, duration_min=a.duration); req["target_kw" if a.request == "reduce_import" else "cap_kw"] = a.target
    out = None
    if a.comm_off:
        s, e = a.comm_off.split("-"); f = lambda t: int(t.split(":")[0]) + int(t.split(":")[1])/60.0; out = [(f(s), f(e))]
    name, item, rows, keep, logs = job(("live demo", dict(req=req, outage=out), a.scenario, a.seed))
    from final.dispatch import respond
    resp = respond(req, logs.get("D@disp_caplog", []), logs.get("D@disp", [])); run = next(x for x in rows if x["variant"] == "D@disp"); base = next(x for x in rows if x["variant"] == "D")
    story = ["1 DISCOM request  : " + json.dumps(req), "2 LocalFlex check : " + f"{resp['status'].upper()} - {resp['reason']}", "3 MPC + validator : planner solved with the cap as a soft constraint; OpenDSS validator fallbacks " + str(run.get("fallbacks_to_rules")) + f", solver failures {run.get('solver_failures')}",
             f"4 Feeder response : 18-22h import peak {run['import_peak_18_22_kW']} kW (baseline {base['import_peak_18_22_kW']} kW); EV unmet {run['ev_unmet_at_departure_kWh']} kWh (baseline {base['ev_unmet_at_departure_kWh']}); under-voltage {run['under_pu_h']} pu-h (baseline {base['under_pu_h']})",
             f"5 Link            : messages lost to DISCOM {run.get('msgs_lost_to_discom')}, requests lost {run.get('requests_lost_from_discom')}; local control and hard-limit protection stayed active" if out else "5 Link            : normal"]
    print("\n".join(story)); d = os.path.join(ROOT, "results", "final", "demo"); os.makedirs(d, exist_ok=True); json.dump(dict(story=story, response=resp, run=run, baseline=base, comm_log=logs.get("D@disp", [])[:80]), open(os.path.join(d, "last_demo.json"), "w"), indent=1, default=str)
if __name__ == "__main__": main()
