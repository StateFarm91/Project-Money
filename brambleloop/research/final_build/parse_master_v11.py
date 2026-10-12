"""Deterministic parser: Final Master v1.1 addendum -> research/final_build/master_registry_v1_1.json.

v1.1 is additive (master §96): §1-93 are the v1.0 text unchanged and stay governed by
master_registry.json (parse_master.py). This parser (1) proves the v1.0 body is unchanged by
comparing non-blank lines of master_v1.1.txt against master_v1.0.txt up to §94, and (2) reads
F-880..F-930 from §94 with their source lines, plus the §95 acceptance tests verbatim.
Run: python3 research/final_build/parse_master_v11.py
"""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
V10 = HERE / "master_v1.0.txt"
V11 = HERE / "master_v1.1.txt"
OUT = HERE / "master_registry_v1_1.json"
DEF_RE = re.compile(r"^F-(\d{3}) - (.+?) - (.*)$")


def _nonblank(lines):
    return [l.rstrip() for l in lines if l.strip()]


def parse():
    v10 = V10.read_text().splitlines()
    v11 = V11.read_text().splitlines()
    s94 = next(i for i, l in enumerate(v11) if l.startswith("94. OWNER COMMAND CENTER"))
    s95 = next(i for i, l in enumerate(v11) if l.startswith("95. OWNER COMMAND CENTER ACCEPTANCE"))
    s96 = next(i for i, l in enumerate(v11) if l.startswith("96. v1.1 GOVERNANCE"))
    # The v1.1 addendum opens with its own title line just before §94; the v1.0 body ends there.
    hdr = max(i for i in range(s94) if v11[i].startswith("BRAMBLELOOP FINAL MASTER v1.1"))
    body_v11 = _nonblank(v11[:hdr])
    body_v10 = _nonblank(v10)
    unchanged = body_v10 == body_v11
    reqs = []
    i = s94
    while i < s95:
        m = DEF_RE.match(v11[i])
        if m:
            start = i
            text = [m.group(3)]
            i += 1
            while i < s95 and not DEF_RE.match(v11[i]) and v11[i].strip():
                text.append(v11[i].strip())
                i += 1
            reqs.append({"id": f"F-{m.group(1)}", "num": int(m.group(1)), "title": m.group(2),
                         "text": " ".join(text), "lines": [start + 1, i], "version": "v1.1",
                         "section": "94"})
            continue
        i += 1
    tests = [l.strip() for l in v11[s95 + 1:s96] if l.strip()]
    nums = [r["num"] for r in reqs]
    return {
        "source": {"text": "research/final_build/master_v1.1.txt",
                   "pdf": "spec/10_Brambleloop_FINAL_Master_v1.1_Owner_Command_Center.pdf",
                   "text_sha256": hashlib.sha256(V11.read_bytes()).hexdigest()},
        "v1_0_body_unchanged": unchanged,
        "v1_0_body_nonblank_lines": len(body_v11),
        "requirements": reqs,
        "count": len(reqs),
        "missing_ids": sorted(set(range(880, 931)) - set(nums)),
        "duplicate_ids": sorted({n for n in nums if nums.count(n) > 1}),
        "acceptance_tests_s95": tests,
    }


if __name__ == "__main__":
    reg = parse()
    OUT.write_text(json.dumps(reg, indent=1) + "\n")
    print(reg["count"], "requirements; v1.0 body unchanged:", reg["v1_0_body_unchanged"],
          "missing:", reg["missing_ids"], "dups:", reg["duplicate_ids"])
