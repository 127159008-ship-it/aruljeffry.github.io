"""Stage 5: variable operating conditions on the FROZEN Stage 2 network, with A0 (fixed PV) and A1 (Stage 3 volt-watt, unchanged) and the Stage 4 validator."""
import sys, os, json, time, platform
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import opendssdirect as dss
from config.feeder_config import CFG, SEED, SCENARIOS, PROFILE_SEEDS, REGISTER, REGISTER_S2, REGISTER_S3, REGISTER_S5, SUPERSEDED_S2
from network.feeder_generator import build, write_dss_4wire
from profiles.household_demand import t
from profiles.scenarios import household_profiles, pv_availability, uniform_profiles
from run_stage3 import vw, vpn, VB          # Stage 3 volt-watt curve and voltage helper, imported unchanged
from validation.validator import validate
R = os.path.join(ROOT, "results"); VER = "stage5-v0.5"; NSTEP = CFG["steps"]

def simulate(case, m, demand, pvav):
    """Same electrical loop as Stage 3, but power inputs come from matrices: demand[k, home], pvav[k, pv]. Convergence failures are recorded, not asserted."""
    path = os.path.join(ROOT, "network", "localflex_stage2.dss"); write_dss_4wire(CFG, m, path)
    dss.Command("clear"); dss.Command(f"redirect {path}")
    nodes = m["nodes"]; lines = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]; pvidx = m["pv"]; pvinfo = {i: m["homes"][i] for i in pvidx}
    rows = []; nonconv = 0; invlim = 0; maxit = 0; curt_phase = [0.0]*3
    for k in range(NSTEP):
        dss.Loads.First()
        while True:
            i = int(dss.Loads.Name()[1:]); dss.Loads.kW(float(demand[k, i]))
            if not dss.Loads.Next(): break
        f = {i: 1.0 for i in pvidx}
        def setpv():
            for j, i in enumerate(pvidx): dss.Generators.Name(f"pv{i}"); dss.Generators.kW(float(pvav[k, j]*f[i]))
        setpv(); dss.Solution.Solve(); conv = bool(dss.Solution.Converged()); it = 0
        if case == "A1" and pvav[k].max() > 0 and conv:
            for it in range(1, 201):
                zs = {n: vpn(n) for n in {pvinfo[i][0] for i in pvinfo}}
                new = {i: vw(abs(zs[pvinfo[i][0]][pvinfo[i][1]] - zs[pvinfo[i][0]][4])/VB) for i in pvinfo}
                delta = max(abs(new[i]-f[i]) for i in pvinfo); f = {i: 0.5*f[i] + 0.5*new[i] for i in pvinfo}
                setpv(); dss.Solution.Solve(); conv = conv and bool(dss.Solution.Converged())
                if delta < 1e-3 or not conv: break
            else: invlim += 1
            maxit = max(maxit, it)
        if not conv: nonconv += 1
        row = {"hour": t[k], "inv_iterations": it, "converged": conv}
        for n in nodes:
            z = vpn(n)
            for ph in range(3): row[f"V_{n}_{'ABC'[ph]}_pu"] = abs(z[ph+1]-z[4])/VB
            row[f"VN_{n}_V"] = abs(z[4])
        for ln in lines:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); cur = dss.CktElement.CurrentsMagAng()[0:8:2]
            for ph in range(3): row[f"I_{ln}_{'ABC'[ph]}_A"] = cur[ph]
            row[f"I_{ln}_N_A"] = cur[3]
        dss.Circuit.SetActiveElement("Transformer.tr"); pw = dss.CktElement.Powers()[:6]; P = sum(pw[0::2]); Q = sum(pw[1::2])
        row.update(trafo_kW=P, trafo_kVA=float(np.hypot(P, Q)), trafo_loading_pct=100*np.hypot(P, Q)/CFG["kva"])
        dem = 0.0; dss.Loads.First()
        while True:
            dem += sum(dss.CktElement.Powers()[0::2])
            if not dss.Loads.Next(): break
        pvk = 0.0; dss.Generators.First()
        while True:
            pvk += -sum(dss.CktElement.Powers()[0::2])
            if not dss.Generators.Next(): break
        loss = dss.Circuit.Losses()[0]/1000; avail = float(pvav[k].sum())
        row.update(demand_kW=dem, pv_avail_kW=avail, pv_kW=pvk, pv_curtailed_kW=avail-pvk, losses_kW=loss, balance_residual_kW=P-(dem-pvk+loss))
        for j, i in enumerate(pvidx): curt_phase[pvinfo[i][1]-1] += pvav[k, j]*(1-f[i])*0.25
        if case == "A1" and pvav[k].max() > 0:
            zs = {n: vpn(n) for n in {pvinfo[i][0] for i in pvinfo}}
            row["vw_max_mismatch"] = max(abs(f[i] - vw(abs(zs[pvinfo[i][0]][pvinfo[i][1]] - zs[pvinfo[i][0]][4])/VB)) for i in pvinfo)
        rows.append(row)
    return pd.DataFrame(rows), dict(nonconv=nonconv, inv_limit=invlim, max_iter=maxit, curt_phase=curt_phase)

