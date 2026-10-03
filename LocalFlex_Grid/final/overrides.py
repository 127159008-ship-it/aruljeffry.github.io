"""Study overrides applied IN PLACE to the frozen configuration objects (restored afterwards) + controller wrappers for participation and communication delay.
No controller parameter is changed by any study except where the study itself defines the variable (forecast sigma, battery size/power/location, participation, network parameters)."""
import copy, contextlib, sys, os
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from config.feeder_config import CFG, DEVICES
from control.mpc import PLAN
@contextlib.contextmanager
def overrides(participation=None, battery=None, plan=None, cfg=None, devices=None, reserve_frac=0.4):
    sys.path.insert(0, os.path.join(ROOT, "simulation")); import sensitivity as _sens
    sv = (copy.deepcopy(CFG), copy.deepcopy(DEVICES), dict(PLAN)); live0 = _sens.LIVE_REF
    try:
        _sens.LIVE_REF = bool(cfg or devices or battery or participation is not None)
        if cfg:
            CFG.update(cfg)
            if "kva" in cfg: PLAN["trafo_cap_kw"] = 0.8*cfg["kva"]          # planner transformer cap = 80 % of rating (= 200 kW at 250 kVA, the reference rule)
        if devices:
            for k, v in devices.items(): DEVICES[k].update(v)
        if battery:
            DEVICES["battery"].update(battery); PLAN["reserve_kwh"] = reserve_frac*DEVICES["battery"]["e_kwh"]       # evening reserve = 40 % of capacity (= 40 kWh at 100 kWh, as in the reference)
        if plan: PLAN.update(plan)
        if participation is not None and participation < 1.0:
            wh, ev = DEVICES["water_heater"], DEVICES["ev"]; n = wh["n"]; nc = max(1, int(round(participation*n))); wh["n_by_group"] = {}; extra = []
            for gid, node, ph in list(wh["groups"]): wh["n_by_group"][gid] = nc; wh["n_by_group"][gid+"N"] = n-nc; extra.append((gid+"N", node, ph))
            wh["groups"] = list(wh["groups"]) + extra; ne = ev["n"]; ec = max(1, int(round(participation*ne))); ev["split"] = {}; extra = []
            for gid, node, ph in list(ev["groups"]): ev["split"][gid] = (gid, list(range(ec))); ev["split"][gid+"N"] = (gid, list(range(ec, ne))); extra.append((gid+"N", node, ph))
            ev["groups"] = list(ev["groups"]) + extra; DEVICES["_participation_realised"] = dict(heater_units_controlled=f"{nc}/{n}", ev_vehicles_controlled=f"{ec}/{ne}")
        yield
    finally:
        _sens.LIVE_REF = live0; CFG.clear(); CFG.update(sv[0]); DEVICES.clear(); DEVICES.update(sv[1]); PLAN.clear(); PLAN.update(sv[2])
def is_np(g): return g.id.endswith("N") and g.id[:-1] in ("WH1", "WH2", "WH3", "WH4", "EV1", "EV2")
class GroupFilter:
    """Hides non-participating sub-groups (ids ending 'N') from a controller; they keep running naturally. Used for Case B and as a base for C/D."""
    def __init__(self, inner): self.inner = inner; self.gate = getattr(inner, "gate", False); self.n_gate = 0; self.n_fb = 0; self.prev = None
    @property
    def alt(self): return getattr(self.inner, "alt", None)
    def __getattr__(self, n): return getattr(self.__dict__["inner"], n)
    def act(self, k, groups, last):
        c = self.inner.act(k, [g for g in groups if not is_np(g)], last); return None if c is None else {a: b for a, b in c.items() if not (a.endswith("N") and a[:-1] in ("WH1", "WH2", "WH3", "WH4", "EV1", "EV2"))}
class Delay:
    """Communication delay in 15-min steps (the model's planning resolution). meas_steps: controller sees measurements that old; cmd_steps: commands take effect that many steps late
    (until then devices run naturally / previous command). Delays of seconds are below the resolution of the 15-min plan / 1-min device model and are not resolvable here."""
    def __init__(self, inner, meas_steps=0, cmd_steps=0): self.inner = inner; self.ms = meas_steps; self.cs = cmd_steps; self.hist = []; self.q = []; self.gate = getattr(inner, "gate", False); self.n_gate = 0; self.n_fb = 0; self.prev = None
    @property
    def alt(self): return getattr(self.inner, "alt", None)
    def __getattr__(self, n): return getattr(self.__dict__["inner"], n)
    def act(self, k, groups, last):
        self.hist.append(last); old = self.hist[-1-self.ms] if len(self.hist) > self.ms else None
        c = self.inner.act(k, groups, old if old is not None else last); self.q.append(c)
        return self.q[-1-self.cs] if len(self.q) > self.cs else {}

class Only:
    """Controller sees only the listed group ids (battery-only comparison: flexible loads stay natural; their natural power is added to the planner base load)."""
    def __init__(self, inner, ids): self.inner = inner; self.ids = set(ids); self.gate = getattr(inner, "gate", False); self.n_gate = 0; self.n_fb = 0; self.prev = None
    @property
    def alt(self): return getattr(self.inner, "alt", None)
    def __getattr__(self, n): return getattr(self.__dict__["inner"], n)
    def act(self, k, groups, last):
        c = self.inner.act(k, [g for g in groups if g.id in self.ids], last); return None if c is None else {a: b for a, b in c.items() if a in self.ids}
