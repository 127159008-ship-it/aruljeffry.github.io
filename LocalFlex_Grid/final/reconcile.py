"""Energy-accounting reconciliation (explicit final test).
  generation(PV delivered) + grid import + battery discharge = loads + grid export + battery charge + feeder/transformer losses
Signs: P_trafo>0 import. Battery in the network model is a signed load (charge >0)."""
import numpy as np
TOL_KWH = 0.5          # documented tolerance per 32 h run: OpenDSS convergence tolerance (1e-4 pu) x ~90 kW  -> well below 0.5 kWh; observed residuals ~0.1 kWh
def reconcile(df, dv, dt=0.25):
    P = df.trafo_kW.values; pv = df.pv_kW.values; avail = df.pv_avail_kW.values; loss = df.losses_kW.values
    bat = dv.P_BATT_kW.values; chg = np.clip(bat, 0, None); dis = np.clip(-bat, 0, None); load_all = df.demand_kW.values; load = load_all - bat
    imp = np.clip(P, 0, None); exp = np.clip(-P, 0, None)
    lhs = (pv + imp + dis).sum()*dt; rhs = (load + exp + chg + loss).sum()*dt; res = lhs - rhs
    curt_raw = avail - pv
    return dict(E_pv_delivered_kWh=pv.sum()*dt, E_import_kWh=imp.sum()*dt, E_batt_discharge_kWh=dis.sum()*dt, E_load_kWh=load.sum()*dt, E_export_kWh=exp.sum()*dt, E_batt_charge_kWh=chg.sum()*dt,
                E_losses_kWh=loss.sum()*dt, energy_balance_residual_kWh=res, energy_balance_rel=abs(res)/max(lhs, 1e-9), energy_balance_ok=bool(abs(res) < TOL_KWH),
                pv_raw_curtail_min_kW=float(curt_raw.min()), pv_available_kWh=avail.sum()*dt, pv_curtailed_physical_kWh=float(np.clip(curt_raw, 0, None).sum()*dt),
                pv_accounting_residual_kWh=float((avail - pv - curt_raw).sum()*dt), pv_negative_curtail_raw_kWh=float(np.clip(-curt_raw, 0, None).sum()*dt))
def more_metrics(df, dv, dt=0.25):
    """Additional final-spec metrics computed from the 128-step window time series."""
    P = df.trafo_kW.values; vc = [c for c in df if c.startswith("V_") and c.endswith("_pu")]; nodes = sorted({c.split("_")[1] for c in vc}); un = 0.0
    for n in nodes:
        a = df[[f"V_{n}_{p}_pu" for p in "ABC"]].values; un = max(un, float(((a.max(axis=1) - a.min(axis=1))/a.mean(axis=1)).max()*100))
    vn = [c for c in df if c.startswith("VN_")]; out = dict(reverse_flow_hours=float((P < 0).sum()*dt), peak_import_kW=float(P.max()), peak_export_kW=float(max(-P.min(), 0.0)), feeder_losses_kWh=float(df.losses_kW.sum()*dt),
        neutral_to_earth_V_max=float(df[vn].values.max()), phase_voltage_unbalance_pct_max=un, peak_trafo_kVA=float(df.trafo_kVA.max()), import_energy_kWh=float(np.clip(P, 0, None).sum()*dt), export_energy_kWh=float(np.clip(-P, 0, None).sum()*dt),
        batt_soc_1700_pct=float(dv.SoC_BATT_pct.iloc[68]), batt_soc_min_pct=float(dv.SoC_BATT_pct.min()), batt_soc_max_pct=float(dv.SoC_BATT_pct.max()))
    lv = [c for c in dv if c.startswith("level_")]; pc = [c for c in dv if c.startswith("P_PUMP")]; wc = [c for c in dv if c.startswith("P_WH")]; ec = [c for c in dv if c.startswith("P_EV")]
    out.update(tank_min_pct=float(dv[lv].values.min()), tank_max_pct=float(dv[lv].values.max()), pump_energy_kWh=float(dv[pc].values.sum()*dt), heater_energy_kWh=float(dv[wc].values.sum()*dt), ev_energy_kWh=float(dv[ec].values.sum()*dt))
    return out
