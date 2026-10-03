"""Planned robustness / sizing / location / participation studies. Same A/B/C/D protocol, same snapshot logic, NO controller retuning.
Each job = one (scenario, seed, overrides) -> list of variants run in ONE process (shared sensitivity build). Results appended incrementally to results/final/<study>.csv."""
import sys, os, json, time, copy, traceback
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from multiprocessing import Pool
OUT = os.path.join(ROOT, "results", "final"); os.makedirs(OUT, exist_ok=True)
def job(spec):
    import run_stage10 as r
    from final.overrides import overrides
    t0 = time.time()
    try:
        with overrides(**spec.get("ov", {})):
            rows, brows, keep, logs = r.task((spec["scn"], spec["seed"], spec["variants"], spec.get("kw", {})))
            extra = {}
            if spec.get("diag_battery_H"):
                from sensitivity import build_H
                from run_stage9 import monitored
                from network.feeder_generator import build
                from config.feeder_config import CFG, SEED, DEVICES
                m = build(CFG, SEED); S = build_H(m, 48); ri = [x[0] for x in S["resources"]].index("BATT"); H = S["H"][:, ri]; mon = S["monitored"]
                far = [i for i, (n, p) in enumerate(mon) if n in ("a5", "b5")]; extra = dict(batt_dV_per_kW_mean=float(H.mean()), batt_dV_per_kW_far_ends=float(H[far].mean()), batt_dV_per_kW_max=float(H.max()))
            bur = brows.copy() if len(brows) else brows
        out = []
        for rw in rows:
            rw = dict(rw); rw.update(study=spec["study"], tag=spec["tag"], ok=True, wall_s=round(time.time()-t0, 1), **spec.get("meta", {}), **extra); out.append(rw)
        if len(bur): bur["study"] = spec["study"]; bur["tag"] = spec["tag"]
        return out, bur, {k: v for k, v in logs.items() if k.endswith("_sup")}
    except Exception as e:
        return [dict(study=spec["study"], tag=spec["tag"], scenario=spec["scn"], seed=spec["seed"], variant="ERROR", ok=False, error=repr(e)[:300], tb=traceback.format_exc()[-600:])], pd.DataFrame(), {}
def run_jobs(name, specs, workers=2):
    path = os.path.join(OUT, f"{name}.csv"); bpath = os.path.join(OUT, f"{name}_burden.csv"); rows = []; brows = []
    with Pool(workers) as p:
        for out, bur, logs in p.imap_unordered(job, specs, chunksize=1):
            rows += out; brows.append(bur); pd.DataFrame(rows).to_csv(path, index=False)
            if any(len(b) for b in brows): pd.concat([b for b in brows if len(b)]).to_csv(bpath, index=False)
            print(name, "done", out[0].get("tag"), out[0].get("variant"), flush=True)
    return pd.DataFrame(rows)
# ------------------------------------------------------------------ planned matrix
def S_participation():
    return [dict(study="participation", tag=f"p{int(p*100)}_{scn}", scn=scn, seed=7, variants=["A", "B", "C", "D"], kw={}, ov=dict(participation=p), meta=dict(participation=p)) for scn in ("clear", "high_demand") for p in (0.3, 0.6)]
def S_forecast():
    return [dict(study="forecast_error", tag=f"sig{int(s*100)}", scn="clear", seed=7, variants=["A", "C", "D"], kw={}, ov=dict(plan=dict(pv_fc_sigma=0.15*s, dem_fc_sigma=0.08*s)), meta=dict(pv_sigma_pct=15*s, dem_sigma_pct=8*s)) for s in (0.0, 1/3, 2/3, 4/3)]
def S_delay():
    kw = lambda ms, cs: {"D": dict(supervise=True, delay=(ms, cs))}
    return [dict(study="comm_delay", tag=f"m{ms}c{cs}", scn="clear", seed=7, variants=["A", "D"], kw=kw(ms, cs), meta=dict(meas_delay_steps=ms, cmd_delay_steps=cs)) for ms, cs in ((1, 0), (4, 0), (0, 1), (0, 4), (1, 1))]
def S_battery_size():
    out = []
    for scn in ("clear", "high_demand"):
        for kwh, kw_ in ((20, 50), (40, 50), (60, 50), (80, 50), (150, 50), (100, 10), (100, 20), (100, 30), (100, 40)):
            out.append(dict(study="battery_size", tag=f"E{kwh}_P{kw_}_{scn}", scn=scn, seed=7, variants=["A", "D"] if (kwh, kw_) == (20, 50) else ["D"], kw={}, ov=dict(battery=dict(e_kwh=float(kwh), p_kw=float(kw_))), meta=dict(batt_kwh=kwh, batt_kw=kw_)))
        for kwh in (40, 100, 150, 200):       # battery-only comparison: same planner (no fairness), flexible loads NOT controlled (natural)
            out.append(dict(study="battery_size", tag=f"BO_E{kwh}_P50_{scn}", scn=scn, seed=7, variants=["C@bo"], kw={"C@bo": dict(battery_only=True)}, ov=dict(battery=dict(e_kwh=float(kwh), p_kw=50.0)), meta=dict(batt_kwh=kwh, batt_kw=50, battery_only=True)))
    return out
def S_battery_location():
    return [dict(study="battery_location", tag=f"loc_{n}", scn="clear", seed=7, variants=["D"], kw={}, ov=dict(battery=dict(node=n)), diag_battery_H=True, meta=dict(batt_node=n)) for n in ("a1", "a3", "a5", "b1", "b3", "b5")]
def S_network():
    L = []
    for tag, cfg in (("trafo160", dict(kva=160)), ("trafo400", dict(kva=400)), ("r1x1.3", dict(r1=0.32*1.3, r0=1.28*1.3)), ("r1x0.7", dict(r1=0.32*0.7, r0=1.28*0.7)), ("neutral_r_x2", dict(r_n=0.64*2)), ("neutral_amp70", dict(neutral_ampacity_a=70.0)),
                     ("pv_phase_even", dict(pv_by_phase=(13, 13, 14))), ("pv_x0.5", dict(pv_by_phase=(11, 6, 3))), ("vlim_0.95_1.05", dict(v_hi=1.05, v_lo=0.95))):
        L.append(dict(study="assumption_sensitivity", tag=tag, scn="clear", seed=7, variants=["A", "B", "C", "D"], kw={}, ov=dict(cfg=cfg), meta=dict(assumption=tag)))
    return L
def S_scale():
    L = []
    for homes, f in ((100, 1), (300, 3), (500, 5)):
        cfg = dict(homes_per_node=10*f, kva=250*f, pv_by_phase=(22*f, 12*f, 6*f)); dev = dict(water_heater=dict(n=8*f), ev=dict(n=6*f), battery=dict(e_kwh=100.0*f, p_kw=50.0*f))
        L.append(dict(study="scalability", tag=f"homes{homes}", scn="clear", seed=7, variants=["A", "D"], kw={"D": dict(supervise=True)}, ov=dict(cfg=cfg, devices=dev), meta=dict(homes=homes, scale_factor=f)))
    return L
STUDIES = dict(participation=S_participation, forecast_error=S_forecast, comm_delay=S_delay, battery_size=S_battery_size, battery_location=S_battery_location, assumption_sensitivity=S_network, scalability=S_scale)
if __name__ == "__main__":
    names = sys.argv[1:] or list(STUDIES)
    for n in names: print("== study", n, flush=True); run_jobs(n, STUDIES[n]())
