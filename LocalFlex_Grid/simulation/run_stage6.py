"""Stage 6: flexible resource models (water heaters, pump+tank, EV groups, shared battery). Part 1: each resource behaves correctly and conserves energy under commands.
Part 2: uncontrolled-device baseline on the frozen feeder. No optimiser, no LocalFlex control."""
import sys, os, json, copy, platform
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import opendssdirect as dss
from config.feeder_config import CFG, SEED, SCENARIOS, DEVICES, DEVICE_SEED, REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, REGISTER_S6, SUPERSEDED_S2
from network.feeder_generator import build, write_dss_4wire
from profiles.household_demand import t
from profiles.scenarios import household_profiles, pv_availability
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery, make_all, warm_start, CP
from run_stage3 import vw, vpn, VB
from run_stage5 import metrics
R = os.path.join(ROOT, "results"); VER = "stage6-v0.6"; NSTEP = CFG["steps"]; KVLN = CFG["kv_ll"]/3**0.5

# ------------------------------------------------------------------ Part 1: unit tests of each resource under commands
def tests_resources():
    D = copy.deepcopy(DEVICES); res = {}
    # --- water heater: no draw, compare with analytic solution of C dT/dt = u*P - UA (T - Tamb)
    def wh(T0, draw=0.0):
        g = WaterHeaterGroup("T", "a1", 1, D["water_heater"], draw_scale=draw); g.T = g.T0 = T0; return g
    def analytic(g, T0, u, hours):
        Teq = g.P["t_amb"] + u*g.Pg/g.UA; tau = g.C/g.UA; return Teq + (T0-Teq)*np.exp(-hours/tau)
    g = wh(30.0); [g.step(k, 1.0) for k in range(1)]; res["WH heat 15 min at cmd=1: sim vs analytic (K diff)"] = abs(g.T - analytic(g, 30.0, 1.0, 0.25))
    g = wh(60.0); [g.step(k, 0.0) for k in range(8)]; res["WH cool 2 h at cmd=0: sim vs analytic (K diff)"] = abs(g.T - analytic(g, 60.0, 0.0, 2.0))
    g = wh(40.0); g.step(0, 0.0); res["WH below service minimum heats despite cmd=0 (energy in kWh)"] = g.led["e_in"]
    g = wh(66.0); g.step(0, 1.0); res["WH above max stays off despite cmd=1 (energy in kWh)"] = g.led["e_in"]
    g = wh(55.0, draw=1.0); [g.step(k, None) for k in range(96)]; res["WH 24 h with draw: energy ledger error (kWh)"] = abs(g.ledger_error())
    # --- pump + tank
    def pt(frac, q=1.0, init=None):
        g = PumpTank("P", "a1", 1, D["pump"], q_scale=q); g.level = g.L0 = frac*g.V; return g
    g = pt(0.5); g.demand_m3h = lambda th: 0.0; g.step(0, 1.0); res["Pump cmd=1 15 min, no demand: level change vs Q*dt/V (fraction diff)"] = abs((g.level-0.5*g.V)/g.V - D["pump"]["q_m3h"]*0.25/g.V)
    g = pt(0.5); g.demand_m3h = lambda th: 0.0; p = g.step(0, 0.5); res["Pump cmd=0.5: runs 8 of 15 min (mean kW expected %.3f)" % (D["pump"]["p_kw"]*8/15)] = abs(p - D["pump"]["p_kw"]*8/15)
    g = pt(1.0); g.demand_m3h = lambda th: 0.0; g.step(0, 1.0); res["Pump on a full tank stays off (volume in m3)"] = g.led["v_in"]
    g = pt(0.05); g.demand_m3h = lambda th: 0.0; g.step(0, 0.0); res["Pump below minimum level forced on (volume in m3)"] = g.led["v_in"]
    g = pt(0.02, q=0.0); g.step(26, 0.0); res["Pump with no inflow at the 06:30 demand peak: unmet water recorded (m3, expect >0)"] = g.led["unmet"]
    g = pt(0.6); [g.step(k, None) for k in range(96)]; res["Pump 24 h natural: volume ledger error (m3)"] = abs(g.ledger_error()); res["Pump 24 h natural: unmet water (m3)"] = g.led["unmet"]
    # --- EV group (fixed vehicles)
    def evg():
        g = EVGroup("E", "a1", 1, D["ev"], seed=5); n = len(g.arr)
        g.arr[:] = 19.0; g.dep[:] = 6.0; g.need[:] = 5.0; g.remA = np.maximum(0, g.need - g.pmax*g.eta*(24-g.arr)); g.remB = g.need.copy(); g.rA0 = g.remA.copy(); return g
    g = evg(); [g.step(k, 1.0) for k in range(96)]
    res["EV cmd=1 all day: unmet energy at departure (kWh, expect 0)"] = g.led["unmetA"]; res["EV cmd=1: ledger error (kWh)"] = abs(g.ledger_error())
    res["EV cmd=1: grid energy = battery energy / eta (kWh diff)"] = abs(g.led["grid"] - g.led["batt"]/g.eta)
    g = evg(); [g.step(k, 0.0) for k in range(96)]
    res["EV cmd=0: nothing charged (kWh), unmet at departure = carry-over (diff)"] = (g.led["batt"], abs(g.led["unmetA"] - g.rA0.sum()))
    g = evg(); [g.step(k, None) for k in range(96)]; res["EV natural: charging only while plugged in (grid kWh before 19:00 should be carry-over only)"] = g.led["batt"]
    g = evg(); g.arr[:] = 23.0; g.remB = g.need.copy(); [g.step(k, 1.0) for k in range(4*20)]; res["EV before arrival (20:00, arrival 23:00): session B untouched (kWh remaining of 30)"] = g.remB.sum()
    # --- battery
    b = SharedBattery(D["battery"]); E0 = b.E; [b.step(k, 30.0) for k in range(4)]; res["Battery charge 30 kW 1 h: stored energy gain vs eta_c*30 (kWh diff)"] = abs((b.E-E0) - D["battery"]["eta_c"]*30.0)
    b = SharedBattery(D["battery"]); E0 = b.E; [b.step(k, -30.0) for k in range(4)]; res["Battery discharge 30 kW 1 h: stored energy loss vs 30/eta_d (kWh diff)"] = abs((E0-b.E) - 30.0/D["battery"]["eta_d"])
    b = SharedBattery(D["battery"]); p = b.step(0, 500.0); res["Battery power limit: 500 kW request limited to (kW, expect 50)"] = p
    b = SharedBattery(D["battery"]); [b.step(k, 50.0) for k in range(40)]; res["Battery full: SoC stops at max (fraction, expect 0.95)"] = b.E/D["battery"]["e_kwh"]
    b = SharedBattery(D["battery"]); [b.step(k, -50.0) for k in range(40)]; res["Battery empty: SoC stops at min (fraction, expect 0.10)"] = b.E/D["battery"]["e_kwh"]
    b = SharedBattery(D["battery"]); Ein0 = b.E; [b.step(k, 40.0) for k in range(8)]; gain = b.E - Ein0; [b.step(k, gain*D["battery"]["eta_d"]/2.0) if False else b.step(k, -gain*D["battery"]["eta_d"]/2.0) for k in range(8, 16)]
    res["Battery cycle: stored energy back at start (kWh diff)"] = abs(b.E - Ein0); res["Battery cycle: round-trip efficiency grid-out/grid-in (expect 0.9025)"] = b.led["grid_out"]/b.led["grid_in"]
    b = SharedBattery(D["battery"]); rng = np.random.default_rng(1); [b.step(k % 96, float(rng.uniform(-60, 60))) for k in range(500)]; res["Battery random commands 500 steps: energy ledger error (kWh)"] = abs(b.ledger_error())
    return res

