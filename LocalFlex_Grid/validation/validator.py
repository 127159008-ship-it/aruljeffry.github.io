"""Stage 4: electrical validator ('referee'). Works on any time-series DataFrame with the Stage 3 column layout, so the
same code can later check a controller's proposed dispatch after an OpenDSS solve. Every violation carries its location."""
import numpy as np, pandas as pd

def _cols(df):
    v = [c for c in df if c.startswith("V_") and c.endswith("_pu")]
    ip = [c for c in df if c.startswith("I_") and c.endswith("_A") and not c.endswith("_N_A")]
    inn = [c for c in df if c.startswith("I_") and c.endswith("_N_A")]
    return v, ip, inn

def _loc_v(c):   # V_a1_A_pu -> "a1/A"
    p = c.split("_"); return f"{p[1]}/{p[2]}"
def _loc_i(c):   # I_F1_a1_A_A -> "F1_a1/A" ; I_F1_a1_N_A -> "F1_a1/N"
    p = c.split("_"); return f"{p[1]}_{p[2]}/{p[3]}"

def validate(df, cfg, export_cap_kw=None, dt_h=0.25):
    """Return (steps, events). steps: one row per time step with min/max values, WHERE, violation flags, PASS/FAIL."""
    v, ip, inn = _cols(df); n = len(df)
    V = df[v].values; Ip = df[ip].values; In = df[inn].values
    hi, lo, amp, namp = cfg["v_hi"], cfg["v_lo"], cfg["ampacity_a"], cfg["neutral_ampacity_a"]
    conv = df["converged"].values if "converged" in df else np.ones(n, bool)
    s = pd.DataFrame({"hour": df["hour"].values})
    s["v_max_pu"] = V.max(axis=1); s["v_max_where"] = [_loc_v(v[j]) for j in V.argmax(axis=1)]
    s["v_min_pu"] = V.min(axis=1); s["v_min_where"] = [_loc_v(v[j]) for j in V.argmin(axis=1)]
    s["n_overvoltage_nodes_phases"] = (V > hi).sum(axis=1); s["n_undervoltage_nodes_phases"] = (V < lo).sum(axis=1)
    s["phase_current_max_A"] = Ip.max(axis=1); s["phase_current_where"] = [_loc_i(ip[j]) for j in Ip.argmax(axis=1)]
    s["phase_current_pct"] = 100*s.phase_current_max_A/amp
    s["neutral_current_max_A"] = In.max(axis=1); s["neutral_current_where"] = [_loc_i(inn[j]) for j in In.argmax(axis=1)]
    s["neutral_current_pct"] = 100*s.neutral_current_max_A/namp
    s["trafo_loading_pct"] = df["trafo_loading_pct"].values; s["reverse_flow_kW"] = (-df["trafo_kW"]).clip(lower=0).values
    # energy accounting: curtailment is physical only if >= 0; raw residual is logged separately
    raw = (df["pv_avail_kW"] - df["pv_kW"]).values
    s["pv_available_kW"] = df["pv_avail_kW"].values; s["pv_delivered_kW"] = df["pv_kW"].values
    s["pv_curtailed_kW"] = np.clip(raw, 0, None); s["pv_accounting_residual_kW"] = np.where(raw < 0, raw, 0.0)
    s["demand_kW"] = df["demand_kW"].values; s["losses_kW"] = df["losses_kW"].values; s["power_balance_residual_kW"] = df["balance_residual_kW"].values
    s["converged"] = conv
    s["viol_voltage"] = (s.n_overvoltage_nodes_phases > 0) | (s.n_undervoltage_nodes_phases > 0)
    s["viol_phase_current"] = s.phase_current_pct > 100; s["viol_neutral_current"] = s.neutral_current_pct > 100
    s["viol_transformer"] = s.trafo_loading_pct > 100
    s["viol_export_cap"] = (s.reverse_flow_kW > export_cap_kw) if export_cap_kw is not None else False
    s["viol_energy_balance"] = s.power_balance_residual_kW.abs() > 0.05
    s["viol_convergence"] = ~s.converged
    flags = ["viol_voltage","viol_phase_current","viol_neutral_current","viol_transformer","viol_export_cap","viol_energy_balance","viol_convergence"]
    s["status"] = np.where(s[flags].any(axis=1), "FAIL", "PASS")
    s["decision"] = [decide(r) for r in s[flags].to_dict("records")]
    # --- events: contiguous runs per location ---
    ev = []
    def runs(mask, label, loc, vals, kind):
        j = 0
        while j < n:
            if mask[j]:
                k = j
                while k + 1 < n and mask[k+1]: k += 1
                ev.append(dict(type=label, location=loc, start_hour=float(df.hour[j]), end_hour=float(df.hour[k]) + dt_h,
                               duration_h=(k - j + 1)*dt_h, peak=float(vals[j:k+1].max() if kind == "max" else vals[j:k+1].min())))
                j = k + 1
            else: j += 1
    for i, c in enumerate(v):
        runs(V[:, i] > hi, "overvoltage", _loc_v(c), V[:, i], "max"); runs(V[:, i] < lo, "undervoltage", _loc_v(c), V[:, i], "min")
    for i, c in enumerate(ip): runs(Ip[:, i] > amp, "phase_current", _loc_i(c), Ip[:, i], "max")
    for i, c in enumerate(inn): runs(In[:, i] > namp, "neutral_current", _loc_i(c), In[:, i], "max")
    runs((df["trafo_loading_pct"].values > 100), "transformer_overload", "transformer", df["trafo_loading_pct"].values, "max")
    return s, pd.DataFrame(ev, columns=["type","location","start_hour","end_hour","duration_h","peak"])

