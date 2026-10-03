"""Environment input layer: synthetic (default, permanent) | CSV | NASA POWER (API client; network-dependent).
irradiance -> PV model -> available PV power -> (inverter volt-watt, curtailment by LocalFlex) -> OpenDSS.
PV model (documented simplification, all parameters are assumptions):  Tcell = Tamb + (NOCT-20)/800 * G ;  P = Prated * (G/1000) * (1 + gamma*(Tcell-25)) * derate ; clipped to [0, Prated*inv_ratio]
Uniform irradiance over the feeder (no spatial cloud delay) when driven by external data; the synthetic cloud model keeps its per-node delays.
NASA POWER hourly parameters: ALLSKY_SFC_SW_DWN (W/m2, global horizontal) and T2M (deg C), request time-standard UTC, converted to local time by tz_offset_h (India 5.5)."""
import os, sys, json, csv, datetime
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
PVM = dict(noct_c=45.0, gamma_per_k=-0.004, derate=0.90, inv_ratio=1.0, rated_kw=3.0)      # ASSUMPTIONS
_REG = {}
def pv_power(G, Tamb, m=PVM):
    G = np.asarray(G, float); Tc = np.asarray(Tamb, float) + (m["noct_c"]-20.0)/800.0*G
    return np.clip(m["rated_kw"]*(G/1000.0)*(1.0 + m["gamma_per_k"]*(Tc-25.0))*m["derate"], 0.0, m["rated_kw"]*m["inv_ratio"])
def to_96(t_hours, y):
    """Interpolate an irregular local-time series onto the 96 x 15-min grid (cyclic day)."""
    t = np.asarray(t_hours, float); y = np.asarray(y, float); o = np.argsort(t); t, y = t[o], y[o]; g = np.arange(96)*0.25 + 0.125
    return np.interp(g, t, y, left=y[0], right=y[-1])
def load_csv(path):
    """CSV columns: time (hh:mm or decimal hour), irradiance_Wm2 [, temp_C]. Returns (G[96], T[96])."""
    t = []; G = []; T = []
    for r in csv.DictReader(open(path)):
        ts = r["time"]; h = float(ts.split(":")[0]) + float(ts.split(":")[1])/60.0 if ":" in ts else float(ts)
        t.append(h); G.append(float(r["irradiance_Wm2"])); T.append(float(r.get("temp_C", 30.0) or 30.0))
    return to_96(t, G), to_96(t, T)
def nasa_power_url(lat, lon, date):
    d = date.replace("-", ""); return (f"https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=ALLSKY_SFC_SW_DWN,T2M&community=RE&longitude={lon}&latitude={lat}&start={d}&end={d}&format=JSON&time-standard=UTC")
def parse_nasa_power(js, date, tz_offset_h=5.5):
    P = js["properties"]["parameter"]; d = date.replace("-", ""); t = []; G = []; T = []
    for k, v in P["ALLSKY_SFC_SW_DWN"].items():
        if not k.startswith(d) or v < -900: continue
        hr = int(k[8:10]) + 0.5 + tz_offset_h                    # hourly value centred on hh:30 UTC
        t.append(hr % 24); G.append(v); T.append(P["T2M"].get(k, 30.0))
    return to_96(t, G), to_96(t, T)
def fetch_nasa_power(lat, lon, date, tz_offset_h=5.5, timeout=30):
    import urllib.request
    js = json.load(urllib.request.urlopen(nasa_power_url(lat, lon, date), timeout=timeout)); return parse_nasa_power(js, date, tz_offset_h)
def register(name, G, T, m=PVM): _REG[name] = pv_power(G, T, m)            # 96 vector (kW per 3 kW array)
def pv_from_registry(name, nPV): return np.tile(_REG[name][:, None], (1, nPV))
def register_scenario(name, G, T, demand_scale=1.0, m=PVM, desc="external irradiance"):
    """Make an external-irradiance day usable as a scenario name in the engine (process-local)."""
    from config.feeder_config import SCENARIOS
    register(name, G, T, m); SCENARIOS[name] = (demand_scale, "ext:"+name, desc)
