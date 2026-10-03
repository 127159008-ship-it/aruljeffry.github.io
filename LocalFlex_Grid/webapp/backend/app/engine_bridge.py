"""Bridge between the web API and the frozen LocalFlex engine (OpenDSS + MPC + supervisor).
Nothing here re-implements physics or control: it only (1) turns a UI configuration into engine configuration overrides,
(2) runs the existing `run_stage10.task` pipeline for cases A/B/C/D, and (3) serialises the per-step results.
All numbers in the output come from OpenDSS solves or from the controllers' own logs."""
import os, sys, json, copy, hashlib, time
import numpy as np

ROOT = os.environ.get("LOCALFLEX_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "simulation")):
    if _p not in sys.path: sys.path.insert(0, _p)

PV_WEIGHTS = (22, 12, 6)           # baseline phase split of the 40 PV homes (frozen scenario choice, see parameter register)
VALIDATED_HOMES = 100
CONTROLLERS = {"A": "No control", "B": "Rules (Stage 7)", "C": "MPC (network-aware)", "D": "MPC + fairness"}


def pv_split(n_pv, caps):
    """Phase split of n_pv PV homes: proportional to the frozen 22/12/6 split (largest remainder), limited by the homes on each phase.
    n_pv = 40 reproduces the frozen baseline exactly."""
    n_pv = int(min(max(n_pv, 0), sum(caps)))
    if n_pv == 40 and all(c >= w for c, w in zip(caps, PV_WEIGHTS)): return tuple(PV_WEIGHTS)
    w = np.array(PV_WEIGHTS, float); out = [0, 0, 0]; left = n_pv
    while left > 0:
        room = [i for i in range(3) if out[i] < caps[i]]
        if not room: break
        share = {i: w[i] for i in room}; tot = sum(share.values())
        want = {i: share[i]/tot*left for i in room}; add = {i: min(int(np.floor(want[i])), caps[i]-out[i]) for i in room}
        for i in room: out[i] += add[i]
        left = n_pv - sum(out)
        if left > 0:
            rem = sorted(room, key=lambda i: -(want[i]-np.floor(want[i])))
            for i in rem:
                if left > 0 and out[i] < caps[i]: out[i] += 1; left -= 1
    return tuple(out)


def fleet(pv_penetration_pct, pv_kw_per_home, homes=VALIDATED_HOMES):
    from config.feeder_config import CFG, SEED
    from network.feeder_generator import build
    base = copy.deepcopy(CFG); m = build(base, SEED); caps = tuple(sum(1 for h in m["homes"] if h[1] == p) for p in (1, 2, 3))
    n_pv = int(round(pv_penetration_pct/100.0*homes)); split = pv_split(n_pv, caps)
    return dict(homes=homes, pv_penetration_requested_pct=pv_penetration_pct, pv_homes=int(sum(split)), pv_penetration_realised_pct=round(100.0*sum(split)/homes, 1), pv_by_phase=split,
                homes_by_phase=caps, pv_kw_per_home=pv_kw_per_home, pv_kwp=round(sum(split)*pv_kw_per_home, 2))


def topology(spec):
    """Real placement of every resource in the engine model for this configuration."""
    from config.feeder_config import CFG, DEVICES, SEED
    from network.feeder_generator import build
    f = fleet(spec["pv_penetration"], spec["pv_kw_per_home"]); cfg = copy.deepcopy(CFG); cfg["pv_by_phase"] = f["pv_by_phase"]; m = build(cfg, SEED)
    nodes = {}
    for fn, ns in CFG["feeders"].items():
        for pos, n in enumerate(ns):
            nodes[n] = dict(bus=n, feeder=fn, position=pos+1, homes=[0, 0, 0], pv_homes=[0, 0, 0], devices=[], segment=f"{fn}_{n}")
    for i, (n, p) in enumerate(m["homes"]):
        nodes[n]["homes"][p-1] += 1
        if i in m["pv"]: nodes[n]["pv_homes"][p-1] += 1
    dev = []
    for key, label in (("water_heater", "Water heater"), ("pump", "Pump / tank"), ("ev", "EV charging")):
        for gid, node, ph in DEVICES[key]["groups"]: nodes[node]["devices"].append(dict(id=gid, kind=label, phase="ABC"[ph-1])); dev.append(gid)
    b = DEVICES["battery"]; nodes[b["node"]]["devices"].append(dict(id="BATT", kind="Battery (shared)", phase="3-phase"))
    return dict(transformer=dict(kva=CFG["kva"], kv_hv=CFG["kv_hv"], kv_ll=CFG["kv_ll"]), feeders=CFG["feeders"], nodes=nodes, limits=dict(v_lo=CFG["v_lo"], v_hi=CFG["v_hi"], neutral_ampacity_a=CFG["neutral_ampacity_a"], phase_ampacity_a=CFG["ampacity_a"]),
                fleet=f, battery=dict(node=b["node"], e_kwh=b["e_kwh"], p_kw=b["p_kw"]), segment_km=CFG["seg_km"])


def make_hook():
    """Optional per-step recorder: kW/kvar into every feeder segment and kW of loads, devices and PV at every bus (read from the OpenDSS solution)."""
    from config.feeder_config import CFG
    segs = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]
    def hook(dss, k):
        out = {}
        for ln in segs:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); p = dss.CktElement.Powers(); out[f"P_{ln}_kW"] = float(sum(p[0:6:2])); out[f"Q_{ln}_kvar"] = float(sum(p[1:6:2]))
        acc = {}
        dss.Loads.First()
        while True:
            nm = dss.Loads.Name(); bus = dss.CktElement.BusNames()[0].split(".")[0]; pw = float(sum(dss.CktElement.Powers()[0::2]))
            key = f"{'DEV' if nm.startswith('dev_') else 'LD'}_{bus}_kW"; acc[key] = acc.get(key, 0.0) + pw
            if not dss.Loads.Next(): break
        dss.Generators.First()
        while True:
            bus = dss.CktElement.BusNames()[0].split(".")[0]; key = f"PV_{bus}_kW"; acc[key] = acc.get(key, 0.0) - float(sum(dss.CktElement.Powers()[0::2]))
            if not dss.Generators.Next(): break
        out.update(acc); return out
    return hook


