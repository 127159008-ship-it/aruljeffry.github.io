"""Forecast layer evidence: expected / low / high PV and demand forecasts vs actual, with MAE, RMSE, MAPE (daytime PV only), bias and interval coverage.
IMPORTANT: forecasts are SYNTHETIC (smoothed truth x AR(1) error, sigma PV 15 %, demand 8 %): metrics describe the synthetic error model, not a real forecaster."""
import sys, os
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "simulation"))
from config.feeder_config import CFG, SEED, SCENARIOS
from network.feeder_generator import build
from profiles.scenarios import household_profiles, pv_availability
from control.mpc import make_forecast, PLAN
Z80 = 1.2816
def metrics_for(scn, seed, m=None, sig_scale=1.0):
    m = m or build(CFG, SEED); pvn = [m["homes"][i][0] for i in m["pv"]]; ds, sm, _ = SCENARIOS[scn]; dem = household_profiles(m["scale"], seed, ds).sum(axis=1); pv = pv_availability(sm, seed, pvn).sum(axis=1)
    P = dict(PLAN); P["pv_fc_sigma"] *= sig_scale; P["dem_fc_sigma"] *= sig_scale; fd, fp = make_forecast(dem, pv, seed, P=P); fd, fp = fd[:96], fp[:96]
    rows = []
    for name, act, fc, sig in (("PV_kW", pv, fp, P["pv_fc_sigma"]), ("demand_kW", dem, fd, P["dem_fc_sigma"])):
        lo, hi = fc*(1-Z80*sig), fc*(1+Z80*sig); e = fc-act; day = act > 0.05*max(act.max(), 1e-9) if name == "PV_kW" else np.ones(96, bool)
        rows.append(dict(scenario=scn, seed=seed, quantity=name, MAE_kW=np.abs(e).mean(), RMSE_kW=np.sqrt((e**2).mean()), bias_kW=e.mean(), MAPE_pct=100*np.mean(np.abs(e[day])/np.maximum(act[day], 1e-9)),
                         coverage_80pct_band=100*np.mean((act >= lo) & (act <= hi)), mean_actual_kW=act.mean(), energy_actual_kWh=act.sum()*.25, energy_forecast_kWh=fc.sum()*.25))
    return rows
def main():
    m = build(CFG, SEED); rows = [r for scn in SCENARIOS for seed in (7, 11, 23, 42) for r in metrics_for(scn, seed, m)]
    d = pd.DataFrame(rows).round(3); d.to_csv(os.path.join(ROOT, "results", "final_forecast_metrics.csv"), index=False)
    print(d.groupby(["scenario", "quantity"])[["MAE_kW", "RMSE_kW", "bias_kW", "MAPE_pct", "coverage_80pct_band"]].mean().round(2))
if __name__ == "__main__": main()
