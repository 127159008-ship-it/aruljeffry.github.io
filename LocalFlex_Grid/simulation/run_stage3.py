"""Stage 3: Case A0 (fixed PV, frozen) vs Case A1 (PV with autonomous volt-watt response) on the Stage 2 4-wire network."""
import sys, os, json, csv, platform
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import opendssdirect as dss
from config.feeder_config import CFG, SEED, REGISTER, REGISTER_S2, SUPERSEDED_S2, INV, REGISTER_S3
from network.feeder_generator import build, write_dss_4wire
from profiles.household_demand import t, home_shape, solar_shape
R = os.path.join(ROOT, "results"); VB = CFG["kv_ll"]*1000/3**0.5; VER = "stage3-v0.3"

def vw(v):
    if v <= INV["v1"]: return 1.0
    if v >= INV["v2"]: return INV["p2"]
    return 1.0 - (1.0-INV["p2"])*(v-INV["v1"])/(INV["v2"]-INV["v1"])

def vpn(node):
    dss.Circuit.SetActiveBus(node); V = dss.Bus.Voltages(); nd = dss.Bus.Nodes(); z = {nd[j]: complex(V[2*j], V[2*j+1]) for j in range(len(nd))}
    return z

def simulate(case):
    m = build(CFG, SEED); path = os.path.join(ROOT, "network", "localflex_stage2.dss"); write_dss_4wire(CFG, m, path)   # identical network for both cases
    dss.Command("clear"); dss.Command(f"redirect {path}")
    nodes = m["nodes"]; lines = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]
    pvinfo = {i: m["homes"][i] for i in m["pv"]}; rows = []; curt_node = {n: 0.0 for n in nodes}; curt_phase = [0.0]*3; maxit = 0; nonconv = 0; maxres = 0.0
    for k in range(CFG["steps"]):
        dss.Loads.First()
        while True:
            i = int(dss.Loads.Name()[1:]); dss.Loads.kW(m["scale"][i]*home_shape[k])
            if not dss.Loads.Next(): break
        pav = CFG["pv_kw"]*solar_shape[k]; f = {i: 1.0 for i in pvinfo}
        def setpv():
            for i in pvinfo:
                dss.Generators.Name(f"pv{i}"); dss.Generators.kW(pav*f[i])
        setpv(); dss.Solution.Solve(); assert dss.Solution.Converged()
        it = 0
        if case == "A1" and pav > 0:
            for it in range(1, 41):
                zs = {n: vpn(n) for n in {pvinfo[i][0] for i in pvinfo}}
                new = {i: vw(abs(zs[pvinfo[i][0]][pvinfo[i][1]] - zs[pvinfo[i][0]][4])/VB) for i in pvinfo}
                delta = max(abs(new[i]-f[i]) for i in pvinfo)
                f = {i: 0.5*f[i] + 0.5*new[i] for i in pvinfo}
                setpv(); dss.Solution.Solve(); assert dss.Solution.Converged()
                if delta < 1e-3: break
            else: nonconv += 1
            maxit = max(maxit, it)
        row = {"hour": t[k], "inv_iterations": it}
        for n in nodes:
            z = vpn(n)
            for ph in range(3): row[f"V_{n}_{'ABC'[ph]}_pu"] = abs(z[ph+1]-z[4])/VB
            row[f"VN_{n}_V"] = abs(z[4])
        for ln in lines:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); cur = dss.CktElement.CurrentsMagAng()[0:8:2]
            for ph in range(3): row[f"I_{ln}_{'ABC'[ph]}_A"] = cur[ph]
            row[f"I_{ln}_N_A"] = cur[3]
        dss.Circuit.SetActiveElement("Transformer.tr"); pw = dss.CktElement.Powers()[:6]; P = sum(pw[0::2]); Q = sum(pw[1::2])
        row.update(trafo_kW=P, trafo_kVA=float(np.hypot(P,Q)), trafo_loading_pct=100*np.hypot(P,Q)/CFG["kva"])
        dem = 0.0; dss.Loads.First()
        while True:
            dem += sum(dss.CktElement.Powers()[0::2])
            if not dss.Loads.Next(): break
        pvk = 0.0; dss.Generators.First()
        while True:
            pvk += -sum(dss.CktElement.Powers()[0::2])
            if not dss.Generators.Next(): break
        loss = dss.Circuit.Losses()[0]/1000; avail = pav*len(pvinfo)
        row.update(demand_kW=dem, pv_avail_kW=avail, pv_kW=pvk, pv_curtailed_kW=avail-pvk, losses_kW=loss, balance_residual_kW=P-(dem-pvk+loss))
        maxres = max(maxres, abs(row["balance_residual_kW"]))
        for i,(n,p) in pvinfo.items(): c = pav*(1-f[i])*0.25; curt_node[n] += c; curt_phase[p-1] += c
        # volt-watt consistency: final operating point vs curve
        if case == "A1" and pav > 0:
            zs = {n: vpn(n) for n in {pvinfo[i][0] for i in pvinfo}}
            row["vw_max_mismatch"] = max(abs(f[i] - vw(abs(zs[pvinfo[i][0]][pvinfo[i][1]] - zs[pvinfo[i][0]][4])/VB)) for i in pvinfo)
        rows.append(row)
    return pd.DataFrame(rows), m, dict(curt_node=curt_node, curt_phase=curt_phase, max_iter=maxit, nonconv=nonconv, maxres=maxres)

