"""LocalFlex Grid digital-twin API (FastAPI). The browser never runs OpenDSS or the MPC: this service owns the simulation.
Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000   (from webapp/backend)."""
import os, json, time, threading, queue, uuid, csv, glob
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import engine_bridge as eb
from . import nasa as nasa_mod

DATA = os.environ.get("LOCALFLEX_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
JOBS = os.path.join(DATA, "jobs"); os.makedirs(JOBS, exist_ok=True)
DEMO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo_jobs")
ANALYSIS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "analysis_data")
ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
MAX_QUEUE = int(os.environ.get("MAX_QUEUE", "3")); WORKERS = int(os.environ.get("SIM_WORKERS", "2"))

app = FastAPI(title="LocalFlex Grid digital twin API", version="1.0.0", description="Runs the frozen LocalFlex engine (OpenDSS + MPC + safety supervisor) for a chosen location, date and PV penetration.")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])


class NasaReq(BaseModel):
    latitude: float; longitude: float; date: str; tz_offset_h: float | None = None; pv_kw_per_home: float = 3.0


class SimReq(BaseModel):
    environment: str = Field("synthetic", description="synthetic | nasa | csv")
    synthetic_scenario: str = Field("clear", description="clear | cloudy | high_solar | high_demand (used when environment=synthetic)")
    latitude: float | None = None; longitude: float | None = None; date: str | None = None; tz_offset_h: float | None = None
    irradiance_Wm2: list[float] | None = Field(None, description="96 values (15-min, local time) for environment=csv")
    temp_C: list[float] | None = None
    pv_penetration: float = Field(40, ge=0, le=100); pv_kw_per_home: float = Field(3.0, gt=0, le=10)
    homes: int = Field(100, description="only 100 is validated")
    controller: str = "D"
    battery_kwh: float = Field(100.0, gt=0, le=1000); battery_kw: float = Field(50.0, gt=0, le=500)
    demand_scale: float = Field(1.0, ge=0.5, le=1.6)


# ---------------------------------------------------------------- job manager (one heavy job at a time; two worker processes per job)
_q: "queue.Queue[str]" = queue.Queue(); _lock = threading.Lock(); _status: dict = {}
_pool = None


def _job_dir(jid): return os.path.join(JOBS, jid)
def _read(path):
    with open(path) as f: return json.load(f)
def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)
def _set(jid, **kw):
    with _lock:
        st = _status.get(jid) or (_read(os.path.join(_job_dir(jid), "status.json")) if os.path.exists(os.path.join(_job_dir(jid), "status.json")) else {})
        st.update(kw); _status[jid] = st; _write(os.path.join(_job_dir(jid), "status.json"), st)


def _get_pool():
    global _pool
    if _pool is None: _pool = ProcessPoolExecutor(max_workers=WORKERS, mp_context=mp.get_context("spawn"))
    return _pool


def _runner():
    while True:
        jid = _q.get()
        try:
            spec = _read(os.path.join(_job_dir(jid), "spec.json")); t0 = time.time(); _set(jid, state="running", started=t0, progress=0.05, message="building the feeder, sensitivities and starting the four cases")
            pool = _get_pool(); futs = [pool.submit(eb.worker, (spec, ["A", "B", "C"])), pool.submit(eb.worker, (spec, ["A", "D"]))]; res = []
            for i, f in enumerate(futs):
                res.append(f.result()); _set(jid, progress=0.5 + 0.5*(i+1)/len(futs)*0.99, message=f"{i+1}/{len(futs)} worker batches finished")
            out = dict(cases={}, metrics={}, burden=[])
            for r in res:
                for k, v in r["cases"].items():
                    if k not in out["cases"]: out["cases"][k] = v
                for k, v in r["metrics"].items():
                    if k not in out["metrics"]: out["metrics"][k] = v
                out["burden"] += r["burden"]
            _write(os.path.join(_job_dir(jid), "result.json"), out); _set(jid, state="done", progress=1.0, message="finished", finished=time.time(), seconds=round(time.time()-t0, 1))
        except Exception as e:
            import traceback; _set(jid, state="failed", message=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-1500:])
        finally: _q.task_done()


