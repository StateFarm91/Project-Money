"""Master v1.1 addendum registry: F-880..F-930 parsed from source lines; v1.0 body unchanged."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "research" / "final_build"


def main():
    subprocess.run([sys.executable, str(FB / "parse_master_v11.py")], check=True,
                   capture_output=True)
    reg = json.loads((FB / "master_registry_v1_1.json").read_text())
    assert reg["v1_0_body_unchanged"] is True
    print("OK v1.0 body (§1-93) unchanged in v1.1")
    reqs = reg["requirements"]
    assert reqs, "no requirements parsed"
    assert [r["num"] for r in reqs] == list(range(880, 931))
    assert reg["missing_ids"] == [] and reg["duplicate_ids"] == []
    print("OK F-880..F-930 contiguous, 51 requirements, no gaps or duplicates")
    lines = (FB / "master_v1.1.txt").read_text().splitlines()
    for r in reqs:
        assert lines[r["lines"][0] - 1].startswith(r["id"] + " - " + r["title"])
        assert len(r["text"]) > 60, r["id"]
    print("OK every requirement cites its source line and carries its full text")
    tests = reg["acceptance_tests_s95"]
    assert tests and any("24 hours" in t for t in tests)
    print("OK §95 acceptance tests captured verbatim")
    # The v1.0 registry is untouched by the addendum.
    v10 = json.loads((FB / "master_registry.json").read_text())
    assert v10["source"]["text"].endswith("master_v1.0.txt")
    print("OK v1.0 registry still sourced from master_v1.0.txt")


if __name__ == "__main__":
    main()