def metrics(df, ex, scenario, seed, case):
    s, e = validate(df, CFG); ov = e[e.type == "overvoltage"]; uv = e[e.type == "undervoltage"]
    j, jm = int(s.v_max_pu.idxmax()), int(s.v_min_pu.idxmin())
    return dict(scenario=scenario, seed=seed, case=case, v_max_pu=round(float(s.v_max_pu.max()), 3), v_max_where=f"{s.v_max_where[j]}@{s.hour[j]:.2f}h",
        v_min_pu=round(float(s.v_min_pu.min()), 3), v_min_where=f"{s.v_min_where[jm]}@{s.hour[jm]:.2f}h",
        hours_any_overvoltage=float((s.n_overvoltage_nodes_phases > 0).sum()/4), hours_any_undervoltage=float((s.n_undervoltage_nodes_phases > 0).sum()/4),
        steps_fail=int((s.status == "FAIL").sum()), overvoltage_node_phases=int(ov.location.nunique()), undervoltage_node_phases=int(uv.location.nunique()),
        peak_phase_current_A=round(float(s.phase_current_max_A.max()), 1), peak_phase_loading_pct=round(float(s.phase_current_pct.max()), 1),
        peak_neutral_current_A=round(float(s.neutral_current_max_A.max()), 1), peak_neutral_loading_pct=round(float(s.neutral_current_pct.max()), 1),
        peak_trafo_loading_pct=round(float(s.trafo_loading_pct.max()), 1), reverse_flow_energy_kWh=round(float(s.reverse_flow_kW.sum()/4), 1),
        pv_available_kWh=round(float(s.pv_available_kW.sum()/4), 1), pv_delivered_kWh=round(float(s.pv_delivered_kW.sum()/4), 1),
        pv_curtailed_kWh=round(float(s.pv_curtailed_kW.sum()/4), 1), pv_accounting_residual_kWh=round(float(s.pv_accounting_residual_kW.sum()/4), 2),
        demand_kWh=round(float(s.demand_kW.sum()/4), 1), peak_demand_kW=round(float(s.demand_kW.max()), 1),
        max_power_balance_residual_kW=round(float(s.power_balance_residual_kW.abs().max()), 4), convergence_failures=int(ex["nonconv"]), inverter_iteration_limit_hits=int(ex["inv_limit"]), max_inverter_iterations=int(ex["max_iter"]),
        curtailed_kWh_by_phase=[round(x, 1) for x in ex["curt_phase"]])