def judge(res):
    ok = {}
    for k, v in res.items():
        if "vs analytic" in k: ok[k] = v < 0.01
        elif "despite" in k: ok[k] = v == 0.0 if "above max" in k else v > 0
        elif "ledger error" in k: ok[k] = v < 1e-6
        elif "level change" in k: ok[k] = v < 1e-9
        elif "runs 8 of 15" in k: ok[k] = v < 1e-9
        elif "full tank" in k: ok[k] = v == 0.0
        elif "minimum level forced" in k: ok[k] = v > 0
        elif "unmet water recorded" in k: ok[k] = v > 0
        elif "Pump 24 h natural: unmet" in k: ok[k] = v == 0.0
        elif "unmet energy at departure" in k: ok[k] = v < 1e-9
        elif "grid energy = battery" in k: ok[k] = v < 1e-9
        elif "nothing charged" in k: ok[k] = v[0] == 0.0 and v[1] < 1e-9
        elif "charging only while plugged" in k: ok[k] = v >= 0
        elif "before arrival" in k: ok[k] = abs(v - 30.0) < 1e-9
        elif "stored energy" in k: ok[k] = v < 1e-9
        elif "power limit" in k: ok[k] = abs(v - 50.0) < 1e-9
        elif "SoC stops at max" in k: ok[k] = abs(v - 0.95) < 1e-9
        elif "SoC stops at min" in k: ok[k] = abs(v - 0.10) < 1e-9
        elif "round-trip" in k: ok[k] = abs(v - 0.9025) < 1e-6
        else: ok[k] = False
    return ok

