"""The reference review action requires a real owner session and step-up."""
import unittest

from fastapi.testclient import TestClient

import test_v11_cc_actions as harness
from brambleloop.core.models import TeardownFinding


class ReviewCommandCenterTests(unittest.TestCase):
    def test_operator_token_and_unstepped_session_cannot_review(self):
        with harness.DB.session() as s:
            finding = TeardownFinding(benchmark_ref="reference", dimension="instruction_clarity",
                                      score=4, recorded_by="teardown_analyst")
            s.add(finding)
            s.flush()
            finding_id = finding.id
        action = "/api/cc/actions/teardown.review_finding"
        body = {"finding_id": finding_id, "decision": "reviewed", "reason": "independent review"}
        no_session = TestClient(harness.main.app, base_url="https://testserver")
        response = no_session.post(action, json=body, headers={"Authorization": f"Bearer {harness.OPS}"})
        self.assertIn(response.status_code, (401, 403))
        no_session.close()
        client, csrf = harness.session()
        harness.expire_stepup(client)
        response = harness.post(client, csrf, action, body)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["code"], "STEP_UP_REQUIRED")
        self.assertEqual(harness.post(client, csrf, "/api/cc/auth/step-up",
                                      {"passphrase": harness.PASS}).status_code, 200)
        response = harness.post(client, csrf, action, body)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["review_state"], "reviewed")
        client.close()


if __name__ == "__main__":
    unittest.main()
