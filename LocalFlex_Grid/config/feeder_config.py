"""LocalFlex Grid - frozen modelling specification v1.0 (synthetic, representative network).
Every value is an ASSUMPTION unless stated. Do not change a value without recording the reason in parameter_register.csv."""
SEED = 7
MODEL_VERSION = "stage1-v0.1"
CFG = dict(
    freq_hz=50, kv_hv=11.0, kv_ll=0.415, kva=250, xhl_pct=4.5, loadloss_pct=1.0,
    feeders={"F1": ["a1","a2","a3","a4","a5"], "F2": ["b1","b2","b3","b4","b5"]},
    seg_km=0.10, homes_per_node=10, phase_prob=(0.40, 0.33, 0.27),
    pv_by_phase=(22, 12, 6), pv_kw=3.0,
    r1=0.32, x1=0.08, r0=1.28, x0=0.32,            # ohm/km, 3-wire sequence model in Stage 1
    ampacity_a=200.0, neutral_ampacity_a=100.0, r_n=0.64, x_self=0.13, x_mutual=0.05, r_ground_ohm=0.001, v_hi=1.06, v_lo=0.94, pf=0.95, home_scale=(0.75, 1.25),
    steps=96, dt_min=15)

# (parameter, value, unit, source_type, source, reason, sensitivity_range)
REGISTER = [
 ("Network type","3-phase, 3-wire sequence model (ideal neutral)","","Design decision","-","Stage 1 only; explicit 4-wire neutral added in Stage 2","-"),
 ("Nominal voltage",415,"V line-to-line","Assumption","Indian LV practice; limits to be verified","Typical Indian LV","-"),
 ("Frequency",50,"Hz","Design value","India grid","Set explicitly (OpenDSS default is 60 Hz)","-"),
 ("Transformer voltage","11/0.415","kV","Assumption","-","Typical distribution transformer","-"),
 ("Transformer rating",250,"kVA","Assumption","-","Sized for ~100 homes","200-315"),
 ("Transformer impedance",4.5,"%","Assumption","-","Typical distribution transformer value, not from a datasheet","4-5"),
 ("Transformer load loss",1.0,"%","Assumption","-","Typical, not from a datasheet","0.8-1.5"),
 ("HV source","ideal (infinite bus)","","Assumption","-","No upstream impedance modelled; optimistic","finite short-circuit level later"),
 ("Feeders / nodes per feeder","2 / 5","","Design decision","-","Keeps debugging tractable","-"),
 ("Segment length",0.10,"km","Assumption","-","Dense semi-urban spacing","0.05-0.25"),
 ("Cable r1",0.32,"ohm/km","Assumption","-","Order of magnitude for ~95 mm2 Al LV cable; NOT from a datasheet","0.32-0.60"),
 ("Cable x1",0.08,"ohm/km","Assumption","-","As above","0.07-0.09"),
 ("Cable r0 / x0","1.28 / 0.32","ohm/km","Assumption","-","Placeholder 4x r1/x1; replaced by explicit neutral in Stage 2","-"),
 ("Cable ampacity",200,"A per phase","Assumption","-","Placeholder for ~95 mm2 Al; verify against cable catalogue","150-250"),
 ("Households",100,"","Design decision","-","10 per node","-"),
 ("Phase allocation","per-home random, p = 0.40/0.33/0.27 (seed 7)","","Assumption","-","Deliberately uneven; resulting counts 42/33/25 are an outcome of the seed","test other seeds"),
 ("Household size factor","uniform 0.75-1.25","","Assumption","-","Size diversity (timing diversity added in Stage 5)","-"),
 ("Household demand shape","synthetic daily curve, evening peak ~1.9 kW (before size factor)","","Assumption","-","Not measured; same curve for all homes in Stage 1","replace with measured/standard profile"),
 ("Load power factor",0.95,"","Assumption","-","Typical residential","0.9-1.0"),
 ("Load model","constant power; OpenDSS reverts to constant impedance below 0.95 pu","","Tool default","OpenDSS","Default behaviour","-"),
 ("PV systems",40,"","Initial scenario","-","Rooftop share 40%","20-60"),
 ("PV allocation by phase","22 / 12 / 6","","Scenario choice","Selected from a sweep of two options (16/13/11 and 22/12/6)","Chosen so the baseline shows midday over-voltage; tilt to phase A is a SCENARIO CHOICE, not measured","16/13/11 .. 22/12/6"),
 ("PV rating per home",3.0,"kW","Assumption","-","Typical rooftop size","2-5"),
 ("PV output shape","clear-sky half-sine 06:30-18:00","","Assumption","-","Synthetic","cloudy case Stage 5"),
 ("PV model (Stage 1 / Case A0)","fixed output, unity power factor, no voltage response","","Design decision","-","Shows natural feeder behaviour","inverter response in Stage 3"),
 ("Voltage limits","0.94 - 1.06","pu","Assumption","To be verified against the applicable Indian standard","Planning limits","0.90-1.10"),
 ("Time grid","96 x 15 min","","Design decision","-","24 h","-"),
 ("Random seed",7,"","Reproducibility","-","Fixed for reference scenario; test other seeds","several seeds"),
]

