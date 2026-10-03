(* LocalFlex Grid - Stage 7 local rule layer in IEC 61131-3 Structured Text.
   Thresholds are PROTOTYPE PLACEHOLDERS identical to control/rule_based.py RULES (v_hi 1.04, v_full 1.07, v_lo 0.96, evening 17-23, shed 18-22,
   ev window 22-06, ev_vlow 0.95, wh_shed_min_T 50, pump evening 17-21, pump_reserve 0.25, pump_run_vhi_level 0.90).
   Return convention: -1.0 = "no command, device keeps its natural/local behaviour" (Python: key absent from the command dict).
   Scope: per-group decision logic. Aggregation of EV session urgency (tot, urg) is computed by the caller. NOT deployed on hardware. *)
FUNCTION WH_RULE : REAL
  VAR_INPUT V : REAL; HOUR : REAL; TEMP : REAL; END_VAR
  IF V > 1.04 THEN
    WH_RULE := 1.0;
  ELSIF ((((HOUR >= 18.0) AND (HOUR < 22.0)) OR (V < 0.96)) AND (TEMP > 50.0)) THEN
    WH_RULE := 0.0;
  ELSE
    WH_RULE := -1.0;
  END_IF;
END_FUNCTION

FUNCTION PUMP_RULE : REAL
  VAR_INPUT V : REAL; HOUR : REAL; LVL : REAL; END_VAR
  IF (V > 1.04) AND (LVL < 0.90) THEN
    PUMP_RULE := 1.0;
  ELSIF (((HOUR >= 17.0) AND (HOUR < 21.0)) OR (V < 0.96)) THEN
    IF LVL > 0.25 THEN PUMP_RULE := 0.0; ELSE PUMP_RULE := 1.0; END_IF;
  ELSE
    PUMP_RULE := -1.0;
  END_IF;
END_FUNCTION

FUNCTION EV_RULE : REAL
  VAR_INPUT V : REAL; HOUR : REAL; TOT : REAL; URG : REAL; END_VAR
  VAR C : REAL; END_VAR
  IF (HOUR >= 22.0) OR (HOUR < 6.0) THEN C := 1.0; ELSE C := 0.0; END_IF;
  IF V < 0.95 THEN C := 0.0; END_IF;
  IF TOT > 0.0 THEN
    IF (URG / TOT) > C THEN C := URG / TOT; END_IF;
  END_IF;
  EV_RULE := C;
END_FUNCTION

FUNCTION BATT_RULE : REAL
  VAR_INPUT VMAX : REAL; VMIN : REAL; HOUR : REAL; PKW : REAL; END_VAR
  VAR C : REAL; X : REAL; END_VAR
  C := 0.0;
  IF VMAX > 1.04 THEN
    X := (VMAX - 1.04) / (1.07 - 1.04); IF X > 1.0 THEN X := 1.0; END_IF;
    C := PKW * X;
  ELSIF ((HOUR >= 17.0) AND (HOUR < 23.0)) AND (VMIN < 0.96) THEN
    X := (0.96 - VMIN) / 0.04; IF X > 1.0 THEN X := 1.0; END_IF;
    C := -PKW * X;
  END_IF;
  BATT_RULE := C;
END_FUNCTION

