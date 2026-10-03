"""Stage 9 predictive controller (Case C9): identical to Stage 8 (C8) except the voltage model.
C8: Vmax/Vmin = a + b*P_net (aggregate).  C9: V_pred[i,j] = V_base_forecast[i,t] + sum_g H[i,g]*(P_g[t] - P_nat_g[t]) for EVERY monitored node/phase i,
with H identified from OpenDSS (bus x phase), regime-selected (midday/evening) by forecast PV. Everything else (forecast, LP structure, objective weights, battery model, devices, gate) is inherited unchanged."""
import time, numpy as np
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
from control.mpc import MPCController, _LP, W, PLAN, CP

class MPC9Controller(MPCController):
    def __init__(self, cal, dem_total, pv_total, seed, Hmid, Hev, resources, monitored, Vbase, Pnat, pv_rated_kw, pv_regime_frac=0.20, trace_steps=(), **kw):
        super().__init__(cal, dem_total, pv_total, seed, **kw)
        self.Hm, self.He = Hmid, Hev; self.res = resources; self.mon = monitored; self.Vb = Vbase; self.Pn = Pnat; self.pv_thr = pv_regime_frac*pv_rated_kw
        self.trace_steps = set(trace_steps); self.trace = []; self.pred_log = []
    def plan(self, k, a, groups):
        P, Wt = self.P, self.W; H, dt = P["H"], P["dt"]; lp = _LP()
        base = self.fc_dem[a:a+H]; pv = self.fc_pv[a:a+H]; tmid = ((k + np.arange(H)) % 96)*dt + dt/2
        dev = [[] for _ in range(H)]; gj = {r[0]: [[] for _ in range(H)] for r in self.res}; wh_idx = {}; pu_idx = {}; ev_idx = {}
        def add(gid, j, idx, c): dev[j].append((idx, c)); gj[gid][j].append((idx, c))
        for g in [g for g in groups if isinstance(g, WaterHeaterGroup)]:
            p = lp.var(H, 0, g.Pg, c=Wt["device_energy"]*dt); T = lp.var(H+1, 30.0, max(P["heater_ceiling_C"], g.T+0.01)); lp.lb[T[0]] = lp.ub[T[0]] = g.T; s = lp.var(H, 0, np.inf, c=Wt["heater_low"]*dt)
            for j in range(H):
                md = g.draw_kg_per_h(tmid[j]); aa = 1 - (g.UA + md*CP)*dt/g.C
                lp.eq([(T[j+1], 1.0), (T[j], -aa), (p[j], -dt/g.C)], (g.UA*g.P["t_amb"]*dt + md*CP*g.P["t_in"]*dt)/g.C); lp.ub_([(T[j+1], -1.0), (s[j], -1.0)], -P["heater_floor_C"]); add(g.id, j, p[j], 1.0)
            wh_idx[g.id] = (p, g.Pg)
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
                    su = lp.var(1, 0, np.inf, c=Wt["ev_unmet"])
                    if valid:
                        p = lp.var(len(valid), 0, g.pmax[i], c=Wt["device_energy"]*dt); lp.ub_([(p[q], -g.eta*dt) for q in range(len(valid))] + [(su[0], -1.0)], -need)
                        for q, j in enumerate(valid): add(g.id, j, p[q], 1.0)
                        if valid[0] == 0: first.append((i, lbl, p[0]))
                    else: lp.ub_([(su[0], -1.0)], -need)
            ev_idx[g.id] = first
        b = [g for g in groups if isinstance(g, SharedBattery)][0]; Pb = b.P; cap = Pb["e_kwh"]
        pch = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt); pdis = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt)
        E = lp.var(H+1, Pb["soc_min"]*cap, Pb["soc_max"]*cap); lp.lb[E[0]] = lp.ub[E[0]] = b.E
        for j in range(H):
            lp.eq([(E[j+1], 1.0), (E[j], -1.0), (pch[j], -Pb["eta_c"]*dt), (pdis[j], dt/Pb["eta_d"])], 0.0); add("BATT", j, pch[j], 1.0); add("BATT", j, pdis[j], -1.0)
        tgt = Pb["soc_init"]*cap; de = 96 - k
        for idx, target, cost in ((H, tgt, Wt["soc_end"]), (de, tgt, Wt["soc_end"]), (P["reserve_step"]-k, P["reserve_kwh"], Wt["soc_reserve"])):
            if 1 <= idx <= H: s = lp.var(1, 0, np.inf, c=cost); lp.ub_([(E[idx], -1.0), (s[0], -1.0)], -target)
        pn = lp.var(H, -np.inf, np.inf); curt = lp.var(H, 0, 1.0, c=Wt["curtail"]*dt); st = lp.var(H, 0, np.inf, c=Wt["trafo"]*dt); rv = lp.var(H, 0, np.inf, c=Wt["reverse"]*dt)
        for j in range(H):
            lp.ub[curt[j]] = max(pv[j], 0.0)
            lp.eq([(pn[j], 1.0), (curt[j], -1.0)] + [(i, -c) for i, c in dev[j]], base[j] - pv[j])
            lp.ub_([(pn[j], 1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (rv[j], -1.0)], 0.0)
        # ---- Stage 9: bus x phase voltage constraints ----
        ids = [r[0] for r in self.res]; nm = len(self.mon); Pg = {gid: lp.var(H, -np.inf, np.inf) for gid in ids}
        for gid in ids:
            for j in range(H): lp.eq([(Pg[gid][j], 1.0)] + [(i, -c) for i, c in gj[gid][j]], 0.0)
        sh = lp.var(nm*H, 0, np.inf, c=Wt["volt"]*dt); sl = lp.var(nm*H, 0, np.inf, c=Wt["volt"]*dt); Hsel = []
        for j in range(H):
            t = (k + j) % 96; Hm = self.Hm if self.fc_pv[a+j] >= self.pv_thr else self.He; Hsel.append(Hm)
            Pnat = np.array([self.Pn[gid][t] for gid in ids])
            for i in range(nm):
                Hi = Hm[i]; const = float(Hi @ Pnat); vb = self.Vb[t, i]
                terms = [(Pg[gid][j], float(Hi[q])) for q, gid in enumerate(ids) if Hi[q] != 0.0]
                lp.ub_(terms + [(sh[i*H+j], -1.0)], P["v_hi"] - vb + const)                       # Vb + H(P-Pnat) - slack <= vhi
                lp.ub_([(ix, -c) for ix, c in terms] + [(sl[i*H+j], -1.0)], -P["v_lo"] + vb - const)   # vlo - (Vb + H(P-Pnat)) <= slack
        r = lp.solve()
        if r.status != 0: return None
        x = r.x; cmds = {}
        for gid, (p, Pgmax) in wh_idx.items(): cmds[gid] = float(np.clip(x[p[0]]/Pgmax, 0, 1))
        for gid, u in pu_idx.items(): cmds[gid] = float(np.clip(x[u[0]], 0, 1))
        for g in [g for g in groups if isinstance(g, EVGroup)]: cmds[g.id] = {(i, lbl): float(x[ix]) for i, lbl, ix in ev_idx[g.id]}
        c, d = x[pch[0]], x[pdis[0]]
        if c > 1e-6 and d > 1e-6: self.n_sim += 1
        cmds["BATT"] = float(c - d); self.plan_log.append((a, float(x[pn[0]]), float(x[curt].sum()*dt), float(x[E[H]])))
        P0 = np.array([x[Pg[gid][0]] for gid in ids]); Pnat0 = np.array([self.Pn[gid][k] for gid in ids]); Vpred = self.Vb[k] + Hsel[0] @ (P0 - Pnat0)
        self.pred_log.append((a, k, Vpred.copy(), self.Vb[k].copy()))
        if a in self.trace_steps:
            Vn = self.Vb[k]; hi_mode = Vn.max() - P["v_hi"] > P["v_lo"] - Vn.min(); w = int(np.argmax(Vn) if hi_mode else np.argmin(Vn))
            self.trace.append(dict(abs_step=a, step=k, hour=k*dt, constraint=("overvoltage" if hi_mode else "undervoltage"), node_phase=f"{self.mon[w][0]}/{self.mon[w][1]}", V_forecast_no_action=float(Vn[w]), V_pred_with_action=float(Vpred[w]),
                candidates=[dict(resource=gid, bus_phase=("a4/3-phase" if gid == "BATT" else f"{next(rr[1] for rr in self.res if rr[0]==gid)}/{'ABC'[next(rr[2] for rr in self.res if rr[0]==gid)-1]}"), H_pu_per_kW=float(Hsel[0][w, q]), natural_kW=float(Pnat0[q]), planned_kW=float(P0[q]), delta_kW=float(P0[q]-Pnat0[q]), predicted_dV_at_node=float(Hsel[0][w, q]*(P0[q]-Pnat0[q]))) for q, gid in enumerate(ids)], regime=("midday" if Hsel[0] is self.Hm else "evening")))
        return cmds
