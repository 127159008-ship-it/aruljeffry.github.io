"""Stage 10 simulated DISCOM <-> LocalFlex interface (aggregated data only; no household-level data leaves the feeder).
LocalFlex -> DISCOM (every 15 min): net-import forecast, available flexibility (up/down kW), operating envelope, events.
DISCOM -> LocalFlex: dispatch request / operating constraint (import cap on the transformer for a time window).
The link can be down (outage windows): messages are lost; LocalFlex keeps operating on its LAST VALID request until it expires, then on its own default envelope."""
import numpy as np
class DiscomLink:
    def __init__(self, outages=()): self.outages = list(outages)         # list of (start_hour, end_hour) in hours of the day, applied every day
    def up(self, k): h = (k % 96)*0.25; return not any(a <= h < b for a, b in self.outages)
class SimDISCOM:
    """Issues a daily dispatch request, `lead_h` before the window starts. Default (Stage 10): absolute import cap (kW).
    Final stage adds: kind='reduce_import' (target_kw below LocalFlex's own published net-import forecast for the window) and kind='export_cap'; with priority and duration."""
    def __init__(self, cap_kw=150.0, window=(18.0, 22.0), lead_h=1.0, kind="import_cap", target_kw=None, export_cap_kw=None, priority="normal"):
        self.cap, self.win, self.lead = cap_kw, window, lead_h; self.kind = kind; self.target = target_kw; self.exp = export_cap_kw; self.priority = priority
    def request_at(self, k):
        h = (k % 96)*0.25
        if abs(h - (self.win[0] - self.lead)) < 1e-9:
            d = dict(type="dispatch", kind=self.kind, import_cap_kw=self.cap, window=self.win, issued_h=h, priority=self.priority, duration_min=int(round((self.win[1]-self.win[0])*60)))
            if self.kind == "reduce_import": d.update(target_kw=self.target, import_cap_kw=None)
            if self.kind == "export_cap": d.update(export_cap_kw=self.exp, import_cap_kw=None)
            return d
        return None
class CommLayer:
    def __init__(self, discom, link, default_cap_kw=200.0, validity_h=3.0):
        self.discom, self.link, self.default = discom, link, default_cap_kw; self.valid_h = validity_h; self.last = None; self.last_k = None; self.log = []; self.lost_down = 0; self.lost_up = 0; self.t_abs = -1
    def step(self, k_abs, report):
        """Called once per control step. Returns the currently valid DISCOM request (or None)."""
        k = k_abs % 96; up = self.link.up(k)
        req = self.discom.request_at(k)
        if req is not None:
            if up: self.last = req; self.last_k = k_abs; self.log.append(dict(step=k_abs, dir="DISCOM->LocalFlex", msg=req))
            else: self.lost_down += 1; self.log.append(dict(step=k_abs, dir="DISCOM->LocalFlex", msg="LOST (link down)"))
        if up: self.log.append(dict(step=k_abs, dir="LocalFlex->DISCOM", msg=report))
        else: self.lost_up += 1
        if self.last is not None and (k_abs - self.last_k)*0.25 > self.valid_h + (self.last["window"][1] - self.last["window"][0]) - 0.0: self.last = None   # expired
        return self.last
    def cap_vector(self, a, k, H, req, forecast=None):
        """Import cap (kW) over the planning horizon: dispatch window if a valid request is held, else the default envelope (np.inf = no extra dispatch limit)."""
        cap = np.full(H, np.inf)
        if req is not None and req.get("kind") == "reduce_import":
            if "cap_by_abs_step" not in req and forecast is not None:        # frozen ONCE, at reception, from LocalFlex's own published net-import forecast (no ratcheting)
                w0, w1 = req["window"]; fa, fv = forecast; req["cap_by_abs_step"] = {}
                for j, v in enumerate(fv):
                    h = ((fa + j) % 96)*0.25
                    if w0 <= h < w1: req["cap_by_abs_step"][fa + j] = max(float(v) - float(req["target_kw"]), 0.0)
            cb = req.get("cap_by_abs_step", {})
            for j in range(H):
                if a + j in cb: cap[j] = cb[a + j]
            return cap
        if req is not None and req.get("kind") == "export_cap": return cap         # export caps are handled as a lower bound on net import in the planner (see MPC10)
        if req is not None:
            w0, w1 = req["window"]
            for j in range(H):
                h = ((k + j) % 96)*0.25
                if w0 <= h < w1: cap[j] = req["import_cap_kw"]
        return cap

def export_cap_vector(a, k, H, req):
    """Export cap (kW, >=0) over the horizon for an 'export_cap' request, else +inf."""
    cap = np.full(H, np.inf)
    if req is not None and req.get("kind") == "export_cap":
        w0, w1 = req["window"]
        for j in range(H):
            h = ((k + j) % 96)*0.25
            if w0 <= h < w1: cap[j] = req["export_cap_kw"]
    return cap
