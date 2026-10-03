import React from "react";
import { f, vstate, STATE_LABEL, CASES } from "./lib.js";

function devState(id, cs, k) {
  if (id.startsWith("WH")) return `tank ${f(cs.devices[`T_${id}_C`][k], 1)} °C`;
  if (id.startsWith("PUMP")) return `tank level ${f(cs.devices[`level_${id}_pct`][k], 0)} %`;
  if (id.startsWith("EV")) return `${f(cs.devices[`rem_${id}_kWh`][k], 2)} kWh still to charge`;
  if (id === "BATT") return `SoC ${f(cs.devices.SoC_BATT_pct[k], 0)} %`;
  return "";
}
function VBar({ label, v, vA, lim }) {
  const lo = 0.88, hi = 1.12, p = (x) => `${Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100))}%`;
  const st = vstate([v], lim);
  return (
    <div className="vbar">
      <span className="vl">Phase {label}</span>
      <div className="track"><i className="lim" style={{ left: p(lim.v_lo) }} /><i className="lim" style={{ left: p(lim.v_hi) }} /><i className={`mark m-${st}`} style={{ left: p(v) }} />{vA != null && <i className="mark-a" style={{ left: p(vA) }} title="case A" />}</div>
      <span className="vv mono">{f(v, 4)} pu</span><span className={`pill s-${st}`}>{st}</span>
    </div>
  );
}
export default function Inspector({ bus, topo, cs, csA, k, caseId }) {
  const n = topo.nodes[bus], lim = topo.limits;
  const v = [0, 1, 2].map((p) => cs.bus_voltage_pu[bus][p][k]), vA = [0, 1, 2].map((p) => csA.bus_voltage_pu[bus][p][k]);
  const seg = n.segment, I = cs.segment_current_A[seg].map((a) => a[k]), P = cs.segment_kW[seg][k], Q = cs.segment_kvar[seg][k], r = cs.bus_resources[bus];
  const st = vstate(v, lim);
  return (
    <section className="panel insp" aria-label={`Bus ${bus} inspector`}>
      <h2>BUS {bus} <span className={`pill s-${st}`} title={STATE_LABEL[st]}>{st}</span></h2>
      <p className="sub">Feeder {n.feeder === "F1" ? "A" : "B"}, position {n.position} of 5 · values from the OpenDSS solution at this step · ○ = case A (no control)</p>
      <h3>Voltage (phase to neutral)</h3>
      {["A", "B", "C"].map((p, i) => (<VBar key={p} label={p} v={v[i]} vA={caseId === "A" ? null : vA[i]} lim={lim} />))}
      <div className="kv"><span>Neutral-to-earth voltage</span><b className="mono">{f(cs.bus_neutral_V[bus][k], 2)} V</b></div>
      <h3>Current in the feeder segment supplying this bus</h3>
      <table className="t"><thead><tr><th></th><th>IA</th><th>IB</th><th>IC</th><th>IN</th></tr></thead><tbody>
        <tr><td>A</td>{I.map((a, i) => (<td key={i} className="mono">{f(a, 1)}</td>))}</tr>
        <tr><td>% of limit</td>{I.map((a, i) => (<td key={i} className="mono">{f((a / (i === 3 ? lim.neutral_ampacity_a : lim.phase_ampacity_a)) * 100, 0)}%</td>))}</tr>
      </tbody></table>
      <p className="note">Limits used: phase {lim.phase_ampacity_a} A, neutral {lim.neutral_ampacity_a} A (assumptions, not datasheet values).</p>
      <h3>Power into the segment</h3>
      <div className="kv"><span>P</span><b className="mono">{f(P, 1)} kW</b></div><div className="kv"><span>Q</span><b className="mono">{f(Q, 1)} kvar</b></div>
      <div className="kv"><span>Direction</span><b>{P >= 0 ? "Import: towards the end of the feeder" : "Export: towards the transformer (reverse flow)"}</b></div>
      <h3>Connected resources</h3>
      <table className="t"><tbody>
        <tr><td>Homes ({n.homes.reduce((a, c) => a + c, 0)})</td><td className="mono">{f(r.load_kW[k], 1)} kW</td><td className="sub">phases A/B/C: {n.homes.join(" / ")}</td></tr>
        <tr><td>PV ({n.pv_homes.reduce((a, c) => a + c, 0)} homes)</td><td className="mono">{f(r.pv_kW[k], 1)} kW</td><td className="sub">delivered, after inverter volt-watt</td></tr>
        {n.devices.map((d) => (<tr key={d.id}><td>{d.kind} {d.id}</td><td className="mono">{f(cs.devices[`P_${d.id}_kW`][k], 2)} kW</td><td className="sub">phase {d.phase} · {devState(d.id, cs, k)}</td></tr>))}
      </tbody></table>
    </section>
  );
}
