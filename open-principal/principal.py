"""Open Principal: stdlib-only, consent-bound introduction and decision ledger.

MIT licensed reference implementation, not Boardy source code.
Run: python principal.py demo
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any

ZERO = "0" * 64
DEFAULT_POLICY = {"min_each_direction": 0.10, "min_total_score": 0.20,
                  "cooldown_days": 30, "proposal_ttl_days": 7,
                  "max_open_proposals_per_person": 5}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def words(text: str) -> set[str]:
    # Explainable toy matcher: language-independent model integration is optional.
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.casefold())}


def relevance(query: str, offer: str) -> float:
    q, o = words(query), words(offer)
    return len(q & o) / len(q) if q else 0.0


class Principal:
    def __init__(self, db_path: str | Path = "principal.db"):
        self.db = sqlite3.connect(str(db_path), timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, seeks TEXT NOT NULL,
            offers TEXT NOT NULL, contact TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS blocks (
            blocker TEXT NOT NULL REFERENCES people(id), blocked TEXT NOT NULL REFERENCES people(id),
            PRIMARY KEY(blocker,blocked));
          CREATE TABLE IF NOT EXISTS policies (
            version INTEGER PRIMARY KEY, body TEXT NOT NULL, body_sha TEXT NOT NULL,
            created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY, a TEXT NOT NULL REFERENCES people(id),
            b TEXT NOT NULL REFERENCES people(id), score REAL NOT NULL,
            reasons TEXT NOT NULL, state TEXT NOT NULL,
            policy_version INTEGER NOT NULL REFERENCES policies(version),
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS decisions (
            proposal_id TEXT NOT NULL REFERENCES proposals(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            decision TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(proposal_id,person_id));
          CREATE TABLE IF NOT EXISTS outcomes (
            proposal_id TEXT NOT NULL REFERENCES proposals(id),
            person_id TEXT NOT NULL REFERENCES people(id),
            value INTEGER NOT NULL CHECK(value BETWEEN -1 AND 1),
            note TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(proposal_id,person_id));
          CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
            kind TEXT NOT NULL, subject TEXT NOT NULL, payload TEXT NOT NULL,
            prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
        """)
        if not self.db.execute("SELECT 1 FROM policies LIMIT 1").fetchone():
            with self.tx():
                self._new_policy(DEFAULT_POLICY)

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _log(self, kind: str, subject: str, payload: dict):
        prior = self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = prior["hash"] if prior else ZERO
        timestamp = now()
        encoded = canonical(payload)
        seal = digest(canonical({"occurred_at": timestamp, "kind": kind,
                                 "subject": subject, "payload": payload, "prev_hash": previous}))
        self.db.execute("INSERT INTO events(occurred_at,kind,subject,payload,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                        (timestamp, kind, subject, encoded, previous, seal))

    def audit(self) -> dict:
        previous = ZERO
        n = 0
        for entry in self.db.execute("SELECT * FROM events ORDER BY seq"):
            value = digest(canonical({"occurred_at": entry["occurred_at"], "kind": entry["kind"],
                                      "subject": entry["subject"], "payload": json.loads(entry["payload"]),
                                      "prev_hash": entry["prev_hash"]}))
            n += 1
            if entry["prev_hash"] != previous or entry["hash"] != value:
                return {"ok": False, "checked": n, "broken_seq": entry["seq"]}
            previous = entry["hash"]
        return {"ok": True, "checked": n, "head": previous,
                "note": "Anchor the head externally; an operator controlling the database can rewrite an unanchored chain."}

    def public_receipts(self) -> dict:
        # Contains pseudonymous IDs and policy hashes, never names, contact data, or free-text notes.
        return {"events": [{"seq": r["seq"], "kind": r["kind"], "subject": r["subject"],
                            "hash": r["hash"], "prev_hash": r["prev_hash"], "occurred_at": r["occurred_at"],
                            "payload": json.loads(r["payload"])}
                           for r in self.db.execute("SELECT * FROM events ORDER BY seq")],
                "anchor": self.audit()}

    def _new_policy(self, body: dict) -> dict:
        if set(body) != set(DEFAULT_POLICY):
            raise ValueError("Policy must contain exactly: " + ", ".join(DEFAULT_POLICY))
        if not (0 <= float(body["min_each_direction"]) <= 1 and
                0 <= float(body["min_total_score"]) <= 2 and
                1 <= int(body["cooldown_days"]) <= 365 and
                1 <= int(body["proposal_ttl_days"]) <= 30 and
                1 <= int(body["max_open_proposals_per_person"]) <= 100):
            raise ValueError("Policy values outside supported bounds")
        prev = self.db.execute("SELECT MAX(version) AS v FROM policies").fetchone()["v"] or 0
        version = prev + 1
        body_text = canonical(body)
        sha = digest(body_text)
        self.db.execute("INSERT INTO policies VALUES(?,?,?,?)", (version, body_text, sha, now()))
        self._log("policy.changed", "policy", {"version": version, "sha256": sha})
        return {"version": version, "sha256": sha, "policy": body}

    def policy(self) -> dict:
        r = self.db.execute("SELECT * FROM policies ORDER BY version DESC LIMIT 1").fetchone()
        return {"version": r["version"], "sha256": r["body_sha"], "policy": json.loads(r["body"])}

    def change_policy(self, updates: dict) -> dict:
        with self.tx():
            p = self.policy()["policy"]
            if not set(updates) <= set(p):
                raise ValueError("Unknown policy field")
            p.update(updates)
            result = self._new_policy(p)
            # Previously granted consent never auto-migrates to changed decision criteria.
            open_rows = list(self.db.execute("SELECT id FROM proposals WHERE state='pending'"))
            for row in open_rows:
                self.db.execute("UPDATE proposals SET state='superseded' WHERE id=?", (row["id"],))
                self._log("proposal.superseded", row["id"], {"new_policy": result["version"]})
        return {**result, "superseded": len(open_rows)}

    def register(self, name: str, seeks: str, offers: str, contact: str, *, opted_in: bool) -> dict:
        if not opted_in:
            raise PermissionError("Explicit opt-in required")
        if not all([name.strip(), seeks.strip(), offers.strip(), contact.strip()]):
            raise ValueError("Missing profile fields")
        person_id = secrets.token_hex(12)
        token = secrets.token_urlsafe(32)
        with self.tx():
            self.db.execute("INSERT INTO people VALUES(?,?,?,?,?,?,1,?)",
                            (person_id, name.strip(), seeks.strip(), offers.strip(), contact.strip(), digest(token), now()))
            self._log("person.enrolled", person_id, {"profile_sha256": digest(canonical({"seeks": seeks, "offers": offers}))})
        return {"id": person_id, "consent_token": token,
                "warning": "Deliver this token privately; it is only displayed once. Identity is not verified."}

    def _person(self, pid: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM people WHERE id=?", (pid,)).fetchone()
        if row is None:
            raise KeyError("No such participant")
        return row

    def _actor(self, token: str, *, allow_inactive: bool = False) -> sqlite3.Row:
        if not token:
            raise PermissionError("Participant token required")
        row = self.db.execute("SELECT * FROM people WHERE token_hash=?", (digest(token),)).fetchone()
        if row is None or (not row["active"] and not allow_inactive):
            raise PermissionError("Invalid or revoked participant token")
        return row

    def _allowed(self, a: sqlite3.Row, b: sqlite3.Row, pol: dict):
        if a["id"] == b["id"] or not a["active"] or not b["active"]:
            raise ValueError("Both distinct participants must be actively opted in")
        if self.db.execute("SELECT 1 FROM blocks WHERE (blocker=? AND blocked=?) OR (blocker=? AND blocked=?)",
                           (a["id"], b["id"], b["id"], a["id"])).fetchone():
            raise PermissionError("Matching blocked")
        if self.db.execute("SELECT 1 FROM proposals WHERE state='pending' AND ((a=? AND b=?) OR (a=? AND b=?))",
                           (a["id"], b["id"], b["id"], a["id"])).fetchone():
            raise ValueError("There is already a pending proposal for this pair")
        for p in (a, b):
            opened = self.db.execute("SELECT COUNT(*) AS n FROM proposals WHERE state='pending' AND (a=? OR b=?)",
                                     (p["id"], p["id"])).fetchone()["n"]
            if opened >= int(pol["max_open_proposals_per_person"]):
                raise ValueError("Open-proposal cap reached")
        last = self.db.execute("SELECT created_at FROM proposals WHERE state='introduced' AND "
                               "((a=? AND b=?) OR (a=? AND b=?)) ORDER BY created_at DESC LIMIT 1",
                               (a["id"], b["id"], b["id"], a["id"])).fetchone()
        if last and datetime.fromisoformat(last["created_at"]) > datetime.now(timezone.utc) - timedelta(days=int(pol["cooldown_days"])):
            raise ValueError("Pair in cooldown period")

    def propose(self, a_id: str, b_id: str) -> dict:
        with self.tx():
            a, b, p = self._person(a_id), self._person(b_id), self.policy()
            self._allowed(a, b, p["policy"])
            score_ab = relevance(a["seeks"], b["offers"])
            score_ba = relevance(b["seeks"], a["offers"])
            if score_ab < p["policy"]["min_each_direction"] or score_ba < p["policy"]["min_each_direction"] or (score_ab + score_ba) < p["policy"]["min_total_score"]:
                self._log("proposal.refused", digest("|".join(sorted([a_id, b_id])))[:24],
                          {"cause": "insufficient_mutual_relevance", "policy_version": p["version"],
                           "directional_scores": [round(score_ab, 3), round(score_ba, 3)]})
                return {"state": "refused", "reason": "insufficient_mutual_relevance",
                        "directional_scores": [round(score_ab, 3), round(score_ba, 3)]}
            proposal_id = secrets.token_hex(12)
            expires = (datetime.now(timezone.utc) + timedelta(days=int(p["policy"]["proposal_ttl_days"]))).isoformat(timespec="seconds")
            reasons = {"a_seeks_b_offers": sorted(words(a["seeks"]) & words(b["offers"])),
                       "b_seeks_a_offers": sorted(words(b["seeks"]) & words(a["offers"]))}
            self.db.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?)",
                            (proposal_id, a_id, b_id, score_ab + score_ba, canonical(reasons),
                             "pending", p["version"], now(), expires))
            self._log("proposal.created", proposal_id,
                      {"participants": [a_id, b_id], "score": round(score_ab + score_ba, 3),
                       "policy_version": p["version"], "expires_at": expires})
        return {"id": proposal_id, "state": "pending", "score": round(score_ab + score_ba, 3),
                "explanation": reasons, "policy_version": p["version"],
                "expires_at": expires, "contacts_released": False}

    def decide(self, proposal_id: str, token: str, accept: bool) -> dict:
        with self.tx():
            person = self._actor(token)
            row = self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not row or person["id"] not in (row["a"], row["b"]):
                raise PermissionError("No authorization for this proposal")
            if row["state"] != "pending":
                raise ValueError("Proposal not pending")
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
                self.db.execute("UPDATE proposals SET state='expired' WHERE id=?", (proposal_id,))
                self._log("proposal.expired", proposal_id, {})
                return {"state": "expired", "contacts_released": False}
            if self.db.execute("SELECT 1 FROM decisions WHERE proposal_id=? AND person_id=?",
                               (proposal_id, person["id"])).fetchone():
                raise ValueError("Already decided; no silent overwrites")
            decision = "accepted" if accept else "declined"
            self.db.execute("INSERT INTO decisions VALUES(?,?,?,?)", (proposal_id, person["id"], decision, now()))
            self._log("consent." + decision, proposal_id, {"person_id": person["id"]})
            if not accept:
                state = "declined"
                self.db.execute("UPDATE proposals SET state=? WHERE id=?", (state, proposal_id))
            else:
                yes = self.db.execute("SELECT COUNT(*) AS n FROM decisions WHERE proposal_id=? AND decision='accepted'",
                                      (proposal_id,)).fetchone()["n"]
                state = "introduced" if yes == 2 else "pending"
                if yes == 2:
                    if not self._person(row["a"])["active"] or not self._person(row["b"])["active"]:
                        raise PermissionError("Participant revoked enrollment")
                    self.db.execute("UPDATE proposals SET state='introduced' WHERE id=?", (proposal_id,))
                    self._log("introduction.released", proposal_id, {"participants": [row["a"], row["b"]]})
        return {"state": state, "contacts_released": state == "introduced"}

    def get_proposal(self, proposal_id: str, token: str) -> dict:
        row = self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown proposal")
        actor = self._actor(token)
        if actor["id"] not in (row["a"], row["b"]):
            raise PermissionError("Only participants may inspect a proposed introduction")
        a, b = self._person(row["a"]), self._person(row["b"])
        blocked = self.db.execute("SELECT 1 FROM blocks WHERE (blocker=? AND blocked=?) OR (blocker=? AND blocked=?)",
                                  (a["id"], b["id"], b["id"], a["id"])).fetchone() is not None
        active = bool(a["active"] and b["active"] and not blocked)
        result = {"id": row["id"], "state": row["state"], "policy_version": row["policy_version"],
                  "explanation": json.loads(row["reasons"]), "score": row["score"],
                  "participants": [{"id": x["id"], "name": x["name"], "seeks": x["seeks"], "offers": x["offers"]}
                                   for x in (a, b)], "contacts_released": False}
        if row["state"] == "introduced" and active:
            result["contacts_released"] = True
            for public, private in zip(result["participants"], (a, b)):
                public["contact"] = private["contact"]
        return result

    def feedback(self, proposal_id: str, token: str, value: int, note: str = "") -> dict:
        if value not in (-1, 0, 1):
            raise ValueError("Outcome must be -1, 0, or +1")
        with self.tx():
            actor = self._actor(token)
            row = self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not row or actor["id"] not in (row["a"], row["b"]) or row["state"] != "introduced":
                raise PermissionError("Only participants in completed introductions may report outcomes")
            self.db.execute("INSERT INTO outcomes VALUES(?,?,?,?,?)", (proposal_id, actor["id"], value, note[:2000], now()))
            self._log("outcome.recorded", proposal_id, {"reporter": actor["id"], "value": value,
                                                         "note_sha256": digest(note[:2000])})
        return {"state": "recorded", "reporter": actor["id"], "value": value}

    def outcomes(self) -> dict:
        r = self.db.execute("SELECT COUNT(*) n, COALESCE(AVG(value),0) avg FROM outcomes").fetchone()
        return {"reports": r["n"], "mean_participant_rating": round(r["avg"], 3),
                "qualification": "Self-reported outcomes, not causal ROI or independently verified reputation."}

    def reputation(self, person_id: str) -> dict:
        """Counterparty-reported outcomes, not self-assessed ratings.

        Withhold aggregate score for fewer than 5 responses to reduce the
        chance a low-sample reputation score misrepresents someone.
        """
        self._person(person_id)
        r = self.db.execute("""SELECT COUNT(*) n, COALESCE(AVG(o.value),0) avg
            FROM outcomes o JOIN proposals p ON p.id=o.proposal_id
            WHERE (p.a=? OR p.b=?) AND o.person_id<>?""",
            (person_id, person_id, person_id)).fetchone()
        return {"person_id": person_id, "counterparty_reports": r["n"],
                "mean_outcome": round(r["avg"], 3) if r["n"] >= 5 else None,
                "reason": "Insufficient counterparty reports" if r["n"] < 5 else "Observed self-reported counterpart experience",
                "warning": "A score is not a verified fact about a person; no automatic access or ranking decisions use it."}

    def block(self, token: str, other_id: str) -> dict:
        with self.tx():
            actor = self._actor(token)
            self._person(other_id)
            self.db.execute("INSERT OR IGNORE INTO blocks VALUES(?,?)", (actor["id"], other_id))
            self._log("person.blocked", actor["id"], {"target": other_id})
        return {"blocked": other_id}

    def revoke(self, token: str) -> dict:
        with self.tx():
            actor = self._actor(token)
            self.db.execute("UPDATE people SET active=0, contact='' WHERE id=?", (actor["id"],))
            pending = list(self.db.execute("SELECT id FROM proposals WHERE state='pending' AND (a=? OR b=?)",
                                           (actor["id"], actor["id"])))
            for item in pending:
                self.db.execute("UPDATE proposals SET state='revoked' WHERE id=?", (item["id"],))
                self._log("proposal.revoked", item["id"], {})
            self._log("person.revoked", actor["id"], {"pending_canceled": len(pending)})
        return {"revoked": actor["id"], "pending_canceled": len(pending),
                "notice": "Prior contact disclosures cannot be retracted from recipients."}

    def erase(self, token: str) -> dict:
        with self.tx():
            actor = self._actor(token, allow_inactive=True)
            self.db.execute("UPDATE people SET active=0, name='[deleted]', seeks='', offers='', contact='', token_hash=? WHERE id=?",
                            (digest(secrets.token_urlsafe(32)), actor["id"]))
            pending = list(self.db.execute("SELECT id FROM proposals WHERE state='pending' AND (a=? OR b=?)",
                                           (actor["id"], actor["id"])))
            for item in pending:
                self.db.execute("UPDATE proposals SET state='revoked' WHERE id=?", (item["id"],))
                self._log("proposal.revoked", item["id"], {})
            # Remove historical free text a participant provided; retain pseudonymous receipts.
            self.db.execute("UPDATE outcomes SET note='' WHERE person_id=?", (actor["id"],))
            self._log("person.erased", actor["id"], {"pending_canceled": len(pending)})
        return {"erased": actor["id"], "note": "DB backup, third-party copies and prior disclosures require separate deletion handling."}


