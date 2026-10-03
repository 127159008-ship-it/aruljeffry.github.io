"""Stage 10 controllers.  C9-fixed = C9 (bus x phase sensitivity MPC) + battery charge/discharge exclusivity (binary mode variable, MILP). Nothing else changes.
D = C9-fixed + fairness: minimise the WORST normalised burden over household-facing flexible groups (4 heater groups, 2 EV groups). Pumps are a shared service (tracked as service, not fairness).
Burden of group g (day-so-far realised + planned horizon): B_g = delay_g/(4 h * E_nat_g) + W_U * unmet_g/E_nat_g, with delay = integral of max(0, natural cumulative energy - planned/realised cumulative energy).
Optional DISCOM dispatch (import cap) is a SEPARATE experiment (comm layer), not part of the A/B/C/D comparison."""
import time, numpy as np
import scipy.sparse as sp
from scipy.optimize import milp, LinearConstraint, Bounds
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
from control.mpc import _LP, W, PLAN, CP
from control.mpc9 import MPC9Controller
FAIR = dict(lam=500.0, w_unmet=10.0, delay_norm_h=4.0, discom_slack_cost=100.0, mip_time_s=1.0, mip_gap=0.02)
HOUSEHOLD = ("WH1", "WH2", "WH3", "WH4", "EV1", "EV2")

class _MILP(_LP):
    def __init__(s): super().__init__(); s.integ = []
    def var(s, n, lb=0.0, ub=np.inf, c=0.0, integer=False):
        idx = super().var(n, lb, ub, c); s.integ += [1 if integer else 0]*n; return idx
    def solve(s, time_s=2.0, gap=0.01):
        Ae = sp.csr_matrix((s.eqv, (s.eqr, s.eqc)), shape=(len(s.beq), s.n)); Au = sp.csr_matrix((s.uv, (s.ur, s.uc)), shape=(len(s.bub), s.n))
        r = milp(c=np.array(s.c), constraints=[LinearConstraint(Au, -np.inf, np.array(s.bub)), LinearConstraint(Ae, np.array(s.beq), np.array(s.beq))], integrality=np.array(s.integ), bounds=Bounds(np.array(s.lb), np.array(s.ub)), options=dict(time_limit=time_s, mip_rel_gap=gap))
        class R: pass
        o = R(); o.x = r.x; o.status = 0 if r.x is not None else 1; o.mip_status = r.status; return o

