"""Stage 10: final comparison A / B / C (= C9-fixed, no fairness) / D (= C9-fixed + fairness), plus development-chain cases C8 and C9-raw (diagnostic), a DISCOM communication test and a fairness-weight sweep.
Protocol: ONE reported day (day 2). Every case starts from the IDENTICAL state snapshot (device states, EV carry-over, battery 50%) = natural end of day 1."""
import sys, os, json, time, copy, pickle
import numpy as np, pandas as pd
from multiprocessing import Pool
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from run_stage9 import *            # forecast_base, extra, build_H, monitored, resource_list, PV_RATED, run_case ... (imports run_stage8/7/6)
from control.mpc import MPCController
from control.mpc9 import MPC9Controller
from control.mpc10 import MPC10Controller, FAIR, HOUSEHOLD
from control.rule_based import RuleController
from control.discom import CommLayer, SimDISCOM, DiscomLink
KEEP_ALL = False; TRACE_ALL = False     # web app: record the decision trace at every scored step
def snapshot0(m, dem, pv):
    g = warm_start(make_all(DEVICES, DEVICE_SEED)); simulate6("A1", m, dem, pv, g); next_day(g); b = [x for x in g if isinstance(x, SharedBattery)][0]; b.E = b.E0 = b.P["soc_init"]*b.P["e_kwh"]; return g
def make_ctl(name, cal, dem, pv, seed, Hm, He, S_mid, Vb, Pn, comm=None, lam=None):
    tot = (dem.sum(axis=1), pv.sum(axis=1)); a = (cal,)+tot+(seed,)
    if name == "B": return RuleController()
    if name == "C8": c = MPCController(*a)
    elif name == "C9raw": c = MPC9Controller(*a, Hm, He, S_mid["resources"], S_mid["monitored"], Vb, Pn, sum(CFG["pv_by_phase"])*CFG["pv_kw"])
    else:
        fair = dict(FAIR); 
        if lam is not None: fair["lam"] = lam
        c = MPC10Controller(*a, Hm, He, S_mid["resources"], S_mid["monitored"], Vb, Pn, sum(CFG["pv_by_phase"])*CFG["pv_kw"], exclusive=True, fairness=name.startswith("D"), comm=comm, fair=fair, trace_steps=(tuple(range(96, 96+128)) if TRACE_ALL else ((96+48, 96+76) if seed == 7 else ())))
    c.a = 96; return c
def burdens(groups, dv, dvA, ex, scn_phase_groups):
    """Ex-post burden per household-facing group vs the natural (Case A) benchmark."""
    rows = []; EA = {}
    for g in groups:
        if g.id in HOUSEHOLD: EA[g.id] = float(dvA[f"P_{g.id}_kW"].sum()*0.25)
    cp = ex["curt_phase"]
    for g in groups:
        if g.id not in HOUSEHOLD: continue
        cn = np.cumsum(dvA[f"P_{g.id}_kW"].values)*0.25; ca = np.cumsum(dv[f"P_{g.id}_kW"].values)*0.25; delay = float(np.clip(cn - ca, 0, None).sum()*0.25); En = max(EA[g.id], 1e-6)
        if isinstance(g, EVGroup): un = float(g.led["unmetA"])
        else: un = float(np.clip(45.0 - dv[f"T_{g.id}_C"].values, 0, None).sum()*0.25*g.C)
        cur = cp[g.phase-1]/scn_phase_groups[g.phase]
        rows.append(dict(group=g.id, delivered_kWh=round(float(dv[f"P_{g.id}_kW"].sum()*0.25), 2), natural_kWh=round(En, 2), delay_kWh_h=round(delay, 3), unmet_kWh=round(un, 3), curtail_share_kWh=round(cur, 3),
                         B_delay=delay/(En*4.0), B_unmet=un/En, B_curt=cur/En, B_plan=delay/(En*4.0) + 10.0*un/En))
    return pd.DataFrame(rows)
