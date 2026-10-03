"""Stage 1: Case A0 (no control, fixed-output PV). Validated 24 h run with full electrical logging."""
import sys, os, json, csv, platform
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import opendssdirect as dss
from config.feeder_config import CFG, SEED, REGISTER, MODEL_VERSION
from network.feeder_generator import build, write_dss
from profiles.household_demand import t, home_shape, solar_shape
R = os.path.join(ROOT, "results"); VB = CFG["kv_ll"]*1000/3**0.5

def hand_calc_check():
    """Independent check: balanced 30 kW load at the end of 1 km of the same cable vs analytic voltage drop."""
    c = dss.Command
    c(f"set DefaultBaseFrequency={CFG['freq_hz']}"); c("clear")
    c(f"new circuit.t basekv={CFG['kv_ll']} pu=1.0 phases=3 bus1=s basefreq={CFG['freq_hz']}")
    c(f"new linecode.lv nphases=3 r1={CFG['r1']} x1={CFG['x1']} r0={CFG['r0']} x0={CFG['x0']} units=km basefreq={CFG['freq_hz']}")
    c("new line.l bus1=s bus2=e linecode=lv length=1 units=km")
    c(f"new load.x bus1=e phases=3 kv={CFG['kv_ll']} kw=30 pf={CFG['pf']} model=1")
    c(f"set voltagebases=[{CFG['kv_ll']}]"); c("calcv"); c("solve")
    dss.Circuit.SetActiveBus("e"); v = np.array(dss.Bus.VMagAngle()[0::2][:3])
    drop_sim = VB - v.mean()
    phi = np.arccos(CFG["pf"]); I = 30000/(3**0.5*CFG["kv_ll"]*1000*CFG["pf"])
    drop_hand = I*(CFG["r1"]*np.cos(phi) + CFG["x1"]*np.sin(phi))
    return dict(drop_sim_V=round(float(drop_sim),2), drop_hand_V=round(float(drop_hand),2),
                rel_diff_pct=round(100*abs(drop_sim-drop_hand)/drop_hand,1))

