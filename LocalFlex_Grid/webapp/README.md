# LocalFlex Grid digital twin (web app)

An interactive front end and API around the existing LocalFlex engine (OpenDSS + Python MPC + safety supervisor). **The browser never runs OpenDSS or the MPC; the backend owns the simulation.** Everything on screen is read from a stored run of the real pipeline:

```
location + date ──► NASA POWER (GHI, T2M) ──► LocalFlex PV model ──► PV power per array
PV penetration ───► PV fleet (homes × kWp, split over phases)
                         │
                         ▼
 OpenDSS feeder state ─► MPC (C / D) ─► OpenDSS trial gate ─► safety supervisor ─► OpenDSS (actual result) ─► UI
```

Cases A (no control), B (Stage-7 rules), C (MPC) and D (MPC + fairness) are the existing definitions; every run solves all four, so the controller selector switches between real, stored results.

## What is new vs the engine

| Need | How it was done |
|---|---|
| Per-bus P/Q, loads and PV | one optional hook (`run_stage6.STEP_HOOK`, `None` by default) records segment kW/kvar and per-bus kW from the OpenDSS solution. Frozen A0/A1 outputs are unchanged. |
| MPC trace at every step | `run_stage10.TRACE_ALL` (default off) extends the existing Stage 9/10 trace from 2 steps to all 128. |
| Safety state per step | `Supervisor.fb_log` records the steps where the OpenDSS gate replaced the MPC command. |
| PV penetration | `engine_bridge.pv_split`: n PV homes split in proportion to the frozen 22/12/6 phase mix, capped by homes per phase. **40 % reproduces the baseline exactly.** |
| NASA → simulation | `app/nasa.py` uses the engine's own reader (`final/environment.py`); the result is registered as an irradiance-driven scenario. |

## Repository layout

```
webapp/backend/   FastAPI service (app/main.py, engine_bridge.py, nasa.py), tests, demo_jobs/, analysis_data/
webapp/frontend/  React + Vite single-page app
Dockerfile, render.yaml, docker-compose.yml   (repository root)
```
The backend imports the engine from the repository root (`LOCALFLEX_ROOT`, default two levels up), so keep `config/ control/ devices/ final/ network/ profiles/ simulation/` next to `webapp/`.

## Local development

```bash
# 1. backend (Python 3.13 was used for testing)
cd webapp/backend
pip install -r requirements.txt
uvicorn app.main:app --port 8000          # API docs: http://localhost:8000/docs

# 2. frontend
cd webapp/frontend
npm install
npm run dev                               # http://localhost:5173, /api is proxied to :8000
```
A run takes about 2.5 minutes on 2 CPUs (A, B, C and D solved with OpenDSS and a 1-second MILP per 15-minute step). Identical configurations are cached by hash.

Tests: `cd webapp/backend && python -m pytest tests -q` (fast API tests, NASA parsing against a local fixture). The fixture holds synthetic values in NASA POWER's response format; **it is not NASA data**.

## Testing NASA POWER live (do this once on your machine or host)

```bash
curl "http://localhost:8000/api/nasa" -H 'content-type: application/json' \
     -d '{"latitude":13.0827,"longitude":80.2707,"date":"2026-03-15"}'
```
The development sandbox this was built in could not reach `power.larc.nasa.gov`, so the live fetch has **not** been exercised against the real service; only the response-format parser has been tested. If it fails, the API returns a clear 502 message (usually: no outbound HTTPS, or a date too recent for NASA's hourly archive). Check the first real response for a plausible GHI peak (roughly 700–1000 W/m² on a clear day) and the right time shift (`tz_offset_h` is derived from longitude to the nearest half hour; override with `tz_offset_h`).

## Production deployment

* **Backend** (needs outbound HTTPS to NASA, at least 2 CPUs and ~2 GB RAM, a small persistent disk for cached runs): `docker build -t localflex-api .` from the repository root, or use `render.yaml`. Set `CORS_ORIGINS` to the frontend's URL. No API keys or secrets exist; do not add any to the frontend.
* **Frontend** (static): `cd webapp/frontend && VITE_API_URL=https://<backend> npm run build`, then host `dist/` on any static host (Netlify, Vercel, GitHub Pages, Render static). `public/legacy-dashboard.html` is the original results dashboard, linked from the Analysis tab.
* The Dockerfile and `render.yaml` were written but **not built or deployed** in the development sandbox (no Docker there). Treat the first deploy as a test.
* One heavy job runs at a time (`MAX_QUEUE` limits the queue). For public use add rate limiting in front of `POST /api/simulation`.

## API summary (full schema at `/docs`)

| Method and path | Purpose |
|---|---|
| `GET /api/health`, `GET /api/config` | status; controllers, limits, synthetic scenarios, known limitations |
| `GET /api/topology?pv_penetration=` | real bus/feeder layout and where PV, loads, devices and the battery sit |
| `POST /api/fleet?pv_penetration=&pv_kw_per_home=` | PV homes, phase split and kWp for a penetration |
| `POST /api/nasa` `{latitude, longitude, date}` | NASA POWER irradiance and temperature as 96 × 15-min values plus PV-model preview |
| `POST /api/simulation` | start a job (`environment`: `nasa`, `synthetic` or `csv`; `pv_penetration`, `pv_kw_per_home`, `battery_kwh`, `battery_kw`, `demand_scale`); returns `job_id` |
| `GET /api/simulation/{id}/status` | `queued` / `running` / `done` / `failed`, progress |
| `GET /api/simulation/{id}/state?timestep=48&controller=D` | everything at one 15-min step: bus voltages (3 phases + neutral), segment currents, P/Q, flow direction, resources, devices, MPC decision, safety state, and case A for comparison |
| `GET /api/simulation/{id}/series?controller=D` | all 128 steps for smooth play-back |
| `GET /api/simulation/{id}/results` | metrics for A/B/C/D, fairness burdens, limitations |
| `GET /api/analysis`, `/api/analysis/{name}` | stored LocalFlex study tables (A/B/C/D, robustness, DISCOM, faults, cost, validation, audit) |

Timesteps 0–95 are the scored day (00:00–23:45); 96–127 are the following morning (the engine's 8 h tail, needed to score EV charging).

## Reading the screen honestly

* Voltage colours use the configured 0.94–1.06 pu limits; "warning" means within 0.01 pu of a limit (a UI choice, not a standard).
* The MPC panel keeps three numbers apart: the forecast with no action, the planner's **linear prediction**, and the **OpenDSS actual**. The prediction is never shown as a result.
* "Without control" values come from case A, a separate run; device states drift apart over the day.
* The known limitations are listed in the app (Analysis tab) and in `/api/config`.

## Limits of this version

Only the 100-home, single-transformer feeder is validated (the homes field is locked). Irradiance is one uniform sky over the feeder, so cloud movement between buses is not modelled for NASA input. PV placement is seeded and deterministic. Geocoding (place search) is not included: use the presets or enter latitude and longitude. The MILP has a 1 s limit per plan, so C and D can differ slightly between identical runs (A and B reproduce exactly).
