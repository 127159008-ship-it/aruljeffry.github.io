#ifdef  DISABLE_EN_ENO_PARAMETERS
  #include "iec_std_FB_no_ENENO_impl.h"
#else
  #include "iec_std_FB_impl.h"
#endif

#ifndef __POUS_INIT_ONLY__
static REAL ___WH_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL TEMP);
#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___PUMP_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL LVL);
#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___EV_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL TOT, 
  REAL URG);
#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___BATT_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL VMAX, 
  REAL VMIN, 
  REAL HOUR, 
  REAL PKW);
#endif

#ifndef __POUS_INIT_ONLY__
static REAL ___WH_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL TEMP)
{
  BOOL ENO = __BOOL_LITERAL(TRUE);
  REAL WH_RULE = 0;

  // Control execution
  if (!EN) {
    if (__ENO != NULL) {
      *__ENO = __BOOL_LITERAL(FALSE);
    }
    return WH_RULE;
  }
  if ((V > __REAL_LITERAL(1.04))) {
    WH_RULE = __REAL_LITERAL(1.0);
  } else if (((((HOUR >= __REAL_LITERAL(18.0)) && (HOUR < __REAL_LITERAL(22.0))) || (V < __REAL_LITERAL(0.96))) && (TEMP > __REAL_LITERAL(50.0)))) {
    WH_RULE = __REAL_LITERAL(0.0);
  } else {
    WH_RULE = __REAL_LITERAL(-1.0);
  };

  goto __end;

__end:
  if (__ENO != NULL) {
    *__ENO = ENO;
  }
  return WH_RULE;
}


#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___PUMP_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL LVL)
{
  BOOL ENO = __BOOL_LITERAL(TRUE);
  REAL PUMP_RULE = 0;

  // Control execution
  if (!EN) {
    if (__ENO != NULL) {
      *__ENO = __BOOL_LITERAL(FALSE);
    }
    return PUMP_RULE;
  }
  if (((V > __REAL_LITERAL(1.04)) && (LVL < __REAL_LITERAL(0.90)))) {
    PUMP_RULE = __REAL_LITERAL(1.0);
  } else if ((((HOUR >= __REAL_LITERAL(17.0)) && (HOUR < __REAL_LITERAL(21.0))) || (V < __REAL_LITERAL(0.96)))) {
    if ((LVL > __REAL_LITERAL(0.25))) {
      PUMP_RULE = __REAL_LITERAL(0.0);
    } else {
      PUMP_RULE = __REAL_LITERAL(1.0);
    };
  } else {
    PUMP_RULE = __REAL_LITERAL(-1.0);
  };

  goto __end;

__end:
  if (__ENO != NULL) {
    *__ENO = ENO;
  }
  return PUMP_RULE;
}


#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___EV_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL V, 
  REAL HOUR, 
  REAL TOT, 
  REAL URG)
{
  BOOL ENO = __BOOL_LITERAL(TRUE);
  REAL C = 0;
  REAL EV_RULE = 0;

  // Control execution
  if (!EN) {
    if (__ENO != NULL) {
      *__ENO = __BOOL_LITERAL(FALSE);
    }
    return EV_RULE;
  }
  if (((HOUR >= __REAL_LITERAL(22.0)) || (HOUR < __REAL_LITERAL(6.0)))) {
    C = __REAL_LITERAL(1.0);
  } else {
    C = __REAL_LITERAL(0.0);
  };
  if ((V < __REAL_LITERAL(0.95))) {
    C = __REAL_LITERAL(0.0);
  };
  if ((TOT > __REAL_LITERAL(0.0))) {
    if (((URG / TOT) > C)) {
      C = (URG / TOT);
    };
  };
  EV_RULE = C;

  goto __end;

__end:
  if (__ENO != NULL) {
    *__ENO = ENO;
  }
  return EV_RULE;
}


#endif
#ifndef __POUS_INIT_ONLY__
static REAL ___BATT_RULE(
  BOOL EN, 
  BOOL *__ENO, 
  REAL VMAX, 
  REAL VMIN, 
  REAL HOUR, 
  REAL PKW)
{
  BOOL ENO = __BOOL_LITERAL(TRUE);
  REAL C = 0;
  REAL X = 0;
  REAL BATT_RULE = 0;

  // Control execution
  if (!EN) {
    if (__ENO != NULL) {
      *__ENO = __BOOL_LITERAL(FALSE);
    }
    return BATT_RULE;
  }
  C = __REAL_LITERAL(0.0);
  if ((VMAX > __REAL_LITERAL(1.04))) {
    X = ((VMAX - __REAL_LITERAL(1.04)) / (__REAL_LITERAL(1.07) - __REAL_LITERAL(1.04)));
    if ((X > __REAL_LITERAL(1.0))) {
      X = __REAL_LITERAL(1.0);
    };
    C = (PKW * X);
  } else if ((((HOUR >= __REAL_LITERAL(17.0)) && (HOUR < __REAL_LITERAL(23.0))) && (VMIN < __REAL_LITERAL(0.96)))) {
    X = ((__REAL_LITERAL(0.96) - VMIN) / __REAL_LITERAL(0.04));
    if ((X > __REAL_LITERAL(1.0))) {
      X = __REAL_LITERAL(1.0);
    };
    C = ( -(PKW) * X);
  };
  BATT_RULE = C;

  goto __end;

__end:
  if (__ENO != NULL) {
    *__ENO = ENO;
  }
  return BATT_RULE;
}


#endif