def demo() -> dict:
    app = Principal(":memory:")
    alice = app.register("Alice", "thermal engineering aerospace", "optical sensors imaging", "alice@demo.invalid", opted_in=True)
    bob = app.register("Bob", "optical sensors imaging", "thermal engineering aerospace", "bob@demo.invalid", opted_in=True)
    proposal = app.propose(alice["id"], bob["id"])
    before = app.get_proposal(proposal["id"], alice["consent_token"])
    first = app.decide(proposal["id"], alice["consent_token"], True)
    second = app.decide(proposal["id"], bob["consent_token"], True)
    after = app.get_proposal(proposal["id"], alice["consent_token"])
    app.feedback(proposal["id"], alice["consent_token"], 1, "Useful meeting")
    result = {"proposal": proposal, "before": before, "first": first, "second": second,
              "after": after, "outcomes": app.outcomes(), "audit": app.audit()}
    app.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Open Principal: open-source bilateral trust/intro engine")
    parser.add_argument("--db", default="principal.db")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo"); sub.add_parser("policy"); sub.add_parser("audit"); sub.add_parser("metrics")
    rep = sub.add_parser("reputation"); rep.add_argument("id")
    reg = sub.add_parser("register")
    for arg in ("name", "seeks", "offers", "contact"):
        reg.add_argument("--" + arg, required=True)
    reg.add_argument("--opt-in", action="store_true", required=True)
    pr = sub.add_parser("propose")
    pr.add_argument("a"); pr.add_argument("b")
    g = sub.add_parser("show"); g.add_argument("id"); g.add_argument("--token", default=None)
    dec = sub.add_parser("decide"); dec.add_argument("id"); dec.add_argument("--token", default=None)
    dec.add_argument("--accept", action="store_true"); dec.add_argument("--decline", action="store_true")
    fb = sub.add_parser("feedback"); fb.add_argument("id"); fb.add_argument("--token", default=None)
    fb.add_argument("--value", type=int, choices=(-1, 0, 1), required=True); fb.add_argument("--note", default="")
    rev = sub.add_parser("revoke"); rev.add_argument("--token", default=None)
    era = sub.add_parser("erase"); era.add_argument("--token", default=None)
    block = sub.add_parser("block"); block.add_argument("other_id"); block.add_argument("--token", default=None)
    pol = sub.add_parser("set-policy"); pol.add_argument("--json", required=True)
    pub = sub.add_parser("export-receipts"); pub.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.cmd == "demo":
        result = demo()
    else:
        db = Principal(args.db)
        try:
            if hasattr(args, "token") and args.token is None:
                args.token = os.environ.get("PRINCIPAL_TOKEN", "")
            if args.cmd == "register":
                result = db.register(args.name, args.seeks, args.offers, args.contact, opted_in=args.opt_in)
            elif args.cmd == "propose": result = db.propose(args.a, args.b)
            elif args.cmd == "show": result = db.get_proposal(args.id, args.token)
            elif args.cmd == "decide":
                if args.accept == args.decline: raise ValueError("Choose exactly one of --accept/--decline")
                result = db.decide(args.id, args.token, args.accept)
            elif args.cmd == "feedback": result = db.feedback(args.id, args.token, args.value, args.note)
            elif args.cmd == "revoke": result = db.revoke(args.token)
            elif args.cmd == "erase": result = db.erase(args.token)
            elif args.cmd == "block": result = db.block(args.token, args.other_id)
            elif args.cmd == "reputation": result = db.reputation(args.id)
            elif args.cmd == "policy": result = db.policy()
            elif args.cmd == "set-policy": result = db.change_policy(json.loads(args.json))
            elif args.cmd == "audit": result = db.audit()
            elif args.cmd == "metrics": result = db.outcomes()
            elif args.cmd == "export-receipts":
                result = db.public_receipts()
                Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
                result = {"saved": args.output, "anchor": result["anchor"]}
        finally:
            db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
