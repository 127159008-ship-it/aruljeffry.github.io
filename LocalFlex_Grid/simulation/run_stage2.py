"""Stage 2: Case A0 on an explicit 3-phase 4-wire network (neutral conductor, neutral earthed at transformer)."""
import sys, os, json, csv, platform
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import opendssdirect as dss
from config.feeder_config import CFG, SEED, REGISTER, REGISTER_S2, SUPERSEDED_S2
from network.feeder_generator import build, write_dss_4wire
from profiles.household_demand import t, home_shape, solar_shape
R = os.path.join(ROOT, "results"); VB = CFG["kv_ll"]*1000/3**0.5; VER = "stage2-v0.2"
KVLN = CFG["kv_ll"]/3**0.5

def neutral_tests():
    """(a) balanced load -> neutral current ~ 0.  (b) single-phase load -> |In| = |Ia| and neutral-end voltage = Ia*|Znn - Zmn|*length."""
    out = {}
    def circuit(loads):
        c = dss.Command; c(f"set DefaultBaseFrequency={CFG['freq_hz']}"); c("clear")
        c(f"new circuit.t basekv={CFG['kv_ll']} pu=1.0 phases=3 bus1=s basefreq={CFG['freq_hz']}")
        r=CFG['r1']; xs,xm=CFG['x_self'],CFG['x_mutual']
        c(f"new linecode.lv4 nphases=4 rmatrix=({r} | 0 {r} | 0 0 {r} | 0 0 0 {CFG['r_n']}) xmatrix=({xs} | {xm} {xs} | {xm} {xm} {xs} | {xm} {xm} {xm} {xs}) units=km basefreq={CFG['freq_hz']}")
        c("new line.l bus1=s.1.2.3.0 bus2=e.1.2.3.4 phases=4 linecode=lv4 length=1 units=km")
        for ph in loads: c(f"new load.x{ph} bus1=e.{ph}.4 phases=1 kv={KVLN:.4f} kw=5 pf={CFG['pf']} model=1")
        c(f"set voltagebases=[{CFG['kv_ll']}]"); c("calcv"); c("solve")
        dss.Circuit.SetActiveElement("Line.l"); mag = dss.CktElement.CurrentsMagAng()[0:8:2]
        dss.Circuit.SetActiveBus("e"); V = dss.Bus.Voltages(); vn = abs(complex(V[6], V[7]))
        return mag, vn
    mag, vn = circuit([1,2,3]); out["balanced_neutral_current_A"] = round(float(mag[3]),3); out["balanced_phase_current_A"] = round(float(mag[0]),1)
    mag, vn = circuit([1]); out["single_phase_Ia_A"] = round(float(mag[0]),2); out["single_phase_In_A"] = round(float(mag[3]),2)
    znn = complex(CFG["r_n"], CFG["x_self"]) - complex(0, CFG["x_mutual"])
    out["neutral_end_voltage_sim_V"] = round(float(vn),2); out["neutral_end_voltage_hand_V"] = round(float(mag[0]*abs(znn)),2)
    return out

