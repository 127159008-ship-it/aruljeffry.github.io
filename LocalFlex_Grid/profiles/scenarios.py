"""Stage 5 operating-condition generators. Deterministic given (profile seed, scenario). Network and PV placement are NOT touched."""
import numpy as np
from config.feeder_config import CFG, DIVERSITY, CLOUD
from profiles.household_demand import t, home_shape, solar_shape
N = 96

def household_profiles(scale, seed, demand_scale=1.0):
    """[96, homes] kW. Each home: base shape shifted in time, with AR(1) noise, renormalised to the SAME daily energy as the base shape, then x size factor x scenario scale."""
    rng = np.random.default_rng(seed*1000 + 1); H = len(scale); D = DIVERSITY
    shifts = np.clip(rng.normal(0, D["shift_sigma_h"], H), -D["shift_clip_h"], D["shift_clip_h"])
    out = np.zeros((N, H))
    for i in range(H):
        base = np.interp((t - shifts[i]) % 24.0, t, home_shape, period=24.0)
        e = np.zeros(N); eta = rng.normal(0, 1, N)
        for k in range(N): e[k] = (D["noise_rho"]*e[k-1] if k else 0) + np.sqrt(1-D["noise_rho"]**2)*eta[k]*D["noise_sigma"]
        p = base*np.exp(e); p *= home_shape.sum()/p.sum()
        out[:, i] = p*scale[i]*demand_scale
    return out

def cloud_transmittance(seed, mode):
    """[96] global transmittance before per-node delay."""
    C = CLOUD; rng = np.random.default_rng(seed*1000 + 2)
    if mode == "overcast":
        e = np.zeros(N)
        for k in range(N): e[k] = (0.7*e[k-1] if k else 0) + np.sqrt(1-0.49)*rng.normal(0, C["overcast_sigma"])
        return np.clip(C["overcast_mean"]*np.exp(e), 0.1, 0.6)
    T = np.zeros(N); e = 0.0
    for k in range(N):
        e = C["haze_rho"]*e + np.sqrt(1-C["haze_rho"]**2)*rng.normal(0, C["haze_sigma"]); T[k] = C["haze"] + e
    for _ in range(C["n_events"]):
        s0 = int(rng.integers(C["first_step"], C["last_step"])); d = int(rng.integers(C["dur_steps"][0], C["dur_steps"][1]+1)); dep = rng.uniform(*C["depth"])
        T[s0:s0+d] *= (1-dep)
    return np.clip(T, 0.1, 1.0)

def pv_availability(mode, seed, pv_nodes, nodes_per_feeder=5):
    """[96, nPV] available kW per PV. clear: frozen shape. cloudy/overcast: shape x transmittance delayed by position along the feeder."""
    nPV = len(pv_nodes); out = np.zeros((N, nPV)); clear = CFG["pv_kw"]*solar_shape
    if isinstance(mode, str) and mode.startswith("ext:"):          # final stage: irradiance-driven PV (CSV / NASA POWER); see final/environment.py
        from final.environment import pv_from_registry
        return pv_from_registry(mode[4:], nPV)
    if mode == "clear":
        for j in range(nPV): out[:, j] = clear
        return out
    T = cloud_transmittance(seed, mode)
    for j, node in enumerate(pv_nodes):
        pos = int(node[1:]) - 1; d = CLOUD["node_delay_steps"][pos]
        Tj = np.concatenate([np.full(d, T[0]), T[:N-d]]) if d else T
        out[:, j] = clear*Tj
    return out

def uniform_profiles(scale, n_pv):
    """The frozen Stage 3 inputs: identical household shape and identical clear PV."""
    return np.outer(home_shape, scale), np.tile((CFG["pv_kw"]*solar_shape)[:, None], (1, n_pv))
