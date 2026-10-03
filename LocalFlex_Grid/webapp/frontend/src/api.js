const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
async function j(path, opt) {
  const r = await fetch(BASE + path, opt);
  if (!r.ok) { let m = r.statusText; try { const b = await r.json(); m = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch (e) {} throw new Error(m); }
  return r.json();
}
const post = (p, b) => j(p, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) });
export const api = {
  config: () => j("/api/config"),
  topology: (pv, kw) => j(`/api/topology?pv_penetration=${pv}&pv_kw_per_home=${kw}`),
  fleet: (pv, kw) => post(`/api/fleet?pv_penetration=${pv}&pv_kw_per_home=${kw}`, {}),
  nasa: (b) => post("/api/nasa", b),
  start: (b) => post("/api/simulation", b),
  status: (id) => j(`/api/simulation/${id}/status`),
  spec: (id) => j(`/api/simulation/${id}/spec`),
  series: (id, c) => j(`/api/simulation/${id}/series?controller=${c}`),
  results: (id) => j(`/api/simulation/${id}/results`),
  demo: () => j("/api/demo"),
  analysisList: () => j("/api/analysis"),
  analysis: (n) => j(`/api/analysis/${n}`),
  imageUrl: (n) => `${BASE}/api/analysis-image/${n}`,
};
