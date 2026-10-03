"""Serves the NASA-POWER-format FIXTURE for tests (NASA_POWER_BASE_URL=http://127.0.0.1:8765). The values are synthetic, not NASA data."""
import http.server, json, os, sys
F = os.path.join(os.path.dirname(__file__), "fixtures", "nasa_power_hourly_fixture.json")
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = open(F, "rb").read(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
if __name__ == "__main__": http.server.HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()
