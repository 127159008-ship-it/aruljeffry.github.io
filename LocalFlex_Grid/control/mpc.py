"""Stage 8 predictive controller (Case C): 24 h rolling-horizon LP, 15-min steps, NO fairness term.
Plans with FORECASTS (not the true inputs), a basic aggregate voltage model (a + b*P_net, identified on other seeds), continuous group-level power,
battery with split charge/discharge variables (+ throughput cost, + post-check for simultaneous use), evening SoC reserve and day-end SoC target.
Only the first step of each plan is executed; the plan is re-solved every step from measured device states."""
import time, numpy as np
from scipy.optimize import linprog
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
from control.rule_based import RuleController
CP = 4.186/3600.0
W = dict(ev_unmet=50.0, heater_low=20.0, pump_low=100.0, volt=4000.0, trafo=1.0, reverse=0.02, curtail=0.2, battery_throughput=0.02, soc_end=20.0, soc_reserve=5.0, device_energy=0.001)
PLAN = dict(H=96, dt=0.25, heater_floor_C=47.0, heater_ceiling_C=64.5, pump_floor_frac=0.20, trafo_cap_kw=200.0, reserve_step=68, reserve_kwh=40.0, v_hi=1.06, v_lo=0.94,
            ev_margin_h=1.0, pv_fc_sigma=0.15, dem_fc_sigma=0.08, fc_rho=0.9, pv_smooth_steps=5)

class _LP:
    def __init__(s): s.n = 0; s.lb = []; s.ub = []; s.c = []; s.eqr = []; s.eqc = []; s.eqv = []; s.beq = []; s.ur = []; s.uc = []; s.uv = []; s.bub = []
    def var(s, n, lb=0.0, ub=np.inf, c=0.0):
        idx = np.arange(s.n, s.n+n); s.n += n; s.lb += list(np.broadcast_to(lb, (n,))); s.ub += list(np.broadcast_to(ub, (n,))); s.c += list(np.broadcast_to(c, (n,))); return idx
    def eq(s, terms, rhs):
        r = len(s.beq)
        for i, v in terms: s.eqr.append(r); s.eqc.append(int(i)); s.eqv.append(float(v))
        s.beq.append(rhs)
    def ub_(s, terms, rhs):
        r = len(s.bub)
        for i, v in terms: s.ur.append(r); s.uc.append(int(i)); s.uv.append(float(v))
        s.bub.append(rhs)
    def solve(s):
        import scipy.sparse as sp
        Ae = sp.csr_matrix((s.eqv, (s.eqr, s.eqc)), shape=(len(s.beq), s.n)); Au = sp.csr_matrix((s.uv, (s.ur, s.uc)), shape=(len(s.bub), s.n))
        return linprog(s.c, A_ub=Au, b_ub=s.bub, A_eq=Ae, b_eq=s.beq, bounds=np.column_stack([s.lb, s.ub]), method="highs")

def make_forecast(dem_total, pv_total, seed, perfect=False, P=PLAN):
    """Forecast = smoothed truth x (1 + AR(1) error), independent noise. Tiled over 4 days (planning horizon wraps past midnight; same-day-profile assumption)."""
    n = 384; rng = np.random.default_rng(1000 + seed)
    def ar(sig):
        e = np.zeros(n); e[0] = rng.normal(0, sig)
        for i in range(1, n): e[i] = P["fc_rho"]*e[i-1] + np.sqrt(1-P["fc_rho"]**2)*rng.normal(0, sig)
        return e
    k = P["pv_smooth_steps"]; pv4 = np.tile(pv_total, 4); pv_s = np.convolve(np.pad(pv4, k, mode="edge"), np.ones(k)/k, mode="same")[k:-k]
    ep, ed = ar(P["pv_fc_sigma"]), ar(P["dem_fc_sigma"])
    if perfect: return np.tile(dem_total, 4), pv4
    return np.tile(dem_total, 4)*(1+ed), np.maximum(0.0, pv_s*(1+ep))

