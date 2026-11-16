import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from principal import Principal, DEFAULT_POLICY, relevance

class OpenPrincipalTests(unittest.TestCase):
    def setUp(self):
        self.app = Principal(":memory:")
        self.a = self.app.register("Alice", "thermal engineering aerospace", "optical sensors imaging", "alice@demo.invalid", opted_in=True)
        self.b = self.app.register("Bob", "optical sensors imaging", "thermal engineering aerospace", "bob@demo.invalid", opted_in=True)

    def tearDown(self): self.app.close()

    def proposal(self):
        return self.app.propose(self.a["id"], self.b["id"])["id"]

    def accepted(self):
        p = self.proposal()
        self.app.decide(p, self.a["consent_token"], True)
        self.app.decide(p, self.b["consent_token"], True)
        return p

    def test_no_registration_without_optin(self):
        with self.assertRaises(PermissionError):
            self.app.register("Mallory", "test", "test", "m@demo.invalid", opted_in=False)

    def test_distinct_people(self):
        with self.assertRaises(ValueError): self.app.propose(self.a["id"], self.a["id"])

    def test_no_relevance_means_refusal_with_receipt(self):
        x = self.app.register("C", "football", "dance", "c@demo.invalid", opted_in=True)
        result = self.app.propose(self.a["id"], x["id"])
        self.assertEqual(result["state"], "refused")
        self.assertIn("proposal.refused", [r["kind"] for r in self.app.db.execute("SELECT kind FROM events")])

    def test_relevance_explainable(self):
        self.assertEqual(relevance("thermal engineering", "engineering thermal"), 1)
        p = self.app.propose(self.a["id"], self.b["id"])
        self.assertEqual(p["score"], 2)
        self.assertEqual(p["explanation"]["a_seeks_b_offers"], ["aerospace", "engineering", "thermal"])

    def test_one_sided_consent_never_releases_contact(self):
        p = self.proposal()
        self.assertFalse(self.app.get_proposal(p, self.a["consent_token"])["contacts_released"])
        self.app.decide(p, self.a["consent_token"], True)
        self.assertFalse(self.app.get_proposal(p, self.a["consent_token"])["contacts_released"])
        self.assertFalse(self.app.get_proposal(p, self.b["consent_token"])["contacts_released"])

    def test_two_sided_consent_releases(self):
        p = self.accepted()
        d = self.app.get_proposal(p, self.b["consent_token"])
        self.assertEqual({x["contact"] for x in d["participants"]}, {"alice@demo.invalid", "bob@demo.invalid"})
        self.assertTrue(d["contacts_released"])

    def test_wrong_actor_cannot_approve(self):
        p = self.proposal()
        x = self.app.register("C", "a", "b", "c@demo.invalid", opted_in=True)
        with self.assertRaises(PermissionError): self.app.decide(p, x["consent_token"], True)
        with self.assertRaises(PermissionError): self.app.get_proposal(p, x["consent_token"])

    def test_fake_token_not_accepted(self):
        p = self.proposal()
        with self.assertRaises(PermissionError): self.app.decide(p, "wrong", True)

    def test_decline_is_terminal(self):
        p = self.proposal()
        self.assertEqual(self.app.decide(p, self.a["consent_token"], False)["state"], "declined")
        with self.assertRaises(ValueError): self.app.decide(p, self.b["consent_token"], True)

    def test_approval_not_repeatable(self):
        p = self.proposal()
        self.app.decide(p, self.a["consent_token"], True)
        with self.assertRaises(ValueError): self.app.decide(p, self.a["consent_token"], True)

    def test_existing_pending_prevents_duplicate(self):
        self.proposal()
        with self.assertRaises(ValueError): self.proposal()

    def test_policy_change_supersedes_pending(self):
        p = self.proposal()
        ch = self.app.change_policy({"min_total_score": 0.3})
        self.assertEqual(ch["superseded"], 1)
        self.assertEqual(self.app.get_proposal(p, self.a["consent_token"])["state"], "superseded")
        with self.assertRaises(ValueError): self.app.decide(p, self.a["consent_token"], True)
        self.assertEqual(self.app.propose(self.a["id"], self.b["id"])["policy_version"], 2)

    def test_policy_rejects_bad_values(self):
        with self.assertRaises(ValueError): self.app.change_policy({"cooldown_days": -1})
        with self.assertRaises(ValueError): self.app.change_policy({"who_cares": "no"})
        self.assertEqual(self.app.policy()["version"], 1)

    def test_block_prevents_match_and_hides_contact(self):
        p = self.accepted()
        self.app.block(self.a["consent_token"], self.b["id"])
        self.assertFalse(self.app.get_proposal(p, self.b["consent_token"])["contacts_released"])
        with self.assertRaises(PermissionError): self.app.propose(self.b["id"], self.a["id"])

    def test_revoke_prevents_future_and_releases_no_contact(self):
        p = self.accepted()
        self.app.revoke(self.a["consent_token"])
        self.assertFalse(self.app.get_proposal(p, self.b["consent_token"])["contacts_released"])
        with self.assertRaises(ValueError): self.app.propose(self.a["id"], self.b["id"])

    def test_revoke_then_erase_personal_data(self):
        self.app.revoke(self.a["consent_token"])
        self.app.erase(self.a["consent_token"])
        self.assertEqual(self.app._person(self.a["id"])["name"], "[deleted]")
        with self.assertRaises(PermissionError):
            self.app.erase(self.a["consent_token"])

    def test_erase_person_pseudonymizes(self):
        p = self.accepted()
        self.app.feedback(p, self.a["consent_token"], 1, "note")
        self.app.erase(self.a["consent_token"])
        a = self.app._person(self.a["id"])
        self.assertEqual((a["name"], a["contact"], a["seeks"]), ("[deleted]", "", ""))
        self.assertEqual(self.app.db.execute("SELECT note FROM outcomes").fetchone()["note"], "")
        self.assertTrue(self.app.audit()["ok"])

    def test_outcome_only_after_completed_intro(self):
        p = self.proposal()
        with self.assertRaises(PermissionError): self.app.feedback(p, self.a["consent_token"], 1)
        self.app.decide(p, self.a["consent_token"], True)
        self.app.decide(p, self.b["consent_token"], True)
        self.app.feedback(p, self.a["consent_token"], -1)
        self.assertEqual(self.app.outcomes()["mean_participant_rating"], -1)
        with self.assertRaises(sqlite3.IntegrityError): self.app.feedback(p, self.a["consent_token"], 1)

    def test_audit_chain_and_tamper_detection(self):
        p = self.accepted()
        self.assertTrue(self.app.audit()["ok"])
        self.app.db.execute("UPDATE events SET kind='forged' WHERE seq=2")
        self.assertFalse(self.app.audit()["ok"])

    def test_receipts_never_export_contact(self):
        p = self.accepted()
        data = json.dumps(self.app.public_receipts())
        self.assertNotIn("@demo.invalid", data)
        self.assertIn("introduction.released", data)

    def test_expiration_blocks_release(self):
        p = self.proposal()
        self.app.db.execute("UPDATE proposals SET expires_at='2001-01-01T00:00:00+00:00' WHERE id=?", (p,))
        self.assertEqual(self.app.decide(p, self.a["consent_token"], True)["state"], "expired")
        self.assertFalse(self.app.get_proposal(p, self.a["consent_token"])["contacts_released"])

    def test_reputation_withholds_small_samples(self):
        p=self.accepted()
        self.app.feedback(p, self.a["consent_token"], 1)
        self.assertEqual(self.app.reputation(self.b["id"])["counterparty_reports"], 1)
        self.assertIsNone(self.app.reputation(self.b["id"])["mean_outcome"])
        self.assertEqual(self.app.reputation(self.a["id"])["counterparty_reports"], 0)

    def test_cooldown(self):
        self.accepted()
        with self.assertRaises(ValueError): self.proposal()

    def test_transactions_rollback_on_bad_policy(self):
        count = self.app.audit()["checked"]
        with self.assertRaises(ValueError): self.app.change_policy({"cooldown_days": 0})
        self.assertEqual(self.app.audit()["checked"], count)

    def test_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "db.sqlite"
            a = Principal(p)
            user = a.register("Person", "research", "science", "p@demo.invalid", opted_in=True)
            head = a.audit()["head"]; a.close()
            b = Principal(p)
            self.assertEqual(b._person(user["id"])["name"], "Person")
            self.assertEqual(b.audit()["head"], head)
            b.close()

if __name__ == "__main__": unittest.main()
