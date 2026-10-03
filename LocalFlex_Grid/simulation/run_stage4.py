"""Stage 4: run the electrical validator on the frozen A0 and A1 reference cases and report WHERE and WHEN limits are violated."""
import sys, os, json
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from config.feeder_config import CFG
from validation.validator import validate, self_test
R = os.path.join(ROOT, "results")

def main():
    a0 = pd.read_csv(os.path.join(R,"stage3_A0_timeseries.csv")); a1 = pd.read_csv(os.path.join(R,"stage3_A1_timeseries.csv"))
    ok, tres = self_test(a0, CFG); assert ok, tres
    out = dict(validator_self_test="PASS", self_test_detail={k: str(v) for k, v in tres.items()}, limits=dict(v_hi=CFG["v_hi"], v_lo=CFG["v_lo"], phase_ampacity_A=CFG["ampacity_a"], neutral_ampacity_A=CFG["neutral_ampacity_a"], transformer_pct=100, note="all limits are assumptions"))
    res = {}
    for name, d in (("A0", a0), ("A1", a1)):
        s, e = validate(d, CFG); s.to_csv(os.path.join(R, f"stage4_{name}_steps.csv"), index=False); e.to_csv(os.path.join(R, f"stage4_{name}_events.csv"), index=False); res[name] = (s, e)
        ov = e[e.type=="overvoltage"]; uv = e[e.type=="undervoltage"]
        out[name] = dict(steps_pass=int((s.status=="PASS").sum()), steps_fail=int((s.status=="FAIL").sum()),
            decisions=s.decision.value_counts().to_dict(),
            overvoltage_node_phases=int(ov.location.nunique()), undervoltage_node_phases=int(uv.location.nunique()),
            worst_overvoltage=None if ov.empty else dict(location=ov.loc[ov.peak.idxmax(),"location"], pu=round(float(ov.peak.max()),3)),
            worst_undervoltage=None if uv.empty else dict(location=uv.loc[uv.peak.idxmin(),"location"], pu=round(float(uv.peak.min()),3)),
            phase_current_events=int((e.type=="phase_current").sum()), neutral_current_events=int((e.type=="neutral_current").sum()), transformer_overload_events=int((e.type=="transformer_overload").sum()),
            reverse_flow_hours=float((s.reverse_flow_kW>0).sum()/4), pv_available_kWh=round(float(s.pv_available_kW.sum()/4),1), pv_delivered_kWh=round(float(s.pv_delivered_kW.sum()/4),1),
            pv_curtailed_kWh_clamped=round(float(s.pv_curtailed_kW.sum()/4),1), pv_accounting_residual_kWh=round(float(s.pv_accounting_residual_kW.sum()/4),2),
            max_power_balance_residual_kW=round(float(s.power_balance_residual_kW.abs().max()),4))
    json.dump(out, open(os.path.join(R,"stage4_summary.json"),"w"), indent=2)
    # --- where/when plots ---
    nodes = [f"{f}{i}" for f in "ab" for i in range(1,6)]; fig, axs = plt.subplots(2, 3, figsize=(15, 8))
    for r_i, name in enumerate(("A0","A1")):
        s, e = res[name]
        for c_i, (typ, cm) in enumerate((("overvoltage","Reds"),("undervoltage","Blues"))):
            M = np.zeros((10,3))
            for _, row in e[e.type==typ].iterrows():
                nd, ph = row.location.split("/"); M[nodes.index(nd), "ABC".index(ph)] += row.duration_h
            im = axs[r_i,c_i].imshow(M, cmap=cm, aspect="auto", vmin=0, vmax=max(8, M.max()))
            axs[r_i,c_i].set_xticks(range(3)); axs[r_i,c_i].set_xticklabels(["A","B","C"]); axs[r_i,c_i].set_yticks(range(10)); axs[r_i,c_i].set_yticklabels(nodes)
            for (y,x),v in np.ndenumerate(M):
                if v>0: axs[r_i,c_i].text(x,y,f"{v:.1f}",ha="center",va="center",fontsize=7)
            axs[r_i,c_i].set_title(f"{name}: hours of {typ} (node x phase)")
        flags = ["viol_voltage","viol_phase_current","viol_neutral_current","viol_transformer","viol_energy_balance","viol_convergence"]
        for j, f in enumerate(flags): axs[r_i,2].fill_between(s.hour, j, j+0.8, where=s[f].values.astype(bool), step="post", color="#B84A4A", linewidth=0)
        axs[r_i,2].set_yticks([j+.4 for j in range(len(flags))]); axs[r_i,2].set_yticklabels([f.replace("viol_","") for f in flags], fontsize=8); axs[r_i,2].set_xlabel("hour of day"); axs[r_i,2].set_title(f"{name}: violation timeline (red = violated)")
    fig.suptitle("LocalFlex Grid - Stage 4 electrical validator on frozen A0 / A1 (assumed limits)", fontsize=12); fig.tight_layout(); fig.savefig(os.path.join(R,"stage4_validation_A0_A1.png"), dpi=130)
    print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
