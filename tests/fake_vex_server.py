"""A fake VE-X for a clean-install check: made-up answers (as in conftest), routed by path.

Run it, then add the integration in a fresh Home Assistant with the base URL
http://127.0.0.1:8199/xv1, key KEY1 and any customer id. Not a test module.
"""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
SP = "SP1"
SERVICE_POINTS = {"result": True, "data": {"servicePoints": [{"servicePointId": SP, "nationalMeteringId": "NMI0"}]}}
DER = {"result": True, "data": {"servicePointId": SP, "endPoints": [
    {"endPointId": "INV1", "endPointType": "smartInverter", "type": "SOLAR_PV", "control": True},
    {"endPointId": "MET1", "endPointType": "smartMeter", "type": "OTHER", "control": False},
    {"endPointId": "BAT1", "endPointType": "battery", "type": "STORAGE", "control": False}]}}
DETAIL = {"result": True, "data": {"servicePointId": SP, "controlLogInfo": {"endPoints": [
    {"start": "20260101T031102Z", "controlAction": "controlBattery", "triggerById": "CON_BAT", "endPointId": "BAT1",
     "batteryMode": "scm", "pSetPoint": 20, "socDischargeThres": 21},
    {"start": "20260101T031046Z", "controlAction": "controlInverter", "triggerById": "CON_SOLAR", "endPointId": "INV1",
     "currentPower": -9.1688, "enableExportControl": True, "exportPSetPoint": "0.05"}]}}}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if self.headers.get("apiKey") != "KEY1":
            self.send_response(403); self.end_headers(); return
        if "/der/" in path: body = DER
        elif "/servicepoints/Voltello/" in path: body = SERVICE_POINTS
        else: body = DETAIL
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)
    def log_message(self, fmt, *args):
        sys.stderr.write("CALL " + self.path.split("?")[0] + "\n"); sys.stderr.flush()
if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8199), H).serve_forever()
