"""Authenticated, loopback-only JSON API for Open Principal.

No TLS termination, identity verification or production hardening is provided.
Never expose directly to the Internet.
"""
from __future__ import annotations
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from principal import Principal

MAX_BODY = 16 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenPrincipal/0.1"

    def _send(self, code: int, data: dict):
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _token(self):
        header = self.headers.get("Authorization", "")
        return header[7:] if header.startswith("Bearer ") else ""

    def _operator(self):
        token = os.environ.get("PRINCIPAL_OPERATOR_TOKEN", "")
        return bool(token) and hmac.compare_digest(self._token(), token)

    def _read(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 <= n <= MAX_BODY:
                raise ValueError("Request body too large")
            data = json.loads(self.rfile.read(n)) if n else {}
            if not isinstance(data, dict):
                raise ValueError("Expected JSON object")
            return data
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON body") from exc

    def _dispatch(self, method):
        path = self.path.split("?", 1)[0]
        db = Principal(self.server.db_path)
        try:
            body = self._read() if method == "POST" else {}
            participant_path = (method == "GET" and path.startswith("/proposal/")) or (
                method == "POST" and path in ("/decide", "/feedback", "/revoke", "/erase", "/block"))
            if not participant_path and not self._operator():
                return self._send(401, {"error": "Operator authorization required"})
            token = self._token()
            if participant_path:
                db._actor(token, allow_inactive=(path == "/erase"))  # no operator shortcut for a participant's decision
            if method == "GET":
                if path == "/health": result = {"ok": True, "audit": db.audit()["ok"]}
                elif path == "/policy": result = db.policy()
                elif path == "/audit": result = db.audit()
                elif path == "/receipts": result = db.public_receipts()
                elif path == "/metrics": result = db.outcomes()
                elif path.startswith("/reputation/"): result = db.reputation(path.removeprefix("/reputation/"))
                elif path.startswith("/proposal/"):
                    result = db.get_proposal(path.removeprefix("/proposal/"), token)
                else: return self._send(404, {"error": "No route"})
            elif method == "POST":
                if path == "/register":
                    result = db.register(body["name"], body["seeks"], body["offers"], body["contact"],
                                         opted_in=body.get("opted_in") is True)
                elif path == "/propose": result = db.propose(body["a"], body["b"])
                elif path == "/policy": result = db.change_policy(body["updates"])
                elif path == "/decide":
                    if type(body.get("accept")) is not bool: raise ValueError("accept must be true or false")
                    result = db.decide(body["id"], token, body["accept"])
                elif path == "/feedback": result = db.feedback(body["id"], token, body["value"], body.get("note", ""))
                elif path == "/block": result = db.block(token, body["other_id"])
                elif path == "/revoke": result = db.revoke(token)
                elif path == "/erase": result = db.erase(token)
                else: return self._send(404, {"error": "No route"})
            else: return self._send(405, {"error": "Method not allowed"})
            return self._send(200, result)
        except (ValueError, KeyError, TypeError) as e:
            return self._send(400, {"error": str(e)})
        except PermissionError as e:
            return self._send(403, {"error": str(e)})
        except Exception:
            # Never leak internals in an HTTP error.
            return self._send(500, {"error": "Internal error"})
        finally:
            db.close()

    def do_GET(self): self._dispatch("GET")
    def do_POST(self): self._dispatch("POST")
    def log_message(self, fmt, *args):
        # Avoid logging URLs, tokens or profile details by default.
        return


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="principal.db")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit("Refusing non-loopback bind; use an authenticated TLS reverse proxy")
    if not os.environ.get("PRINCIPAL_OPERATOR_TOKEN") or len(os.environ["PRINCIPAL_OPERATOR_TOKEN"]) < 24:
        raise SystemExit("Set PRINCIPAL_OPERATOR_TOKEN to a random secret of at least 24 characters")
    # Initialize in main thread so requests can open existing database.
    db = Principal(args.db); db.close()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.db_path = args.db
    print(f"Open Principal API listening at http://{args.host}:{args.port}; operator token required", flush=True)
    server.serve_forever()

if __name__ == "__main__": main()
