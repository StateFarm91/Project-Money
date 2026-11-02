"""The existing authenticated intake route accepts a recorded purchase."""
import json
import unittest

import test_cert_culture_teardown as harness
from test_codex_purchase_intake import purchase


class PurchaseIntakeAPITests(unittest.TestCase):
    def test_recorded_purchase_and_missing_licence(self):
        client, db = harness._client()
        headers = {"Authorization": f"Bearer {harness.TOKEN}"}
        response = client.post("/api/teardown/intake", headers=headers,
            data={"purchase_record": json.dumps(purchase())},
            files={"files": ("pattern.pdf", b"test PDF", "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["paid_source"], "owner purchase record")
        record = purchase()
        record.pop("licence_terms")
        response = client.post("/api/teardown/intake", headers=headers,
            data={"purchase_record": json.dumps(record)},
            files={"files": ("pattern.pdf", b"test PDF", "application/pdf")})
        self.assertEqual(response.status_code, 400, response.text)
        client.close()


if __name__ == "__main__":
    unittest.main()