class MPC10Controller(MPC9Controller):
    def __init__(self, *a, exclusive=True, fairness=False, comm=None, fair=FAIR, E_nat=None, **kw):
        super().__init__(*a, **kw); self.exclusive = exclusive; self.fairness = fairness; self.F = fair; self.comm = comm
        self.hist = {g: 0.0 for g in HOUSEHOLD}; self.n_sim_plan = 0; self.n_plan = 0; self.mip_nonopt = 0; self.burden_log = []; self.reports = []; self.cap_active_steps = 0; self.cap_log = []; self.last_pn = None; self.res_ids = {r[0] for r in self.res}
        self.E_nat = {g: float(self.Pn[g].sum()*0.25) for g in HOUSEHOLD}
    def _update_history(self, k, groups):
        if k == 0: self.hist = {g: 0.0 for g in HOUSEHOLD}
        for g in groups:
            if g.id in HOUSEHOLD:
                cact = g.led["e_in"] if isinstance(g, WaterHeaterGroup) else g.led["grid"]; cnat = float(self.Pn[g.id][:k].sum()*0.25)
                self.hist[g.id] += max(0.0, cnat - cact)*0.25
    def act(self, k, groups, last):
        self._update_history(k, groups); self.req = None
        if self.comm is not None:
            rep = self._report(k, groups, last); self.req = self.comm.step(self.a, rep)
        return super().act(k, groups, last)
    def _report(self, k, groups, last=None):
        """LocalFlex -> DISCOM message, AGGREGATED ONLY (no household or group-level data)."""
        b = [g for g in groups if isinstance(g, SharedBattery)][0]; pnp = None if self.last_pn is None else self.last_pn[1][:16]
        ev = []; st = "NORMAL"; feeder = None
        if last is not None:
            vc = [c for c in last if c.startswith("V_") and c.endswith("_pu")]; vmax = max(last[c] for c in vc); vmin = min(last[c] for c in vc); tl = last["trafo_loading_pct"]
            feeder = dict(v_max_pu=round(vmax, 3), v_min_pu=round(vmin, 3), transformer_loading_pct=round(tl, 1))
            if vmin < self.P["v_lo"]: ev.append("undervoltage"); st = "WARNING"
            if vmax > self.P["v_hi"]: ev.append("overvoltage"); st = "WARNING"
            if tl > 100.0: ev.append("transformer_overload"); st = "ALARM"
        return dict(step_time_h=k*0.25, status=st, net_import_forecast_kW_next_4h=None if pnp is None else [round(float(max(v, 0.0)), 1) for v in pnp], net_export_forecast_kW_next_4h=None if pnp is None else [round(float(max(-v, 0.0)), 1) for v in pnp],
                    flexibility_up_kW=round(float(sum(g.Pg if isinstance(g, WaterHeaterGroup) else g.P["p_kw"] if isinstance(g, PumpTank) else 0.0 for g in groups if g.id in self.res_ids) + b.P["p_kw"]), 1),
                    flexibility_down_kW=round(float(min(b.P["p_kw"], (b.E - b.P["soc_min"]*b.P["e_kwh"])*b.P["eta_d"]/0.25)), 1),
                    envelope_import_cap_kW=self.P["trafo_cap_kw"], envelope_export_cap_kW=self.P["trafo_cap_kw"], feeder=feeder, events=ev)
    def plan(self, k, a, groups):
        P, Wt, Fr = self.P, self.W, self.F; H, dt = P["H"], P["dt"]; lp = _MILP() if self.exclusive else _LP()
        base = self.fc_dem[a:a+H] + getattr(self, "extra_base", np.zeros(4*96))[a:a+H]; pv = self.fc_pv[a:a+H]; tmid = ((k + np.arange(H)) % 96)*dt + dt/2
        dev = [[] for _ in range(H)]; gj = {r[0]: [[] for _ in range(H)] for r in self.res}; wh_idx = {}; pu_idx = {}; ev_idx = {}; unmet = {r[0]: [] for r in self.res}
        def add(gid, j, idx, c): dev[j].append((idx, c)); gj[gid][j].append((idx, c))
        for g in [g for g in groups if isinstance(g, WaterHeaterGroup)]:
            p = lp.var(H, 0, g.Pg, c=Wt["device_energy"]*dt); T = lp.var(H+1, 30.0, max(P["heater_ceiling_C"], g.T+0.01)); lp.lb[T[0]] = lp.ub[T[0]] = g.T; s = lp.var(H, 0, np.inf, c=Wt["heater_low"]*dt)
            for j in range(H):
                md = g.draw_kg_per_h(tmid[j]); aa = 1 - (g.UA + md*CP)*dt/g.C
                lp.eq([(T[j+1], 1.0), (T[j], -aa), (p[j], -dt/g.C)], (g.UA*g.P["t_amb"]*dt + md*CP*g.P["t_in"]*dt)/g.C); lp.ub_([(T[j+1], -1.0), (s[j], -1.0)], -P["heater_floor_C"]); add(g.id, j, p[j], 1.0)
            wh_idx[g.id] = (p, g.Pg); unmet[g.id] = [(s, g.C*dt)]       # heater service shortfall as energy-equivalent (kWh): K below floor x heat capacity, per step
        for g in [g for g in groups if isinstance(g, PumpTank)]:
            u = lp.var(H, 0, 1, c=Wt["device_energy"]*dt*g.P["p_kw"]); L = lp.var(H+1, 0, g.V); lp.lb[L[0]] = lp.ub[L[0]] = g.level; s = lp.var(H, 0, np.inf, c=Wt["pump_low"]*dt)
            for j in range(H):
                lp.eq([(L[j+1], 1.0), (L[j], -1.0), (u[j], -g.q*dt)], -g.demand_m3h(tmid[j])*dt); lp.ub_([(L[j+1], -1.0), (s[j], -1.0)], -P["pump_floor_frac"]*g.V); add(g.id, j, u[j], g.P["p_kw"])
            pu_idx[g.id] = u
        for g in [g for g in groups if isinstance(g, EVGroup)]:
            first = []; n = len(g.arr)
            for i in range(n):
                for lbl in ("A", "B"):
                    rem = g.remA[i] if lbl == "A" else g.remB[i]
                    if rem <= 1e-9: continue
                    def steps(mg):
                        out = []
                        for j in range(H):
                            ts = (k+j)*dt
                            if lbl == "A": ok = (k+j) < 96 and ts + dt <= g.dep[i] - mg + 1e-9 and not g.departedA[i]
                            else: ok = ts >= g.arr[i] - 1e-9 and ts + dt <= g.dep[i] + 24 - mg + 1e-9
                            if ok: out.append(j)
                        return out
                    mg = P["ev_margin_h"]; valid = steps(mg)
                    if not valid: mg = 0.0; valid = steps(0.0)
                    need = rem
                    if lbl == "B": need = max(0.0, rem - g.pmax[i]*g.eta*max(0.0, g.dep[i] + 24 - mg - (k+H)*dt))
                    if lbl == "A" and not valid: continue
                    su = lp.var(1, 0, np.inf, c=Wt["ev_unmet"]); unmet[g.id].append((su, 1.0))
                    if valid:
                        p = lp.var(len(valid), 0, g.pmax[i], c=Wt["device_energy"]*dt); lp.ub_([(p[q], -g.eta*dt) for q in range(len(valid))] + [(su[0], -1.0)], -need)
                        for q, j in enumerate(valid): add(g.id, j, p[q], 1.0)
                        if valid[0] == 0: first.append((i, lbl, p[0]))
                    else: lp.ub_([(su[0], -1.0)], -need)
            ev_idx[g.id] = first
        b = [g for g in groups if isinstance(g, SharedBattery)][0]; Pb = b.P; cap = Pb["e_kwh"]
        pch = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt); pdis = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt)
        E = lp.var(H+1, Pb["soc_min"]*cap, Pb["soc_max"]*cap); lp.lb[E[0]] = lp.ub[E[0]] = b.E
        if self.exclusive:
            zc = lp.var(H, 0, 1, integer=True)                                           # 1 = charging mode, 0 = discharging/idle mode
            for j in range(H): lp.ub_([(pch[j], 1.0), (zc[j], -Pb["p_kw"])], 0.0); lp.ub_([(pdis[j], 1.0), (zc[j], Pb["p_kw"])], Pb["p_kw"])
        for j in range(H):
            lp.eq([(E[j+1], 1.0), (E[j], -1.0), (pch[j], -Pb["eta_c"]*dt), (pdis[j], dt/Pb["eta_d"])], 0.0); add("BATT", j, pch[j], 1.0); add("BATT", j, pdis[j], -1.0)
        tgt = Pb["soc_init"]*cap; de = 96 - k
        for idx, target, cost in ((H, tgt, Wt["soc_end"]), (de, tgt, Wt["soc_end"]), (P["reserve_step"]-k, P["reserve_kwh"], Wt["soc_reserve"])):
            if 1 <= idx <= H: s = lp.var(1, 0, np.inf, c=cost); lp.ub_([(E[idx], -1.0), (s[0], -1.0)], -target)
        pn = lp.var(H, -np.inf, np.inf); curt = lp.var(H, 0, 1.0, c=Wt["curtail"]*dt); st = lp.var(H, 0, np.inf, c=Wt["trafo"]*dt); rv = lp.var(H, 0, np.inf, c=Wt["reverse"]*dt)
        capv = self.comm.cap_vector(a, k, H, self.req, forecast=getattr(self, "last_pn", None)) if self.comm is not None else np.full(H, np.inf); capsl = []; from control.discom import export_cap_vector; capx = export_cap_vector(a, k, H, self.req) if self.comm is not None else np.full(H, np.inf)
        for j in range(H):
            lp.ub[curt[j]] = max(pv[j], 0.0)
            lp.eq([(pn[j], 1.0), (curt[j], -1.0)] + [(i, -c) for i, c in dev[j]], base[j] - pv[j])
            lp.ub_([(pn[j], 1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (rv[j], -1.0)], 0.0)
            if np.isfinite(capv[j]): sd = lp.var(1, 0, np.inf, c=Fr["discom_slack_cost"]*dt); lp.ub_([(pn[j], 1.0), (sd[0], -1.0)], capv[j]); capsl.append((j, sd[0], capv[j], pn[j]))
            if np.isfinite(capx[j]): se = lp.var(1, 0, np.inf, c=Fr["discom_slack_cost"]*dt); lp.ub_([(pn[j], -1.0), (se[0], -1.0)], capx[j]); capsl.append((j, se[0], capx[j], pn[j], "export"))
        if np.isfinite(capv).any() or np.isfinite(capx).any(): self.cap_active_steps += 1
        ids = [r[0] for r in self.res]; nm = len(self.mon); Pg = {gid: lp.var(H, -np.inf, np.inf) for gid in ids}
        for gid in ids:
            for j in range(H): lp.eq([(Pg[gid][j], 1.0)] + [(i, -c) for i, c in gj[gid][j]], 0.0)
        sh = lp.var(nm*H, 0, np.inf, c=Wt["volt"]*dt); sl = lp.var(nm*H, 0, np.inf, c=Wt["volt"]*dt); Hsel = []
        for j in range(H):
            t = (k + j) % 96; Hm = self.Hm if self.fc_pv[a+j] >= self.pv_thr else self.He; Hsel.append(Hm); Pnat = np.array([self.Pn[gid][t] for gid in ids])
            for i in range(nm):
                Hi = Hm[i]; const = float(Hi @ Pnat); vb = self.Vb[t, i]; terms = [(Pg[gid][j], float(Hi[q])) for q, gid in enumerate(ids) if Hi[q] != 0.0]
                lp.ub_(terms + [(sh[i*H+j], -1.0)], P["v_hi"] - vb + const); lp.ub_([(ix, -c) for ix, c in terms] + [(sl[i*H+j], -1.0)], -P["v_lo"] + vb - const)
        if self.fairness:
            Bmax = lp.var(1, 0, np.inf, c=Fr["lam"])
            for gid in HOUSEHOLD:
                En = max(self.E_nat[gid], 1e-6); nD = En*Fr["delay_norm_h"]; cum = lp.var(H, 0, np.inf); w = lp.var(H, 0, np.inf)
                for j in range(H):
                    lp.eq([(cum[j], 1.0)] + ([(cum[j-1], -1.0)] if j else []) + [(Pg[gid][j], -dt)], 0.0)
                    cn = float(sum(self.Pn[gid][(k+q) % 96] for q in range(j+1))*dt); lp.ub_([(cum[j], -1.0), (w[j], -1.0)], -cn)           # w_j >= natural cumulative - planned cumulative
                # B_g = (hist + dt*sum w)/nD + W_U*unmet/En   <=  Bmax
                terms = [(w[j], dt/nD) for j in range(H)] + [(si, Fr["w_unmet"]*coef/En) for (sidx, coef) in unmet.get(gid, []) for si in sidx] + [(Bmax[0], -1.0)]
                lp.ub_(terms, -self.hist[gid]/nD)
        self.nvars = lp.n; self.ncons = len(lp.beq) + len(lp.bub)
        r = lp.solve(Fr["mip_time_s"], Fr["mip_gap"]) if self.exclusive else lp.solve()
        if r.x is None or r.status != 0: return None
        if self.exclusive and getattr(r, "mip_status", 0) != 0: self.mip_nonopt += 1
        x = r.x; cmds = {}; self.last_pn = (a, np.array(x[pn]))
        if capsl: self.cap_log.append(dict(a=a, k=k, kind=("export" if len(capsl[0]) > 4 else "import"), window_steps=len(capsl), cap_min_kW=float(min(c[2] for c in capsl)), predicted_max_flow_kW=float(max((-x[c[3]] if len(c) > 4 else x[c[3]]) for c in capsl)), slack_max_kW=float(max(x[c[1]] for c in capsl))))
        for gid, (p, Pgmax) in wh_idx.items(): cmds[gid] = float(np.clip(x[p[0]]/Pgmax, 0, 1))
        for gid, u in pu_idx.items(): cmds[gid] = float(np.clip(x[u[0]], 0, 1))
        for g in [g for g in groups if isinstance(g, EVGroup)]: cmds[g.id] = {(i, lbl): float(x[ix]) for i, lbl, ix in ev_idx[g.id]}
        sim_all = int(((x[pch] > 1e-6) & (x[pdis] > 1e-6)).sum()); self.n_sim_plan += sim_all; self.n_plan += 1
        c, d = x[pch[0]], x[pdis[0]]
        if c > 1e-6 and d > 1e-6: self.n_sim += 1
        cmds["BATT"] = float(c - d); self.plan_log.append((a, float(x[pn[0]]), float(x[curt].sum()*dt), float(x[E[H]])))
        P0 = np.array([x[Pg[gid][0]] for gid in ids]); Pnat0 = np.array([self.Pn[gid][k] for gid in ids]); Vpred = self.Vb[k] + Hsel[0] @ (P0 - Pnat0); self.pred_log.append((a, k, Vpred.copy(), self.Vb[k].copy()))
        if a in self.trace_steps:                                         # decision trace (same content as Stage 9) for the FINAL controller
            Vn = self.Vb[k]; hi_mode = Vn.max() - P["v_hi"] > P["v_lo"] - Vn.min(); w = int(np.argmax(Vn) if hi_mode else np.argmin(Vn)); rr = {r_[0]: r_ for r_ in self.res}
            self.trace.append(dict(abs_step=a, step=k, hour=k*dt, constraint=("overvoltage" if hi_mode else "undervoltage"), node_phase=f"{self.mon[w][0]}/{self.mon[w][1]}", V_forecast_no_action=float(Vn[w]), V_pred_with_action=float(Vpred[w]),
                candidates=[dict(resource=gid, bus_phase=(f"{rr[gid][1]}/3-phase" if gid == "BATT" else f"{rr[gid][1]}/{'ABC'[rr[gid][2]-1]}"), H_pu_per_kW=float(Hsel[0][w, q]), natural_kW=float(Pnat0[q]), planned_kW=float(P0[q]), delta_kW=float(P0[q]-Pnat0[q]), predicted_dV_at_node=float(Hsel[0][w, q]*(P0[q]-Pnat0[q]))) for q, gid in enumerate(ids)],
                regime=("midday" if Hsel[0] is self.Hm else "evening"), executed=dict((g_, (v_ if not isinstance(v_, dict) else sum(v_.values()))) for g_, v_ in cmds.items())))
        if self.fairness: self.burden_log.append((a, {gid: float(self.hist[gid]/(max(self.E_nat[gid], 1e-6)*Fr["delay_norm_h"])) for gid in HOUSEHOLD}))
        return cmds
