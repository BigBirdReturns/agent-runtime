import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.port = 18765
        cls.token = "test-operator-secret-1234567890"
        env = dict(os.environ, PRINCIPAL_OPERATOR_TOKEN=cls.token)
        cls.process = subprocess.Popen([sys.executable, str(ROOT / "server.py"),
                                      "--db", str(Path(cls.temp.name) / "principal.db"),
                                      "--port", str(cls.port)], cwd=ROOT,
                                      env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError(cls.process.stderr.read().decode())
            try:
                cls.call("GET", "/health", token=cls.token)
                return
            except Exception: time.sleep(0.03)
        raise RuntimeError("Server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate(); cls.process.wait(timeout=5)
        cls.process.stderr.close(); cls.temp.cleanup()

    @classmethod
    def call(cls, method, path, data=None, token=None):
        payload = json.dumps(data).encode() if data is not None else None
        hdr = {"Content-Type": "application/json"}
        if token: hdr["Authorization"] = "Bearer " + token
        req = Request(f"http://127.0.0.1:{cls.port}{path}", payload, hdr, method=method)
        with urlopen(req, timeout=2) as r: return json.load(r)

    def test_operator_required(self):
        with self.assertRaises(HTTPError) as e:
            self.call("GET", "/audit")
        self.assertEqual(e.exception.code, 401)

    def test_api_consent_end_to_end(self):
        a = self.call("POST", "/register", {"name":"A", "seeks":"thermal engineering", "offers":"optics imaging", "contact":"a@demo.invalid", "opted_in":True}, self.token)
        b = self.call("POST", "/register", {"name":"B", "seeks":"optics imaging", "offers":"thermal engineering", "contact":"b@demo.invalid", "opted_in":True}, self.token)
        p = self.call("POST", "/propose", {"a": a["id"], "b": b["id"]}, self.token)
        with self.assertRaises(HTTPError) as err:
            self.call("GET", "/proposal/" + p["id"], token=self.token)
        self.assertEqual(err.exception.code, 403)  # operator cannot impersonate a person
        self.assertFalse(self.call("GET", "/proposal/"+p["id"], token=a["consent_token"])["contacts_released"])
        self.call("POST", "/decide", {"id": p["id"], "accept": True}, a["consent_token"])
        self.assertFalse(self.call("GET", "/proposal/"+p["id"], token=b["consent_token"])["contacts_released"])
        self.call("POST", "/decide", {"id": p["id"], "accept": True}, b["consent_token"])
        assert self.call("GET", "/proposal/"+p["id"], token=a["consent_token"])["contacts_released"]
        self.assertTrue(self.call("GET", "/audit", token=self.token)["ok"])

if __name__ == "__main__": unittest.main()
