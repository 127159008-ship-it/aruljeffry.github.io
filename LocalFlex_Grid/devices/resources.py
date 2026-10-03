"""Stage 6 flexible resource models. Each group steps in 1-minute substeps over a 15-minute interval and returns mean grid power (kW).
cmd=None means the device's natural (uncontrolled) behaviour. Safety limits always override commands. Every model keeps an energy/volume ledger."""
import copy, numpy as np
CP = 4.186/3600.0   # kWh per kg per K
def _g(t, mu, sig): return np.exp(-0.5*((t-mu)/sig)**2)

class WaterHeaterGroup:
    def __init__(self, gid, node, phase, P, draw_scale=1.0):
        self.id, self.node, self.phase, self.P = gid, node, phase, P; n = P["n"]
        self.Pg = n*P["p_kw_each"]; self.C = n*P["tank_l"]*CP; self.UA = n*P["ua_w_per_k"]/1000.0; self.draw_scale = draw_scale
        self.T = P["t_set"] - 2.0; self.led = dict(e_in=0.0, e_loss=0.0, e_draw=0.0); self.T0 = self.T
    def draw_kg_per_h(self, th):
        shape = 0.65*_g(th % 24, 6.5, 0.8) + 0.35*_g(th % 24, 19.5, 1.2); tot = 0.65*0.8*np.sqrt(2*np.pi) + 0.35*1.2*np.sqrt(2*np.pi)
        return self.draw_scale*self.P["n"]*self.P["draw_l_per_day"]*shape/tot
    def step(self, k, cmd=None):
        P, e_in = self.P, 0.0
        for m in range(15):
            th = (15*k + m)/60.0; dt = 1/60.0
            u = float(np.clip((P["t_set"] - self.T)/P["band"], 0, 1)) if cmd is None else float(np.clip(cmd, 0, 1))
            if self.T < P["t_min"]: u = 1.0
            if self.T >= P["t_max"]: u = 0.0
            md = self.draw_kg_per_h(th); ein = u*self.Pg*dt; eloss = self.UA*(self.T-P["t_amb"])*dt; edraw = md*CP*(self.T-P["t_in"])*dt
            self.T += (ein - eloss - edraw)/self.C; self.led["e_in"] += ein; self.led["e_loss"] += eloss; self.led["e_draw"] += edraw; e_in += ein
        return e_in/0.25
    def ledger_error(self): return self.C*(self.T-self.T0) - (self.led["e_in"]-self.led["e_loss"]-self.led["e_draw"])   # kWh, should be ~0

class PumpTank:
    def __init__(self, gid, node, phase, P, q_scale=1.0):
        self.id, self.node, self.phase, self.P = gid, node, phase, P; self.V = P["tank_m3"]; self.level = P["init_frac"]*self.V; self.on = False; self.q = P["q_m3h"]*q_scale
        self.led = dict(v_in=0.0, v_served=0.0, unmet=0.0, spill=0.0, run_min=0); self.L0 = self.level
    def demand_m3h(self, th):
        shape = 0.45*_g(th % 24, 6.5, 1.2) + 0.40*_g(th % 24, 18.5, 1.5); z = 0.45*1.2*np.sqrt(2*np.pi) + 0.40*1.5*np.sqrt(2*np.pi)
        return self.P["demand_m3_per_day"]*(0.85*shape/z + 0.15/24.0)
    def step(self, k, cmd=None):
        P = self.P; run_min = 0; allowed = None if cmd is None else int(round(float(np.clip(cmd, 0, 1))*15))
        for m in range(15):
            th = (15*k + m)/60.0
            if cmd is None:
                if self.level < P["on_frac"]*self.V: self.on = True
                if self.level > P["off_frac"]*self.V: self.on = False
                run = self.on
            else: run = m < allowed
            if self.level < P["min_frac"]*self.V: run = True        # safety: keep the service
            if self.level >= self.V: run = False                    # safety: tank full
            vin = self.q/60.0 if run else 0.0; vout = self.demand_m3h(th)/60.0
            self.level += vin; served = vout
            if self.level - vout < 0: served = max(self.level, 0.0); self.led["unmet"] += vout - served
            self.level -= served
            if self.level > self.V: self.led["spill"] += self.level - self.V; self.level = self.V
            self.led["v_in"] += vin; self.led["v_served"] += served; run_min += int(run)
        self.led["run_min"] += run_min; return P["p_kw"]*run_min/15.0
    def ledger_error(self): return (self.level-self.L0) - (self.led["v_in"] - self.led["v_served"] - self.led["spill"])   # m3

