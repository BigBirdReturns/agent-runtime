"""Independently verify exported pseudonymous event receipts against an anchored head.

Usage: python verify_receipts.py receipts.json --expected-head SHA256_FROM_TRUSTED_SOURCE
"""
import argparse
import json
from pathlib import Path
from principal import ZERO, canonical, digest


def verify(bundle: dict, expected_head: str | None = None) -> dict:
    previous = ZERO
    previous_seq = 0
    for row in bundle["events"]:
        if row["seq"] != previous_seq + 1 or row["prev_hash"] != previous:
            return {"ok": False, "broken_seq": row["seq"], "cause": "noncontiguous_chain"}
        calc = digest(canonical({"occurred_at": row["occurred_at"], "kind": row["kind"],
                                 "subject": row["subject"], "payload": row["payload"],
                                 "prev_hash": row["prev_hash"]}))
        if calc != row["hash"]:
            return {"ok": False, "broken_seq": row["seq"], "cause": "invalid_hash"}
        previous = calc
        previous_seq += 1
    if expected_head is not None and previous != expected_head:
        return {"ok": False, "cause": "untrusted_or_divergent_head", "actual_head": previous}
    return {"ok": True, "checked": previous_seq, "head": previous,
            "externally_anchored": expected_head is not None}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("receipts")
    p.add_argument("--expected-head", help="Original chain head obtained from an independent, trusted source")
    args = p.parse_args()
    result = verify(json.loads(Path(args.receipts).read_text(encoding="utf-8")), args.expected_head)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__": main()