def _r(x, n=4): return None if x is None else round(float(x), n)


def _case_payload(df, dv, trace, predlog, sup, fb, topo):
    nodes = list(topo["nodes"]); segs = [topo["nodes"][n]["segment"] for n in nodes]; n_steps = len(df)
    V = {n: [[_r(v, 4) for v in df[f"V_{n}_{p}_pu"]] for p in "ABC"] for n in nodes}; VN = {n: [_r(v, 3) for v in df[f"VN_{n}_V"]] for n in nodes}
    I = {s: [[_r(v, 2) for v in df[f"I_{s}_{p}_A"]] for p in "ABCN"] for s in segs}
    P = {s: [_r(v, 2) for v in df[f"P_{s}_kW"]] for s in segs}; Q = {s: [_r(v, 2) for v in df[f"Q_{s}_kvar"]] for s in segs}
    res = {n: dict(load_kW=[_r(v, 2) for v in df.get(f"LD_{n}_kW", [0]*n_steps)], device_kW=[_r(v, 2) for v in df.get(f"DEV_{n}_kW", [0]*n_steps)], pv_kW=[_r(v, 2) for v in df.get(f"PV_{n}_kW", [0]*n_steps)]) for n in nodes}
    dev = {c: [_r(v, 3) for v in dv[c]] for c in dv.columns if c not in ("hour", "t_h")}
    out = dict(n_steps=n_steps, hour=[_r(v, 2) for v in df["t_h"]], bus_voltage_pu=V, bus_neutral_V=VN, segment_current_A=I, segment_kW=P, segment_kvar=Q, bus_resources=res, devices=dev,
               system={k: [_r(v, 3) for v in df[c]] for k, c in dict(pv_available_kW="pv_avail_kW", pv_delivered_kW="pv_kW", pv_curtailed_kW="pv_curtailed_kW", demand_kW="demand_kW", base_demand_kW="base_demand_kW", device_demand_kW="device_kW",
                                                                      transformer_kW="trafo_kW", transformer_kVA="trafo_kVA", transformer_loading_pct="trafo_loading_pct", losses_kW="losses_kW").items()},
               converged=[bool(v) for v in df["converged"]])
    if trace is not None:
        tr = {}
        for t in trace:
            k = int(t["abs_step"]) - 96; vf = t["V_forecast_no_action"]; v_hi, v_lo = topo["limits"]["v_hi"], topo["limits"]["v_lo"]
            t = dict(t); t["problem_active"] = bool(vf > v_hi or vf < v_lo); t["limit_pu"] = v_hi if t["constraint"] == "overvoltage" else v_lo; tr[k] = t
        out["mpc_trace"] = tr
    if predlog is not None: out["mpc_voltage_prediction"] = {int(a)-96: dict(predicted=[_r(x, 4) for x in vp], forecast_no_action=[_r(x, 4) for x in vb]) for a, k, vp, vb in predlog}
    out["supervisor_events"] = sup or []; out["validator_fallback_steps"] = sorted(set(int(x) for x in (fb or [])))
    return out


def worker(args):
    """Runs in a worker process. args = (spec_json, case_names)."""
    spec, names = args
    import run_stage6 as r6, run_stage10 as r10
    from final.environment import register_scenario
    from final.overrides import overrides
    from config.feeder_config import SCENARIOS
    r6.STEP_HOOK = make_hook(); r10.TRACE_ALL = True; r10.KEEP_ALL = True
    f = fleet(spec["pv_penetration"], spec["pv_kw_per_home"]); scn = spec["scenario"]
    if spec["environment"] != "synthetic": register_scenario(scn, np.array(spec["irradiance_Wm2"]), np.array(spec["temp_C"]), demand_scale=spec.get("demand_scale", 1.0))
    PVM = dict(spec.get("pv_model", {}))
    if PVM and spec["environment"] != "synthetic":
        from final import environment as env
        m = dict(env.PVM); m.update(PVM); m["rated_kw"] = spec["pv_kw_per_home"]; env.register(scn, np.array(spec["irradiance_Wm2"]), np.array(spec["temp_C"]), m)
    cfgo = dict(pv_by_phase=f["pv_by_phase"], pv_kw=spec["pv_kw_per_home"]); bat = dict(e_kwh=spec["battery_kwh"], p_kw=spec["battery_kw"])
    extra = {n: dict(supervise=True) for n in names if n in ("C", "D")}
    t0 = time.time()
    with overrides(cfg=cfgo, battery=bat):
        topo = topology(spec)
        rows, brows, keep, logs = r10.task((scn, 7, names, extra))
    out = dict(cases={}, metrics={}, seconds=round(time.time()-t0, 1))
    for r in rows: out["metrics"][r["variant"]] = {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v)) for k, v in r.items()}
    for n in names:
        df, dv = keep[(scn, n)]
        out["cases"][n] = _case_payload(df, dv, logs.get(n+"_trace"), logs.get(n+"_predlog"), logs.get(n+"_sup"), logs.get(n+"_fb"), topo)
    out["burden"] = brows.to_dict("records") if len(brows) else []
    return json.loads(json.dumps(out, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def spec_hash(spec):
    s = json.dumps(spec, sort_keys=True, default=str); return hashlib.sha1(s.encode()).hexdigest()[:12]
