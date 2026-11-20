"""Owner Decision 2: generate, show, label and record a 24-frame contact sheet of Laura.

    python3 scripts/identity_contact_sheet.py plan                      # prints the 24 shots; free
    python3 scripts/identity_contact_sheet.py generate DIR --db URL     # the worker; US$1.15 cap
    python3 scripts/identity_contact_sheet.py sheet DIR                 # contact_sheet.png + label.html
    python3 scripts/identity_contact_sheet.py label DIR --by NAME --laura 1-20,22 --not-laura 21,23,24
    python3 scripts/identity_contact_sheet.py add DIR                   # into calibration_set.json

`generate` refuses (exit 2, nothing reserved or spent) unless the BFL key is present AND the
owner's `generation` activation of flux-3-image is active. Every frame is conditioned on all
three canonical references, verified by sha256. Labels come only from the owner: `label`
refuses a sheet with any frame unlabelled or labelled twice, or with no labeller named.
See `brambleloop.visual.identity_labelling`.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DEFAULT_DIR = ROOT / "research/final_build/w6/identity_calibration/contact_sheet"
SET_PATH = ROOT / "research/final_build/w6/identity_calibration/calibration_set.json"


def main(argv=None) -> int:
    from brambleloop.visual import identity_labelling as L

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    g = sub.add_parser("generate")
    g.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    g.add_argument("--db", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    lb = sub.add_parser("label")
    lb.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    lb.add_argument("--by", required=True)
    lb.add_argument("--laura", required=True)
    lb.add_argument("--not-laura", required=True)
    a = sub.add_parser("add")
    a.add_argument("dir", nargs="?", default=str(DEFAULT_DIR))
    args = ap.parse_args(argv)

    if args.cmd == "plan":
        for shot in L.plan():
            print(shot["n"], shot["prompt"])
        print(f"{L.N_FRAMES} frames x US${L.price_usd()} = US${L.N_FRAMES * L.price_usd():.3f} "
              f"(cap US${L.CAP_USD}); nothing generated")
        return 0
    d = Path(args.dir)
    mpath = d / "contact_sheet.json"
    if args.cmd == "generate":
        from brambleloop.core.db import Database

        try:
            man = L.generate(Database(args.db), d)
        except L.NotReady as exc:
            print(str(exc))
            return 2
        print(f"{len(man['frames'])} frames in {d}; spent at list price "
              f"US${man['spent_usd_at_list_price']}")
        return 0
    man = json.loads(mpath.read_text())
    if args.cmd == "sheet":
        (d / "contact_sheet.png").write_bytes(L.contact_sheet(man, d))
        (d / "label.html").write_text(L.labelling_page(man))
        print(f"wrote {d / 'contact_sheet.png'} and {d / 'label.html'}")
        return 0
    if args.cmd == "label":
        try:
            man = L.apply_labels(man, d, laura=L.parse_numbers(args.laura),
                                 not_laura=L.parse_numbers(args.not_laura), labelled_by=args.by)
        except L.LabelsRefused as exc:
            print(f"REFUSED: {exc}")
            return 2
        mpath.write_text(json.dumps(man, indent=1))
        n = sum(1 for f in man["frames"] if f["label"] == L.LAURA)
        print(f"labelled {len(man['frames'])} frames: {n} Laura, "
              f"{len(man['frames']) - n} not Laura")
        return 0
    if args.cmd == "add":
        try:
            print(L.add_to_calibration_set(man, d, SET_PATH, ROOT))
        except L.LabelsRefused as exc:
            print(f"REFUSED: {exc}")
            return 2
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
