"""Stage 7 rule-based controller (Case B). No forecast, no optimiser, no network model, no MPC.
Each device group reacts to (i) the voltage measured at its OWN bus/phase in the previous 15-min step and (ii) fixed time-of-day windows.
Thresholds are placeholders (see RULES). Device safety limits always override these commands (Stage 6)."""
import numpy as np
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
RULES = dict(v_hi=1.04, v_full=1.07, v_lo=0.96, evening=(17.0, 23.0), shed_win=(18.0, 22.0), ev_window=(22.0, 6.0), ev_margin_h=1.0, ev_vlow=0.95,
             wh_shed_min_T=50.0, pump_evening=(17.0, 21.0), pump_reserve=0.25, pump_run_vhi_level=0.90)
def _in(h, w): return (w[0] <= h < w[1]) if w[0] < w[1] else (h >= w[0] or h < w[1])
class RuleController:
    def __init__(self, R=RULES): self.R = R; self.prev = None
    def act(self, k, groups, last):
        R = self.R; h = k*0.25; cmds = {}
        if last is None: return cmds                      # first step ever: natural behaviour
        V = lambda node, ph: last[f"V_{node}_{'ABC'[ph-1]}_pu"]
        for g in groups:
            if isinstance(g, WaterHeaterGroup):
                v = V(g.node, g.phase)
                if v > R["v_hi"]: cmds[g.id] = 1.0                                              # absorb surplus (stops at t_max by device safety)
                elif (_in(h, R["shed_win"]) or v < R["v_lo"]) and g.T > R["wh_shed_min_T"]: cmds[g.id] = 0.0   # shed in peak / low voltage
            elif isinstance(g, PumpTank):
                v = V(g.node, g.phase); lvl = g.level/g.V
                if v > R["v_hi"] and lvl < R["pump_run_vhi_level"]: cmds[g.id] = 1.0
                elif (_in(h, R["pump_evening"]) or v < R["v_lo"]): cmds[g.id] = 0.0 if lvl > R["pump_reserve"] else 1.0
            elif isinstance(g, EVGroup):
                v = V(g.node, g.phase); cmd = 1.0 if _in(h, R["ev_window"]) else 0.0
                if v < R["ev_vlow"]: cmd = 0.0
                tot = urg = 0.0
                for i in range(len(g.arr)):
                    if (h < g.dep[i]) and (not g.departedA[i]) and g.remA[i] > 1e-12:
                        tot += g.pmax[i]; 
                        if g.remA[i]/(g.pmax[i]*g.eta) + R["ev_margin_h"] >= g.dep[i]-h: urg += g.pmax[i]
                    if h >= g.arr[i] and g.remB[i] > 1e-12:
                        tot += g.pmax[i]
                        if g.remB[i]/(g.pmax[i]*g.eta) + R["ev_margin_h"] >= g.dep[i]+24.0-h: urg += g.pmax[i]
                if tot > 0: cmd = max(cmd, urg/tot)
                cmds[g.id] = cmd
            elif isinstance(g, SharedBattery):
                vs = [V(g.node, p) for p in (1, 2, 3)]; vmax, vmin = max(vs), min(vs); P = g.P["p_kw"]; c = 0.0
                if vmax > R["v_hi"]: c = P*min(1.0, (vmax-R["v_hi"])/(R["v_full"]-R["v_hi"]))
                elif _in(h, R["evening"]) and vmin < R["v_lo"]: c = -P*min(1.0, (R["v_lo"]-vmin)/0.04)
                cmds[g.id] = c
        return cmds
