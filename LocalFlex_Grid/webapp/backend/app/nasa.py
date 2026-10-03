"""NASA POWER client for the web API (uses the engine's own reader/parser in final/environment.py).
NASA supplies irradiance (ALLSKY_SFC_SW_DWN, W/m2) and air temperature (T2M, deg C). It does NOT supply PV power: the LocalFlex PV model
(cell temperature from NOCT, temperature coefficient, derate) converts them to electrical output per array.
Set NASA_POWER_BASE_URL to point at another host (tests use a local fixture server)."""
import os, json, urllib.request, urllib.error, datetime
import numpy as np
from . import engine_bridge as eb
from final import environment as env

BASE = os.environ.get("NASA_POWER_BASE_URL", "https://power.larc.nasa.gov")


class NasaError(Exception): pass


def tz_from_lon(lon): return round(lon/15.0*2.0)/2.0          # approximation (nearest half hour of solar time); the UI lets the user override it


def fetch(lat, lon, date, tz_offset_h=None, timeout=30):
    try: d = datetime.date.fromisoformat(date)
    except ValueError: raise NasaError("date must be YYYY-MM-DD")
    if d < datetime.date(2001, 1, 1): raise NasaError("NASA POWER hourly data start in 2001")
    if d >= datetime.date.today(): raise NasaError("choose a past date: NASA POWER hourly data are published with a delay of days to weeks")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise NasaError("latitude/longitude out of range")
    tz = tz_from_lon(lon) if tz_offset_h is None else float(tz_offset_h); dd = date.replace("-", "")
    url = (f"{BASE}/api/temporal/hourly/point?parameters=ALLSKY_SFC_SW_DWN,T2M&community=RE&longitude={lon}&latitude={lat}&start={dd}&end={dd}&format=JSON&time-standard=UTC")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r: js = json.load(r)
    except urllib.error.HTTPError as e: raise NasaError(f"NASA POWER returned HTTP {e.code}")
    except Exception as e: raise NasaError(f"could not reach NASA POWER ({type(e).__name__}); the backend host needs outbound HTTPS to power.larc.nasa.gov")
    try: P = js["properties"]["parameter"]; g = P["ALLSKY_SFC_SW_DWN"]; t2 = P["T2M"]
    except KeyError: raise NasaError("unexpected NASA POWER response format")
    vals = [v for k, v in g.items() if k.startswith(dd)]
    if not vals or all(v < -900 for v in vals): raise NasaError("NASA POWER has no data for this location/date (fill value -999)")
    G, T = env.parse_nasa_power(js, date, tz)
    hourly = [dict(utc=k, ghi_Wm2=g[k], t2m_C=t2.get(k)) for k in sorted(g) if k.startswith(dd)]
    return dict(latitude=lat, longitude=lon, date=date, tz_offset_h=tz, source="NASA POWER hourly (ALLSKY_SFC_SW_DWN, T2M), UTC converted to local time",
                irradiance_Wm2=[round(float(x), 2) for x in G], temp_C=[round(float(x), 2) for x in T], hourly_raw=hourly)


def preview(rec, pv_kw_per_home=3.0):
    """96 x 15-min preview rows + per-array PV power from the LocalFlex PV model."""
    m = dict(env.PVM); m["rated_kw"] = pv_kw_per_home; pv = env.pv_power(rec["irradiance_Wm2"], rec["temp_C"], m)
    rows = [dict(step=i, time=f"{int(i*15//60):02d}:{i*15%60:02d}", ghi_Wm2=rec["irradiance_Wm2"][i], temp_C=rec["temp_C"][i], pv_kW_per_array=round(float(pv[i]), 3)) for i in range(96)]
    return dict(rows=rows, pv_model=dict(m), pv_daily_kWh_per_array=round(float(pv.sum()*0.25), 2),
                note="15-min values are interpolated from the hourly NASA data; one uniform sky over the feeder (no cloud movement between buses).")
