"""Stage 9 offline sensitivity builder: H[i,j] = dV_i / dP_j from OpenDSS perturbations at a frozen reference state.
i = monitored node/phase (phase-to-neutral voltage, pu); j = controllable resource group at its ACTUAL bus/phase (battery = balanced 3-phase, per kW of TOTAL power)."""
import sys, os
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
import opendssdirect as dss
from config.feeder_config import CFG, SEED, DEVICES, DEVICE_SEED
from network.feeder_generator import build, write_dss_4wire
from profiles.scenarios import household_profiles, pv_availability
from devices.resources import make_all
from run_stage3 import vpn, VB
from run_stage6 import device_lines
R = os.path.join(ROOT, "results")
LIVE_REF = False      # study overrides (changed network/devices) compute the reference natural state live instead of reading the frozen Stage 6 CSVs
DP_KW = 1.0           # perturbation per single-phase group; battery perturbed by 3*DP_KW total (1 kW per phase), reported per kW of total power
def monitored(m): return [(n, p) for n in m["nodes"] for p in "ABC"]
def resource_list(): return [(g.id, getattr(g, "node", None), getattr(g, "phase", None)) for g in make_all(DEVICES, DEVICE_SEED)]
def _load_ref_state(m, ref_step, scenario="clear", seed=7):
    """Reference operating point = the Stage 6 natural (A1) state of the given scenario at ref_step (demand, device powers, delivered PV share)."""
    from config.feeder_config import SCENARIOS
    ds, sm, _ = SCENARIOS[scenario]; pvn = [m["homes"][i][0] for i in m["pv"]]; dem = household_profiles(m["scale"], seed, ds); pv = pv_availability(sm, seed, pvn)
    if LIVE_REF:
        from run_stage6 import simulate6
        from devices.resources import warm_start
        ts, dv, *_ = simulate6("A1", m, dem, pv, warm_start(make_all(DEVICES, DEVICE_SEED)))
    else: ts = pd.read_csv(os.path.join(R, f"stage6_{scenario}_A1_baseline_timeseries.csv")); dv = pd.read_csv(os.path.join(R, f"stage6_{scenario}_A1_device_states.csv"))
    ratio = float(ts.pv_kW[ref_step]/ts.pv_avail_kW[ref_step]) if ts.pv_avail_kW[ref_step] > 0 else 1.0
    return dem[ref_step], pv[ref_step]*ratio, {c[2:-3]: float(dv[c][ref_step]) for c in dv if c.startswith("P_")}, float(dv.hour[ref_step])
def build_H(m, ref_step, scenario="clear", seed=7, dp=DP_KW):
    base = os.path.join(ROOT, "network", f"_sens_base_{os.getpid()}.dss"); write_dss_4wire(CFG, m, base)
    lines = open(base).read().splitlines(); idx = [i for i, l in enumerate(lines) if l.startswith("set voltagebases")][0]
    path = os.path.join(ROOT, "network", f"_sens_{os.getpid()}.dss"); open(path, "w").write("\n".join(lines[:idx] + device_lines() + lines[idx:]) + "\n")
    dem_k, pv_k, devP, hour = _load_ref_state(m, ref_step, scenario, seed); mon = monitored(m); res = resource_list()
    dss.Command("clear"); dss.Command(f"redirect {path}")
    def setall(extra=None):
        dss.Loads.First()
        while True:
            nm = dss.Loads.Name()
            if nm.startswith("dev_"):
                gid = nm[4:].upper() if nm[4:].upper() in devP else nm[4:]; dss.Loads.kW(float(devP[gid] + (extra or {}).get(gid, 0.0)))
            else: dss.Loads.kW(float(dem_k[int(nm[1:])]))
            if not dss.Loads.Next(): break
        for j, i in enumerate(m["pv"]): dss.Generators.Name(f"pv{i}"); dss.Generators.kW(float(pv_k[j]))
        dss.Solution.Solve(); assert dss.Solution.Converged()
        out = []
        for n, p in mon: z = vpn(n); out.append(abs(z["ABC".index(p)+1] - z[4])/VB)
        return np.array(out)
    V0 = setall(); H = np.zeros((len(mon), len(res)))
    for j, (gid, node, ph) in enumerate(res):
        d = 3*dp if gid == "BATT" else dp; H[:, j] = (setall({gid: d}) - V0)/d
    setall()                                                       # restore base point
    return dict(solve=setall, H=H, V0=V0, monitored=mon, resources=res, dp_kw=dp, ref_step=ref_step, ref_hour=hour, scenario=scenario, seed=seed)
if __name__ == "__main__":
    m = build(CFG, SEED)
    for nm, k in (("midday", 48), ("evening", 76)):
        S = build_H(m, k); df = pd.DataFrame(S["H"], index=[f"{n}/{p}" for n, p in S["monitored"]], columns=[f"{g}@{n}/{p}" if n else g for g, n, p in S["resources"]]); df.to_csv(os.path.join(R, f"stage9_H_{nm}.csv"))
        print(nm, "ref hour", S["ref_hour"], "H shape", S["H"].shape, "min/max (pu per kW):", S["H"].min().round(5), S["H"].max().round(5)); print(df.loc[["a5/A", "b5/A", "a5/B", "a5/C", "b5/C"]].round(5).to_string())