def main():
    chk = hand_calc_check()
    m = build(CFG, SEED); dsspath = os.path.join(ROOT, "network", "localflex_stage1.dss"); write_dss(CFG, m, dsspath)
    dss.Command("clear"); dss.Command(f"redirect {dsspath}")
    freq = dss.Solution.Frequency()
    nodes = m["nodes"]; lines = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]
    rows = []; maxres = 0.0
    for k in range(CFG["steps"]):
        dss.Loads.First()
        while True:
            i = int(dss.Loads.Name()[1:]); dss.Loads.kW(m["scale"][i]*home_shape[k]); 
            if not dss.Loads.Next(): break
        dss.Generators.First()
        while True:
            dss.Generators.kW(CFG["pv_kw"]*solar_shape[k])
            if not dss.Generators.Next(): break
        dss.Solution.Solve(); assert dss.Solution.Converged(), f"no convergence at step {k}"
        row = {"hour": t[k]}
        for n in nodes:
            dss.Circuit.SetActiveBus(n); mg = dss.Bus.VMagAngle()[0::2][:3]
            for ph in range(3): row[f"V_{n}_{'ABC'[ph]}_pu"] = mg[ph]/VB
        for ln in lines:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); cur = dss.CktElement.CurrentsMagAng()[0:6:2]
            for ph in range(3): row[f"I_{ln}_{'ABC'[ph]}_A"] = cur[ph]
        dss.Circuit.SetActiveElement("Transformer.tr"); pw = dss.CktElement.Powers()[:6]
        P = sum(pw[0::2]); Q = sum(pw[1::2]); row.update(trafo_kW=P, trafo_kvar=Q, trafo_kVA=float(np.hypot(P,Q)),
            trafo_loading_pct=100*np.hypot(P,Q)/CFG["kva"])
        dem = 0.0
        dss.Loads.First()
        while True:
            dem += dss.CktElement.Powers()[0]; 
            if not dss.Loads.Next(): break
        pvk = 0.0
        dss.Generators.First()
        while True:
            pvk += -dss.CktElement.Powers()[0]
            if not dss.Generators.Next(): break
        loss = dss.Circuit.Losses()[0]/1000
        row.update(demand_kW=dem, pv_kW=pvk, losses_kW=loss, balance_residual_kW=P - (dem - pvk + loss))
        maxres = max(maxres, abs(row["balance_residual_kW"])); rows.append(row)
    df = pd.DataFrame(rows); df.to_csv(os.path.join(R, "stage1_caseA0_timeseries.csv"), index=False)
    vcols = [c for c in df if c.startswith("V_")]; icols = [c for c in df if c.startswith("I_")]
    vmax = df[vcols].max().max(); vmin = df[vcols].min().min()
    hi = (df[[c for c in vcols]].max(axis=1) > CFG["v_hi"]).sum()/4; lo = (df[vcols].min(axis=1) < CFG["v_lo"]).sum()/4
    summ = dict(model_version=MODEL_VERSION, seed=SEED, freq_hz=freq, opendssdirect=dss.__version__ if hasattr(dss,"__version__") else "n/a",
        python=platform.python_version(), homes=len(m["homes"]), pv_units=len(m["pv"]),
        homes_by_phase=[sum(1 for h in m["homes"] if h[1]==p) for p in (1,2,3)], pv_by_phase=[sum(1 for i in m["pv"] if m["homes"][i][1]==p) for p in (1,2,3)],
        hand_calc=chk, max_power_balance_residual_kW=round(maxres,4), converged_all_steps=True,
        v_max_pu=round(float(vmax),3), v_min_pu=round(float(vmin),3), hours_above_limit=hi, hours_below_limit=lo,
        peak_trafo_kVA=round(float(df.trafo_kVA.max()),1), peak_trafo_loading_pct=round(float(df.trafo_loading_pct.max()),1),
        reverse_flow_hours=float((df.trafo_kW<0).sum()/4), reverse_flow_energy_kWh=round(float(-df.trafo_kW.clip(upper=0).sum()/4),1),
        peak_line_current_A=round(float(df[icols].max().max()),1), peak_line_loading_pct=round(100*float(df[icols].max().max())/CFG["ampacity_a"],1),
        total_demand_kWh=round(float(df.demand_kW.sum()/4),1), total_pv_kWh=round(float(df.pv_kW.sum()/4),1))
    json.dump(summ, open(os.path.join(R,"stage1_summary.json"),"w"), indent=2)
    with open(os.path.join(ROOT,"config","parameter_register.csv"),"w",newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter","Value","Unit","Source type","Source","Reason","Sensitivity range","Version"])
        for r in REGISTER: w.writerow(list(r)+[MODEL_VERSION])
    # ---- plots ----
    fig, axs = plt.subplots(3, 2, figsize=(14, 12)); cols = ["#B84A4A","#E8A33D","#2B6CA0"]
    for ph in range(3):
        for n in nodes: axs[0,0].plot(df.hour, df[f"V_{n}_{'ABC'[ph]}_pu"], c=cols[ph], lw=0.8, alpha=0.7)
    axs[0,0].axhline(CFG["v_hi"],c="k",ls="--",lw=1); axs[0,0].axhline(CFG["v_lo"],c="k",ls="--",lw=1)
    axs[0,0].set_title("Voltage, all 10 nodes x 3 phases (red A, amber B, blue C)"); axs[0,0].set_ylabel("pu")
    axs[0,1].plot(df.hour, df.trafo_loading_pct, c="#1F7A7A"); axs[0,1].axhline(100,c="k",ls="--",lw=1)
    axs[0,1].set_title("Transformer loading (% of 250 kVA)"); axs[0,1].set_ylabel("%")
    for fn in CFG["feeders"]:
        head = f"{fn}_{CFG['feeders'][fn][0]}"
        for ph in range(3): axs[1,0].plot(df.hour, df[f"I_{head}_{'ABC'[ph]}_A"], c=cols[ph], ls="-" if fn=="F1" else ":", label=f"{fn} {'ABC'[ph]}")
    axs[1,0].axhline(CFG["ampacity_a"],c="k",ls="--",lw=1); axs[1,0].legend(fontsize=7, ncol=2); axs[1,0].set_title("Feeder head phase currents vs assumed ampacity"); axs[1,0].set_ylabel("A")
    axs[1,1].plot(df.hour, df.trafo_kW, c="#2B6CA0"); axs[1,1].axhline(0,c="k",lw=1); axs[1,1].fill_between(df.hour, df.trafo_kW, 0, where=df.trafo_kW<0, color="#B84A4A", alpha=.4)
    axs[1,1].set_title("Net power at transformer (below zero = reverse flow)"); axs[1,1].set_ylabel("kW")
    axs[2,0].plot(df.hour, df.demand_kW, c="#E8A33D", label="home demand"); axs[2,0].plot(df.hour, df.pv_kW, c="#4A9060", label="PV generation"); axs[2,0].legend(); axs[2,0].set_title("PV generation vs home demand"); axs[2,0].set_ylabel("kW")
    seg = df[[c for c in icols]].max().groupby(lambda c: c.split("_")[1]+"_"+c.split("_")[2]).max()
    lbls = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]
    axs[2,1].bar(range(len(lbls)), [100*df[[f"I_{l}_{p}_A" for p in 'ABC']].max().max()/CFG["ampacity_a"] for l in lbls], color="#1F7A7A")
    axs[2,1].set_xticks(range(len(lbls))); axs[2,1].set_xticklabels(lbls, rotation=45, fontsize=7); axs[2,1].set_title("Cable-segment peak loading (% of assumed ampacity)"); axs[2,1].set_ylabel("%")
    for a in axs.flat[:5]: a.set_xlabel("hour of day"); a.grid(alpha=.3)
    fig.suptitle("LocalFlex Grid - Stage 1, Case A0 (no control, fixed PV) - synthetic network, assumed values", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(R, "stage1_caseA0_overview.png"), dpi=140)
    print(json.dumps(summ, indent=2))
if __name__ == "__main__": main()
