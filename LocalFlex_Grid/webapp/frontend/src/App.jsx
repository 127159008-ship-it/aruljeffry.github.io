import React, { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { CASES, CASE_COLOR, f, clock, busVoltages } from "./lib.js";
import SLD from "./SLD.jsx";
import Inspector from "./Inspector.jsx";
import MpcPanel from "./MpcPanel.jsx";
import Setup from "./Setup.jsx";
import Analysis from "./Analysis.jsx";
import { LineChart } from "./components_charts.jsx";

const DEFAULT = { environment: "nasa", preset: "Chennai", latitude: 13.0827, longitude: 80.2707, date: "2026-03-15", synthetic_scenario: "clear", pv_penetration: 40, pv_kw_per_home: 3, battery_kwh: 100, battery_kw: 50, demand_scale: 1.0 };

export default function App() {
  const [view, setView] = useState("twin"), [config, setConfig] = useState(null), [cfg, setCfgS] = useState(DEFAULT), [nasa, setNasa] = useState(null);
  const [job, setJob] = useState(null), [data, setData] = useState(null), [ctl, setCtl] = useState("D"), [k, setK] = useState(48), [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1), [bus, setBus] = useState("a4"), [msg, setMsg] = useState(null);
  const set = (p) => setCfgS((c) => ({ ...c, ...p }));
  const timer = useRef(null);
  useEffect(() => { api.config().then(setConfig).catch((e) => setMsg("Cannot reach the backend API: " + e.message)); }, []);
  useEffect(() => { api.demo().then((d) => { if (d.length && !data) loadJob(d[0].job_id, d[0].label); }).catch(() => {}); /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => setK((x) => (x >= 127 ? (setPlaying(false), 127) : x + 1)), 450 / speed);
    return () => clearInterval(timer.current);
  }, [playing, speed]);

  async function loadJob(id, label) {
    setMsg("Loading simulation…");
    try {
      const spec = await api.spec(id); const series = {};
      await Promise.all(Object.keys(CASES).map(async (c) => { series[c] = await api.series(id, c); }));
      const res = await api.results(id); setData({ id, spec, series, metrics: res.metrics, label: label || null }); setMsg(null);
    } catch (e) { setMsg("Could not load the simulation: " + e.message); }
  }
  async function run() {
    setMsg(null); setData(null);
    const body = { environment: cfg.environment, synthetic_scenario: cfg.synthetic_scenario, latitude: +cfg.latitude, longitude: +cfg.longitude, date: cfg.date, pv_penetration: cfg.pv_penetration, pv_kw_per_home: cfg.pv_kw_per_home, homes: 100, controller: ctl, battery_kwh: cfg.battery_kwh, battery_kw: cfg.battery_kw, demand_scale: cfg.demand_scale };
    try {
      const r = await api.start(body); setJob({ state: r.state, progress: 0, message: "submitted" });
      for (;;) {
        const s = await api.status(r.job_id); setJob(s);
        if (s.state === "done") { await loadJob(r.job_id); break; }
        if (s.state === "failed") break;
        await new Promise((res) => setTimeout(res, 3000));
      }
    } catch (e) { setJob({ state: "failed", message: e.message }); }
  }
  const busy = job && (job.state === "queued" || job.state === "running");
  const cs = data?.series[ctl], csA = data?.series.A, topo = data?.spec.topology;
  const derived = useMemo(() => {
    if (!data) return null; const out = {};
    for (const c of Object.keys(CASES)) {
      const s = data.series[c], nodes = Object.keys(topo.nodes);
      const mn = [], mx = [];
      for (let i = 0; i < s.n_steps; i++) { let lo = 9, hi = 0; for (const b of nodes) for (let p = 0; p < 3; p++) { const v = s.bus_voltage_pu[b][p][i]; if (v < lo) lo = v; if (v > hi) hi = v; } mn.push(lo); mx.push(hi); }
      const neutral = []; for (let i = 0; i < s.n_steps; i++) neutral.push(Math.max(...nodes.map((b) => s.segment_current_A[topo.nodes[b].segment][3][i])));
      out[c] = { vmin: mn, vmax: mx, neutral };
    }
    return out;
  }, [data]);
  const hours = cs ? cs.hour : [];
  const ghi = data?.spec.spec.irradiance_Wm2;
  const lim = topo?.limits;
  const sys = cs?.system;
  return (
    <div className="app">
      <header className="top">
        <div><h1>LocalFlex Grid <span>digital twin</span></h1><p className="sub">415 V 3Φ+N feeder · OpenDSS electrical authority · MPC proposes, OpenDSS validates, supervisor authorises. Simulation only, no hardware.</p></div>
        <nav className="tabs" role="tablist">
          <button role="tab" aria-selected={view === "twin"} className={view === "twin" ? "on" : ""} onClick={() => setView("twin")}>Digital Twin</button>
          <button role="tab" aria-selected={view === "analysis"} className={view === "analysis" ? "on" : ""} onClick={() => setView("analysis")}>Analysis</button>
        </nav>
      </header>
      {msg && <p className="banner" role="status">{msg}</p>}
      {view === "analysis" ? <Analysis limitations={config?.limitations} /> : (
        <main className="twin">
          <aside><Setup cfg={cfg} set={set} nasa={nasa} setNasa={setNasa} busy={busy} onRun={run} job={job} config={config} /></aside>
          <div className="stage">
            {!data && <section className="panel empty"><h2>No simulation loaded</h2><p>Choose a location and date (or a synthetic day), set the PV penetration and press <b>RUN SIMULATION</b>. The backend runs the real LocalFlex pipeline: PV model, OpenDSS, MPC, safety supervisor, OpenDSS again.</p></section>}
            {data && cs && (<>
              <section className="panel bar">
                <div className="ctl-row">
                  <div className="seg-btn" role="group" aria-label="Controller">
                    {Object.entries(CASES).map(([c, n]) => (<button key={c} className={ctl === c ? "on" : ""} onClick={() => setCtl(c)}><i style={{ background: CASE_COLOR[c] }} />{c} · {n}</button>))}
                  </div>
                  <div className="run-info mono">{data.label ? `${data.label} · ` : ""}{data.spec.spec.environment === "synthetic" ? `synthetic "${data.spec.spec.scenario}"` : data.spec.spec.environment === "nasa" ? `NASA POWER ${data.spec.spec.latitude}, ${data.spec.spec.longitude}, ${data.spec.spec.date}` : "CSV irradiance"} · PV {data.spec.fleet.pv_homes}/100 homes ({data.spec.fleet.pv_kwp} kWp)</div>
                </div>
                <div className="time">
                  <button className="btn sm" onClick={() => { if (k >= 127) setK(0); setPlaying(!playing); }} aria-label={playing ? "Pause" : "Play"}>{playing ? "⏸ Pause" : "▶ Play"}</button>
                  <div className="slider"><input type="range" min="0" max="127" value={k} onChange={(e) => { setPlaying(false); setK(+e.target.value); }} aria-label="Time of day" aria-valuetext={clock(k)} />
                    <div className="marks"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span><span>08:00 next day</span></div></div>
                  <div className="clock mono">{clock(k)}<small>step {k}</small></div>
                  <select value={speed} onChange={(e) => setSpeed(+e.target.value)} aria-label="Play speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select>
                </div>
                <div className="jumps">{[["10:00", 40], ["12:00", 48], ["14:00", 56], ["18:00", 72], ["20:00", 80], ["06:00", 24]].map(([l, v]) => (<button key={l} className="link" onClick={() => { setPlaying(false); setK(v); }}>{l}</button>))}</div>
              </section>
              <section className="panel sld-panel"><div className="scroll"><SLD topo={topo} cs={cs} k={k} selected={bus} onSelect={setBus} /></div><p className="note">Click a bus to inspect it below. Voltage colours use the configured limits {lim.v_lo}–{lim.v_hi} pu; every value is the OpenDSS result of the selected case at the selected step.</p></section>
              <section className="tiles" aria-label="System state">
                {[
                  ["Irradiance", ghi ? f(ghi[k % 96], 0) : "synthetic", ghi ? "W/m² GHI (NASA)" : "clear-sky shape"],
                  ["PV available", f(sys.pv_available_kW[k], 1), "kW"], ["PV delivered", f(sys.pv_delivered_kW[k], 1), "kW after inverter volt-watt"], ["PV curtailed", f(sys.pv_curtailed_kW[k], 1), "kW"],
                  ["Demand", f(sys.demand_kW[k], 1), "kW incl. flexible devices"], ["Transformer", f(sys.transformer_kW[k], 1), sys.transformer_kW[k] >= 0 ? "kW import" : "kW REVERSE FLOW"], ["Loading", f(sys.transformer_loading_pct[k], 0), "% of " + topo.transformer.kva + " kVA"],
                  ["Lowest voltage", f(derived[ctl].vmin[k], 3), "pu (limit " + lim.v_lo + ")"], ["Highest voltage", f(derived[ctl].vmax[k], 3), "pu (limit " + lim.v_hi + ")"], ["Neutral current", f(derived[ctl].neutral[k], 0), "A max segment (limit " + lim.neutral_ampacity_a + ")"],
                  ["Battery", f(cs.devices.P_BATT_kW[k], 1), "kW (+ charging) · SoC " + f(cs.devices.SoC_BATT_pct[k], 0) + " %"], ["OpenDSS", cs.converged[k] ? "converged" : "NOT converged", "power flow"],
                ].map(([a, b, c]) => (<div className="tile" key={a}><span>{a}</span><b className="mono">{b}</b><small>{c}</small></div>))}
              </section>
              <div className="grid-main">
                <Inspector bus={bus} topo={topo} cs={cs} csA={csA} k={k} caseId={ctl} />
                <MpcPanel caseId={ctl} cs={cs} csA={csA} k={k} topo={topo} />
              </div>
              <section className="charts panel">
                <h2>Day profile · case {ctl} <span className="sub">solid = selected, dashed = case A (no control) · click a chart to move the time</span></h2>
                <div className="chart-grid">
                  <LineChart title="Voltage extremes (all buses, all phases)" unit="pu" hours={hours} cursor={k} onSeek={(i) => { setPlaying(false); setK(i); }}
                    series={[{ label: `highest`, color: "var(--case-b)", values: derived[ctl].vmax }, { label: "lowest", color: "var(--case-a)", values: derived[ctl].vmin }, ...(ctl !== "A" ? [{ label: "A highest", color: "var(--case-b)", dash: "4 3", values: derived.A.vmax, w: 1.2 }, { label: "A lowest", color: "var(--case-a)", dash: "4 3", values: derived.A.vmin, w: 1.2 }] : [])]}
                    bands={[{ y: lim.v_hi, label: `${lim.v_hi} pu` }, { y: lim.v_lo, label: `${lim.v_lo} pu` }]} />
                  <LineChart title="Transformer power (+ import, − reverse flow)" unit="kW" hours={hours} cursor={k} onSeek={(i) => { setPlaying(false); setK(i); }}
                    series={[{ label: `case ${ctl}`, color: CASE_COLOR[ctl], values: sys.transformer_kW }, ...(ctl !== "A" ? [{ label: "A", color: CASE_COLOR.A, dash: "4 3", values: csA.system.transformer_kW, w: 1.2 }] : [])]} bands={[{ y: 0, label: "0" }]} />
                  <LineChart title="PV and demand" unit="kW" hours={hours} cursor={k} onSeek={(i) => { setPlaying(false); setK(i); }}
                    series={[{ label: "PV available", color: "var(--case-d)", values: sys.pv_available_kW, dash: "4 3", w: 1.3 }, { label: "PV delivered", color: "var(--case-d)", values: sys.pv_delivered_kW }, { label: "demand", color: "var(--case-a)", values: sys.demand_kW }]} />
                  <LineChart title="Battery state of charge" unit="%" hours={hours} cursor={k} onSeek={(i) => { setPlaying(false); setK(i); }} yMin={0} yMax={100}
                    series={[{ label: `case ${ctl}`, color: CASE_COLOR[ctl], values: cs.devices.SoC_BATT_pct }]} bands={[{ y: 10, label: "min 10" }, { y: 95, label: "max 95" }]} />
                </div>
              </section>
              <section className="panel">
                <h2>Run summary (32 h scoring window)</h2>
                <div className="scroll"><table className="t"><thead><tr><th>Metric</th>{Object.keys(CASES).map((c) => (<th key={c}>{c} · {CASES[c]}</th>))}</tr></thead><tbody>
                  {[["under_pu_h", "Under-voltage magnitude (pu·h)", 3], ["over_pu_h", "Over-voltage magnitude (pu·h)", 3], ["hours_any_undervoltage", "Hours with any under-voltage", 1], ["hours_any_overvoltage", "Hours with any over-voltage", 1], ["peak_trafo_loading_pct", "Transformer peak loading (%)", 1], ["reverse_flow_energy_kWh", "Reverse-flow energy (kWh)", 1], ["pv_curtailed_kWh", "PV curtailed (kWh)", 1], ["ev_unmet_at_departure_kWh", "EV energy unmet (kWh)", 2], ["fallbacks_to_rules", "OpenDSS gate fallbacks to rules", 0], ["solver_failures", "MILP solver failures", 0]].map(([key, l, d]) => (
                    <tr key={key}><td>{l}</td>{Object.keys(CASES).map((c) => (<td key={c} className="mono">{data.metrics[c] && data.metrics[c][key] != null ? f(data.metrics[c][key], d) : "–"}</td>))}</tr>))}
                </tbody></table></div>
              </section>
            </>)}
          </div>
        </main>
      )}
      <footer>Prototype on synthetic and NASA-derived inputs with assumed network parameters; not field-validated. See Analysis → Assumptions and known limitations.</footer>
    </div>
  );
}
