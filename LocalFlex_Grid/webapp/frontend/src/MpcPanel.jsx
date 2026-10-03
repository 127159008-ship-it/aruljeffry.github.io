import React from "react";
import { f, CASES } from "./lib.js";

export default function MpcPanel({ caseId, cs, csA, k, topo, onSelectBus }) {
  const tr = cs.mpc_trace && cs.mpc_trace[k];
  const sup = (cs.supervisor_events || []).filter((e) => e.k_start <= k && k <= e.k_end);
  const gate = (cs.validator_fallback_steps || []).includes(k);
  const deltas = Object.keys(cs.devices).filter((c) => /^P_.*_kW$/.test(c)).map((c) => ({ id: c.slice(2, -3), a: csA.devices[c][k], s: cs.devices[c][k] })).filter((d) => d.a !== undefined);
  if (caseId === "A" || caseId === "B") {
    return (
      <section className="panel"><h2>Controller decision</h2>
        <p>{caseId === "A" ? "Case A has no controller: devices follow their natural behaviour." : "Case B is the Stage-7 rule controller: local rules act on the previous step's measurements. It has no optimiser, so there is no MPC trace."}</p>
        <p className="note">Select case C or D to see the MPC decision for this step.</p></section>
    );
  }
  const [nb, ph] = tr ? tr.node_phase.split("/") : [null, null], pi = ph ? "ABC".indexOf(ph) : -1;
  const actual = tr ? cs.bus_voltage_pu[nb][pi][k] : null, actualA = tr ? csA.bus_voltage_pu[nb][pi][k] : null;
  const cand = tr ? [...tr.candidates].sort((a, b) => Math.abs(b.predicted_dV_at_node) - Math.abs(a.predicted_dV_at_node)) : [];
  return (
    <section className="panel mpc">
      <h2>MPC decision trace <span className="sub">case {caseId} · {topo ? "" : ""}step {k}</span></h2>
      {!tr && <p>No decision trace was recorded for this step.</p>}
      {tr && (<>
        <ol className="flow">
          <li><b>1. Problem</b><span>{tr.problem_active ? `Forecast ${tr.constraint} at ${nb} phase ${ph}: ${f(tr.V_forecast_no_action, 4)} pu against the ${f(tr.limit_pu, 2)} pu limit.` : `No limit violation forecast. Most extreme node-phase: ${nb} phase ${ph}, ${f(tr.V_forecast_no_action, 4)} pu (${tr.constraint} side). The planner still optimises energy, peak and fairness costs.`}</span></li>
          <li><b>2. Candidates</b><span>Every flexible resource, with its OpenDSS-derived sensitivity dV/dP at {nb}/{ph} ({tr.regime} sensitivity matrix).</span></li>
          <li><b>3. Optimisation</b><span>MILP (battery cannot charge and discharge together) chooses the planned powers below.</span></li>
          <li><b>4. Prediction</b><span>Linear model: {f(tr.V_pred_with_action, 4)} pu at {nb}/{ph} with the plan (planner estimate, not a measurement).</span></li>
          <li><b>5. Safety</b><span>{gate ? "OpenDSS trial solve judged the MPC command worse than the rule command: rule command executed." : "OpenDSS trial solve accepted the MPC command."} {sup.length ? "Supervisor: " + sup.map((e) => `${e.cause} → ${e.action}`).join("; ") : "Supervisor: no event."} Power flow {cs.converged[k] ? "converged" : "DID NOT converge"}.</span></li>
          <li><b>6. OpenDSS result</b><span>Actual {f(actual, 4)} pu at {nb}/{ph}. Without control (case A) the same node-phase is {f(actualA, 4)} pu.</span></li>
        </ol>
        <div className="cmp">
          <div><span>Forecast, no action</span><b className="mono">{f(tr.V_forecast_no_action, 4)}</b></div>
          <div><span>Planner prediction with plan</span><b className="mono">{f(tr.V_pred_with_action, 4)}</b></div>
          <div className="act"><span>OpenDSS actual (case {caseId})</span><b className="mono">{f(actual, 4)}</b></div>
          <div><span>OpenDSS actual (case A)</span><b className="mono">{f(actualA, 4)}</b></div>
        </div>
        <table className="t"><thead><tr><th>Resource</th><th>Bus/phase</th><th>dV/dP (pu/kW)</th><th>Natural kW</th><th>Planned kW</th><th>Change kW</th><th>Predicted ΔV (mV)</th></tr></thead><tbody>
          {cand.map((c) => (<tr key={c.resource} className={Math.abs(c.delta_kW) > 0.05 ? "chg" : ""}><td>{c.resource}</td><td>{c.bus_phase}</td><td className="mono">{c.H_pu_per_kW.toExponential(2)}</td><td className="mono">{f(c.natural_kW, 2)}</td><td className="mono">{f(c.planned_kW, 2)}</td><td className="mono">{f(c.delta_kW, 2)}</td><td className="mono">{f(c.predicted_dV_at_node * 1000, 2)}</td></tr>))}
        </tbody></table>
        <p className="note">The first-step command that is executed may differ slightly from the plan after rounding to device limits. Negative battery power = discharging, positive = charging.</p>
      </>)}
      <h3>What changed against no control at this time (OpenDSS-run device powers)</h3>
      <table className="t"><thead><tr><th>Device</th><th>Case A kW</th><th>Case {caseId} kW</th><th>Difference</th></tr></thead><tbody>
        {deltas.map((d) => (<tr key={d.id}><td>{d.id}</td><td className="mono">{f(d.a, 2)}</td><td className="mono">{f(d.s, 2)}</td><td className="mono">{f(d.s - d.a, 2)}</td></tr>))}
      </tbody></table>
      <p className="note">Case A is a separate run, so device states (tank temperature, EV progress, battery) drift apart over the day; differences here include earlier decisions, not only this step.</p>
    </section>
  );
}