class EVGroup:
    def __init__(self, gid, node, phase, P, seed):
        self.id, self.node, self.phase, self.P = gid, node, phase, P; rng = np.random.default_rng(seed); n = P["n"]
        self.arr = rng.uniform(*P["arr"], n); self.dep = rng.uniform(*P["dep"], n); self.need = rng.uniform(*P["e_req"], n)
        self.pmax = np.full(n, P["p_kw"]); self.eta = P["eta"]
        self.remA = np.maximum(0.0, self.need - self.pmax*self.eta*(24.0 - self.arr))   # carry-over from previous evening (natural charging)
        self.remB = self.need.copy(); self.led = dict(grid=0.0, batt=0.0, unmetA=0.0); self.rA0 = self.remA.copy(); self.departedA = np.zeros(n, bool)
    def present(self, th):
        return (th < self.dep) & ~self.departedA, th >= self.arr
    def step(self, k, cmd=None):
        e_grid = 0.0; n = len(self.arr)
        for m in range(15):
            th = (15*k + m)/60.0; dt = 1/60.0
            for i in range(n):
                if not self.departedA[i] and th >= self.dep[i]: self.led["unmetA"] += self.remA[i]; self.remA[i] = 0.0; self.departedA[i] = True
            pa, pb = self.present(th)
            pres = [(i, "A") for i in range(n) if pa[i] and self.remA[i] > 1e-12] + [(i, "B") for i in range(n) if pb[i] and self.remB[i] > 1e-12]
            if isinstance(cmd, dict): cap = np.inf        # per-session power commands (kW), used by the predictive planner
            else: cap = np.inf if cmd is None else float(np.clip(cmd, 0, 1))*sum(self.pmax[i] for i, _ in pres) if pres else 0.0
            order = sorted(pres, key=lambda x: (self.dep[x[0]] if x[1] == "A" else self.dep[x[0]] + 24.0))   # earliest departure first
            for i, s in order:
                p = min(self.pmax[i], cap) if not isinstance(cmd, dict) else min(self.pmax[i], max(0.0, cmd.get((i, s), 0.0))); eb = min(p*self.eta*dt, self.remA[i] if s == "A" else self.remB[i]); p_used = eb/(self.eta*dt)
                if s == "A": self.remA[i] -= eb
                else: self.remB[i] -= eb
                cap -= p_used; e_grid += p_used*dt; self.led["grid"] += p_used*dt; self.led["batt"] += eb
        return e_grid/0.25
    def ledger_error(self):    # delivered battery energy + remaining + unmet - initial need (A carry-over + B need), kWh
        return self.led["batt"] + self.remA.sum() + self.remB.sum() + self.led["unmetA"] - (self.rA0.sum() + self.need.sum())

class SharedBattery:
    def __init__(self, P):
        self.P = P; self.E = P["soc_init"]*P["e_kwh"]; self.E0 = self.E; self.node = P["node"]; self.led = dict(grid_in=0.0, grid_out=0.0); self.id = "BATT"
    def step(self, k, cmd=None):
        P = self.P; dt = 0.25; c = 0.0 if cmd is None else float(cmd)
        emax, emin = P["soc_max"]*P["e_kwh"], P["soc_min"]*P["e_kwh"]
        if c >= 0: c = min(c, P["p_kw"], (emax - self.E)/(P["eta_c"]*dt)); self.E += P["eta_c"]*c*dt; self.led["grid_in"] += c*dt
        else:
            d = min(-c, P["p_kw"], (self.E - emin)*P["eta_d"]/dt); self.E -= d*dt/P["eta_d"]; self.led["grid_out"] += d*dt; c = -d
        return c
    def ledger_error(self):
        P = self.P; return (self.E - self.E0) - (P["eta_c"]*self.led["grid_in"] - self.led["grid_out"]/P["eta_d"])

def _slice_ev(full, gid, idx):
    import copy as _c
    g = _c.copy(full); g.id = gid; n = len(full.arr)
    for k, v in list(vars(full).items()):
        if isinstance(v, np.ndarray) and len(v) == n: setattr(g, k, v[idx].copy())
    g.led = dict(grid=0.0, batt=0.0, unmetA=0.0); g.P = dict(full.P, n=len(idx)); return g
def make_all(cfg_dev, seed):
    """Group list. Optional participation split (final stage): DEVICES['water_heater']['n_by_group'] / DEVICES['ev']['split'] describe NON-participating sub-groups
    (ids ending in 'N') that always run naturally; with no such keys the behaviour is exactly the frozen Stage 6 model."""
    g = []; D = cfg_dev; nbg = D["water_heater"].get("n_by_group", {}); split = D["ev"].get("split", {})
    for gid, node, ph in D["water_heater"]["groups"]: g.append(WaterHeaterGroup(gid, node, ph, dict(D["water_heater"], n=nbg.get(gid, D["water_heater"]["n"]))))
    for gid, node, ph in D["pump"]["groups"]: g.append(PumpTank(gid, node, ph, D["pump"]))
    ids = [x[0] for x in D["ev"]["groups"]]; cache = {}
    for j, (gid, node, ph) in enumerate(D["ev"]["groups"]):
        if gid in split:
            base, idx = split[gid]; jb = ids.index(base)
            if base not in cache: cache[base] = EVGroup(base, D["ev"]["groups"][jb][1], D["ev"]["groups"][jb][2], D["ev"], seed*1000 + 3 + jb)
            e = _slice_ev(cache[base], gid, idx); e.node, e.phase = node, ph; g.append(e)
        else: g.append(EVGroup(gid, node, ph, D["ev"], seed*1000 + 3 + j))
    g.append(SharedBattery(D["battery"])); return g

def warm_start(groups, days=2):
    """Run natural behaviour for a few days (no grid) and keep the state at 00:00 so every case starts from the same cyclic initial condition."""
    for g in groups:
        if isinstance(g, EVGroup): continue          # EV initial state defined analytically (carry-over)
        for _ in range(days):
            for k in range(96): g.step(k, None)
        if isinstance(g, WaterHeaterGroup): g.T0 = g.T; g.led = dict(e_in=0.0, e_loss=0.0, e_draw=0.0)
        if isinstance(g, PumpTank): g.L0 = g.level; g.led = dict(v_in=0.0, v_served=0.0, unmet=0.0, spill=0.0, run_min=0)
    return groups