# Stage 2 additions / supersessions (explicit 4-wire neutral). Matrices in ohm/km: phase self r=r1, mutual r=0 (no earth return), neutral r=r_n,
# x_self - x_mutual = x1 so the positive-sequence reactance is unchanged.
REGISTER_S2 = [
 ("Network type","3-phase, 4-wire (explicit neutral), neutral earthed at transformer only","","Design decision","-","Stage 2; supersedes Stage 1 3-wire model","-"),
 ("Neutral conductor resistance",0.64,"ohm/km","Assumption","-","Half-size neutral (twice phase resistance); typical of reduced-neutral LV cable but NOT from a datasheet","0.32-0.64"),
 ("Cable self / mutual reactance","0.13 / 0.05","ohm/km","Assumption","-","Chosen so x1 = 0.13-0.05 = 0.08 as in Stage 1","-"),
 ("Neutral ampacity",100,"A","Assumption","-","Half of phase ampacity placeholder","75-150"),
 ("Neutral earthing","at transformer only, 0.001 ohm","","Assumption","-","Conservative: Indian practice often adds earthing along the feeder, which would reduce neutral rise","add end-of-feeder earthing"),
]
SUPERSEDED_S2 = {"Network type","Cable r0 / x0"}

# Stage 3: autonomous inverter voltage response (NOT LocalFlex control)
INV = dict(v1=1.06, v2=1.10, p2=0.20)   # IEEE 1547-2018-style Category B volt-watt: full output up to v1, linear to p2 at v2, held at p2 above
REGISTER_S3 = [
 ("PV inverter model (Case A1)","volt-watt response, unity power factor, no volt-var","","Assumption","IEEE 1547-2018-style Category B default curve; NOT verified against the applicable Indian standard","Represents inverter protection behaviour, separate from LocalFlex supervisory control","curve start 1.04-1.08 pu"),
 ("Volt-watt curve","100% up to 1.06 pu, linearly to 20% at 1.10 pu, 20% above","pu / % of available","Assumption","as above","as above","v2 1.08-1.12"),
 ("Inverter trip","not modelled","","Simplification","-","Above 1.10 pu real inverters may trip; this would curtail more than modelled","-"),
]

# Stage 5: operating-condition variability (network, PV ratings, limits, A0/A1 logic all FROZEN)
PROFILE_SEEDS = [7, 11, 23, 42]            # 7 = reference; others for robustness. Network/home/PV placement always uses SEED=7.
DIVERSITY = dict(shift_sigma_h=0.5, shift_clip_h=1.5, noise_sigma=0.10, noise_rho=0.6)   # per-home timing shift and short-term noise
CLOUD = dict(haze=0.92, haze_sigma=0.04, haze_rho=0.7, n_events=7, dur_steps=(1,4), depth=(0.25,0.75), first_step=26, last_step=72, node_delay_steps=(0,0,1,1,2),
             overcast_mean=0.30, overcast_sigma=0.15)
