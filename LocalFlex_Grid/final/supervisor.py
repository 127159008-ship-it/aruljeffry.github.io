"""Independent safety supervisor wrapped around any LocalFlex controller (MPC C/D).
Ladder per 15-min step:
  1. MPC command (inner controller)            -> sanitised (invalid values repaired = clipped to device limits)  [REPAIR]
  2. simulate6 gate: trial OpenDSS solve, MPC command vs rule command; worse -> rule command                       [FALLBACK:rules]
  3. inner controller unavailable (solver / forecast / OpenDSS-convergence / stale measurement):
        previous approved command held for <= HOLD_MAX steps (1 h)   [FALLBACK:previous_plan]
        then Stage-7 rules                                           [FALLBACK:rules]
  4. hard-limit local override on the LAST measurement (transformer >100 %, voltage > 1.10 pu or < 0.80 pu: equipment-protection bands, prototype assumptions; the 0.94-1.06 pu design band is handled by the planner/validator):  [OVERRIDE]
Every non-PASS event is logged with time, cause, action, duration and whether hard limits stayed inside bounds."""
import numpy as np
from devices.resources import WaterHeaterGroup, PumpTank, EVGroup, SharedBattery
from control.rule_based import RuleController
from final.overrides import is_np
HOLD_MAX = 4; V_HARD_HI = 1.10; V_HARD_LO = 0.80; TRAFO_HARD_PCT = 100.0; STALE_MAX_STEPS = 2
FAULTS = ("solver_unavailable", "opendss_convergence_failure", "communication_lost", "stale_measurement", "invalid_command", "battery_unavailable", "forecast_missing")
class Supervisor:
    def __init__(self, inner, faults=()):
        self.inner = inner; self.rules = RuleController(); self.faults = list(faults)          # faults: [(name, k_start, k_end)] in absolute steps
        self.gate = True; self.fb_log = []; self.alt = None; self.n_gate = 0; self.n_fb = 0; self.prev = None; self.events = []; self.hold = 0; self.last_ok = None; self.force_unsafe = False; self._frozen_last = None; self._open = {}
        self.counts = dict(pass_=0, repair=0, fallback_previous=0, fallback_rules=0, override=0)
    def __getattr__(self, n): return getattr(self.__dict__["inner"], n)      # n_fail, solve_s, n_sim ... read through
    def _active(self, k): return {n for n, a, b in self.faults if a <= k < b}
    def _log(self, k, cause, action, safe=None):
        key = (cause, action); e = self._open.get(key)
        if e is not None and e["k_end"] == k-1: e["k_end"] = k; e["duration_min"] += 15; return
        e = dict(k_start=k, k_end=k, hour=(k % 96)*0.25, cause=cause, action=action, duration_min=15, safe=safe); self._open[key] = e; self.events.append(e)
    def _sanitise(self, groups, cmds):
        """returns (clean_cmds, status): 'ok' | 'repaired' (small excursion beyond limits, clipped) | 'invalid' (NaN/inf or > 5 % beyond limits -> rejected, ladder falls back)."""
        status = "ok"; out = {}
        def chk(x, lo, hi):
            nonlocal status
            if not np.isfinite(x): status = "invalid"; return lo
            span = max(hi - lo, 1e-9)
            if x < lo - 0.05*span or x > hi + 0.05*span: status = "invalid"
            elif x < lo - 1e-6*span or x > hi + 1e-6*span:
                if status == "ok": status = "repaired"
            return float(min(max(x, lo), hi))
        for g in groups:
            if g.id not in cmds: continue
            v = cmds[g.id]
            if isinstance(v, dict): out[g.id] = {kk: chk(x, 0.0, g.pmax[kk[0]]) for kk, x in v.items()}
            elif isinstance(g, SharedBattery): out[g.id] = chk(v, -g.P["p_kw"], g.P["p_kw"])
            else: out[g.id] = chk(v, 0.0, 1.0)
        return out, status
    def act(self, k, groups, last):
        groups = [g for g in groups if not is_np(g)]      # non-participating sub-groups (study only) are invisible to the controller and run naturally
        act_f = self._active(k); self.force_unsafe = False
        self.alt = self.rules.act(k, groups, last if "stale_measurement" not in act_f else (self._frozen_last if self._frozen_last is not None else last))
        if "stale_measurement" not in act_f: self._frozen_last = last
        cmds = None; cause = None
        for f in ("solver_unavailable", "forecast_missing", "communication_lost", "stale_measurement"):
            if f in act_f and f != "communication_lost": cause = f; break
        if "communication_lost" in act_f and cause is None:
            cause = None      # communication loss only removes the DISCOM interface; the planner continues on its last valid request (handled by CommLayer outage windows)
        if cause is None:
            cmds = self.inner.act(k, groups, last)
            if cmds is None: cause = "solver_failure"
        if "opendss_convergence_failure" in act_f: self.force_unsafe = True; self._log(k, "opendss_convergence_failure (trial solve rejected)", "FALLBACK:rules")
        if cause is not None:
            if self.last_ok is not None and self.hold < HOLD_MAX: cmds = self.last_ok; self.hold += 1; self.counts["fallback_previous"] += 1; self._log(k, cause, "FALLBACK:previous_plan")
            else: cmds = self.alt; self.counts["fallback_rules"] += 1; self._log(k, cause, "FALLBACK:rules")
        else:
            if "invalid_command" in act_f:                       # fault injection: corrupt the planner output
                cmds = dict(cmds); 
                for g in groups:
                    if isinstance(g, SharedBattery): cmds[g.id] = float("nan")
                    elif g.id in cmds and not isinstance(cmds[g.id], dict): cmds[g.id] = 7.5
                    elif g.id in cmds: cmds[g.id] = {kk: float("nan") for kk in cmds[g.id]}
            cmds, st = self._sanitise(groups, cmds)
            if st == "invalid":
                if self.last_ok is not None and self.hold < HOLD_MAX: cmds = self.last_ok; self.hold += 1; self.counts["fallback_previous"] += 1; self._log(k, "invalid_command", "FALLBACK:previous_plan")
                else: cmds = self.alt; self.counts["fallback_rules"] += 1; self._log(k, "invalid_command", "FALLBACK:rules")
            else:
                if st == "repaired": self.counts["repair"] += 1; self._log(k, "command_slightly_out_of_limits", "REPAIR")
                else: self.counts["pass_"] += 1
                if not self.force_unsafe: self.last_ok = cmds; self.hold = 0
        if "battery_unavailable" in act_f:
            cmds = dict(cmds); cmds["BATT"] = 0.0; self._log(k, "battery_unavailable", "REPLAN:battery=0")
        # hard-limit local override on the last measurement (always active; independent of the optimiser)
        if last is not None:
            ov = self._override(groups, last, cmds)
            if ov is not None: cmds = ov; self.counts["override"] += 1; self._log(k, "hard_limit", "OVERRIDE")
        return cmds
    def _override(self, groups, last, cmds):
        vcols = [c for c in last if c.startswith("V_") and c.endswith("_pu")]; vmax = max(last[c] for c in vcols); vmin = min(last[c] for c in vcols); tl = last["trafo_loading_pct"]
        if vmax <= V_HARD_HI and vmin >= V_HARD_LO and tl <= TRAFO_HARD_PCT: return None
        out = dict(cmds)
        for g in groups:
            if isinstance(g, SharedBattery):
                lim = g.P["p_kw"]; out[g.id] = lim if vmax > V_HARD_HI else (-lim if (vmin < V_HARD_LO or tl > TRAFO_HARD_PCT) else out.get(g.id, 0.0))
            elif isinstance(g, (WaterHeaterGroup, PumpTank)): out[g.id] = 1.0 if vmax > V_HARD_HI else (0.0 if (vmin < V_HARD_LO or tl > TRAFO_HARD_PCT) else out.get(g.id, None))
            elif isinstance(g, EVGroup): 
                if vmin < V_HARD_LO or tl > TRAFO_HARD_PCT: out[g.id] = 0.0        # EV device-level deadline protection still overrides in the rule layer on the next step
        return {k: v for k, v in out.items() if v is not None}
