import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { f } from "./lib.js";

const GROUPS = {
  "A/B/C/D comparison": ["A_B_C_D_comparison", "final_summary"],
  "Robustness studies": ["participation", "forecast_error", "comm_delay", "battery_size", "battery_location", "assumption_sensitivity", "scalability"],
  "DISCOM requests": ["dispatch_verified", "dispatch_suite"],
  "Fault injection": ["final_fault_tests"],
  "Fairness": ["final_burden_by_group"],
  "Cost and emissions": ["cost_emissions"],
  "Validation": ["final_validation"],
  "Assumptions audit": ["standards_audit"],
};
const fmt = (v) => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3)) : v == null ? "" : String(v));
function Table({ rows }) {
  if (!Array.isArray(rows) || !rows.length || typeof rows[0] !== "object") return <pre className="json">{JSON.stringify(rows, null, 1)}</pre>;
  const cols = Object.keys(rows[0]);
  return (<div className="scroll tall"><table className="t dense"><thead><tr>{cols.map((c) => (<th key={c}>{c}</th>))}</tr></thead><tbody>{rows.map((r, i) => (<tr key={i}>{cols.map((c) => (<td key={c} className={typeof r[c] === "number" ? "mono" : ""}>{fmt(r[c])}</td>))}</tr>))}</tbody></table></div>);
}
export default function Analysis({ limitations }) {
  const [avail, setAvail] = useState([]), [grp, setGrp] = useState("A/B/C/D comparison"), [name, setName] = useState("A_B_C_D_comparison"), [data, setData] = useState(null), [err, setErr] = useState(null);
  useEffect(() => { api.analysisList().then(setAvail).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { setData(null); setErr(null); api.analysis(name).then(setData).catch((e) => setErr(e.message)); }, [name]);
  const names = (GROUPS[grp] || []).filter((n) => avail.includes(n));
  return (
    <div className="analysis">
      <section className="panel">
        <h2>Analysis and results</h2>
        <p className="sub">The stored LocalFlex study results (final integration stage). Synthetic profiles throughout; see the assumptions below.</p>
        <div className="tabs2" role="tablist">{Object.keys(GROUPS).map((g) => (<button key={g} className={g === grp ? "on" : ""} onClick={() => { setGrp(g); const first = GROUPS[g].find((n) => avail.includes(n)); if (first) setName(first); }}>{g}</button>))}</div>
        {names.length > 1 && <label className="inl">Table<select value={name} onChange={(e) => setName(e.target.value)}>{names.map((n) => (<option key={n}>{n}</option>))}</select></label>}
        {err && <p className="err">{err}</p>}{data ? <Table rows={data} /> : !err && <p>Loading…</p>}
        {grp === "A/B/C/D comparison" && <figure><img src={api.imageUrl("A_B_C_D_comparison.png")} alt="A/B/C/D comparison across scenarios" style={{ maxWidth: "100%" }} /><figcaption className="note">Means of four seeds, identical initial state, 32 h scoring window.</figcaption></figure>}
        <p><a href="/legacy-dashboard.html" target="_blank" rel="noreferrer">Open the original results dashboard (static)</a></p>
      </section>
      <section className="panel">
        <h2>Assumptions and known limitations</h2>
        <ul className="lim">{(limitations || []).map((l, i) => (<li key={i}>{l}</li>))}</ul>
      </section>
    </div>
  );
}
