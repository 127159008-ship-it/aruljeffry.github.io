export const CASES = { A: "No control", B: "Rules", C: "MPC", D: "MPC + fairness" };
export const CASE_COLOR = { A: "var(--case-a)", B: "var(--case-b)", C: "var(--case-c)", D: "var(--case-d)" };
export const f = (x, n = 1) => (x == null || Number.isNaN(+x) ? "n/a" : (+x).toFixed(n));
export const clock = (k) => { const m = k * 15; return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}` + (k >= 96 ? " +1d" : ""); };
export const WARN_MARGIN = 0.01; // pu: "warning" when within this distance of a configured limit
export function vstate(vs, lim) {
  const lo = Math.min(...vs), hi = Math.max(...vs);
  if (lo < lim.v_lo || hi > lim.v_hi) return "violation";
  if (lo < lim.v_lo + WARN_MARGIN || hi > lim.v_hi - WARN_MARGIN) return "warning";
  return "normal";
}
export const STATE_LABEL = { normal: "Normal", warning: "Warning (within 0.01 pu of a limit)", violation: "Violation" };
export function busVoltages(cs, bus, k) { return [0, 1, 2].map((p) => cs.bus_voltage_pu[bus][p][k]); }
