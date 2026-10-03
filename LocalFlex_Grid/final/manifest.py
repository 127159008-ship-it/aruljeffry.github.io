"""FINAL_REFERENCE = localflex-final-v1: frozen configuration fingerprint + run record (versions, seeds, solver settings)."""
import sys, os, json, hashlib, platform, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
FINAL_REFERENCE = "localflex-final-v1"
FROZEN_FILES = ["config/feeder_config.py", "network/feeder_generator.py", "profiles/household_demand.py", "profiles/scenarios.py", "devices/resources.py", "validation/validator.py",
                "control/rule_based.py", "control/mpc.py", "control/mpc9.py", "control/mpc10.py", "control/discom.py", "simulation/sensitivity.py", "simulation/run_stage6.py", "simulation/run_stage8.py", "simulation/run_stage9.py", "simulation/run_stage10.py"]
def file_hashes():
    return {f: hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest()[:16] for f in FROZEN_FILES}
def config_snapshot():
    from config.feeder_config import CFG, DEVICES, SCENARIOS, SEED, DEVICE_SEED
    from control.mpc import W, PLAN
    from control.mpc10 import FAIR
    from control.rule_based import RULES
    return dict(CFG=CFG, DEVICES=DEVICES, SCENARIOS={k: list(v) for k, v in SCENARIOS.items()}, SEED=SEED, DEVICE_SEED=DEVICE_SEED, MPC_WEIGHTS=W, MPC_PLAN=PLAN, FAIRNESS=FAIR, RULES=RULES)
def config_hash():
    return hashlib.sha256(json.dumps(config_snapshot(), sort_keys=True, default=str).encode()).hexdigest()[:16]
def versions():
    import numpy, scipy, pandas, opendssdirect
    return dict(python=platform.python_version(), numpy=numpy.__version__, scipy=scipy.__version__, pandas=pandas.__version__, opendssdirect=opendssdirect.__version__,
                platform=platform.platform(), solver_lp="scipy.optimize.linprog (HiGHS)", solver_milp="scipy.optimize.milp (HiGHS), time limit 1 s, rel. gap 2%")
def manifest(extra=None):
    m = dict(final_reference=FINAL_REFERENCE, created_utc=datetime.datetime.utcnow().isoformat(timespec="seconds"), config_hash=config_hash(), file_hashes=file_hashes(), versions=versions(),
             forecast_error_seed_rule="1000 + profile seed", profile_seeds=[7, 11, 23, 42], timestep_min=15, local_resolution="1-min device sub-steps inside each 15-min step")
    if extra: m.update(extra)
    return m
def run_record(scenario, seed, variant, **kw):
    from control.mpc10 import FAIR
    from config.feeder_config import DEVICES
    b = DEVICES["battery"]
    rec = dict(final_reference=FINAL_REFERENCE, config_hash=config_hash(), scenario=scenario, seed=seed, forecast_error_seed=1000+seed, variant=variant, initial_soc_pct=b["soc_init"]*100,
               battery_kwh=b["e_kwh"], battery_kw=b["p_kw"], battery_node=b["node"], fairness_lambda=FAIR["lam"], initial_state="natural end of day 1 (identical snapshot for every case)")
    rec.update(kw); return rec
if __name__ == "__main__": print(json.dumps(manifest(), indent=1)[:1500])