threading.Thread(target=_runner, daemon=True).start()


def _resolve_spec(r: SimReq):
    if r.homes != eb.VALIDATED_HOMES: raise HTTPException(422, "only the validated 100-home feeder is available (other sizes are not validated)")
    if r.controller not in eb.CONTROLLERS: raise HTTPException(422, "controller must be A, B, C or D")
    spec = r.model_dump(); spec["pv_model"] = {}
    if r.environment == "synthetic":
        from config.feeder_config import SCENARIOS
        if r.synthetic_scenario not in SCENARIOS: raise HTTPException(422, f"unknown synthetic scenario; choose from {list(SCENARIOS)}")
        spec["scenario"] = r.synthetic_scenario; spec["irradiance_Wm2"] = None; spec["temp_C"] = None
    elif r.environment == "nasa":
        if r.latitude is None or r.longitude is None or not r.date: raise HTTPException(422, "latitude, longitude and date are required for NASA input")
        try: rec = nasa_mod.fetch(r.latitude, r.longitude, r.date, r.tz_offset_h)
        except nasa_mod.NasaError as e: raise HTTPException(502, str(e))
        spec["irradiance_Wm2"] = rec["irradiance_Wm2"]; spec["temp_C"] = rec["temp_C"]; spec["tz_offset_h"] = rec["tz_offset_h"]; spec["scenario"] = "web_" + eb.spec_hash(dict(lat=r.latitude, lon=r.longitude, d=r.date))
    elif r.environment == "csv":
        if not r.irradiance_Wm2 or len(r.irradiance_Wm2) != 96: raise HTTPException(422, "csv input needs 96 irradiance values (15-min, local time)")
        spec["temp_C"] = r.temp_C if r.temp_C and len(r.temp_C) == 96 else [30.0]*96; spec["scenario"] = "web_csv_" + eb.spec_hash(r.irradiance_Wm2)
    else: raise HTTPException(422, "environment must be synthetic, nasa or csv")
    spec.pop("controller", None); return spec


@app.get("/api/health")
def health():
    return dict(status="ok", queue=_q.qsize(), engine_root=eb.ROOT, engine_reference="localflex-final-v1")


@app.get("/api/config")
def config():
    from config.feeder_config import CFG, SCENARIOS, INV
    return dict(controllers=eb.CONTROLLERS, synthetic_scenarios={k: v[2] for k, v in SCENARIOS.items()}, validated_homes=eb.VALIDATED_HOMES, limits=dict(v_lo=CFG["v_lo"], v_hi=CFG["v_hi"]),
                pv_penetration_range=[0, 100], defaults=dict(pv_penetration=40, pv_kw_per_home=3.0, battery_kwh=100, battery_kw=50, controller="D"), volt_watt_assumption=INV,
                limitations=LIMITATIONS, typical_run_minutes=4)


@app.get("/api/topology")
def topology(pv_penetration: float = 40, pv_kw_per_home: float = 3.0):
    return eb.topology(dict(pv_penetration=pv_penetration, pv_kw_per_home=pv_kw_per_home))


@app.post("/api/nasa")
def nasa(req: NasaReq):
    try: rec = nasa_mod.fetch(req.latitude, req.longitude, req.date, req.tz_offset_h)
    except nasa_mod.NasaError as e: raise HTTPException(502, str(e))
    return dict(**rec, **nasa_mod.preview(rec, req.pv_kw_per_home))


@app.post("/api/fleet")
def fleet(pv_penetration: float, pv_kw_per_home: float = 3.0):
    return eb.fleet(pv_penetration, pv_kw_per_home)