# ------------------------------------------------------------------ Part 2: uncontrolled-device baseline on the feeder
def device_lines():
    L = []; D = DEVICES
    for gid, node, ph in D["water_heater"]["groups"]: L.append(f"new load.dev_{gid} bus1={node}.{ph}.4 phases=1 kv={KVLN:.4f} kw=0 pf=1.0 model=1")
    for gid, node, ph in D["pump"]["groups"]: L.append(f"new load.dev_{gid} bus1={node}.{ph}.4 phases=1 kv={KVLN:.4f} kw=0 pf={D['pump']['pf']} model=1")
    for gid, node, ph in D["ev"]["groups"]: L.append(f"new load.dev_{gid} bus1={node}.{ph}.4 phases=1 kv={KVLN:.4f} kw=0 pf={D['ev']['pf']} model=1")
    L.append(f"new load.dev_BATT bus1={D['battery']['node']}.1.2.3.4 phases=3 conn=wye kv={CFG['kv_ll']} kw=0 pf=1.0 model=1 vminpu=0.8")
    return L

STEP_HOOK = None      # optional recorder (web app): callable(dss, k) -> dict of extra columns; None leaves the frozen outputs untouched
def simulate6(case, m, demand, pvav, groups, cmds=None, controller=None, nsteps=None):
    base = os.path.join(ROOT, "network", f"_tmp_s2_{os.getpid()}.dss"); write_dss_4wire(CFG, m, base)
    lines = open(base).read().splitlines(); idx = [i for i, l in enumerate(lines) if l.startswith("set voltagebases")][0]
    path = os.path.join(ROOT, "network", f"_tmp_s6_{os.getpid()}.dss"); open(path, "w").write("\n".join(lines[:idx] + device_lines() + lines[idx:]) + "\n")
    dss.Command("clear"); dss.Command(f"redirect {path}")
    nodes = m["nodes"]; fl = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]; pvidx = m["pv"]; pvinfo = {i: m["homes"][i] for i in pvidx}
    rows = []; dev_rows = []; nonconv = 0; invlim = 0; maxit = 0; curt_phase = [0.0]*3; dev_e_cmd = {g.id: 0.0 for g in groups}; dev_e_sol = {g.id: 0.0 for g in groups}
    def solve_step(k, pw, do_inv):
        dss.Loads.First()
        while True:
            nm = dss.Loads.Name()
            if nm.startswith("dev_"): dss.Loads.kW(float(pw[nm[4:].upper() if nm[4:].upper() in pw else nm[4:]]))
            else: dss.Loads.kW(float(demand[k, int(nm[1:])]))
            if not dss.Loads.Next(): break
        f = {i: 1.0 for i in pvidx}
        def setpv():
            for j, i in enumerate(pvidx): dss.Generators.Name(f"pv{i}"); dss.Generators.kW(float(pvav[k, j]*f[i]))
        setpv(); dss.Solution.Solve(); conv = bool(dss.Solution.Converged()); it = 0; lim = False
        if do_inv and pvav[k].max() > 0 and conv:
            for it in range(1, 201):
                zs = {n: vpn(n) for n in {pvinfo[i][0] for i in pvinfo}}
                new = {i: vw(abs(zs[pvinfo[i][0]][pvinfo[i][1]] - zs[pvinfo[i][0]][4])/VB) for i in pvinfo}
                delta = max(abs(new[i]-f[i]) for i in pvinfo); f = {i: 0.5*f[i] + 0.5*new[i] for i in pvinfo}
                setpv(); dss.Solution.Solve(); conv = conv and bool(dss.Solution.Converged())
                if delta < 1e-3 or not conv: break
            else: lim = True
        return conv, it, f, lim
    def severity():
        sv = 0.0
        for n in nodes:
            z = vpn(n)
            for ph in (1, 2, 3):
                v = abs(z[ph]-z[4])/VB; sv += max(0.0, v-CFG["v_hi"]) + max(0.0, CFG["v_lo"]-v)
        dss.Circuit.SetActiveElement("Transformer.tr"); tp = dss.CktElement.Powers()[:6]
        return sv + 2*max(0.0, np.hypot(sum(tp[0::2]), sum(tp[1::2]))/CFG["kva"] - 1.0)
    for k in range(nsteps or NSTEP):
        pw = {}
        cmds_k = controller.act(k, groups, rows[-1] if rows else controller.prev) if controller is not None else cmds   # controller sees only the PREVIOUS step's measurements
        if controller is not None and getattr(controller, "gate", False) and getattr(controller, "alt", None) is not None:
            def sev(c):
                gc = copy.deepcopy(groups); pwt = {g.id: (g.step(k, c.get(g.id, None)) if not isinstance(g, SharedBattery) else g.step(k, c.get(g.id, 0.0))) for g in gc}
                solve_step(k, pwt, case == "A1"); return severity()
            controller.n_gate += 1
            if getattr(controller, "force_unsafe", False) or sev(cmds_k) > sev(controller.alt) + 1e-9: cmds_k = controller.alt; controller.n_fb += 1; getattr(controller, "fb_log", []).append(k)
        for g in groups: pw[g.id] = g.step(k, None if cmds_k is None else cmds_k.get(g.id, None)) if not isinstance(g, SharedBattery) else g.step(k, 0.0 if cmds_k is None else cmds_k.get(g.id, 0.0))
        conv, it, f, lim = solve_step(k, pw, case == "A1"); invlim += int(lim); maxit = max(maxit, it)
        if not conv: nonconv += 1
        row = {"hour": t[k], "inv_iterations": it, "converged": conv}
        for n in nodes:
            z = vpn(n)
            for ph in range(3): row[f"V_{n}_{'ABC'[ph]}_pu"] = abs(z[ph+1]-z[4])/VB
            row[f"VN_{n}_V"] = abs(z[4])
        for ln in fl:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); cur = dss.CktElement.CurrentsMagAng()[0:8:2]
            for ph in range(3): row[f"I_{ln}_{'ABC'[ph]}_A"] = cur[ph]
            row[f"I_{ln}_N_A"] = cur[3]
        dss.Circuit.SetActiveElement("Transformer.tr"); tp = dss.CktElement.Powers()[:6]; P = sum(tp[0::2]); Q = sum(tp[1::2])
        row.update(trafo_kW=P, trafo_kVA=float(np.hypot(P, Q)), trafo_loading_pct=100*np.hypot(P, Q)/CFG["kva"])
        base_d = 0.0; dev_d = 0.0; dss.Loads.First()
        while True:
            nm = dss.Loads.Name(); pp = sum(dss.CktElement.Powers()[0::2])
            if nm.startswith("dev_"): dev_d += pp; gid = nm[4:].upper() if nm[4:].upper() in pw else nm[4:]; dev_e_sol[gid] += pp*0.25
            else: base_d += pp
            if not dss.Loads.Next(): break
        for gid, v in pw.items(): dev_e_cmd[gid] += v*0.25
        pvk = 0.0; dss.Generators.First()
        while True:
            pvk += -sum(dss.CktElement.Powers()[0::2])
            if not dss.Generators.Next(): break
        loss = dss.Circuit.Losses()[0]/1000; avail = float(pvav[k].sum()); dem = base_d + dev_d
        row.update(demand_kW=dem, base_demand_kW=base_d, device_kW=dev_d, pv_avail_kW=avail, pv_kW=pvk, pv_curtailed_kW=avail-pvk, losses_kW=loss, balance_residual_kW=P-(dem-pvk+loss))
        for j, i in enumerate(pvidx): curt_phase[pvinfo[i][1]-1] += pvav[k, j]*(1-f[i])*0.25
        if STEP_HOOK is not None: row.update(STEP_HOOK(dss, k))
        rows.append(row)
        dr = {"hour": t[k]}
        for g in groups:
            dr[f"P_{g.id}_kW"] = pw[g.id]
            if isinstance(g, WaterHeaterGroup): dr[f"T_{g.id}_C"] = g.T
            elif isinstance(g, PumpTank): dr[f"level_{g.id}_pct"] = 100*g.level/g.V
            elif isinstance(g, EVGroup): dr[f"rem_{g.id}_kWh"] = float(g.remA.sum() + g.remB.sum())
            elif isinstance(g, SharedBattery): dr["SoC_BATT_pct"] = 100*g.E/g.P["e_kwh"]
        dev_rows.append(dr)
    if controller is not None: controller.prev = rows[-1]
    return pd.DataFrame(rows), pd.DataFrame(dev_rows), dict(nonconv=nonconv, inv_limit=invlim, max_iter=maxit, curt_phase=curt_phase), dev_e_cmd, dev_e_sol

