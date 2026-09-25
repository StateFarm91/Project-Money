"""The shadow-safe Etsy exercise: the smallest sequence that proves the write path works.

Seven steps, in this order, because each one is only meaningful if the one before it
succeeded:

1. **Ping** -- can this environment reach Etsy at all.
2. **Read the shop** -- is the key live and is the shop id right.
3. **Create a draft** -- does Etsy accept our form-encoded create request.
4. **Upload a listing image** -- the step whose absence made every draft unactivatable.
5. **Update permitted draft fields** -- does a form-encoded PATCH change what it says.
6. **Read it back** -- does the listing on Etsy match what we sent. This is the only step
   that produces evidence; the others produce 200s.
7. **Delete the test draft** -- leave the shop exactly as it was found.

What this deliberately does not do: activate. A draft is invisible to buyers and free; a
publish is neither. Etsy charges its listing fee at publication, so step 6 is where this
sequence ends for good until somebody with Launch-0 authority says otherwise, and `activate`
refuses without an authorisation passed to the call.

**Cleanup is part of the exercise, not a courtesy.** A test artefact left in a real shop is
indistinguishable from a product with a mistake in it. The deletion reads the listing's state
back before deleting, so a wrong id refuses rather than destroys, and if the deletion fails
the report says the shop still holds the artefact and names its id.

Run it: `python3 -m brambleloop.integrations.etsy_probe`. It refuses unless
`ETSY_SHADOW_WRITE=1` is set in the environment, which is the operator saying "yes, write
drafts to the real shop". Reads happen without it.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
import zlib
from typing import Any

from ..core.resilience import PermanentError, TransientError
from .etsy import (
    Authority, Credentials, EtsyClient, EtsyNotPermitted, EtsyRejected, build_payload,
)
from .etsy_verify import verify

# What the test draft says it is, in the first words of its title, so that a human who finds
# it in Shop Manager before the cleanup runs knows immediately what it is and that it is safe
# to delete. Etsy's title character set allows letters, digits, punctuation and whitespace.
TEST_TITLE_PREFIX = "DO NOT BUY - Brambleloop transport test"

# A one-pixel PNG, built rather than stored, so no binary file enters the repository and the
# bytes are provably an image rather than something renamed. Etsy's image requirements
# (minimum dimensions, maximum size) are on help.etsy.com, which refuses automated readers, so
# **whether Etsy accepts an image this small is exactly the sort of thing this probe finds
# out.** If it refuses, that is a real finding and not a bug in the probe.
def one_pixel_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (len(data).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big")
                 + bytes([8, 2, 0, 0, 0]))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x7f\x5a\x3c"))
    return header + ihdr + idat + chunk(b"IEND", b"")


def test_payload(marker: str):
    """The draft this probe creates: a real listing shape, unmistakably not a product.

    It goes through `build_payload`, which means it is checked against Etsy's character sets
    and limits exactly as a real listing would be. A probe that bypassed those checks would be
    exercising a path no product takes.
    """
    return build_payload(
        title=f"{TEST_TITLE_PREFIX} {marker}",
        description=(
            "This is not a product. It is an automated transport test created by "
            "Brambleloop Studio's own software to verify that its Etsy integration can "
            "create a draft, attach an image and read the result back. It is a draft, it is "
            "not for sale, and the software deletes it immediately after the check. "
            f"Marker: {marker}."),
        price_cad=9.99,
        tags=["do not buy", "test draft"],
        materials=["test"],
    )


def _step(record: list[dict[str, Any]], name: str, why: str):
    """Record one step's outcome, including its own failure, and keep going where safe."""
    entry: dict[str, Any] = {"step": name, "measures": why, "started_at": time.time()}
    record.append(entry)
    return entry