@app.post("/api/simulation", status_code=202)
def start(req: SimReq):
    spec = _resolve_spec(req); jid = eb.spec_hash(spec); d = _job_dir(jid)
    if os.path.exists(os.path.join(d, "result.json")): return dict(job_id=jid, cached=True, state="done")
    st = _status.get(jid) or (_read(os.path.join(d, "status.json")) if os.path.exists(os.path.join(d, "status.json")) else None)
    if st and st.get("state") in ("queued", "running"): return dict(job_id=jid, cached=False, state=st["state"])
    if _q.qsize() >= MAX_QUEUE: raise HTTPException(429, "simulation queue is full; try again in a few minutes")
    os.makedirs(d, exist_ok=True); _write(os.path.join(d, "spec.json"), spec); _set(jid, state="queued", progress=0.0, message="waiting for a free simulation slot", created=time.time(), queue_position=_q.qsize()); _q.put(jid)
    return dict(job_id=jid, cached=False, state="queued", selected_controller=req.controller)


def _find(jid):
    for base in (JOBS, DEMO):
        d = os.path.join(base, jid)
        if os.path.isdir(d): return d
    raise HTTPException(404, "unknown job")


@app.get("/api/simulation/{jid}/status")
def status(jid: str):
    d = _find(jid); p = os.path.join(d, "status.json"); st = _status.get(jid) or _read(p)
    if st.get("state") == "running" and st.get("started"): st = dict(st, elapsed_s=round(time.time()-st["started"], 0))
    return dict(job_id=jid, **{k: v for k, v in st.items() if k != "traceback"})


_cache: dict = {}
def _result(jid):
    d = _find(jid)
    if not os.path.exists(os.path.join(d, "result.json")): raise HTTPException(409, "simulation not finished")
    if jid not in _cache:
        if len(_cache) > 3: _cache.pop(next(iter(_cache)))
        _cache[jid] = dict(result=_read(os.path.join(d, "result.json")), spec=_read(os.path.join(d, "spec.json")))
    return _cache[jid]


@app.get("/api/simulation/{jid}/spec")
def spec_of(jid: str):
    s = _result(jid)["spec"]; return dict(spec=s, topology=eb.topology(s) if True else None, fleet=eb.fleet(s["pv_penetration"], s["pv_kw_per_home"]))


@app.get("/api/simulation/{jid}/series")
def series(jid: str, controller: str = "D"):
    """The full stored simulation of one controller (all steps), used by the UI for smooth slider/play-back. Every value comes from the run."""
    r = _result(jid)["result"]
    if controller not in r["cases"]: raise HTTPException(404, "controller not in this run")
    return r["cases"][controller]


@app.get("/api/simulation/{jid}/state")
def state(jid: str, timestep: int = Query(..., ge=0, le=127), controller: str = "D"):
    """Actual simulation state at one 15-min step (0 = 00:00 of the scored day; 96-127 = the next morning's tail)."""
    R = _result(jid); r = R["result"]; spec = R["spec"]
    if controller not in r["cases"]: raise HTTPException(404, "controller not in this run")
    topo = eb.topology(spec); out = {}
    for c in ("A", controller):
        cs = r["cases"][c]; k = timestep
        out[c] = dict(system={n: v[k] for n, v in cs["system"].items()},
                      buses={b: dict(voltage_pu=[cs["bus_voltage_pu"][b][p][k] for p in range(3)], neutral_V=cs["bus_neutral_V"][b][k], segment_current_A=[cs["segment_current_A"][topo["nodes"][b]["segment"]][p][k] for p in range(4)],
                                     segment_kW=cs["segment_kW"][topo["nodes"][b]["segment"]][k], segment_kvar=cs["segment_kvar"][topo["nodes"][b]["segment"]][k],
                                     flow_direction="import (towards the end of the feeder)" if cs["segment_kW"][topo["nodes"][b]["segment"]][k] >= 0 else "export (towards the transformer)",
                                     **{kk: vv[k] for kk, vv in cs["bus_resources"][b].items()}) for b in topo["nodes"]},
                      devices={n: v[k] for n, v in cs["devices"].items()})
    tr = r["cases"][controller].get("mpc_trace", {}).get(str(timestep))
    sup = [e for e in r["cases"][controller].get("supervisor_events", []) if e["k_start"] <= timestep <= e["k_end"]]
    return dict(timestep=timestep, time=f"{int(timestep*15//60) % 24:02d}:{timestep*15 % 60:02d}" + (" (+1 day)" if timestep >= 96 else ""), controller=controller, case_A_no_control=out["A"], selected=out[controller],
                mpc_decision=tr, mpc_voltage_prediction=r["cases"][controller].get("mpc_voltage_prediction", {}).get(str(timestep)),
                safety=dict(supervisor_events_active=sup, opendss_converged=r["cases"][controller]["converged"][timestep], opendss_gate_replaced_mpc_command=timestep in r["cases"][controller].get("validator_fallback_steps", [])))


