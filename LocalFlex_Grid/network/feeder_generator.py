import numpy as np
def build(cfg, seed):
    rng = np.random.default_rng(seed)
    nodes = [n for f in cfg["feeders"].values() for n in f]
    homes = [(n, int(rng.choice([1,2,3], p=cfg["phase_prob"]))) for n in nodes for _ in range(cfg["homes_per_node"])]
    scale = rng.uniform(*cfg["home_scale"], size=len(homes)); pv = []
    for ph, k in zip((1,2,3), cfg["pv_by_phase"]):
        idx = [i for i,h in enumerate(homes) if h[1]==ph]
        pv += [int(i) for i in rng.choice(idx, size=min(k,len(idx)), replace=False)]
    return dict(nodes=nodes, homes=homes, scale=scale, pv=sorted(pv))

def write_dss(cfg, m, path):
    L = ["! LocalFlex Grid network (Stage 1: 3-wire sequence model, 50 Hz). ALL VALUES ARE ASSUMPTIONS - see parameter_register.csv.",
         "! Load and PV powers (kW) are set by the Python runner each 15-min step; kW values below are base values.",
         f"set DefaultBaseFrequency={cfg['freq_hz']}", "clear",
         f"new circuit.lf basekv={cfg['kv_hv']} pu=1.0 phases=3 bus1=src basefreq={cfg['freq_hz']}",
         f"new transformer.tr phases=3 windings=2 buses=[src,lv] conns=[delta,wye] kvs=[{cfg['kv_hv']},{cfg['kv_ll']}] kvas=[{cfg['kva']},{cfg['kva']}] %loadloss={cfg['loadloss_pct']} xhl={cfg['xhl_pct']}",
         f"new linecode.lv nphases=3 r1={cfg['r1']} x1={cfg['x1']} r0={cfg['r0']} x0={cfg['x0']} units=km basefreq={cfg['freq_hz']}"]
    for fn, ns in cfg["feeders"].items():
        prev = "lv"
        for n in ns:
            L.append(f"new line.{fn}_{n} bus1={prev} bus2={n} linecode=lv length={cfg['seg_km']} units=km"); prev = n
    for i,(n,p) in enumerate(m["homes"]):
        L.append(f"new load.h{i} bus1={n}.{p} phases=1 kv={cfg['kv_ll']/3**0.5:.4f} kw={m['scale'][i]:.3f} pf={cfg['pf']} model=1")
    for i in m["pv"]:
        n,p = m["homes"][i]
        L.append(f"new generator.pv{i} bus1={n}.{p} phases=1 kv={cfg['kv_ll']/3**0.5:.4f} kw={cfg['pv_kw']} pf=1 model=1")
    L += [f"set voltagebases=[{cfg['kv_hv']},{cfg['kv_ll']}]", "calcv", "set mode=snap"]
    open(path, "w").write("\n".join(L) + "\n")

def write_dss_4wire(cfg, m, path):
    kvln = cfg["kv_ll"]/3**0.5
    r=cfg['r1']; rm = f"({r} | 0 {r} | 0 0 {r} | 0 0 0 {cfg['r_n']})"
    xs, xm = cfg["x_self"], cfg["x_mutual"]
    xmat = f"({xs} | {xm} {xs} | {xm} {xm} {xs} | {xm} {xm} {xm} {xs})"
    L = ["! LocalFlex Grid network (Stage 2: 3-phase 4-wire with explicit neutral, 50 Hz). ALL VALUES ARE ASSUMPTIONS - see parameter_register.csv.",
         f"set DefaultBaseFrequency={cfg['freq_hz']}", "clear",
         f"new circuit.lf basekv={cfg['kv_hv']} pu=1.0 phases=3 bus1=src basefreq={cfg['freq_hz']}",
         f"new transformer.tr phases=3 windings=2 buses=[src,lv.1.2.3.4] conns=[delta,wye] kvs=[{cfg['kv_hv']},{cfg['kv_ll']}] kvas=[{cfg['kva']},{cfg['kva']}] %loadloss={cfg['loadloss_pct']} xhl={cfg['xhl_pct']}",
         f"new reactor.ng phases=1 bus1=lv.4 R={cfg['r_ground_ohm']} X=0.0001",
         f"new linecode.lv4 nphases=4 rmatrix={rm} xmatrix={xmat} units=km basefreq={cfg['freq_hz']}"]
    for fn, ns in cfg["feeders"].items():
        prev = "lv"
        for n in ns:
            L.append(f"new line.{fn}_{n} bus1={prev}.1.2.3.4 bus2={n}.1.2.3.4 phases=4 linecode=lv4 length={cfg['seg_km']} units=km"); prev = n
    for i,(n,p) in enumerate(m["homes"]):
        L.append(f"new load.h{i} bus1={n}.{p}.4 phases=1 kv={kvln:.4f} kw={m['scale'][i]:.3f} pf={cfg['pf']} model=1")
    for i in m["pv"]:
        n,p = m["homes"][i]
        L.append(f"new generator.pv{i} bus1={n}.{p}.4 phases=1 kv={kvln:.4f} kw={cfg['pv_kw']} pf=1 model=1")
    L += [f"set voltagebases=[{cfg['kv_hv']},{cfg['kv_ll']}]", "calcv", "set mode=snap"]
    open(path, "w").write("\n".join(L) + "\n")