def run_exercise(client: EtsyClient, *, image: bytes | None = None,
                 image_filename: str = "brambleloop-transport-test.png",
                 pattern: bytes | None = None,
                 cleanup: bool = True) -> dict[str, Any]:
    """Run the seven steps against whatever `client` points at, and report what happened.

    Returns a record rather than raising, because a partial run is the interesting case: a
    draft created and not deleted is a fact about a real shop, and a function that raised
    would leave the caller to guess whether that happened.
    """
    steps: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "at": time.time(),
        "base_url": client.BASE,
        "phase": client.phase,
        "authority": {
            "read": client.refusal_for(Authority.READ) or "permitted",
            "draft_write": client.refusal_for(Authority.DRAFT_WRITE) or "permitted",
            "activate": client.refusal_for(Authority.ACTIVATE) or "permitted",
        },
        "steps": steps,
        "listing_id": None,
        "cleaned_up": None,
        "verified": False,
        "activation_attempted": False,   # stays false. See the module docstring.
    }
    image = image if image is not None else one_pixel_png()
    marker = uuid.uuid4().hex[:10]

    # 2. Read the shop.
    entry = _step(steps, "read_shop",
                  "that the API key is live and ETSY_SHOP_ID names a shop we can read")
    try:
        shop = client.get_shop()
        entry["ok"] = True
        # Shop name and id are the owner's business identity; the fact that a shop was read
        # is the evidence, the identity is not.
        entry["observed"] = {"shop_returned": bool(shop),
                             "fields": sorted(k for k in shop)[:12]}
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        report["stopped_at"] = "read_shop"
        return report

    # 3. Create the draft.
    entry = _step(steps, "create_draft",
                  "that Etsy accepts a form-encoded createDraftListing and returns an id")
    try:
        payload = test_payload(marker)
        sent = payload.to_dict()
        sent.pop("state", None)
        listing_id = client.create_draft(payload)
        report["listing_id"] = listing_id
        entry["ok"] = True
        entry["observed"] = {"listing_id": listing_id,
                             "encoding_sent": client.calls[-1]["encoding"]}
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        report["stopped_at"] = "create_draft"
        return report

    # 4. Upload the image. The step that did not exist.
    entry = _step(steps, "upload_image",
                  "that a multipart part named `image` reaches Etsy and becomes a listing "
                  "image -- the thing a draft needs before it can ever be activated")
    image_id = None
    try:
        uploaded = client.upload_image(
            listing_id, filename=image_filename, data=image, rank=1,
            alt_text="Automated transport test image. Not a product photograph.")
        image_id = uploaded.get("listing_image_id")
        entry["ok"] = True
        entry["observed"] = {"listing_image_id": image_id,
                             "encoding_sent": client.calls[-1]["encoding"]}
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)

    # 4b. The digital file, only if the caller supplied bytes. Optional because the pattern
    # PDF is a release artefact and this probe must not need one to run.
    if pattern:
        entry = _step(steps, "upload_file",
                      "that a multipart part named `file` attaches the digital download")
        try:
            entry["ok"] = client.attach_file(listing_id,
                                             filename=f"transport-test-{marker}.pdf",
                                             data=pattern)
        except (PermanentError, TransientError) as e:
            entry["ok"] = False
            entry["error"] = str(e)

    # 5. Update permitted draft fields.
    entry = _step(steps, "update_listing",
                  "that a form-encoded PATCH changes the fields it names, and only those")
    update = {"title": f"{TEST_TITLE_PREFIX} {marker} updated",
              "tags": ["do not buy", "test draft", "updated"]}
    try:
        client.update_listing(listing_id, update)
        entry["ok"] = True
        entry["observed"] = {"fields": sorted(update),
                             "encoding_sent": client.calls[-1]["encoding"]}
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)
        update = {}

    # 5b. Prove the refusals are refusals, not documentation. Free: nothing is sent.
    entry = _step(steps, "refusals_hold",
                  "that price cannot be sent to updateListing, that state cannot be set "
                  "through it, and that activation refuses without a Launch-0 authorisation")
    observed: dict[str, Any] = {}
    for label, call in (
            ("price_refused", lambda: client.update_listing(listing_id, {"price": 1.0})),
            ("state_refused", lambda: client.update_listing(listing_id, {"state": "active"})),
            ("activation_refused", lambda: client.activate(listing_id)),
    ):
        try:
            call()
            observed[label] = "NOT REFUSED -- this is a defect in the gate"
        except (EtsyRejected, EtsyNotPermitted) as e:
            observed[label] = str(e)[:140]
    entry["ok"] = all("NOT REFUSED" not in v for v in observed.values())
    entry["observed"] = observed

    # 6. Read it back. The only step that produces evidence.
    entry = _step(steps, "read_back",
                  "that the listing Etsy holds matches what we sent, that it is still a "
                  "draft, and that Etsy has the image")
    try:
        remote = client.get_listing(listing_id)
        expected = {**sent, **update}
        result = verify(expected, remote, listing_id=listing_id, expect_state="draft",
                        expect_images=1 if image_id else 0)
        report["verified"] = result.verified
        report["read_back"] = result.summary()
        entry["ok"] = result.verified
        entry["observed"] = result.summary()
    except (PermanentError, TransientError) as e:
        entry["ok"] = False
        entry["error"] = str(e)

    # 7. Clean up. Always attempted; always reported.
    if cleanup:
        entry = _step(steps, "cleanup",
                      "that the test artefact is gone from the shop, and that the delete "
                      "refuses if the listing is not the draft we expect")
        try:
            report["cleaned_up"] = client.delete_listing(listing_id,
                                                         expect_states=("draft",))
            entry["ok"] = bool(report["cleaned_up"])
        except (PermanentError, TransientError) as e:
            report["cleaned_up"] = False
            entry["ok"] = False
            entry["error"] = str(e)
            entry["owner_action"] = (
                f"listing {listing_id} still exists in the shop as a draft and this run could "
                f"not remove it. Delete it in Shop Manager: it is titled "
                f"'{TEST_TITLE_PREFIX} {marker}'.")
    else:
        report["cleaned_up"] = False
        report["note"] = (f"cleanup was not requested; draft {listing_id} remains in the "
                          f"shop.")

    for step in steps:
        step["seconds"] = round(time.time() - step["started_at"], 3)
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the exercise against the real shop, or explain precisely why it cannot.

    Writes nothing to the repository and prints no secret. What it prints is a record of what
    was measured, which is the thing the deliverable needs and the thing a token is not.
    """
    argv = argv if argv is not None else sys.argv[1:]
    env = os.environ
    from .http import UrllibTransport, probe_live

    transport = UrllibTransport()
    credentials = Credentials.from_env(env, transport=transport)

    report: dict[str, Any] = {"at": time.time()}

    # 1. Ping, always. It needs no OAuth token and it is the one fact available without an
    # owner action.
    report["ping"] = probe_live(
        credentials.api_key_header() if credentials is not None else "", transport)

    if credentials is None:
        from .etsy_oauth import OAuthApp, owner_action
        report["status"] = "NOT EXERCISED -- no Etsy credentials in this environment"
        report["owner_action"] = owner_action(OAuthApp.from_env(env))
        print(json.dumps(report, indent=2, default=str))
        return 2

    if env.get("ETSY_SHADOW_WRITE", "") != "1":
        client = EtsyClient(transport, credentials=credentials,
                            phase=env.get("BRAMBLELOOP_PHASE", "shadow"))
        try:
            shop = client.get_shop()
            report["read_shop"] = {"ok": True, "fields": sorted(shop)[:12]}
        except (PermanentError, TransientError) as e:
            report["read_shop"] = {"ok": False, "error": str(e)}
        report["status"] = ("READ ONLY -- set ETSY_SHADOW_WRITE=1 to let this probe create "
                            "and then delete one draft in the real shop. No listing is ever "
                            "activated and no fee is incurred either way.")
        print(json.dumps(report, indent=2, default=str))
        return 0

    client = EtsyClient(transport, credentials=credentials,
                        phase=env.get("BRAMBLELOOP_PHASE", "shadow"),
                        shadow_writes_authorised=True)
    report["exercise"] = run_exercise(client, cleanup="--keep" not in argv)
    report["status"] = ("EXERCISED against api.etsy.com"
                        if report["exercise"].get("verified")
                        else "ATTEMPTED -- see steps for what failed")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["exercise"].get("verified") else 1


if __name__ == "__main__":   # pragma: no cover - operator entry point
    raise SystemExit(main())
