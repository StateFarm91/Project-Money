"""Record your own reading of one Etsy policy page with the deployed service.

Etsy refuses automated retrieval of its policy pages, and Brambleloop does not evade that.
You open the page in your own browser, read it, and paste it into a file. Pasting a page
you read is not evasion; it is how a seller reads the rules. This script sends that text
to POST /api/policy/snapshot, which stores a digest (never the text) and closes the
source's open `policy_stale` incident if the reading is current.

    BRAMBLELOOP_OPS_TOKEN=... python scripts/record_policy.py \\
        --url https://<service>/api/policy/snapshot --source seller_policy \\
        --file seller_policy.txt --read-by "owner" [--version 2026-09-27] [--summary "..."]

Sources: seller_policy, creativity_standards, listing_image_rules, advertising_rules,
shilling_and_reviews, children_and_baby. The token is read from the environment and never
printed; the page text is never printed either.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def build_body(args: argparse.Namespace, text: str) -> dict:
    body = {"source": args.source, "text": text, "version": args.version or "",
            "summary": args.summary or "", "read_by": args.read_by}
    if args.checked_on:
        body["checked_on"] = args.checked_on
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="the /api/policy/snapshot URL")
    parser.add_argument("--source", required=True)
    parser.add_argument("--file", help="text file holding the page you read (default stdin)")
    parser.add_argument("--read-by", required=True, dest="read_by")
    parser.add_argument("--version", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--checked-on", default="", dest="checked_on",
                        help="ISO date you read it, default today")
    args = parser.parse_args(argv)

    token = (os.environ.get("BRAMBLELOOP_OPS_TOKEN") or "").strip()
    if not token:
        print("set BRAMBLELOOP_OPS_TOKEN in the environment", file=sys.stderr)
        return 2
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not text.strip():
        print("the page text is empty", file=sys.stderr)
        return 2

    request = urllib.request.Request(
        args.url, data=json.dumps(build_body(args, text)).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
            return 0
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