def main():
    chk = neutral_tests()
    m = build(CFG, SEED); dsspath = os.path.join(ROOT, "network", "localflex_stage2.dss"); write_dss_4wire(CFG, m, dsspath)
    dss.Command("clear"); dss.Command(f"redirect {dsspath}"); freq = dss.Solution.Frequency()
    nodes = m["nodes"]; lines = [f"{fn}_{n}" for fn, ns in CFG["feeders"].items() for n in ns]; rows = []; maxres = 0.0
    for k in range(CFG["steps"]):
        dss.Loads.First()
        while True:
            i = int(dss.Loads.Name()[1:]); dss.Loads.kW(m["scale"][i]*home_shape[k])
            if not dss.Loads.Next(): break
        dss.Generators.First()
        while True:
            dss.Generators.kW(CFG["pv_kw"]*solar_shape[k])
            if not dss.Generators.Next(): break
        dss.Solution.Solve(); assert dss.Solution.Converged(), f"no convergence at step {k}"
        row = {"hour": t[k]}
        for n in nodes:
            dss.Circuit.SetActiveBus(n); V = dss.Bus.Voltages(); nd = dss.Bus.Nodes(); z = {nd[j]: complex(V[2*j], V[2*j+1]) for j in range(len(nd))}
            for ph in range(3): row[f"V_{n}_{'ABC'[ph]}_pu"] = abs(z[ph+1]-z[4])/VB
            row[f"VN_{n}_V"] = abs(z[4])
        for ln in lines:
            dss.Circuit.SetActiveElement(f"Line.{ln}"); cur = dss.CktElement.CurrentsMagAng()[0:8:2]
            for ph in range(3): row[f"I_{ln}_{'ABC'[ph]}_A"] = cur[ph]
            row[f"I_{ln}_N_A"] = cur[3]
        dss.Circuit.SetActiveElement("Transformer.tr"); pw = dss.CktElement.Powers()[:6]
        P = sum(pw[0::2]); Q = sum(pw[1::2]); row.update(trafo_kW=P, trafo_kvar=Q, trafo_kVA=float(np.hypot(P,Q)), trafo_loading_pct=100*np.hypot(P,Q)/CFG["kva"])
        dem = 0.0; dss.Loads.First()
        while True:
            dem += sum(dss.CktElement.Powers()[0::2])
            if not dss.Loads.Next(): break
        pvk = 0.0; dss.Generators.First()
        while True:
            pvk += -sum(dss.CktElement.Powers()[0::2])
            if not dss.Generators.Next(): break
        loss = dss.Circuit.Losses()[0]/1000
        row.update(demand_kW=dem, pv_kW=pvk, losses_kW=loss, balance_residual_kW=P - (dem - pvk + loss))
        maxres = max(maxres, abs(row["balance_residual_kW"])); rows.append(row)
    df = pd.DataFrame(rows); df.to_csv(os.path.join(R, "stage2_caseA0_timeseries.csv"), index=False)
    vcols = [c for c in df if c.startswith("V_")]; pcols = [c for c in df if c.startswith("I_") and not c.endswith("_N_A")]; ncols = [c for c in df if c.endswith("_N_A")]; vncols = [c for c in df if c.startswith("VN_")]
    s1 = json.load(open(os.path.join(R, "stage1_summary.json")))
    summ = dict(model_version=VER, seed=SEED, freq_hz=freq, python=platform.python_version(), homes=len(m["homes"]), pv_units=len(m["pv"]),
        neutral_tests=chk, max_power_balance_residual_kW=round(maxres,4), converged_all_steps=True,
        v_max_pu=round(float(df[vcols].max().max()),3), v_min_pu=round(float(df[vcols].min().min()),3),
        hours_above_limit=float((df[vcols].max(axis=1)>CFG["v_hi"]).sum()/4), hours_below_limit=float((df[vcols].min(axis=1)<CFG["v_lo"]).sum()/4),
        peak_trafo_kVA=round(float(df.trafo_kVA.max()),1), peak_trafo_loading_pct=round(float(df.trafo_loading_pct.max()),1),
        reverse_flow_hours=float((df.trafo_kW<0).sum()/4), reverse_flow_energy_kWh=round(float(-df.trafo_kW.clip(upper=0).sum()/4),1),
        peak_phase_current_A=round(float(df[pcols].max().max()),1), peak_phase_loading_pct=round(100*float(df[pcols].max().max())/CFG["ampacity_a"],1),
        peak_neutral_current_A=round(float(df[ncols].max().max()),1), peak_neutral_loading_pct=round(100*float(df[ncols].max().max())/CFG["neutral_ampacity_a"],1),
        peak_neutral_to_earth_V=round(float(df[vncols].max().max()),1), peak_neutral_to_earth_pct_of_phase=round(100*float(df[vncols].max().max())/VB,1),
        total_demand_kWh=round(float(df.demand_kW.sum()/4),1), total_pv_kWh=round(float(df.pv_kW.sum()/4),1),
        stage1_for_comparison={k: s1[k] for k in ("v_max_pu","v_min_pu","hours_above_limit","hours_below_limit","peak_trafo_loading_pct","reverse_flow_energy_kWh","peak_line_loading_pct")})
    json.dump(summ, open(os.path.join(R,"stage2_summary.json"),"w"), indent=2)
    with open(os.path.join(ROOT,"config","parameter_register.csv"),"w",newline="") as f:
        w = csv.writer(f); w.writerow(["Parameter","Value","Unit","Source type","Source","Reason","Sensitivity range","Version"])
        for r in REGISTER:
            if r[0] in SUPERSEDED_S2: w.writerow(list(r)+["stage1-v0.1 (SUPERSEDED in stage2)"])
            else: w.writerow(list(r)+["stage1-v0.1"])
        for r in REGISTER_S2: w.writerow(list(r)+[VER])
    d1 = pd.read_csv(os.path.join(R,"stage1_caseA0_timeseries.csv")); cols = ["#B84A4A","#E8A33D","#2B6CA0"]
    fig, axs = plt.subplots(4, 2, figsize=(14, 17))
    for ph in range(3):
        for n in nodes: axs[0,0].plot(df.hour, df[f"V_{n}_{'ABC'[ph]}_pu"], c=cols[ph], lw=.8, alpha=.7)
    axs[0,0].axhline(CFG["v_hi"],c="k",ls="--",lw=1); axs[0,0].axhline(CFG["v_lo"],c="k",ls="--",lw=1); axs[0,0].set_title("Phase-to-neutral voltage, all 10 nodes x 3 phases"); axs[0,0].set_ylabel("pu")
    axs[0,1].plot(d1.hour, d1[[f"V_{n}_A_pu" for n in nodes]].max(axis=1), c="#999", label="Stage 1 (3-wire, ideal neutral)"); axs[0,1].plot(df.hour, df[[f"V_{n}_A_pu" for n in nodes]].max(axis=1), c="#B84A4A", label="Stage 2 (explicit neutral)")
    axs[0,1].plot(d1.hour, d1[[f"V_{n}_A_pu" for n in nodes]].min(axis=1), c="#999"); axs[0,1].plot(df.hour, df[[f"V_{n}_A_pu" for n in nodes]].min(axis=1), c="#B84A4A")
    axs[0,1].axhline(CFG["v_hi"],c="k",ls="--",lw=1); axs[0,1].axhline(CFG["v_lo"],c="k",ls="--",lw=1); axs[0,1].legend(fontsize=8); axs[0,1].set_title("Phase A highest and lowest voltage: Stage 1 vs Stage 2"); axs[0,1].set_ylabel("pu")
    for fn in CFG["feeders"]:
        head = f"{fn}_{CFG['feeders'][fn][0]}"; ls = "-" if fn=="F1" else ":"
        for ph in range(3): axs[1,0].plot(df.hour, df[f"I_{head}_{'ABC'[ph]}_A"], c=cols[ph], ls=ls, lw=1, label=f"{fn} {'ABC'[ph]}")
        axs[1,0].plot(df.hour, df[f"I_{head}_N_A"], c="k", ls=ls, lw=1.8, label=f"{fn} neutral")
    axs[1,0].axhline(CFG["ampacity_a"],c="k",ls="--",lw=.8); axs[1,0].axhline(CFG["neutral_ampacity_a"],c="#555",ls="-.",lw=.8)
    axs[1,0].legend(fontsize=6, ncol=4); axs[1,0].set_title("Feeder-head phase and neutral currents (dashed: phase / neutral ampacity)"); axs[1,0].set_ylabel("A")
    for n in ("a1","a5","b1","b5"): axs[1,1].plot(df.hour, df[f"VN_{n}_V"], label=n)
    axs[1,1].legend(fontsize=8); axs[1,1].set_title("Neutral-to-earth voltage"); axs[1,1].set_ylabel("V")
    axs[2,0].plot(df.hour, df.trafo_loading_pct, c="#1F7A7A"); axs[2,0].axhline(100,c="k",ls="--",lw=1); axs[2,0].set_title("Transformer loading (% of 250 kVA)"); axs[2,0].set_ylabel("%")
    axs[2,1].plot(df.hour, df.trafo_kW, c="#2B6CA0"); axs[2,1].axhline(0,c="k",lw=1); axs[2,1].fill_between(df.hour, df.trafo_kW, 0, where=df.trafo_kW<0, color="#B84A4A", alpha=.4); axs[2,1].set_title("Net power at transformer (below zero = reverse flow)"); axs[2,1].set_ylabel("kW")
    axs[3,0].plot(df.hour, df.demand_kW, c="#E8A33D", label="home demand"); axs[3,0].plot(df.hour, df.pv_kW, c="#4A9060", label="PV generation"); axs[3,0].legend(); axs[3,0].set_title("PV generation vs home demand"); axs[3,0].set_ylabel("kW")
    x = np.arange(len(lines)); pk = [100*df[[f"I_{l}_{p}_A" for p in 'ABC']].max().max()/CFG["ampacity_a"] for l in lines]; nk = [100*df[f"I_{l}_N_A"].max()/CFG["neutral_ampacity_a"] for l in lines]
    axs[3,1].bar(x-.2, pk, .4, label="phase (% of 200 A)", color="#1F7A7A"); axs[3,1].bar(x+.2, nk, .4, label="neutral (% of 100 A)", color="#333"); axs[3,1].set_xticks(x); axs[3,1].set_xticklabels(lines, rotation=45, fontsize=7); axs[3,1].legend(fontsize=8); axs[3,1].set_title("Cable-segment peak loading"); axs[3,1].set_ylabel("%")
    for a in axs.flat: a.grid(alpha=.3)
    for a in axs.flat[[0,1,2,3,4,5,6]]: a.set_xlabel("hour of day")
    fig.suptitle("LocalFlex Grid - Stage 2, Case A0 (no control, fixed PV), 4-wire network - synthetic, assumed values", fontsize=12)
    fig.tight_layout(); fig.savefig(os.path.join(R, "stage2_caseA0_overview.png"), dpi=130)
    print(json.dumps(summ, indent=2))
if __name__ == "__main__": main()