def task(args):
    scn, seed, names, extra_kw = args; m = build(CFG, SEED); pvn = [m["homes"][i][0] for i in m["pv"]]; cal = json.load(open(os.path.join(R, "stage8_voltage_model.json")))
    S_mid = build_H(m, 48); S_ev = build_H(m, 76); ds, sm, _ = SCENARIOS[scn]; dem = household_profiles(m["scale"], seed, ds); pv = pv_availability(sm, seed, pvn)
    S0 = snapshot0(m, dem, pv); Vb, Pn = forecast_base(m, dem, pv, seed); rows = []; brows = []; keep = {}; dvA = None; logs = {}
    for name in names:
        nm = name.split("@")[0]; kw = extra_kw.get(name, {}); groups = copy.deepcopy(S0)
        comm = None
        if "comm" in kw: comm = CommLayer(SimDISCOM(**kw["comm"]["discom"]), DiscomLink(kw["comm"]["outages"]))
        ctl = None if nm == "A" else make_ctl(("D" if nm.startswith("D") else "C" if nm.startswith("C") and nm not in ("C8", "C9raw") else nm), cal, dem, pv, seed, S_mid["H"], S_ev["H"], S_mid, Vb, Pn, comm=comm, lam=kw.get("lam"))
        if ctl is not None and kw.get("battery_only"):
            from final.overrides import Only
            if hasattr(ctl, "Pn"): ctl.extra_base = np.tile(sum(ctl.Pn[g.id] for g in groups if g.id != "BATT"), 4)[:384]
            ctl = Only(ctl, ["BATT"])
        if ctl is not None and any(g.id.endswith("N") and g.id[:-1] in ("WH1", "WH2", "WH3", "WH4", "EV1", "EV2") for g in groups):     # participation study: non-participating sub-groups run naturally
            from final.overrides import GroupFilter
            ids = [g.id for g in groups if g.id.endswith("N") and g.id[:-1] in ("WH1", "WH2", "WH3", "WH4", "EV1", "EV2")]
            if hasattr(ctl, "Pn"): ctl.extra_base = np.tile(sum(ctl.Pn[i] for i in ids), 4)[:384]
            ctl = GroupFilter(ctl)
        if nm != "A" and ("faults" in kw or kw.get("supervise")):
            from final.supervisor import Supervisor; ctl = Supervisor(ctl, kw.get("faults", ()))
        if ctl is not None and "delay" in kw:
            from final.overrides import Delay; ctl = Delay(ctl, *kw["delay"])
        t0 = time.time(); df, dv1, ex, ec, es = simulate6("A1", m, dem, pv, groups, controller=ctl)                  # reported day (day 2)
        led1 = {g.id: copy.deepcopy(g.led) for g in groups if hasattr(g, "led")}; soc_end = float(dv1.SoC_BATT_pct.iloc[-1])
        for g in groups:
            if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
        _fb_day = list(getattr(ctl, "fb_log", []))
        next_day(groups); df2, dv2, ex2, ec2, es2 = simulate6("A1", m, dem, pv, groups, controller=ctl, nsteps=32)       # tail: morning of day 3 (departures of day-2 evening sessions)
        led2 = {g.id: copy.deepcopy(g.led) for g in groups if hasattr(g, "led")}; dv = pd.concat([dv1, dv2], ignore_index=True)
        for g in groups:
            if hasattr(g, "ledger_error"): assert abs(g.ledger_error()) < 1e-6, (g.id, g.ledger_error())
        if nm == "A": dvA = dv
        evun = {g.id: led1[g.id]["unmetA"] + led2[g.id]["unmetA"] for g in groups if isinstance(g, EVGroup)}
        dfa = pd.concat([df, df2], ignore_index=True); dfa["t_h"] = np.arange(len(dfa))*0.25; dv["t_h"] = np.arange(len(dv))*0.25
        exa = dict(nonconv=ex["nonconv"]+ex2["nonconv"], inv_limit=ex["inv_limit"]+ex2["inv_limit"], max_iter=max(ex["max_iter"], ex2["max_iter"]), curt_phase=[a+b for a, b in zip(ex["curt_phase"], ex2["curt_phase"])])
        mm = metrics(dfa, exa, scn, seed, name); mm["curtailed_kWh_by_phase"] = exa["curt_phase"]; mm.update(extra(dfa)); df = dfa; ex = exa             # ELECTRICAL metrics over the full 32 h window (day 2 + next-morning tail): all energy of day-2 evening sessions is scored
        vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]; V = df[vc].values; ph = df.hour.values; T = dv[[c for c in dv if c.startswith("T_")]]
        mm.update(ev_unmet_at_departure_kWh=round(sum(evun.values()), 2), unmet_water_m3=round(sum(led1[g.id]["unmet"] + led2[g.id]["unmet"] for g in groups if isinstance(g, PumpTank)), 3), min_heater_T_C=round(float(T.min().min()), 1), heater_hours_below_45C=float((T < 45).any(axis=1).sum()/4),
                  ev_delivered_kWh_incl_tail=round(float(sum(dv[f"P_{g}_kW"].sum() for g in ("EV1", "EV2"))*.25), 1), ev_natural_kWh_incl_tail=round(float(sum(dvA[f"P_{g}_kW"].sum() for g in ("EV1", "EV2"))*.25), 1) if dvA is not None else None,
                  under_pu_h=round(float(np.clip(0.94-V, 0, None).sum()*.25), 3), over_pu_h=round(float(np.clip(V-1.06, 0, None).sum()*.25), 3), deepest_under_pu=round(float(np.clip(0.94-V, 0, None).max()), 3),
                  curtailment_pct=round(100*mm["pv_curtailed_kWh"]/max(mm["pv_available_kWh"], 1e-9), 2), pv_utilisation_pct=round(100*mm["pv_delivered_kWh"]/max(mm["pv_available_kWh"], 1e-9), 2),
                  batt_initial_soc_pct=round(float(S0[[i for i, g in enumerate(S0) if isinstance(g, SharedBattery)][0]].E/S0[[i for i, g in enumerate(S0) if isinstance(g, SharedBattery)][0]].P["e_kwh"]*100), 1), batt_final_soc_pct=round(soc_end, 1), batt_final_soc_after_tail_pct=round(float(dv2.SoC_BATT_pct.iloc[-1]), 1), batt_charge_kWh=round(float(dv.P_BATT_kW.clip(lower=0).sum()*.25), 1), batt_discharge_kWh=round(float((-dv.P_BATT_kW).clip(lower=0).sum()*.25), 1),
                  batt_throughput_kWh=round(float(dv.P_BATT_kW.abs().sum()*.25), 1), import_peak_18_22_kW=round(float(df.trafo_kW[(ph >= 18) & (ph < 22)].max()), 1), run_s=round(time.time()-t0, 1))
        _t = getattr(ctl, "trace", None)
        if _t: logs[name+"_trace"] = _t; logs[name+"_predlog"] = [(int(a_), int(k_), np.asarray(vp).tolist(), np.asarray(vb).tolist()) for a_, k_, vp, vb in ctl.pred_log]
        if hasattr(ctl, "fb_log"): logs[name+"_fb"] = _fb_day + [x + 96 for x in ctl.fb_log[len(_fb_day):]]       # steps (0-127 of the scored window) where the OpenDSS gate replaced the MPC command by the rule command
        if hasattr(ctl, "events"): mm.update(sup_events=len(ctl.events), sup_counts=str(ctl.counts)); logs[name+"_sup"] = ctl.events
        if ctl is not None and nm not in ("B",):
            mm.update(planner_vars=getattr(ctl, "nvars", None), planner_cons=getattr(ctl, "ncons", None), gate_checks=ctl.n_gate, fallbacks_to_rules=ctl.n_fb, solver_failures=ctl.n_fail, simultaneous_batt_steps_first_step=ctl.n_sim, mean_solve_s=round(float(np.mean(ctl.solve_s)), 3))
            if hasattr(ctl, "n_sim_plan"): mm.update(simultaneous_batt_steps_anywhere_in_plans=ctl.n_sim_plan, plans=ctl.n_plan, mip_time_limited_plans=ctl.mip_nonopt)
        if comm is not None: mm.update(msgs_lost_to_discom=comm.lost_up, requests_lost_from_discom=comm.lost_down, steps_with_dispatch_cap=ctl.cap_active_steps); logs[name] = comm.log[:400]; logs[name+"_caplog"] = getattr(ctl, "cap_log", [])
        from final.reconcile import reconcile, more_metrics
        mm.update({k: (round(float(v), 3)) for k, v in more_metrics(df, dv).items()}); mm["water_delivered_m3"] = round(sum(led1[g.id]["v_served"] + led2[g.id]["v_served"] for g in groups if isinstance(g, PumpTank)), 3)
        mm.update({k: (round(float(v), 4) if not isinstance(v, (bool, np.bool_)) else bool(v)) for k, v in reconcile(df, dv).items()})
        mm["variant"] = name; rows.append(mm)
        if dvA is not None:
            for g in groups:
                if isinstance(g, EVGroup): g.led = dict(g.led, unmetA=evun[g.id])
            groups_phase = {p: sum(1 for g in groups if g.id in HOUSEHOLD and g.phase == p) for p in (1, 2, 3)}; bd = burdens(groups, dv, dvA, ex, groups_phase); bd["scenario"] = scn; bd["seed"] = seed; bd["variant"] = name; brows.append(bd)
        if seed == 7 or KEEP_ALL: keep[(scn, name)] = (df, dv)
        print(f"{scn} s{seed} {name} done {time.time()-t0:.0f}s", flush=True)
    return rows, (pd.concat(brows) if brows else pd.DataFrame()), keep, logs