def summarize(df, ex, m):
    vcols = [c for c in df if c.startswith("V_")]; pc = [c for c in df if c.startswith("I_") and not c.endswith("_N_A")]; nc = [c for c in df if c.endswith("_N_A")]
    return dict(v_max_pu=round(float(df[vcols].max().max()),3), v_min_pu=round(float(df[vcols].min().min()),3),
        hours_above_1p06=float((df[vcols].max(axis=1)>CFG["v_hi"]).sum()/4), hours_below_0p94=float((df[vcols].min(axis=1)<CFG["v_lo"]).sum()/4),
        peak_trafo_loading_pct=round(float(df.trafo_loading_pct.max()),1), reverse_flow_hours=float((df.trafo_kW<0).sum()/4),
        reverse_flow_energy_kWh=round(float(-df.trafo_kW.clip(upper=0).sum()/4),1),
        peak_phase_loading_pct=round(100*float(df[pc].max().max())/CFG["ampacity_a"],1), peak_neutral_current_A=round(float(df[nc].max().max()),1),
        peak_neutral_to_earth_V=round(float(df[[c for c in df if c.startswith("VN_")]].max().max()),1),
        pv_available_kWh=round(float(df.pv_avail_kW.sum()/4),1), pv_delivered_kWh=round(float(df.pv_kW.sum()/4),1),
        pv_curtailed_kWh=round(float(df.pv_curtailed_kW.sum()/4),1), pv_curtailed_pct=round(100*float(df.pv_curtailed_kW.sum()/df.pv_avail_kW.sum()),1),
        curtailed_kWh_by_phase=[round(x,1) for x in ex["curt_phase"]], max_balance_residual_kW=round(ex["maxres"],4),
        max_inverter_iterations=ex["max_iter"], nonconverged_steps=ex["nonconv"])

