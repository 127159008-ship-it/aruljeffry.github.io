import React from "react";
import { f, vstate, busVoltages, STATE_LABEL } from "./lib.js";

const BX = (i) => 385 + i * 140, FY = { F1: 175, F2: 405 };
const COL = { normal: "var(--ok)", warning: "var(--warn)", violation: "var(--crit)" };

function Chip({ x, y, w = 74, label, value, kind, onClick }) {
  return (
    <g transform={`translate(${x - w / 2},${y})`} className={`chip chip-${kind}`}>
      <rect width={w} height="30" rx="5" />
      <text x="7" y="13" className="chip-l">{label}</text>
      <text x="7" y="25" className="chip-v">{value}</text>
    </g>
  );
}
function Arrow({ x1, x2, y, kW }) {
  if (Math.abs(kW) < 0.3) return null;
  const dir = kW >= 0 ? 1 : -1, mid = (x1 + x2) / 2, s = 7;
  return <path d={`M${mid - dir * s},${y - 6} L${mid + dir * s},${y} L${mid - dir * s},${y + 6} Z`} className={kW >= 0 ? "arrow-imp" : "arrow-exp"} />;
}

export default function SLD({ topo, cs, k, selected, onSelect }) {
  const lim = topo.limits, nodes = topo.nodes, sys = cs.system;
  const imp = sys.transformer_kW[k] >= 0;
  return (
    <svg viewBox="0 0 1050 640" className="sld" role="img" aria-label="Single-line diagram of the 415 V feeder at the selected time">
      {/* grid and transformer */}
      <g>
        <text x="70" y="262" textAnchor="middle" className="sld-t">11 kV GRID</text>
        <rect x="42" y="272" width="56" height="36" rx="4" className="box" /><text x="70" y="295" textAnchor="middle" className="sld-t">GRID</text>
        <line x1="98" y1="290" x2="165" y2="290" className="wire" />
        <circle cx="185" cy="290" r="22" className="trafo" /><circle cx="213" cy="290" r="22" className="trafo" />
        <line x1="235" y1="290" x2="320" y2="290" className="wire" />
        <text x="200" y="334" textAnchor="middle" className="sld-t">11/0.415 kV · {topo.transformer.kva} kVA</text>
        <text x="200" y="350" textAnchor="middle" className="sld-s">Δ-Y · 3Φ + N</text>
        <text x="200" y="366" textAnchor="middle" className="sld-s mono">{f(sys.transformer_kW[k], 1)} kW · {f(sys.transformer_loading_pct[k], 0)} % loaded</text>
        <text x="200" y="382" textAnchor="middle" className="sld-s">{imp ? "importing from grid" : "REVERSE FLOW: exporting to grid"}</text>
        <Arrow x1={105} x2={160} y={290} kW={sys.transformer_kW[k]} />
        <text x="270" y="278" textAnchor="middle" className="sld-s">415 V 3Φ+N</text>
      </g>
      {/* LV busbar */}
      <line x1="320" y1={FY.F1} x2="320" y2={FY.F2} className="busbar" />
      {Object.entries(topo.feeders).map(([fn, ns]) => {
        const y = FY[fn];
        return (
          <g key={fn}>
            <line x1="320" y1={y} x2={BX(0)} y2={y} className="wire" />
            <text x="306" y={y + 4} textAnchor="end" className="sld-t">FEEDER {fn === "F1" ? "A" : "B"} →</text>
            {ns.map((b, i) => {
              const seg = nodes[b].segment, x0 = i === 0 ? 320 : BX(i - 1), kw = cs.segment_kW[seg][k], I = cs.segment_current_A[seg].map((a) => a[k]);
              const w = 2 + Math.min(7, Math.abs(kw) / 18);
              return (
                <g key={"s" + b}>
                  <line x1={x0 + (i === 0 ? 0 : 10)} x2={BX(i) - 10} y1={y} y2={y} className={`seg ${kw >= 0 ? "seg-imp" : "seg-exp"}`} style={{ strokeWidth: w }} />
                  <Arrow x1={x0 + (i === 0 ? 0 : 10)} x2={BX(i) - 10} y={y} kW={kw} />
                  <text x={(x0 + BX(i)) / 2 + (i === 0 ? 0 : 5)} y={y - 18} textAnchor="middle" className="sld-s mono">{f(Math.abs(kw), 0)} kW</text>
                  <text x={(x0 + BX(i)) / 2 + (i === 0 ? 0 : 5)} y={y - 6} textAnchor="middle" className="sld-s mono">{f(Math.max(...I.slice(0, 3)), 0)} A</text>
                </g>
              );
            })}
            {ns.map((b, i) => {
              const x = BX(i), v = busVoltages(cs, b, k), st = vstate(v, lim), n = nodes[b], r = cs.bus_resources[b], up = fn === "F1";
              const chips = [];
              const npv = n.pv_homes.reduce((a, c) => a + c, 0);
              if (npv) chips.push({ key: "pv", kind: "pv", label: `PV ×${npv}`, value: `${f(r.pv_kW[k], 1)} kW` });
              n.devices.forEach((d) => chips.push({ key: d.id, kind: d.id === "BATT" ? "batt" : "dev", label: d.id === "BATT" ? "BATTERY" : d.id, value: `${f(cs.devices[`P_${d.id}_kW`][k], 1)} kW${d.id === "BATT" ? " " + (cs.devices.P_BATT_kW[k] >= 0 ? "chg" : "dis") : ""}` }));
              const sideY = (j) => (up ? y - 96 - j * 36 : y + 66 + j * 36);
              const sel = selected === b;
              return (
                <g key={b} className="bus" onClick={() => onSelect(b)} tabIndex={0} role="button" aria-label={`Bus ${b}, ${STATE_LABEL[st]}`} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(b)}>
                  {chips.map((c, j) => (<g key={c.key}><line x1={x} x2={x} y1={y} y2={sideY(j) + (up ? 30 : 0)} className="stub" /><Chip x={x} y={sideY(j)} kind={c.kind} label={c.label} value={c.value} /></g>))}
                  <line x1={x} x2={x} y1={y} y2={up ? y + 38 : y - 38} className="stub" />
                  <Chip x={x} y={up ? y + 38 : y - 68} kind="load" label={`HOMES ${n.homes.reduce((a, c) => a + c, 0)}`} value={`${f(r.load_kW[k], 1)} kW`} w={74} />
                  <rect x={x - 32} y={y - 36} width="64" height="72" fill="transparent" style={{ pointerEvents: "all" }} />
                  <rect x={x - 9} y={y - 24} width="18" height="48" rx="3" fill={COL[st]} className={`node ${sel ? "node-sel" : ""}`} />
                  {st === "violation" && <text x={x} y={y + 6} textAnchor="middle" className="node-ex">!</text>}
                  {st === "warning" && <text x={x} y={y + 6} textAnchor="middle" className="node-ex">~</text>}
                  <text x={x} y={y - 30} textAnchor="middle" className="bus-n">{b}</text>
                  <text x={x + 13} y={y - 4} className="sld-v mono">{f(Math.max(...v), 3)}</text>
                  <text x={x + 13} y={y + 14} className="sld-v mono">{f(Math.min(...v), 3)}</text>
                </g>
              );
            })}
          </g>
        );
      })}
      <g transform="translate(330,606)" className="sld-leg">
        <rect width="10" height="10" fill="var(--ok)" /><text x="14" y="9" className="sld-s">normal</text>
        <rect x="70" width="10" height="10" fill="var(--warn)" /><text x="84" y="9" className="sld-s">warning ~ (within 0.01 pu of {lim.v_lo}/{lim.v_hi})</text>
        <rect x="300" width="10" height="10" fill="var(--crit)" /><text x="314" y="9" className="sld-s">violation ! (outside {lim.v_lo}–{lim.v_hi} pu)</text>

      </g>
    </svg>
  );
}