def decide(flags):
    """Placeholder for the PASS / REPAIR / FALLBACK logic that the controller will use from Stage 7 onward."""
    if flags["viol_convergence"]: return "FALLBACK"
    if flags["viol_energy_balance"]: return "FALLBACK"
    if any(flags[k] for k in ("viol_voltage","viol_phase_current","viol_neutral_current","viol_transformer","viol_export_cap")): return "REPAIR"
    return "PASS"

def self_test(df, cfg):
    """Inject known violations into a copy of clean-ish data and confirm the validator finds them with the right location/duration."""
    d = df.copy(); res = {}
    base_s, base_e = validate(d, cfg)
    d.loc[10:12, "V_b3_B_pu"] = 1.20            # 3 steps -> 0.75 h overvoltage at b3/B
    d.loc[20:20, "V_a2_C_pu"] = 0.85            # 1 step  -> 0.25 h undervoltage at a2/C
    d.loc[30:33, "I_F2_b2_N_A"] = 150.0         # 4 steps neutral overload at F2_b2/N
    d.loc[40:41, "trafo_loading_pct"] = 105.0   # 2 steps transformer overload
    d["converged"] = True; d.loc[50, "converged"] = False
    s, e = validate(d, cfg)
    def find(t, loc): r = e[(e.type == t) & (e.location == loc)]; return None if r.empty else (float(r.duration_h.iloc[0]), round(float(r.peak.iloc[0]), 2))
    res["overvoltage b3/B (expect 0.75 h, 1.2)"] = find("overvoltage", "b3/B")
    res["undervoltage a2/C (expect 0.25 h, 0.85)"] = find("undervoltage", "a2/C")
    res["neutral F2_b2/N (expect 1.0 h, 150)"] = find("neutral_current", "F2_b2/N")
    res["transformer (expect 0.5 h, 105)"] = find("transformer_overload", "transformer")
    res["step 50 decision (expect FALLBACK)"] = s.decision.iloc[50]
    res["step 10 where (expect b3/B)"] = s.v_max_where.iloc[10]
    ok = (res["overvoltage b3/B (expect 0.75 h, 1.2)"] == (0.75, 1.2) and res["undervoltage a2/C (expect 0.25 h, 0.85)"] == (0.25, 0.85)
          and res["neutral F2_b2/N (expect 1.0 h, 150)"] == (1.0, 150.0) and res["transformer (expect 0.5 h, 105)"] == (0.5, 105.0)
          and res["step 50 decision (expect FALLBACK)"] == "FALLBACK" and res["step 10 where (expect b3/B)"] == "b3/B")
    return ok, res