def main():
    t0 = time.time(); full = "--full" in sys.argv; seeds = [7, 11, 23, 42] if full else [7]; core = ["A", "B", "C8", "C9raw", "C", "D"]; tasks = []
    for scn in SCENARIOS:
        for seed in seeds: tasks.append((scn, seed, core, {}))
    # extras on clear seed 7: fairness-weight sweep, communication tests
    cm = lambda outs: dict(comm=dict(discom=dict(cap_kw=150.0, window=(18.0, 22.0), lead_h=1.0), outages=outs))
    tasks.append(("clear", 7, ["A", "D@lam100", "D@lam2000", "D@dispatch_up", "D@dispatch_lost_before", "D@dispatch_lost_after"], {"D@lam100": dict(lam=100.0), "D@lam2000": dict(lam=2000.0), "D@dispatch_up": cm([]), "D@dispatch_lost_before": cm([(16.5, 23.0)]), "D@dispatch_lost_after": cm([(17.5, 23.0)])}))
    with Pool(2) as pool: res = pool.map(task, tasks, chunksize=1)
    rows = [r for t in res for r in t[0]]; bur = pd.concat([t[1] for t in res]); keep = {}; logs = {}
    for t in res: keep.update(t[2]); logs.update(t[3])
    out = pd.DataFrame(rows); out["curtailed_kWh_by_phase"] = out["curtailed_kWh_by_phase"].astype(str); out.to_csv(os.path.join(R, "stage10_summary.csv"), index=False); bur.to_csv(os.path.join(R, "stage10_burden_by_group.csv"), index=False)
    pickle.dump(dict(keep=keep, logs=logs), open(os.path.join(R, "_s10keep.pkl"), "wb")); print("total", round(time.time()-t0), "s")
if __name__ == "__main__": main()