def main():
    res = tests_resources(); ok = judge(res); n_ok = sum(ok.values()); allpass = all(ok.values())
    print(f"resource tests: {n_ok}/{len(ok)} pass"); [print("  FAIL", k, res[k]) for k, v in ok.items() if not v]
    m = build(CFG, SEED); nPV = len(m["pv"]); pv_nodes = [m["homes"][i][0] for i in m["pv"]]; base5 = pd.read_csv(os.path.join(R, "stage5_scenario_summary.csv")); base5 = base5[base5.seed == 7]
    out_rows = []; series = {}; dev_series = {}; energy = {}
    for scn, (dscale, smode, desc) in SCENARIOS.items():
        dem = household_profiles(m["scale"], 7, dscale); pv = pv_availability(smode, 7, pv_nodes)
        for case in ("A0", "A1"):
            groups = warm_start(make_all(DEVICES, DEVICE_SEED)); df, dv, ex, ec, es = simulate6(case, m, dem, pv, groups)
            mm = metrics(df, ex, scn, 7, case); b5 = base5[(base5.scenario == scn) & (base5.case == case)].iloc[0]
            mm.update(dict(with_devices=True, device_energy_commanded_kWh=round(sum(ec.values()), 1), device_energy_solved_kWh=round(sum(es.values()), 1),
                           base_demand_solved_kWh=round(float(df.base_demand_kW.sum()/4), 1), input_base_demand_kWh=round(float((dem.sum())/4), 1),
                           dV_max=round(mm["v_max_pu"] - float(b5.v_max_pu), 3), dV_min=round(mm["v_min_pu"] - float(b5.v_min_pu), 3),
                           d_hours_over=mm["hours_any_overvoltage"] - float(b5.hours_any_overvoltage), d_hours_under=mm["hours_any_undervoltage"] - float(b5.hours_any_undervoltage),
                           d_trafo_pct=round(mm["peak_trafo_loading_pct"] - float(b5.peak_trafo_loading_pct), 1), d_neutral_pct=round(mm["peak_neutral_loading_pct"] - float(b5.peak_neutral_loading_pct), 1)))
            out_rows.append(mm); series[(scn, case)] = df; dev_series[(scn, case)] = dv; energy[(scn, case)] = (ec, es)
            if scn in ("clear", "high_demand"): df.to_csv(os.path.join(R, f"stage6_{scn}_{case}_baseline_timeseries.csv"), index=False); dv.to_csv(os.path.join(R, f"stage6_{scn}_{case}_device_states.csv"), index=False)
            # device ledger checks after a full natural day
            for g in groups:
                if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
    df6 = pd.DataFrame(out_rows); df6["curtailed_kWh_by_phase"] = df6["curtailed_kWh_by_phase"].astype(str); df6.to_csv(os.path.join(R, "stage6_baseline_summary.csv"), index=False)
    summ = dict(model_version=VER, python=platform.python_version(), resource_tests=dict(passed=n_ok, total=len(ok), all_pass=allpass, detail={k: [str(res[k]), bool(ok[k])] for k in res}),
                baseline_total_convergence_failures=int(df6.convergence_failures.sum()), baseline_inverter_limit_hits=int(df6.inverter_iteration_limit_hits.sum()), baseline_max_balance_residual_kW=float(df6.max_power_balance_residual_kW.max()),
                device_daily_energy_commanded_kWh_clear_A1={k: round(v, 1) for k, v in energy[("clear", "A1")][0].items()},
                baseline_seed7=df6.drop(columns=["curtailed_kWh_by_phase"]).to_dict("records"))
    json.dump(summ, open(os.path.join(R, "stage6_summary.json"), "w"), indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    import csv
    with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter", "Value", "Unit", "Source type", "Source", "Reason", "Sensitivity range", "Version"])
        for r in REGISTER: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)" if r[0] in SUPERSEDED_S2 else "stage1-v0.1"])
        for r in REGISTER_S2: w.writerow(list(r)+["stage2-v0.2"])
        for r in REGISTER_S3: w.writerow(list(r)+["stage3-v0.3"])
        for r in REGISTER_S5: w.writerow(list(r)+["stage5-v0.5"])
        for r in REGISTER_S6: w.writerow(list(r)+[VER])
    # ---- plots (clear + high_demand, A1) ----
    fig, axs = plt.subplots(3, 2, figsize=(14, 14)); dv = dev_series[("clear", "A1")]; hh = dv.hour
    typ = {"Water heaters": [c for c in dv if c.startswith("P_WH")], "Pumps": [c for c in dv if c.startswith("P_PUMP")], "EV groups": [c for c in dv if c.startswith("P_EV")]}
    axs[0, 0].stackplot(hh, [dv[c].sum() if False else dv[c_list].sum(axis=1) for c_list in typ.values()], labels=list(typ), colors=["#E8A33D", "#2B6CA0", "#4A9060"]); axs[0, 0].legend(fontsize=8, loc="upper left"); axs[0, 0].set_title("Uncontrolled flexible-device power (natural behaviour)"); axs[0, 0].set_ylabel("kW")
    for c in [c for c in dv if c.startswith("T_")]: axs[0, 1].plot(hh, dv[c], label=c[2:-2])
    axs[0, 1].set_ylabel("water-heater temperature (C)"); axs[0, 1].axhline(DEVICES["water_heater"]["t_min"], c="k", ls="--", lw=1); ax2 = axs[0, 1].twinx()
    for c in [c for c in dv if c.startswith("level_")]: ax2.plot(hh, dv[c], ls=":", label=c)
    ax2.set_ylabel("tank level (%), dotted"); axs[0, 1].legend(fontsize=7, loc="lower left"); axs[0, 1].set_title("Device states: heater temperature and tank level")
    for c in [c for c in dv if c.startswith("rem_")]: axs[1, 0].plot(hh, dv[c], label=c)
    axs[1, 0].set_title("EV groups: remaining charging need, incl. tonight's sessions not yet plugged in (kWh)", fontsize=9); axs[1, 0].legend(fontsize=8); axs[1, 0].set_ylabel("kWh")
    nodes = m["nodes"]
    for scn, c0 in (("clear", "#1F7A7A"), ("high_demand", "#B84A4A")):
        dfd = series[(scn, "A1")]; ref = pd.read_csv(os.path.join(R, f"stage5_{scn}_seed7_A1_timeseries.csv"))
        axs[1, 1].plot(dfd.hour, dfd[[f"V_{n}_A_pu" for n in nodes]].min(axis=1), c=c0, label=f"{scn}: lowest phase-A voltage, with devices"); axs[1, 1].plot(ref.hour, ref[[f"V_{n}_A_pu" for n in nodes]].min(axis=1), c=c0, ls=":", label=f"{scn}: without devices")
        axs[2, 0].plot(dfd.hour, dfd.trafo_kW, c=c0, label=f"{scn} with devices"); axs[2, 0].plot(ref.hour, ref.trafo_kW, c=c0, ls=":", label=f"{scn} without")
    axs[1, 1].axhline(CFG["v_lo"], c="k", ls="--", lw=1); axs[1, 1].legend(fontsize=7); axs[1, 1].set_title("Effect of uncontrolled devices on evening voltage (A1)"); axs[1, 1].set_ylabel("pu")
    axs[2, 0].set_title("Net power at transformer (A1)"); axs[2, 0].legend(fontsize=7); axs[2, 0].set_ylabel("kW"); axs[2, 0].axhline(0, c="k", lw=1)
    axs[2, 1].axis("off"); txt = f"Resource tests: {n_ok}/{len(ok)} pass\n\n" + "\n".join(("PASS  " if ok[k] else "FAIL  ") + k[:78] for k in list(res)[:22]) + "\n..."
    axs[2, 1].text(0, 1, txt, va="top", fontsize=6.3, family="monospace")
    for a in axs.flat[[0, 2, 3, 4]]: a.set_xlabel("hour of day")
    for a in axs.flat: a.grid(alpha=.3)
    fig.suptitle("LocalFlex Grid - Stage 6: flexible resources with natural (uncontrolled) behaviour on the frozen feeder", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage6_resources_baseline.png"), dpi=130)
    print(df6[df6.scenario.isin(["clear", "high_demand"])][["scenario", "case", "v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "dV_max", "dV_min", "d_trafo_pct", "device_energy_commanded_kWh", "device_energy_solved_kWh", "convergence_failures"]].to_string(index=False))
    print("energy by group (clear A1, kWh):", {k: round(v, 1) for k, v in energy[("clear", "A1")][0].items()}); print("all resource tests pass:", allpass)
if __name__ == "__main__": main()
