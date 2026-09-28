"""Audit an evidence packet, never award COMPLETE+PROVEN.

CLI is a read-only matrix consumer with a separate durable report output. Hashes bind
bytes, not their truth. REVIEWABLE means structurally complete evidence for independent
adjudication; it does not establish that claimed events really happened.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

STAGES = ("producer", "durable_state", "consumer", "decision", "effect", "result")


def validate(row: dict, packet: dict, *, head: str, root: Path) -> dict:
    errors = []
    def need(ok, reason):
        if not ok:
            errors.append(reason)
    need(bool(re.fullmatch(r"[0-9a-f]{40}", head)), "invalid effective head")
    need(packet.get("uid") == row.get("uid") and bool(row.get("uid")), "qualified requirement mismatch")
    need(packet.get("head") == head, "stale source head")
    need(packet.get("evidence_class") == "runtime", "static or fixture evidence cannot prove runtime")
    need(packet.get("direct") is True, "proxy cannot satisfy direct proof")
    run = packet.get("run_id")
    need(isinstance(run, str) and bool(run.strip()), "missing run identity")
    artifacts = packet.get("artifacts", {})
    valid = set()
    if not isinstance(artifacts, dict):
        artifacts = {}
    for name, item in artifacts.items():
        try:
            path = (root / item["path"]).resolve()
            path.relative_to(root.resolve())
            need(path.is_file(), f"missing artifact:{name}")
            if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
                valid.add(name)
            else:
                errors.append(f"artifact digest mismatch:{name}")
        except (KeyError, TypeError, ValueError, OSError):
            errors.append(f"invalid artifact:{name}")
    def receipt(item, label):
        if not isinstance(item, dict):
            errors.append(f"missing receipt:{label}")
            return
        need(item.get("artifact") in valid, f"unbound receipt:{label}")
        need(item.get("head") == head and item.get("run_id") == run, f"stale or unrelated receipt:{label}")
        need(item.get("observed") is True, f"unobserved:{label}")
    stages = packet.get("chain", {})
    if not isinstance(stages, dict):
        stages = {}
    previous = None
    for stage in STAGES:
        item = stages.get(stage)
        receipt(item, stage)
        if isinstance(item, dict):
            need(bool(item.get("identity")), f"missing identity:{stage}")
            if previous:
                need(item.get("input") == previous, f"broken evidence edge:{stage}")
            previous = item.get("identity")
    live = packet.get("live_root", {})
    receipt(live, "live_root")
    need(live.get("kind") in {"scheduler", "worker", "api", "event"}, "not a runtime root")
    need(live.get("producer") == stages.get("producer", {}).get("identity"), "root does not reach producer")
    receipt(packet.get("production_producer"), "production_producer")
    receipt(packet.get("failure_test"), "failure_test")
    receipt(packet.get("suite"), "suite")
    suite = packet.get("suite", {})
    need(suite.get("passed", 0) > 0 and suite.get("failed") == 0 and suite.get("clean") is True,
         "non-green or dirty suite")
    # Applicable protected behavior is specified by the audited row, not opted out by packet.
    if row.get("protected_effect"):
        execution = packet.get("execution_gate", {})
        receipt(execution, "execution_gate")
        need(execution.get("phase") == "execution", "planning-only authority")
        need(execution.get("effect") == stages.get("effect", {}).get("identity"), "gate not bound to effect")
        need(execution.get("outcome") in {"allowed", "refused"}, "unknown execution authority")
    review = packet.get("independent_review", {})
    receipt(review, "independent_review")
    need(bool(packet.get("implementer")) and bool(review.get("reviewer"))
         and review.get("reviewer") != packet.get("implementer"), "worker self-review")
    need(review.get("verdict") == "supported", "independent review not supportive")
    need(review.get("result") == stages.get("result", {}).get("identity"), "review does not bind result")
    return {"uid": row.get("uid"), "head": head,
            "verdict": "BLOCKED" if errors else "REVIEWABLE", "errors": errors,
            "certified": False,
            "limitation": "Artifact integrity and packet consistency only; independent source authenticity and semantic audit still required."}


def audit(rows, packets, *, head, root):
    if not rows:
        raise ValueError("empty matrix cannot establish proof")
    uids = [r["uid"] for r in rows]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate qualified matrix uid")
    by_uid = {}
    for packet in packets:
        uid = packet.get("uid")
        if uid in by_uid or uid not in uids:
            raise ValueError("duplicate or unknown packet uid")
        by_uid[uid] = packet
    return {"head": head, "certified": False, "rows": [
        validate(row, by_uid.get(row["uid"], {}), head=head, root=root) for row in rows]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("matrix", "packets", "head", "artifacts", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    matrix_path, packets_path, output = map(Path, (args.matrix, args.packets, args.output))
    if output.resolve() in {matrix_path.resolve(), packets_path.resolve()}:
        parser.error("report must not overwrite source matrix or packets")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = matrix if isinstance(matrix, list) else matrix["matrix"]
    report = audit(rows, json.loads(packets_path.read_text(encoding="utf-8")),
                   head=args.head, root=Path(args.artifacts))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return int(any(r["verdict"] == "BLOCKED" for r in report["rows"]))


if __name__ == "__main__":
    raise SystemExit(main())