class MPCController:
    def __init__(self, cal, dem_total, pv_total, seed, gate=True, perfect=False, weights=W, plan=PLAN):
        self.cal = cal; self.W = weights; self.P = plan; self.fc_dem, self.fc_pv = make_forecast(dem_total, pv_total, seed, perfect, plan)
        self.rules = RuleController(); self.prev = None; self.a = 0; self.gate = gate; self.alt = None
        self.n_gate = 0; self.n_fb = 0; self.n_fail = 0; self.n_sim = 0; self.solve_s = []; self.plan_log = []
    def act(self, k, groups, last):
        a = self.a; self.a += 1; self.alt = self.rules.act(k, groups, last); t0 = time.time()
        try: cmds = self.plan(k, a, groups)
        except Exception as e: cmds = None; self.last_err = repr(e)
        self.solve_s.append(time.time()-t0)
        if cmds is None: self.n_fail += 1; return self.alt
        return cmds
    def plan(self, k, a, groups):
        P, Wt, cal = self.P, self.W, self.cal; H, dt = P["H"], P["dt"]; lp = _LP()
        base = self.fc_dem[a:a+H]; pv = self.fc_pv[a:a+H]; tmid = ((k + np.arange(H)) % 96)*dt + dt/2
        dev = [[] for _ in range(H)]; wh_idx = {}; pu_idx = {}; ev_idx = {}
        for g in [g for g in groups if isinstance(g, WaterHeaterGroup)]:
            p = lp.var(H, 0, g.Pg, c=Wt["device_energy"]*dt); T = lp.var(H+1, 30.0, max(P["heater_ceiling_C"], g.T+0.01)); lp.lb[T[0]] = lp.ub[T[0]] = g.T
            s = lp.var(H, 0, np.inf, c=Wt["heater_low"]*dt)
            for j in range(H):
                md = g.draw_kg_per_h(tmid[j]); aa = 1 - (g.UA + md*CP)*dt/g.C
                lp.eq([(T[j+1], 1.0), (T[j], -aa), (p[j], -dt/g.C)], (g.UA*g.P["t_amb"]*dt + md*CP*g.P["t_in"]*dt)/g.C)
                lp.ub_([(T[j+1], -1.0), (s[j], -1.0)], -P["heater_floor_C"]); dev[j].append((p[j], 1.0))
            wh_idx[g.id] = (p, g.Pg)
        for g in [g for g in groups if isinstance(g, PumpTank)]:
            u = lp.var(H, 0, 1, c=Wt["device_energy"]*dt*g.P["p_kw"]); L = lp.var(H+1, 0, g.V); lp.lb[L[0]] = lp.ub[L[0]] = g.level; s = lp.var(H, 0, np.inf, c=Wt["pump_low"]*dt)
            for j in range(H):
                lp.eq([(L[j+1], 1.0), (L[j], -1.0), (u[j], -g.q*dt)], -g.demand_m3h(tmid[j])*dt)
                lp.ub_([(L[j+1], -1.0), (s[j], -1.0)], -P["pump_floor_frac"]*g.V); dev[j].append((u[j], g.P["p_kw"]))
            pu_idx[g.id] = u
        for g in [g for g in groups if isinstance(g, EVGroup)]:
            first = []; n = len(g.arr); tot_pres = 0.0
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
                    if not valid: mg = 0.0; valid = steps(0.0)          # deadline margin cannot be kept: plan to the true departure
                    need = rem
                    if lbl == "B": need = max(0.0, rem - g.pmax[i]*g.eta*max(0.0, g.dep[i] + 24 - mg - (k+H)*dt))
                    if lbl == "A" and not valid: continue
                    su = lp.var(1, 0, np.inf, c=Wt["ev_unmet"])
                    if valid:
                        p = lp.var(len(valid), 0, g.pmax[i], c=Wt["device_energy"]*dt)
                        lp.ub_([(p[q], -g.eta*dt) for q in range(len(valid))] + [(su[0], -1.0)], -need)
                        for q, j in enumerate(valid): dev[j].append((p[q], 1.0))
                        if valid[0] == 0: first.append((i, lbl, p[0]))
                    else: lp.ub_([(su[0], -1.0)], -need)
            ev_idx[g.id] = first
        b = [g for g in groups if isinstance(g, SharedBattery)][0]; Pb = b.P; cap = Pb["e_kwh"]
        pch = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt); pdis = lp.var(H, 0, Pb["p_kw"], c=Wt["battery_throughput"]*dt)
        E = lp.var(H+1, Pb["soc_min"]*cap, Pb["soc_max"]*cap); lp.lb[E[0]] = lp.ub[E[0]] = b.E
        for j in range(H):
            lp.eq([(E[j+1], 1.0), (E[j], -1.0), (pch[j], -Pb["eta_c"]*dt), (pdis[j], dt/Pb["eta_d"])], 0.0); dev[j] += [(pch[j], 1.0), (pdis[j], -1.0)]
        tgt = Pb["soc_init"]*cap; de = 96 - k
        for idx, target, cost in ((H, tgt, Wt["soc_end"]), (de, tgt, Wt["soc_end"]), (P["reserve_step"]-k, P["reserve_kwh"], Wt["soc_reserve"])):
            if 1 <= idx <= H: s = lp.var(1, 0, np.inf, c=cost); lp.ub_([(E[idx], -1.0), (s[0], -1.0)], -target)
        pn = lp.var(H, -np.inf, np.inf); curt = lp.var(H, 0, 1.0, c=Wt["curtail"]*dt); sh = lp.var(H, 0, np.inf, c=Wt["volt"]*dt); sl = lp.var(H, 0, np.inf, c=Wt["volt"]*dt)
        st = lp.var(H, 0, np.inf, c=Wt["trafo"]*dt); rv = lp.var(H, 0, np.inf, c=Wt["reverse"]*dt)
        for j in range(H):
            lp.ub[curt[j]] = max(pv[j], 0.0)
            lp.eq([(pn[j], 1.0), (curt[j], -1.0)] + [(i, -c) for i, c in dev[j]], base[j] - pv[j])
            lp.ub_([(pn[j], cal["b_hi"]), (sh[j], -1.0)], P["v_hi"] - cal["a_hi"]); lp.ub_([(pn[j], -cal["b_lo"]), (sl[j], -1.0)], cal["a_lo"] - P["v_lo"])
            lp.ub_([(pn[j], 1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (st[j], -1.0)], P["trafo_cap_kw"]); lp.ub_([(pn[j], -1.0), (rv[j], -1.0)], 0.0)
        r = lp.solve()
        if r.status != 0: return None
        x = r.x; cmds = {}
        for gid, (p, Pg) in wh_idx.items(): cmds[gid] = float(np.clip(x[p[0]]/Pg, 0, 1))
        for gid, u in pu_idx.items(): cmds[gid] = float(np.clip(x[u[0]], 0, 1))
        for g in [g for g in groups if isinstance(g, EVGroup)]: cmds[g.id] = {(i, lbl): float(x[ix]) for i, lbl, ix in ev_idx[g.id]}
        c, d = x[pch[0]], x[pdis[0]]
        if c > 1e-6 and d > 1e-6: self.n_sim += 1
        cmds["BATT"] = float(c - d)
        self.plan_log.append((a, float(x[pn[0]]), float(x[curt].sum()*dt), float(x[E[H]])))
        return cmds