def main():
    t0 = time.time(); m = build(CFG, SEED); nPV = len(m["pv"]); pv_nodes = [m["homes"][i][0] for i in m["pv"]]; tests = {}
    # ---- test 3: frozen baselines unchanged (uniform inputs reproduce Stage 3 exactly) ----
    d_u, p_u = uniform_profiles(m["scale"], nPV); reg = {}
    for case in ("A0", "A1"):
        df, _ = simulate(case, m, d_u, p_u); ref = pd.read_csv(os.path.join(R, f"stage3_{case}_timeseries.csv"))
        cols = [c for c in ref.columns if c in df.columns and c != "vw_max_mismatch"]; reg[case] = float(np.max(np.abs(ref[cols].values - df[cols].values)))
    tests["A0_A1_unchanged_vs_stage3_max_abs_diff"] = reg
    # ---- test 2: different seeds -> different household profiles, same energy ----
    a = household_profiles(m["scale"], 7); b = household_profiles(m["scale"], 11); base = np.outer(__import__("profiles.household_demand", fromlist=["home_shape"]).home_shape, m["scale"])
    tests["different_seeds_differ_mean_abs_kW"] = round(float(np.abs(a-b).mean()), 4)
    tests["per_home_daily_energy_preserved_max_rel_err"] = float(np.max(np.abs(a.sum(axis=0)-base.sum(axis=0))/base.sum(axis=0)))
    tests["aggregate_demand_energy_ref_vs_diverse_kWh"] = [round(float(base.sum()/4), 1), round(float(a.sum()/4), 1)]
    tests["aggregate_peak_kW_ref_vs_diverse"] = [round(float(base.sum(axis=1).max()), 1), round(float(a.sum(axis=1).max()), 1)]
    # ---- all scenarios x seeds x cases ----
    allm = []; series = {}
    for si, (scn, (dscale, smode, desc)) in enumerate(SCENARIOS.items()):
        for seed in PROFILE_SEEDS:
            dem = household_profiles(m["scale"], seed, dscale); pv = pv_availability(smode, seed, pv_nodes)
            for case in ("A0", "A1"):
                df, ex = simulate(case, m, dem, pv); allm.append(metrics(df, ex, scn, seed, case))
                if seed == 7: series[(scn, case)] = df; df.assign(scenario=scn, seed=seed, case=case).to_csv(os.path.join(R, f"stage5_{scn}_seed7_{case}_timeseries.csv"), index=False)
            print(f"{scn} seed {seed} done ({time.time()-t0:.0f}s)", flush=True)
    # ---- test 1: identical seed -> identical results (re-run cloudy seed 7 A1) ----
    dem = household_profiles(m["scale"], 7, 1.0); pv = pv_availability("cloudy", 7, pv_nodes); d2, _ = simulate("A1", m, dem, pv)
    tests["identical_seed_max_abs_diff_cloudy_A1"] = float(np.max(np.abs(d2[[c for c in d2 if c.startswith("V_")]].values - series[("cloudy", "A1")][[c for c in d2 if c.startswith("V_")]].values)))
    mm = pd.DataFrame(allm); mm["curtailed_kWh_by_phase"] = mm["curtailed_kWh_by_phase"].astype(str); mm.to_csv(os.path.join(R, "stage5_scenario_summary.csv"), index=False)
    tests["max_power_balance_residual_kW_all_runs"] = float(mm.max_power_balance_residual_kW.max()); tests["total_convergence_failures"] = int(mm.convergence_failures.sum()); tests["total_inverter_iteration_limit_hits"] = int(mm.inverter_iteration_limit_hits.sum()); tests["max_inverter_iterations_used"] = int(mm.max_inverter_iterations.max())
    tests["curtailment_never_negative"] = bool((mm.pv_curtailed_kWh >= 0).all()); tests["runs"] = len(mm)
    ok = (max(reg.values()) < 1e-9 and tests["identical_seed_max_abs_diff_cloudy_A1"] == 0.0 and tests["different_seeds_differ_mean_abs_kW"] > 0.01
          and tests["per_home_daily_energy_preserved_max_rel_err"] < 1e-9 and tests["max_power_balance_residual_kW_all_runs"] < 0.05 and tests["total_convergence_failures"] == 0 and tests["total_inverter_iteration_limit_hits"] == 0)
    tests["ALL_PASS"] = bool(ok)
    # robustness table: min / max across seeds
    rob = {}
    for (scn, case), g in mm.groupby(["scenario", "case"]):
        rob[f"{scn}/{case}"] = {k: [float(g[k].min()), float(g[k].max())] for k in ("v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh")}
    out = dict(model_version=VER, python=platform.python_version(), network_seed=SEED, profile_seeds=PROFILE_SEEDS, scenarios={k: dict(demand_scale=v[0], solar=v[1], description=v[2]) for k, v in SCENARIOS.items()},
               tests=tests, reference_seed7=mm[mm.seed == 7].drop(columns=["curtailed_kWh_by_phase"]).to_dict("records"), robustness_min_max_across_seeds=rob)
    json.dump(out, open(os.path.join(R, "stage5_scenario_summary.json"), "w"), indent=2)
    import csv
    with open(os.path.join(ROOT, "config", "parameter_register.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter", "Value", "Unit", "Source type", "Source", "Reason", "Sensitivity range", "Version"])
        for r in REGISTER: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)" if r[0] in SUPERSEDED_S2 else "stage1-v0.1"])
        for r in REGISTER_S2: w.writerow(list(r)+["stage2-v0.2"])
        for r in REGISTER_S3: w.writerow(list(r)+["stage3-v0.3"])
        for r in REGISTER_S5: w.writerow(list(r)+[VER])
    # ---- plots ----
    cols = {"clear": "#1F7A7A", "cloudy": "#E8A33D", "high_solar": "#4A9060", "high_demand": "#B84A4A"}; nodes = m["nodes"]; fig, axs = plt.subplots(3, 2, figsize=(14, 14))
    for scn in SCENARIOS:
        for case, ls in (("A0", "-"), ("A1", "--")):
            d = series[(scn, case)]; axs[0, 0 if case == "A0" else 1].plot(d.hour, d[[f"V_{n}_A_pu" for n in nodes]].max(axis=1), c=cols[scn], label=scn)
            axs[1, 0 if case == "A0" else 1].plot(d.hour, d.trafo_kW, c=cols[scn], label=scn)
    for j, case in enumerate(("A0 fixed PV", "A1 volt-watt")):
        axs[0, j].axhline(CFG["v_hi"], c="k", ls="--", lw=1); axs[0, j].axhline(CFG["v_lo"], c="k", ls=":", lw=1); axs[0, j].set_title(f"{case}: highest phase-A voltage (seed 7)"); axs[0, j].set_ylabel("pu"); axs[0, j].legend(fontsize=8)
        axs[1, j].axhline(0, c="k", lw=1); axs[1, j].set_title(f"{case}: net power at transformer (below 0 = reverse flow)"); axs[1, j].set_ylabel("kW"); axs[1, j].legend(fontsize=8)
    for scn in SCENARIOS:
        d = series[(scn, "A0")]; axs[2, 0].plot(d.hour, d.pv_avail_kW, c=cols[scn], label=f"{scn} PV"); axs[2, 0].plot(d.hour, d.demand_kW, c=cols[scn], ls=":", lw=1)
    axs[2, 0].set_title("PV available (solid) and home demand (dotted), seed 7"); axs[2, 0].set_ylabel("kW"); axs[2, 0].legend(fontsize=7, ncol=2)
    xs = np.arange(len(SCENARIOS)); 
    for off, case in ((-0.2, "A0"), (0.2, "A1")):
        lo = [mm[(mm.scenario == s) & (mm.case == case)].hours_any_overvoltage.min() for s in SCENARIOS]; hi = [mm[(mm.scenario == s) & (mm.case == case)].hours_any_overvoltage.max() for s in SCENARIOS]
        axs[2, 1].bar(xs+off, hi, 0.35, label=f"{case} max over seeds", color="#999" if case == "A0" else "#B84A4A", alpha=.5); axs[2, 1].bar(xs+off, lo, 0.35, label=f"{case} min over seeds", color="#999" if case == "A0" else "#B84A4A")
    axs[2, 1].set_xticks(xs); axs[2, 1].set_xticklabels(list(SCENARIOS)); axs[2, 1].set_ylabel("hours"); axs[2, 1].set_title("Hours with any node over 1.06 pu: min-max across 4 seeds"); axs[2, 1].legend(fontsize=7)
    for a in axs.flat[:5]: a.set_xlabel("hour of day")
    for a in axs.flat: a.grid(alpha=.3)
    fig.suptitle("LocalFlex Grid - Stage 5: same network, different weather and demand (synthetic, assumed values)", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R, "stage5_scenario_comparison.png"), dpi=130)
    print(json.dumps(dict(tests=tests), indent=2)); print(mm[mm.seed == 7][["scenario", "case", "v_max_pu", "v_min_pu", "hours_any_overvoltage", "hours_any_undervoltage", "peak_neutral_loading_pct", "peak_trafo_loading_pct", "reverse_flow_energy_kWh", "pv_curtailed_kWh", "peak_demand_kW"]].to_string(index=False)); print("total s", round(time.time()-t0))
if __name__ == "__main__": main()
