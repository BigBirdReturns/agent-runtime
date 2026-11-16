import json
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from principal import Principal
from verify_receipts import verify

class ReceiptTests(unittest.TestCase):
    def test_end_to_end_verifier(self):
        app=Principal(":memory:")
        a=app.register("Alice", "health tech", "research", "a@demo.invalid", opted_in=True)
        bundle=app.public_receipts()
        anchored=app.audit()["head"]
        self.assertTrue(verify(bundle, anchored)["ok"])
        self.assertTrue(verify(bundle)["ok"])
        bundle["events"][1]["kind"]="lies"
        self.assertFalse(verify(bundle, anchored)["ok"])
        app.close()
    def test_externally_anchored_head_prevents_truncation(self):
        app=Principal(":memory:")
        app.register("Alice", "health tech", "research", "a@demo.invalid", opted_in=True)
        bundle=app.public_receipts()
        anchored=app.audit()["head"]
        bundle["events"].pop()
        self.assertFalse(verify(bundle, anchored)["ok"])
        app.close()

if __name__=="__main__": unittest.main()
