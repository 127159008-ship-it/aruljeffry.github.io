"""LocalFlex Grid - final integrated platform. ONE command:  python run_final.py [--profile quick|full] [--stage core|studies|report|all]
core    : A/B/C/D on identical initial state for scenario x seed (full = 4 x 4), master loop = simulate6 + MPC + supervisor (+DISCOM layer), 128-step scoring window
studies : planned robustness / sizing / location / participation / assumption studies (final/studies.py)
report  : aggregates, plots, conclusions, FINAL_REPORT.md, dashboard data
All numbers come from the runs; nothing is copied by hand."""
import sys, os, json, time, pickle, argparse
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
OUT = os.path.join(ROOT, "results", "final"); os.makedirs(OUT, exist_ok=True)
SCNS = ["clear", "cloudy", "high_solar", "high_demand"]; SEEDS = [7, 11, 23, 42]
def core(profile):
    from multiprocessing import Pool
    import run_stage10 as r
    from final.manifest import manifest, run_record
    scns, seeds = (["clear"], [7]) if profile == "quick" else (SCNS, SEEDS)
    json.dump(manifest(dict(profile=profile)), open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
    sup = {"C": dict(supervise=True), "D": dict(supervise=True)}
    tasks = [(s, sd, ["A", "B", "C", "D"], sup) for s in scns for sd in seeds]; rows = []; bur = []; keep = {}; logs = {}; recs = []
    with Pool(2) as p:
        for rr, bb, kk, ll in p.imap_unordered(r.task, tasks, chunksize=1):
            rows += rr; bur.append(bb); keep.update(kk); logs.update({f"{rr[0]['scenario']}_{rr[0]['seed']}_{k}": v for k, v in ll.items()})
            pd.DataFrame(rows).to_csv(os.path.join(OUT, "final_summary.csv"), index=False); print("core done", rr[0]["scenario"], rr[0]["seed"], flush=True)
    rows = sorted(rows, key=lambda x: (x["scenario"], x["seed"], x["variant"])); df = pd.DataFrame(rows); df.to_csv(os.path.join(OUT, "final_summary.csv"), index=False)
    pd.concat(bur).to_csv(os.path.join(OUT, "final_burden_by_group.csv"), index=False)
    pickle.dump(dict(keep=keep, logs=logs), open(os.path.join(OUT, "_keep.pkl"), "wb"))
    for rw in rows: recs.append(run_record(rw["scenario"], rw["seed"], rw["variant"], batt_initial_soc_pct_logged=rw["batt_initial_soc_pct"]))
    json.dump(recs, open(os.path.join(OUT, "run_records.json"), "w"), indent=1, default=str)
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--profile", default="full", choices=["quick", "full"]); ap.add_argument("--stage", default="all", choices=["core", "studies", "report", "all"]); a = ap.parse_args()
    t0 = time.time()
    if a.stage in ("core", "all"): core(a.profile)
    if a.stage in ("studies", "all"):
        from final.studies import STUDIES, run_jobs
        for n in STUDIES: run_jobs(n, STUDIES[n]())
    if a.stage in ("report", "all"):
        from final.report import build_report; build_report()
    print(f"run_final finished in {time.time()-t0:.0f} s")
if __name__ == "__main__": main()
