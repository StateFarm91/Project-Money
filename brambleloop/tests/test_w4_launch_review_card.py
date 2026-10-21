"""D-W4-LAUNCH-VISION-BATCH: the Command Center card that activates the launch image review.

The owner works from an Android phone, so activation is a card with an Activate button on the
Completion tab -- the same POST /api/cc/launch-review/activate, through the shared api.js CSRF +
nonce path and the shared step-up flow (`guardedAction`, `stepUpDialog`). The button is disabled,
with the reason shown, whenever the server would refuse: no step-up, already active (or used), or
frames not yet built for every Launch-0 release. Static checks plus the reason function run under
node (the same runtime test_v11_pwa_browser uses); without node that half is reported, not passed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
CARD = STATIC / "js" / "views" / "_launch_review.js"


def test_the_card_is_on_the_completion_tab_and_reads_the_batch():
    js = (STATIC / "js" / "views" / "completion.js").read_text()
    assert 'import { launchReviewCard } from "./_launch_review.js";' in js
    assert "api.launchReview()" in js and "launchReviewCard(lr, rerender)" in js
    assert "export async function render({ rerender } = {})" in js


def test_activate_uses_the_same_endpoint_through_the_shared_csrf_and_step_up_flow():
    api = (STATIC / "js" / "api.js").read_text()
    assert 'launchReview: () => `${API_BASE}/launch-review`' in api
    assert 'launchReviewActivate: () => `${API_BASE}/launch-review/activate`' in api
    assert "activateLaunchReview: () => post(ENDPOINTS.launchReviewActivate(), {})" in api
    card = CARD.read_text()
    assert "guardedAction(" in card and "requiresStepUp: true" in card
    assert "run: () => api.activateLaunchReview()" in card
    assert "stepUpDialog(" in card and "stepUp(cred.passphrase, cred.totp)" in card
    # no private network path, no HTML sink: every request goes through api.js
    for bad in ("fetch(", "XMLHttpRequest", "innerHTML", "insertAdjacentHTML", "method:",
                "X-CSRF-Token", "localStorage"):
        assert bad not in card, bad


def test_the_button_is_disabled_with_its_reason_whenever_the_server_would_refuse():
    card = CARD.read_text()
    assert "disabled: !!blocked" in card
    assert 'id: "launch-review-why"' in card and "blocked ||" in card
    for reason in ("Step-up needed first.", "Already active.",
                   "Frames are not yet built for every Launch-0 release"):
        assert reason in card, reason


def test_the_reason_function_agrees_with_the_server_rules():
    node = shutil.which("node")
    if not node:
        print("NOT RUN (node not found): the reason function was checked statically only")
        return
    src = CARD.read_text()
    m = re.search(r"export function activateBlockedReason\(st, stepped\) \{.*?\n\}\n", src, re.S)
    assert m, "activateBlockedReason not found"
    fn = m.group(0).replace("export function", "function")
    cases = [
        ({"status": "not_activated", "frames_ready": True}, True, ""),
        ({"status": "not_activated", "frames_ready": True}, False, "Step-up needed first."),
        ({"status": "not_activated", "frames_ready": False,
          "missing_releases": ["market-basket-small@1.2.0"]}, True, "Frames are not yet built"),
        ({"status": "not_activated"}, True, "Frames are not yet built"),   # unknown: refused
        ({"status": "open"}, True, "Already active."),
        ({"status": "expired"}, True, "Already used (expired)."),
        ({"status": "completed"}, True, "Already used (completed)."),
        (None, True, "could not be read"),
    ]
    harness = fn + "\nconst cases = " + json.dumps(cases) + ";\n" + """
const out = cases.map(([st, stepped]) => activateBlockedReason(st, stepped));
console.log(JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "h.mjs"
        p.write_text(harness)
        got = json.loads(subprocess.run([node, str(p)], capture_output=True, text=True,
                                        check=True, timeout=60).stdout)
    for (st, stepped, want), reason in zip(cases, got):
        if want == "":
            assert reason == "", (st, stepped, reason)
        else:
            assert reason and want in reason, (st, stepped, reason)


def test_the_card_ships_in_the_offline_shell():
    sw = (STATIC / "sw.js").read_text()
    assert '"js/views/_launch_review.js"' in sw
    assert 'const VERSION = "cc-shell-v20";' in sw


def test_the_state_route_tells_the_card_whether_the_frames_are_built():
    api_py = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "api.py").read_text()
    route = api_py[api_py.index('@router.get("/launch-review")'):
                   api_py.index('@router.post("/launch-review/activate")')]
    assert 'out["frames_ready"]' in route and 'out["missing_releases"]' in route
    assert "launch_review.frame_scope(db)" in route


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
