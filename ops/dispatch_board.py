#!/usr/bin/env python3
"""Dispatch board for the BRAMBLELOOP ENGINEERING DISPATCH issue (MAIN <-> SECONDARY).

Reuses ops/assignments.py. It is read-only except for one board comment, which it edits in place.
It reports:
  * unanswered messages: the newest message from one side that needs a reply (ASSIGN,
    QUESTION, BLOCKED, REVIEW-REQUEST or VERDICT) with no later message from the other side
    after REPLY_SLA minutes;
  * missing acknowledgements, stalled checkpoints and blocked items (`assignments.stale`);
  * review results not yet relayed: COORDINATION.json reviews recorded after the last [MAIN]
    message.
It never assigns, reassigns, merges or deploys anything.

  GITHUB_TOKEN=... python3 ops/dispatch_board.py --repo OWNER/REPO --issue N [--post]
Without a token it reads the public API and only prints.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assignments as A  # noqa: E402

TAG = re.compile(r"^\s*\[(MAIN|SECONDARY|CODEX)\]\s*([A-Z-]+)?", re.M)
NEEDS_REPLY = {"ASSIGN", "QUESTION", "BLOCKED", "REVIEW-REQUEST", "VERDICT", "NEXT"}
REPLY_SLA = timedelta(minutes=15)
BOARD_MARK = "<!-- dispatch-board -->"
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}   # review F1: public issue; ignore anyone else
BOT = "github-actions[bot]"


def api(url: str, token: str | None, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body else None)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def comments(repo: str, issue: int, token: str | None) -> list[dict]:
    out, page = [], 1
    while True:
        batch = api(f"https://api.github.com/repos/{repo}/issues/{issue}/comments"
                    f"?per_page=100&page={page}", token)
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def messages(cs: list[dict]) -> list[dict]:
    out = []
    for c in cs:
        m = TAG.match(c.get("body") or "")
        if c.get("author_association") not in TRUSTED:
            continue
        if m and BOARD_MARK not in (c.get("body") or ""):
            out.append({"id": c["id"], "who": m.group(1), "kind": (m.group(2) or "").strip(),
                        "at": A.parse(c["created_at"]), "url": c["html_url"]})
    return out


def unanswered(msgs: list[dict], t: datetime) -> list[dict]:
    late = []
    for i, m in enumerate(msgs):
        if m["kind"] not in NEEDS_REPLY:
            continue
        replied = any(n["who"] != m["who"] for n in msgs[i + 1:])
        if not replied and t - m["at"] > REPLY_SLA:
            late.append(m)
    return late


def board(repo: str, issue: int, token: str | None, root: Path = A.ROOT,
          t: datetime | None = None) -> str:
    t = t or A.now()
    msgs = messages(comments(repo, issue, token))
    late = unanswered(msgs, t)
    stale = [r for r in A.status(root, t) if r["overdue"]]
    last_main = max((m["at"] for m in msgs if m["who"] == "MAIN"), default=None)
    reviews = []
    for r in A.load_coord(root).get("reviews", []):
        when = A.parse(r.get("recorded") or r.get("at"))
        if last_main and when and when > last_main:       # review F3: undated entries skipped
            reviews.append((r.get("subject") or r.get("sha") or r.get("pr") or "review", A.iso(when)))
    seen = {}
    for m in msgs:
        seen[m["who"]] = m["at"]
    # review F4: no timestamp in the body, so an unchanged board is not re-edited every run
    lines = [BOARD_MARK, "**Dispatch board** (read-only; never assigns or reassigns). Counts only "
             "messages from the repository owner or collaborators.", ""]
    lines.append("Last message: " + ", ".join(f"{k} {A.iso(v)}" for k, v in sorted(seen.items())) if seen else "No tagged messages yet.")
    lines.append("")
    lines.append(f"**Unanswered more than {int(REPLY_SLA.total_seconds() // 60)} min ({len(late)})**")
    lines += [f"- {m['who']} {m['kind']} at {A.iso(m['at'])}: {m['url']}" for m in late] or ["- none"]
    lines.append(f"**Overdue assignments ({len(stale)})**")
    lines += [f"- {r['id']} ({r['owner']}, {r['stage']}): " + "; ".join(r["overdue"]) for r in stale] or ["- none"]
    lines.append(f"**Reviews recorded since Main's last message ({len(reviews)})**")
    lines += [f"- {s} {w}" for s, w in reviews] or ["- none"]
    return "\n".join(lines)


def post(repo: str, issue: int, token: str, text: str) -> None:
    for c in comments(repo, issue, token):
        if BOARD_MARK in (c.get("body") or "") and (c.get("user") or {}).get("login") == BOT:
            if c["body"] != text:
                api(c["url"], token, "PATCH", {"body": text})
            return
    api(f"https://api.github.com/repos/{repo}/issues/{issue}/comments", token, "POST", {"body": text})


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--post", action="store_true")
    a = p.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    text = board(a.repo, a.issue, token)
    print(text)
    if a.post and token:
        post(a.repo, a.issue, token, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
