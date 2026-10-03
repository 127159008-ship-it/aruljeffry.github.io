"""Battery-size requirement check, cost model, emissions, reinforcement comparison. Requirements are fixed BEFORE looking at results (below) and applied identically to every size.
REQUIREMENTS (per scenario, relative to the no-control Case A of the same scenario/seed, window 32 h):
  Q1 voltage violation magnitude (under+over pu-h) <= 50 % of A          Q2 transformer peak <= 100 % and <= A
  Q3 EV unmet <= 1.0 kWh and unmet water = 0                            Q4 PV curtailed <= 5 % of available
  Q5 evening reserve: battery SoC at 17:00 >= 40 % of nominal energy  (the planner's own reserve target)
All thresholds are prototype definitions, not standards."""
import sys, os, json
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from final.economics import annual_cost, reinforcement_cost, emissions, EMISSION, UNIT
OUT = os.path.join(ROOT, "results", "final")
def check(d, A):
    vm = d.under_pu_h + d.over_pu_h; vA = A.under_pu_h + A.over_pu_h
    q = dict(Q1_voltage=bool(vm <= 0.5*vA + 1e-9), Q2_transformer=bool(d.peak_trafo_loading_pct <= 100 and d.peak_trafo_loading_pct <= A.peak_trafo_loading_pct + 1e-9), Q3_service=bool(d.ev_unmet_at_departure_kWh <= 1.0 and d.unmet_water_m3 <= 1e-9),
             Q4_curtail=bool(d.curtailment_pct <= 5.0), Q5_reserve=bool(d.get("batt_soc_1700_pct", np.nan) >= 40.0*d.batt_kwh/100.0 - 1e-6) if "batt_soc_1700_pct" in d else None)
    q["all_met"] = all(v for v in q.values() if v is not None); return q
def sizing():
    p = os.path.join(OUT, "battery_size.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p); d = d[d.ok == True]; rows = []
    for scn in ("clear", "high_demand"):
        A = d[(d.scenario == scn) & (d.variant == "A")].iloc[0]
        for _, r in d[(d.scenario == scn) & (d.variant != "A")].iterrows():
            q = check(r, A); rows.append(dict(scenario=scn, variant=r.variant, battery_only=bool(r.get("battery_only", False)), batt_kwh=r.batt_kwh, batt_kw=r.batt_kw, **q, voltage_pu_h=round(r.under_pu_h+r.over_pu_h, 3), A_voltage_pu_h=round(A.under_pu_h+A.over_pu_h, 3), trafo_pct=r.peak_trafo_loading_pct, ev_unmet=r.ev_unmet_at_departure_kWh, curtail_pct=r.curtailment_pct))
    T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "battery_sizing", "requirement_check.csv"), index=False); return T
def smallest(T, battery_only, kw=50):
    t = T[(T.battery_only == battery_only) & (T.batt_kw == kw)]; res = {}
    for kwh, g in t.groupby("batt_kwh"): res[kwh] = bool(g.all_met.all()) if len(g) == 2 else None
    ok = sorted(k for k, v in res.items() if v); return (ok[0] if ok else None), res
def economics():
    S = pd.read_csv(os.path.join(OUT, "final_summary_core.csv")); T = sizing(); out = dict(assumptions="ALL COST INPUTS ARE PLACEHOLDERS (final/economics.py UNIT); see standards_audit", unit=UNIT)
    n_sw = 4*8 + 2 + 2*6           # heater units + pumps + EV charge points controlled
    lf = annual_cost(100, 50, n_sw); lf2 = annual_cost(133, 50, n_sw, second_life=True); out["localflex_new_100kWh_50kW"] = lf; out["localflex_second_life_133kWh_nominal"] = lf2; out["transformer_upgrade_250_to_400kVA"] = reinforcement_cost()
    if T is not None:
        s_lf, r_lf = smallest(T, False); s_bo, r_bo = smallest(T, True); out["smallest_battery_meeting_requirements_LocalFlex_kWh"] = s_lf; out["smallest_battery_meeting_requirements_battery_only_kWh"] = s_bo; out["requirement_pass_by_size_LocalFlex"] = r_lf; out["requirement_pass_by_size_battery_only"] = r_bo
        kb = s_bo if s_bo else 200; out["battery_only_cost_at_size"] = annual_cost(kb, 50, 0); out["battery_only_size_note"] = "smallest size meeting requirements" if s_bo else "NO tested size (<=200 kWh) met all requirements; cost shown for 200 kWh (lower bound)"
        if s_lf: out["localflex_cost_at_smallest_size"] = annual_cost(s_lf, 50, n_sw)
    im = S[S.variant.isin(["A", "C", "D"])].groupby(["scenario", "variant"]).import_energy_kWh.mean().unstack(); exp = S[S.variant.isin(["A", "C", "D"])].groupby(["scenario", "variant"]).export_energy_kWh.mean().unstack()
    em = {}
    for s in im.index:
        for v in ("C", "D"): net_a = im.loc[s, "A"] - exp.loc[s, "A"]; net_v = im.loc[s, v] - exp.loc[s, v]; em[f"{s}|{v}"] = emissions(float(im.loc[s, "A"]), float(im.loc[s, v])); em[f"{s}|{v}"]["net_import_after_losses_A_minus_export"] = float(net_a); em[f"{s}|{v}"]["net_import_after_losses_variant_minus_export"] = float(net_v)
    out["emissions_per_32h_window"] = em; out["emission_factor"] = EMISSION
    json.dump(out, open(os.path.join(OUT, "cost_emissions.json"), "w"), indent=1, default=str); return out
if __name__ == "__main__": economics(); print("ok")
