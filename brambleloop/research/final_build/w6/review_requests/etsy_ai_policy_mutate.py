"""Apply one mutant at a time to the new gates, run the suite, restore. Prints KILLED/SURVIVED."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # brambleloop/
SRC = ROOT / "src/brambleloop"
SUITE = sys.argv[1:] or ["tests/test_w6_etsy_ai_policy.py"]

MUTANTS = [
    ("M1 check_ai_disclosure returns []", "gates/policy.py",
     "    from .platform_policy import DISCLOSURES\n\n    if classification is None:",
     "    return []\n    from .platform_policy import DISCLOSURES\n\n    if classification is None:"),
    ("M2 unclassified package owes nothing", "gates/policy.py",
     '        owed = [DISCLOSURES["ai_assisted_design"]]', "        owed = []"),
    ("M3 check_authorship returns []", "gates/policy.py",
     "    from ..publish.etsy_ai_policy import CODE, authorship_claim_problems\n",
     "    return []\n"),
    ("M4 check_listing skips authorship", "gates/policy.py",
     '    out += check_authorship(draft.description, "listing.description")\n', ""),
    ("M5 claims() finds nothing", "publish/etsy_ai_policy.py",
     "    found: dict[tuple[str, str], None] = {}\n",
     "    return []\n    found: dict[tuple[str, str], None] = {}\n"),
    ("M6 no Unicode folding", "publish/etsy_ai_policy.py",
     '    t = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE)\n',
     '    return (text or "").lower()\n'),
    ("M7 no joined form", "publish/etsy_ai_policy.py",
     '    joined = re.sub(rf"(?<=[a-z]){_JOINERS}+(?=[a-z])", "", t)',
     "    joined = spaced"),
    ("M8 no spaced-letter collapse", "publish/etsy_ai_policy.py",
     '    return re.sub(r"\\b(?:[a-z] ){2,}[a-z]\\b", join, t)', "    return t"),
    ("M9 allowlist not removed (raw text scanned)", "publish/etsy_ai_policy.py",
     "    for sentence in honest_statements():\n        out = out.replace(sentence, \" \")",
     "    pass"),
    ("M10 allowlist removes everything", "publish/etsy_ai_policy.py",
     "    out = text or \"\"\n    for sentence", "    out = \"\"\n    for sentence"),
    ("M11 status always PERMITTED", "publish/etsy_ai_policy.py",
     '    return {"status": UNKNOWN, "hold": True, "reading": None,',
     '    return {"status": PERMITTED, "hold": False, "reading": None,'),
    ("M12 anonymous reading accepted", "publish/etsy_ai_policy.py",
     '        out.append("read_by is required")', "        pass"),
    ("M13 stale reading accepted", "publish/etsy_ai_policy.py",
     '        out.append(f"read_on is before the rules were last edited ({LATEST_EDIT})")',
     "        pass"),
    ("M13b reading of any age accepted", "publish/etsy_ai_policy.py",
     '        out.append(f"the reading is older than {READING_MAX_AGE_DAYS} days (stale)")',
     "        pass"),
    ("M13c non-step-up reading accepted", "publish/etsy_ai_policy.py",
     '        out.append("a reading is recorded only through the owner\'s step-up action")',
     "        pass"),
    ("M14 unreadable db is PERMITTED", "publish/etsy_ai_policy.py",
     "    except Exception:  # noqa: BLE001 - unreadable is UNKNOWN\n        readings = []",
     "    except Exception:  # noqa: BLE001 - unreadable is UNKNOWN\n"
     "        return {\"status\": PERMITTED, \"hold\": False, \"reason\": \"\", \"reading\": None}"),
    ("M15 for_publish ignores AI status", "publish/release_gates.py",
     '        reasons.append(ai_policy["reason"])\n', "        pass\n"),
    ("M16 hold_card writes nothing", "publish/etsy_ai_policy.py",
     "    problems = [str(p) for p in problems if p]\n    if not problems:",
     "    problems = []\n    if not problems:"),
    ("M17 owner-accepted copy unguarded", "publish/manual_adoption.py",
     "    problems.extend(authorship_claim_problems(\n", "    (authorship_claim_problems(\n"),
    ("M18 PROHIBITED releases", "publish/etsy_ai_policy.py",
     '        return {"status": PROHIBITED, "hold": True, "reading": d,',
     '        return {"status": PROHIBITED, "hold": False, "reading": d,'),
]

survived = 0
for name, rel, old, new in MUTANTS:
    path = SRC / rel
    orig = path.read_text()
    if orig.count(old) != 1:
        print(f"BADMUTANT {name}: anchor count {orig.count(old)}")
        survived += 1
        continue
    path.write_text(orig.replace(old, new))
    try:
        r = subprocess.run([sys.executable, *SUITE], cwd=ROOT, capture_output=True, text=True,
                           timeout=600)
        ok = r.returncode == 0
    finally:
        path.write_text(orig)
    print(f"{'SURVIVED' if ok else 'KILLED  '} {name}")
    survived += ok
print(f"survivors: {survived}")
raise SystemExit(1 if survived else 0)
