import React, { useEffect, useState } from "react";
import { LineChart } from "./components_charts.jsx";
import { api } from "./api.js";
import { f } from "./lib.js";

export const PRESETS = { Chennai: [13.0827, 80.2707], Madurai: [9.9252, 78.1198], Bengaluru: [12.9716, 77.5946], Hyderabad: [17.385, 78.4867], Mumbai: [19.076, 72.8777], Delhi: [28.6139, 77.209], Jaipur: [26.9124, 75.7873], Kolkata: [22.5726, 88.3639], Custom: null };

export default function Setup({ cfg, set, nasa, setNasa, busy, onRun, job, config }) {
  const [fl, setFl] = useState(null), [err, setErr] = useState(null), [fetching, setFetching] = useState(false), [showTable, setShowTable] = useState(false);
  useEffect(() => { const t = setTimeout(() => { api.fleet(cfg.pv_penetration, cfg.pv_kw_per_home).then(setFl).catch(() => {}); }, 200); return () => clearTimeout(t); }, [cfg.pv_penetration, cfg.pv_kw_per_home]);
  const fetchNasa = async () => {
    setErr(null); setFetching(true); setNasa(null);
    try { setNasa(await api.nasa({ latitude: +cfg.latitude, longitude: +cfg.longitude, date: cfg.date, pv_kw_per_home: +cfg.pv_kw_per_home })); } catch (e) { setErr(e.message); }
    setFetching(false);
  };
  const preset = (n) => { set({ preset: n }); if (PRESETS[n]) set({ latitude: PRESETS[n][0], longitude: PRESETS[n][1] }); setNasa(null); };
  const nasaOk = cfg.environment !== "nasa" || (nasa && nasa.date === cfg.date && +nasa.latitude === +cfg.latitude && +nasa.longitude === +cfg.longitude);
  return (
    <section className="panel setup" aria-label="Simulation setup">
      <h2>LOCALFLEX ENVIRONMENT</h2>
      <div className="seg-btn" role="group" aria-label="Irradiance source">
        <button className={cfg.environment === "nasa" ? "on" : ""} onClick={() => set({ environment: "nasa" })}>NASA POWER</button>
        <button className={cfg.environment === "synthetic" ? "on" : ""} onClick={() => set({ environment: "synthetic" })}>Synthetic day</button>
      </div>
      {cfg.environment === "synthetic" && (
        <label>Synthetic scenario<select value={cfg.synthetic_scenario} onChange={(e) => set({ synthetic_scenario: e.target.value })}>{Object.entries(config?.synthetic_scenarios || {}).map(([k, v]) => (<option key={k} value={k}>{k}: {v}</option>))}</select></label>
      )}
      {cfg.environment === "nasa" && (<>
        <label>Location<select value={cfg.preset} onChange={(e) => preset(e.target.value)}>{Object.keys(PRESETS).map((k) => (<option key={k}>{k}</option>))}</select></label>
        <div className="row2">
          <label>Latitude<input type="number" step="0.0001" value={cfg.latitude} onChange={(e) => { set({ latitude: e.target.value, preset: "Custom" }); setNasa(null); }} /></label>
          <label>Longitude<input type="number" step="0.0001" value={cfg.longitude} onChange={(e) => { set({ longitude: e.target.value, preset: "Custom" }); setNasa(null); }} /></label>
        </div>
        <label>Date (past day)<input type="date" value={cfg.date} max={new Date(Date.now() - 864e5).toISOString().slice(0, 10)} onChange={(e) => { set({ date: e.target.value }); setNasa(null); }} /></label>
        <button className="btn" disabled={fetching} onClick={fetchNasa}>{fetching ? "Fetching…" : "FETCH NASA POWER"}</button>
        {err && <p className="err" role="alert">{err}</p>}
        {nasa && (<div className="nasa">
          <p className="note">NASA POWER hourly GHI and 2 m temperature, shifted to local time (UTC{nasa.tz_offset_h >= 0 ? "+" : ""}{nasa.tz_offset_h}) and interpolated to 15 min. NASA gives irradiation, not electrical power: PV output below comes from the LocalFlex PV model (NOCT {nasa.pv_model.noct_c} °C, {nasa.pv_model.gamma_per_k * 100} %/K, derate {nasa.pv_model.derate}).</p>
          <LineChart title="GHI" unit="W/m²" height={110} hours={nasa.rows.map((r) => r.step / 4)} series={[{ label: "NASA GHI", color: "var(--accent)", values: nasa.rows.map((r) => r.ghi_Wm2) }]} />
          <LineChart title="PV output per array" unit="kW" height={110} hours={nasa.rows.map((r) => r.step / 4)} series={[{ label: `${cfg.pv_kw_per_home} kWp array`, color: "var(--case-d)", values: nasa.rows.map((r) => r.pv_kW_per_array) }]} />
          <button className="link" onClick={() => setShowTable(!showTable)}>{showTable ? "Hide" : "Show"} 15-min preview table</button>
          {showTable && (<div className="scroll tall"><table className="t"><thead><tr><th>Time</th><th>GHI W/m²</th><th>Temp °C</th><th>PV kW/array</th></tr></thead><tbody>{nasa.rows.filter((r) => r.ghi_Wm2 > 0 || r.step % 4 === 0).map((r) => (<tr key={r.step}><td>{r.time}</td><td className="mono">{f(r.ghi_Wm2, 0)}</td><td className="mono">{f(r.temp_C, 1)}</td><td className="mono">{f(r.pv_kW_per_array, 2)}</td></tr>))}</tbody></table></div>)}
        </div>)}
      </>)}
      <h3>Feeder and PV</h3>
      <label>PV penetration: <b>{cfg.pv_penetration} %</b><input type="range" min="0" max="100" step="5" value={cfg.pv_penetration} onChange={(e) => set({ pv_penetration: +e.target.value })} /></label>
      <div className="row2">
        <label>Homes<input type="number" value={100} disabled title="Only the validated 100-home feeder is available" /></label>
        <label>PV size per PV home (kWp)<input type="number" min="1" max="10" step="0.5" value={cfg.pv_kw_per_home} onChange={(e) => set({ pv_kw_per_home: +e.target.value })} /></label>
      </div>
      {fl && <p className="note mono">{fl.pv_penetration_requested_pct} % × {fl.homes} homes = {fl.pv_homes} PV homes ({fl.pv_by_phase.join("/")} on A/B/C, max {fl.homes_by_phase.join("/")}) × {fl.pv_kw_per_home} kWp = {fl.pv_kwp} kWp</p>}
      <details><summary>More settings</summary>
        <div className="row2">
          <label>Battery (kWh)<input type="number" min="10" max="1000" value={cfg.battery_kwh} onChange={(e) => set({ battery_kwh: +e.target.value })} /></label>
          <label>Battery (kW)<input type="number" min="5" max="500" value={cfg.battery_kw} onChange={(e) => set({ battery_kw: +e.target.value })} /></label>
        </div>
        <label>Demand scale<input type="number" step="0.05" min="0.5" max="1.6" value={cfg.demand_scale} onChange={(e) => set({ demand_scale: +e.target.value })} /></label>
      </details>
      <button className="btn primary" disabled={busy || !nasaOk} onClick={onRun}>{busy ? "RUNNING…" : "RUN SIMULATION"}</button>
      {!nasaOk && <p className="note">Fetch NASA POWER for this location and date first.</p>}
      {job && job.state !== "done" && (<div className="progress" role="status"><div className="bar"><i style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div><p className="note">{job.state}: {job.message}{job.elapsed_s ? ` · ${job.elapsed_s}s` : ""}{job.queue_position ? ` · queue ${job.queue_position}` : ""}. A run solves four cases with OpenDSS and a MILP planner; expect roughly {config?.typical_run_minutes ?? 4}+ minutes.</p></div>)}
      {job && job.state === "failed" && <p className="err" role="alert">{job.message}</p>}
    </section>
  );
}
