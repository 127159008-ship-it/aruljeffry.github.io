import React from "react";
import { CASE_COLOR } from "./lib.js";
/* Small SVG line chart with a time cursor. series: [{label,color,values,dash}], hours: x values (hours). bands: [{y,label}] horizontal reference lines. */
export function LineChart({ series, hours, cursor, onSeek, unit, height = 150, bands = [], yMin, yMax, title }) {
  const W = 560, H = height, L = 44, R = 10, T = 8, B = 22;
  const all = series.flatMap((s) => s.values.filter((v) => v != null)).concat(bands.map((b) => b.y));
  let lo = yMin ?? Math.min(...all), hi = yMax ?? Math.max(...all);
  if (hi - lo < 1e-9) { hi = lo + 1; }
  const pad = (hi - lo) * 0.06; if (yMin == null) lo -= pad; if (yMax == null) hi += pad;
  const n = hours.length, x = (i) => L + (i / (n - 1)) * (W - L - R), y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const path = (vals) => vals.map((v, i) => (v == null ? "" : `${i && vals[i - 1] != null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)).join("");
  const ticks = [0, 4, 8, 12, 16, 20, 24, 28, 32].filter((h) => h <= (n - 1) / 4);
  const seek = (e) => { if (!onSeek) return; const r = e.currentTarget.getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; onSeek(Math.max(0, Math.min(n - 1, Math.round(((px - L) / (W - L - R)) * (n - 1))))); };
  const yt = [lo, (lo + hi) / 2, hi];
  return (
    <figure className="chart">
      {title && <figcaption>{title} <span className="unit">{unit}</span></figcaption>}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} onClick={seek} style={{ cursor: onSeek ? "pointer" : "default" }}>
        {yt.map((v, i) => (<g key={i}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 6} y={y(v) + 3} textAnchor="end" className="ax">{Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2).replace(/\.?0+$/, "")}</text></g>))}
        {ticks.map((h) => (<text key={h} x={x(h * 4)} y={H - 6} textAnchor="middle" className="ax">{String(h % 24).padStart(2, "0")}h</text>))}
        {bands.map((b, i) => (<g key={i}><line x1={L} x2={W - R} y1={y(b.y)} y2={y(b.y)} className="band" /><text x={W - R - 2} y={y(b.y) - 3} textAnchor="end" className="ax">{b.label}</text></g>))}
        {series.map((s, i) => (<path key={i} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.w || 1.8} strokeDasharray={s.dash} strokeLinejoin="round" />))}
        {cursor != null && <line x1={x(cursor)} x2={x(cursor)} y1={T} y2={H - B} className="cursor" />}
        {cursor != null && series.map((s, i) => s.values[cursor] != null && <circle key={i} cx={x(cursor)} cy={y(s.values[cursor])} r="3.5" fill={s.color} stroke="var(--surface)" strokeWidth="1.5" />)}
      </svg>
      <div className="legend">{series.map((s, i) => (<span key={i}><i style={{ background: s.color, ...(s.dash ? { backgroundImage: "none", borderTop: `2px dashed ${s.color}`, background: "none", height: 0 } : {}) }} />{s.label}{cursor != null && s.values[cursor] != null ? <b className="mono"> {s.values[cursor].toFixed(Math.abs(s.values[cursor]) > 50 ? 0 : 3)}</b> : null}</span>))}</div>
    </figure>
  );
}
export { CASE_COLOR };
