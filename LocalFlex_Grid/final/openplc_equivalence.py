"""Equivalence test: Python RuleController (Stage 7) vs the IEC 61131-3 Structured Text in openplc/localflex_rules.st, compiled to C with the matiec ST compiler
(the compiler OpenPLC uses) and called through ctypes. Random test vectors; vectors within 1e-4 of a threshold are excluded (ST REAL is 32-bit float).
This shows logic equivalence of the compiled ST with the Python rules. It is NOT a hardware deployment and not an OpenPLC-runtime/Modbus test."""
import sys, os, ctypes, json, copy
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from config.feeder_config import DEVICES
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
from control.rule_based import RuleController, RULES
lib = ctypes.CDLL(os.path.join(ROOT, "openplc", "liblocalflex_rules.so"))
for f, n in (("wh_rule", 3), ("pump_rule", 3), ("ev_rule", 4), ("batt_rule", 4)): getattr(lib, f).restype = ctypes.c_float; getattr(lib, f).argtypes = [ctypes.c_float]*n
TH_V = [1.04, 1.07, 0.96, 0.95]; TH_H = [6.0, 17.0, 18.0, 21.0, 22.0, 23.0]
def near(x, ths, eps=1e-4): return any(abs(x-t) < eps for t in ths)
def main(N=20000, seed=3):
    rng = np.random.default_rng(seed); R = RuleController(); res = {}; D = DEVICES; skipped = 0
    for name in ("WH", "PUMP", "EV", "BATT"): res[name] = dict(n=0, mismatches=0, max_abs_diff=0.0)
    for _ in range(N):
        k = int(rng.integers(0, 96)); h = k*0.25; v = float(rng.uniform(0.84, 1.12)); last = {f"V_a4_{p}_pu": float(rng.uniform(0.84, 1.12)) for p in "ABC"}; last["V_a2_C_pu"] = v
        # --- water heater
        g = WaterHeaterGroup("WH", "a2", 3, D["water_heater"]); g.T = float(rng.uniform(40, 66))
        if not (near(v, TH_V) or near(g.T, [50.0])):
            c = R.act(k, [g], last).get("WH", -1.0); s = lib.wh_rule(v, h, g.T); d = abs(c-s); r = res["WH"]; r["n"] += 1; r["max_abs_diff"] = max(r["max_abs_diff"], d); r["mismatches"] += int(d > 1e-4)
        else: skipped += 1
        # --- pump
        p = PumpTank("PUMP", "a2", 3, D["pump"]); p.level = float(rng.uniform(0, 1))*p.V; lvl = p.level/p.V
        if not (near(v, TH_V) or near(lvl, [0.25, 0.90])):
            c = R.act(k, [p], last).get("PUMP", -1.0); s = lib.pump_rule(v, h, lvl); d = abs(c-s); r = res["PUMP"]; r["n"] += 1; r["max_abs_diff"] = max(r["max_abs_diff"], d); r["mismatches"] += int(d > 1e-4)
        else: skipped += 1
        # --- EV (caller-side aggregation of session urgency, copied from the Python rule loop)
        e = EVGroup("EV", "a2", 3, D["ev"], seed=int(rng.integers(1, 1000)))
        e.remA = rng.uniform(0, 4, len(e.arr))*(rng.random(len(e.arr)) < 0.6); e.remB = e.need*(rng.random(len(e.arr)) < 0.7); e.departedA[:] = rng.random(len(e.arr)) < 0.2
        tot = urg = 0.0
        for i in range(len(e.arr)):
            if (h < e.dep[i]) and (not e.departedA[i]) and e.remA[i] > 1e-12:
                tot += e.pmax[i]
                if e.remA[i]/(e.pmax[i]*e.eta) + RULES["ev_margin_h"] >= e.dep[i]-h: urg += e.pmax[i]
            if h >= e.arr[i] and e.remB[i] > 1e-12:
                tot += e.pmax[i]
                if e.remB[i]/(e.pmax[i]*e.eta) + RULES["ev_margin_h"] >= e.dep[i]+24.0-h: urg += e.pmax[i]
        if not near(v, TH_V):
            c = R.act(k, [e], last)["EV"]; s = lib.ev_rule(v, h, tot, urg); d = abs(c-s); r = res["EV"]; r["n"] += 1; r["max_abs_diff"] = max(r["max_abs_diff"], d); r["mismatches"] += int(d > 1e-4)
        else: skipped += 1
        # --- battery
        b = SharedBattery(D["battery"]); vs = [last[f"V_a4_{q}_pu"] for q in "ABC"]
        if not (near(max(vs), TH_V) or near(min(vs), TH_V)):
            c = R.act(k, [b], last)["BATT"]; s = lib.batt_rule(max(vs), min(vs), h, b.P["p_kw"]); d = abs(c-s); r = res["BATT"]; r["n"] += 1; r["max_abs_diff"] = max(r["max_abs_diff"], d); r["mismatches"] += int(d > 2e-3)    # kW scale, float32
        else: skipped += 1
    ok = all(v["mismatches"] == 0 and v["n"] > 1000 for v in res.values()); out = dict(vectors_per_block=N, skipped_near_threshold=skipped, blocks=res, pass_=ok, compiler="matiec iec2c (OpenPLC ST->C), gcc", scope="per-group rule logic; not hardware")
    json.dump(out, open(os.path.join(ROOT, "results", "final_openplc_equivalence.json"), "w"), indent=1); print(json.dumps(out, indent=1)); return ok
if __name__ == "__main__": main()