@app.get("/api/simulation/{jid}/results")
def results(jid: str):
    R = _result(jid); r = R["result"]; return dict(spec=R["spec"], metrics=r["metrics"], burden=r["burden"], fleet=eb.fleet(R["spec"]["pv_penetration"], R["spec"]["pv_kw_per_home"]), limitations=LIMITATIONS)


@app.get("/api/demo")
def demo_list():
    out = []
    if os.path.isdir(DEMO):
        for jid in sorted(os.listdir(DEMO)):
            p = os.path.join(DEMO, jid, "demo.json")
            if os.path.exists(p): out.append(dict(job_id=jid, **_read(p)))
    return out


# ---------------------------------------------------------------- analysis / results section (existing LocalFlex outputs)
def _analysis_index():
    idx = {}
    if os.path.isdir(ANALYSIS):
        for p in sorted(glob.glob(os.path.join(ANALYSIS, "*"))):
            n, ext = os.path.splitext(os.path.basename(p))
            if ext in (".csv", ".json"): idx[n] = p
    return idx


@app.get("/api/analysis")
def analysis_list(): return sorted(_analysis_index())


@app.get("/api/analysis/{name}")
def analysis(name: str):
    p = _analysis_index().get(name)
    if not p: raise HTTPException(404, "unknown analysis table")
    if p.endswith(".json"): return _read(p)
    with open(p, newline="") as f: rows = list(csv.DictReader(f))
    for r in rows:
        for k, v in r.items():
            try: r[k] = float(v) if v not in ("", None) else None
            except ValueError: pass
    return rows


@app.get("/api/analysis-image/{name}")
def analysis_image(name: str):
    p = os.path.join(ANALYSIS, name)
    if not (name.endswith(".png") and os.path.isfile(p) and os.path.basename(p) == name): raise HTTPException(404)
    return FileResponse(p)


LIMITATIONS = [
    "All published A/B/C/D results use synthetic profiles; NASA POWER input is real data but is mapped to one uniform sky over the feeder and a synthetic demand profile.",
    "NASA POWER access is made by this backend; if the host has no outbound HTTPS the fetch fails and the UI says so.",
    "The PV model (NOCT 45 C, -0.4 %/K, derate 0.90) and the volt-watt curve (1.06 to 1.10 pu, 20 % at 1.10) are placeholders, not verified Indian-standard values.",
    "Cable and neutral parameters, voltage limits (0.94 to 1.06 pu) and all costs are assumptions. Protection, harmonics and unbalance limits are not modelled.",
    "Only one transformer with 100 homes is validated; PV penetration above 60 % has not been studied for stability of the voltage sensitivity model (R2 about 0.6).",
    "The MILP planner is limited to 1 s per plan, so results can differ slightly between runs. DISCOM caps are soft constraints and are not guaranteed.",
    "Fairness (case D) can trade EV charging service for equity between household groups.",
    "MPC voltage predictions use a linear sensitivity model; the OpenDSS value is the actual electrical result and the two are always shown separately.",
]
