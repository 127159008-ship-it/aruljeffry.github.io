"""Fast API tests (no full simulation). Run from webapp/backend:  python -m pytest tests -q
The NASA tests use tests/fixtures/nasa_power_hourly_fixture.json (synthetic values in NASA POWER's response format), served locally."""
import os, sys, threading, http.server
HERE = os.path.dirname(__file__); sys.path.insert(0, os.path.dirname(HERE))
import pytest
from fastapi.testclient import TestClient

def _serve():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            b = open(os.path.join(HERE, "fixtures", "nasa_power_hourly_fixture.json"), "rb").read(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    s = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=s.serve_forever, daemon=True).start(); return s

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["LOCALFLEX_DATA_DIR"] = str(tmp_path_factory.mktemp("lf"))
    srv = _serve(); os.environ["NASA_POWER_BASE_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
    from app import main, nasa
    nasa.BASE = os.environ["NASA_POWER_BASE_URL"]
    yield TestClient(main.app); srv.shutdown()

def test_health_config(client):
    assert client.get("/api/health").json()["status"] == "ok"
    c = client.get("/api/config").json(); assert set(c["controllers"]) == {"A", "B", "C", "D"} and c["validated_homes"] == 100 and c["limitations"]

def test_fleet_baseline_is_frozen_split(client):
    f = client.post("/api/fleet?pv_penetration=40&pv_kw_per_home=3").json()
    assert f["pv_homes"] == 40 and f["pv_by_phase"] == [22, 12, 6] and f["pv_kwp"] == 120.0

@pytest.mark.parametrize("p", [10, 20, 60, 80, 100])
def test_fleet_scales(client, p):
    f = client.post(f"/api/fleet?pv_penetration={p}&pv_kw_per_home=3").json()
    assert f["pv_homes"] == p and all(a <= b for a, b in zip(f["pv_by_phase"], f["homes_by_phase"]))

def test_topology_has_real_placement(client):
    t = client.get("/api/topology?pv_penetration=40").json()
    assert set(t["nodes"]) == {f"{x}{i}" for x in "ab" for i in range(1, 6)}
    assert sum(sum(n["pv_homes"]) for n in t["nodes"].values()) == 40 and any(d["id"] == "BATT" for d in t["nodes"]["a4"]["devices"])

def test_nasa_fixture_parse(client):
    r = client.post("/api/nasa", json={"latitude": 13.08, "longitude": 80.27, "date": "2026-03-15"}); assert r.status_code == 200, r.text
    d = r.json(); assert len(d["rows"]) == 96 and d["tz_offset_h"] == 5.5 and max(x["ghi_Wm2"] for x in d["rows"]) > 500
    noon = d["rows"][48]; assert noon["pv_kW_per_array"] > 1.5 and d["rows"][0]["pv_kW_per_array"] == 0

def test_nasa_rejects_future_date_and_bad_coords(client):
    assert client.post("/api/nasa", json={"latitude": 13, "longitude": 80, "date": "2099-01-01"}).status_code == 502
    assert client.post("/api/nasa", json={"latitude": 130, "longitude": 80, "date": "2026-03-15"}).status_code == 502

def test_simulation_validation(client):
    assert client.post("/api/simulation", json={"homes": 300}).status_code == 422
    assert client.post("/api/simulation", json={"synthetic_scenario": "nope"}).status_code == 422
    assert client.post("/api/simulation", json={"environment": "csv", "irradiance_Wm2": [1, 2]}).status_code == 422

def test_demo_state_consistency(client):
    demo = client.get("/api/demo").json(); assert demo
    jid = demo[0]["job_id"]; s = client.get(f"/api/simulation/{jid}/state?timestep=48&controller=D").json()
    assert s["time"] == "12:00" and set(s["selected"]["buses"]) >= {"a1", "b5"}
    sysd = s["selected"]["system"]; bal = sum(b["load_kW"] + b["device_kW"] - b["pv_kW"] for b in s["selected"]["buses"].values())
    assert abs(bal - (sysd["demand_kW"] - sysd["pv_delivered_kW"])) < 0.3          # bus-level resources reconcile with the system totals
    assert s["mpc_decision"]["node_phase"] and "safety" in s
    assert client.get(f"/api/simulation/{jid}/state?timestep=200").status_code == 422