SCENARIOS = {   # name: (demand_scale, solar_mode, description)
  "clear":       (1.00, "clear",    "reference weather, per-home timing diversity"),
  "cloudy":      (1.00, "cloudy",   "time-varying cloud transients moving along the feeders"),
  "high_solar":  (0.75, "clear",     "clear sky on a low-demand day (demand x0.75); PV ratings unchanged"),
  "high_demand": (1.25, "overcast", "overcast (transmittance ~0.3) on a high-demand day (demand x1.25)"),
}
REGISTER_S5 = [
 ("Household timing diversity","per-home shift ~ N(0, 0.5 h) clipped +-1.5 h; AR(1) noise sigma 10%, rho 0.6; daily energy per home preserved","","Assumption","-","Replaces identical household shape; aggregate energy unchanged, peak flattens slightly","sigma 0.25-1.0 h"),
 ("Cloud model","haze 0.92 (AR noise 4%) plus 7 transient events (1-4 steps, depth 25-75%), delayed 0-2 steps along each feeder","","Assumption","-","Synthetic; 15-min resolution cannot show faster cloud edges","n_events 3-12"),
 ("Scenario: high-solar day","clear sky, demand x0.75","","Assumption","-","Low-demand day with PV ratings unchanged","demand 0.6-0.9"),
 ("Scenario: high-demand day","overcast transmittance ~0.30, demand x1.25","","Assumption","-","Strong evening-peak stress case","demand 1.1-1.4"),
 ("Profile seeds","7 (reference), 11, 23, 42","","Reproducibility","-","Vary household and cloud randomness only; network and PV placement stay at seed 7","more seeds later"),
]

# Stage 6: flexible resource models. Groups live at a bus/phase (NOT per home). All values are ASSUMPTIONS.
DEVICE_SEED = 7
DEVICES = dict(
  water_heater=dict(n=8, p_kw_each=1.5, tank_l=25.0, ua_w_per_k=1.5, t_amb=25.0, t_in=25.0, t_set=60.0, band=5.0, t_min=45.0, t_max=65.0,
                    draw_l_per_day=40.0, groups=[("WH1","a2",3),("WH2","a4",1),("WH3","b3",2),("WH4","b5",1)]),
  pump=dict(p_kw=2.2, q_m3h=10.0, tank_m3=15.0, on_frac=0.30, off_frac=0.90, min_frac=0.10, init_frac=0.60, demand_m3_per_day=20.0, pf=0.85,
            groups=[("PUMP1","a3",1),("PUMP2","b2",3)]),
  ev=dict(n=6, p_kw=1.0, eta=0.90, arr=(17.5,21.5), dep=(5.0,8.0), e_req=(3.5,6.0), pf=0.95, groups=[("EV1","a5",1),("EV2","b4",2)]),
  battery=dict(node="a4", e_kwh=100.0, p_kw=50.0, eta_c=0.95, eta_d=0.95, soc_min=0.10, soc_max=0.95, soc_init=0.50),
)
REGISTER_S6 = [
 ("Flexible resources","modelled as groups at a bus/phase, not per home","","Design decision","-","Keeps the optimisation size manageable and keeps location/phase awareness","-"),
 ("Water heater group","4 groups x 8 heaters x 1.5 kW, 25 L tank, UA 1.5 W/K, set 60 C (band 5 K), service minimum 45 C, max 65 C, 40 L/day hot-water draw per heater","","Assumption","-","Small storage geysers; thermal storage is the flexibility","tank 15-50 L; draw 25-60 L/day"),
 ("Water heater natural control","aggregate proportional thermostat evaluated every minute","","Assumption","-","Represents desynchronised heaters; a single on/off would cycle all heaters together","-"),
 ("Community pump + tank","2 pumps, 2.2 kW, 10 m3/h, 15 m3 tank, 20 m3/day demand, float switch on 30% / off 90%, forced on below 10%","","Assumption","-","Pump + tank is a constrained buffer","tank 10-25 m3"),
 ("EV / e-rickshaw groups","2 groups x 6 vehicles, 1.0 kW grid-side, 90% charger efficiency, arrive 17.5-21.5 h, depart 5-8 h, need 3.5-6.0 kWh","","Assumption","-","Overnight depot-style home charging; not from a survey","arrival/need ranges"),
 ("EV natural control","plug-in-and-charge at full power until the energy need is met","","Assumption","-","Uncontrolled baseline","-"),
 ("EV carry-over at 00:00","previous evening assumed charged naturally","","Assumption","-","Initial state, same for all cases","-"),
 ("Shared battery","100 kWh / 50 kW, 95% each way (about 90% round trip), SoC 10-95%, start 50%, 3-phase balanced at a4","","Placeholder","-","Site and size to be chosen by study in later stages","size and site sweep"),
 ("Flexible-device placement","WH a2/C a4/A b3/B b5/A; pumps a3/A b2/C; EV a5/A b4/B","","Scenario choice","-","Spread over feeders, phases and electrical distances","-"),
 ("Device sub-stepping","1-minute internal steps, mean power over each 15-min step applied to OpenDSS","","Design decision","-","Avoids 15-minute discretisation artefacts in thermostat/float behaviour","-"),
]