def main():
    a0, m, e0 = simulate("A0"); a1, _, e1 = simulate("A1")
    a0.to_csv(os.path.join(R,"stage3_A0_timeseries.csv"), index=False); a1.to_csv(os.path.join(R,"stage3_A1_timeseries.csv"), index=False)
    s2 = pd.read_csv(os.path.join(R,"stage2_caseA0_timeseries.csv")); common = [c for c in s2.columns if c in a0.columns and c not in ("balance_residual_kW",)]
    reg = float(np.max(np.abs(s2[common].values - a0[common].values)))
    # curve unit test
    curve = {v: round(vw(v),3) for v in (1.00, 1.06, 1.08, 1.10, 1.12)}
    out = dict(model_version=VER, python=platform.python_version(), A0_frozen_regression_max_abs_diff_vs_stage2=reg, volt_watt_curve_test=curve,
        A1_final_vs_curve_max_mismatch=round(float(a1.vw_max_mismatch.max()),4), A0=summarize(a0,e0,m), A1=summarize(a1,e1,m),
        A1_curtailed_kWh_by_node={n: round(v,1) for n,v in e1["curt_node"].items()}, volt_limits_note="1.06/0.94 pu assumed")
    json.dump(out, open(os.path.join(R,"stage3_summary.json"),"w"), indent=2)
    with open(os.path.join(ROOT,"config","parameter_register.csv"),"w",newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter","Value","Unit","Source type","Source","Reason","Sensitivity range","Version"])
        for r in REGISTER: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)" if r[0] in SUPERSEDED_S2 else "stage1-v0.1"])
        for r in REGISTER_S2: w.writerow(list(r)+["stage2-v0.2"])
        for r in REGISTER_S3: w.writerow(list(r)+[VER])
    nodes = m["nodes"]; cols = ["#B84A4A","#E8A33D","#2B6CA0"]; fig, axs = plt.subplots(3, 2, figsize=(14, 13))
    for lab, d, c in (("A0 fixed PV", a0, "#999"), ("A1 volt-watt", a1, "#B84A4A")):
        axs[0,0].plot(d.hour, d[[f"V_{n}_A_pu" for n in nodes]].max(axis=1), c=c, label=lab)
        axs[1,1].plot(d.hour, d.trafo_kW, c=c, label=lab); axs[1,0].plot(d.hour, d[[c2 for c2 in d if c2.endswith("_N_A")]].max(axis=1), c=c, label=lab)
    axs[0,0].axhline(CFG["v_hi"],c="k",ls="--",lw=1); axs[0,0].set_title("Highest phase-A voltage on network"); axs[0,0].set_ylabel("pu"); axs[0,0].legend()
    axs[0,1].plot(a1.hour, a1.pv_avail_kW, c="#4A9060", label="PV available"); axs[0,1].plot(a1.hour, a1.pv_kW, c="#B84A4A", label="PV delivered (A1)"); axs[0,1].fill_between(a1.hour, a1.pv_kW, a1.pv_avail_kW, color="#B84A4A", alpha=.25); axs[0,1].legend(); axs[0,1].set_title("PV available vs delivered under volt-watt"); axs[0,1].set_ylabel("kW")
    axs[1,0].set_title("Peak neutral current on any segment"); axs[1,0].set_ylabel("A"); axs[1,0].axhline(CFG["neutral_ampacity_a"],c="k",ls="--",lw=.8); axs[1,0].legend()
    axs[1,1].axhline(0,c="k",lw=1); axs[1,1].set_title("Net power at transformer"); axs[1,1].set_ylabel("kW"); axs[1,1].legend()
    axs[2,0].bar(range(len(nodes)), [e1["curt_node"][n] for n in nodes], color=["#1F7A7A"]*5+["#E8A33D"]*5); axs[2,0].set_xticks(range(len(nodes))); axs[2,0].set_xticklabels(nodes); axs[2,0].set_title("PV energy curtailed by node (A1)"); axs[2,0].set_ylabel("kWh")
    axs[2,1].bar(["A","B","C"], e1["curt_phase"], color=cols); axs[2,1].set_title("PV energy curtailed by phase (A1)"); axs[2,1].set_ylabel("kWh")
    for a in axs.flat[:4]: a.set_xlabel("hour of day")
    for a in axs.flat: a.grid(alpha=.3)
    fig.suptitle("LocalFlex Grid - Stage 3: fixed-output PV (A0) vs inverter volt-watt response (A1) - synthetic, assumed values", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(R,"stage3_A0_vs_A1.png"), dpi=130); print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
