#include "iec_std_lib.h"
#include "accessor.h"
#include "POUS.h"
#include "POUS.c"
float wh_rule(float v, float hour, float temp){ BOOL eno; return ___WH_RULE(1, &eno, v, hour, temp); }
float pump_rule(float v, float hour, float lvl){ BOOL eno; return ___PUMP_RULE(1, &eno, v, hour, lvl); }
float ev_rule(float v, float hour, float tot, float urg){ BOOL eno; return ___EV_RULE(1, &eno, v, hour, tot, urg); }
float batt_rule(float vmax, float vmin, float hour, float pkw){ BOOL eno; return ___BATT_RULE(1, &eno, vmax, vmin, hour, pkw); }
