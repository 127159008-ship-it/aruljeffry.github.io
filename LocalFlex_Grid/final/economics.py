"""Cost, emissions and reinforcement comparison. EVERY cost number below is a PROTOTYPE PLACEHOLDER ASSUMPTION (not a quote, not a measured result).
Replace with vendor quotes / tariff-order data before any claim. Structure follows the project spec: annual cost = capex x CRF + O&M (+ replacement annuity);
cost per household = annual cost / homes. Emissions use the factor from the submission (CEA CO2 Baseline Database V21.0, FY 2024-25: 0.710 tCO2/MWh), configurable."""
import json, os
EMISSION = dict(factor_tco2_per_mwh=0.710, source="CEA CO2 Baseline Database for the Indian Power Sector, V21.0 (FY 2024-25) - value as stated in the submission", note="grid-average factor applied to the CHANGE in net grid import after losses; marginal factor would differ")
FIN = dict(discount_rate=0.10, note="ASSUMPTION: 10 % real discount rate")
def crf(i, n): return i*(1+i)**n/((1+i)**n - 1)
# unit-cost placeholders (INR). Label: ASSUMPTION
UNIT = dict(
  battery_per_kwh_new=18000.0, battery_life_new_y=10, battery_om_pct_capex=0.015,
  battery_per_kwh_second_life=9000.0, battery_life_second_y=6, battery_om_pct_capex_second=0.025, second_life_usable_fraction=0.75,   # usable energy fraction after degradation: ASSUMPTION
  converter_per_kw=6000.0, converter_life_y=10,
  smart_switch_each=2500.0, switch_life_y=10, switches_per_participating_group_unit=1,     # one smart switch per controllable heater unit/pump/EV charger point
  comms_gateway_each=40000.0, comms_life_y=8, comms_opex_per_year=12000.0,
  install_pct_of_hardware=0.15, controller_software_per_year=30000.0,
  transformer_upgrade_250_to_400kva=450000.0, transformer_life_y=25, transformer_om_pct=0.01)
def annual_cost(batt_kwh, batt_kw, n_switches, n_gateways=1, second_life=False, homes=100, unit=UNIT, fin=FIN):
    i = fin["discount_rate"]; u = unit
    pk = u["battery_per_kwh_second_life"] if second_life else u["battery_per_kwh_new"]; L = u["battery_life_second_y"] if second_life else u["battery_life_new_y"]
    om = u["battery_om_pct_capex_second"] if second_life else u["battery_om_pct_capex"]
    items = {"battery": (batt_kwh*pk, L, om), "converter": (batt_kw*u["converter_per_kw"], u["converter_life_y"], 0.01), "smart_switches": (n_switches*u["smart_switch_each"], u["switch_life_y"], 0.02),
             "comms": (n_gateways*u["comms_gateway_each"], u["comms_life_y"], 0.0)}
    hw = sum(v[0] for v in items.values()); inst = hw*u["install_pct_of_hardware"]; rows = {}; ann = 0.0
    for k, (cap, life, omp) in items.items():
        a = cap*crf(i, life); o = cap*omp; rows[k] = dict(capex=cap, life_y=life, annualised_capex=a, om=o); ann += a + o     # replacement is embedded: each item annualised over ITS OWN life
    inst_a = inst*crf(i, 10); ann += inst_a + u["comms_opex_per_year"] + u["controller_software_per_year"]; rows["installation"] = dict(capex=inst, life_y=10, annualised_capex=inst_a, om=0.0)
    rows["comms_opex"] = dict(capex=0, life_y=None, annualised_capex=0, om=u["comms_opex_per_year"]); rows["software"] = dict(capex=0, life_y=None, annualised_capex=0, om=u["controller_software_per_year"])
    return dict(total_capex=hw+inst, annual_cost=ann, cost_per_household_per_year=ann/homes, usable_battery_kwh=batt_kwh*(u["second_life_usable_fraction"] if second_life else 1.0), items=rows)
def reinforcement_cost(homes=100, unit=UNIT, fin=FIN):
    c = unit["transformer_upgrade_250_to_400kva"]; a = c*crf(fin["discount_rate"], unit["transformer_life_y"]) + c*unit["transformer_om_pct"]
    return dict(total_capex=c, annual_cost=a, cost_per_household_per_year=a/homes)
def emissions(import_before_kwh, import_after_kwh, ef=EMISSION): d = (import_after_kwh - import_before_kwh)/1000.0; return dict(net_import_before_kWh=import_before_kwh, net_import_after_kWh=import_after_kwh, delta_MWh=d, factor=ef["factor_tco2_per_mwh"], delta_tCO2_per_day=d*ef["factor_tco2_per_mwh"])
