import subprocess, sys, pathlib
bl = pathlib.Path("/home/user/bl-runs/wt-rev-a1r/brambleloop")
S = "/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/u2probes"
L = "src/brambleloop/products/launch0.py"; P = "src/brambleloop/publish/pdf.py"
F = "src/brambleloop/products/text_fold.py"; SP = "src/brambleloop/gates/small_parts.py"
R = "src/brambleloop/runtime/release.py"; LP = "src/brambleloop/publish/listing_package.py"
FC = "src/brambleloop/creative/fallback_constructions.py"
T1="test_a1r1_a_one_piece_ball_and_every_filling_spelling_is_a_closed_stuffed_form"
T2="test_a1r2_greek_cherokee_and_cyrillic_capitals_fold_before_case_through_the_worker"
T3="test_a1r3_one_fold_reads_drafting_rendering_survey_and_motifs"
T4="test_a1r4_a_hold_is_named_permanent_owner_visible_and_blocks_no_other_product"
T5="test_a1r5_small_parts_for_every_assigned_product_and_unknown_blocks"
T6="test_a1r6_decisions_carry_who_and_when_and_the_listing_reads_the_held_decision"
ALL = None
M = {
 "N1 capitals mapped after lower": (F, "return t.translate(CAPITAL_LOOKALIKES).lower().translate(LOOKALIKES)", "return t.lower().translate(LOOKALIKES)", [T2,T3]),
 "N2 closes_on_itself always False": (L, '    if getattr(component, "construction", None) not in ROUNDS:\n        return False\n', '    return False\n', [T1]),
 "N3 old narrow stuffing regex": (L, 'if STUFFING_WORDS.search(name):', 'if re.search(r"\\b(?:fibre ?fill|fiber ?fill|stuffing|poly[- ]?fil+|polyfill|toy filling|wadding|batting)\\b", name):', [T1]),
 "N4 notes not read": (L, "        if STUFFING_NOTE_WORDS.search(_folded(notes)):", "        if False:", [T1]),
 "N5 non-yarn branch dropped": (L, '            elif not getattr(m, "yarn_weight", None):', '            elif False:', [T1]),
 "N6 unreadable -> [] (fail open)": (L, '        return [f"construction unreadable ({type(exc).__name__}): UNKNOWN, held"]', '        return []', ALL),
 "N7 small parts only if stuffed": (P, "        blocks = small_parts.blocking(cir)\n", "        blocks = small_parts.blocking(cir) if stuffed else []\n", [T5]),
 "N8 UNKNOWN treated as clear (M10)": (SP, "for name, n, l in pieces if verdict(n, l) != CLEAR]", "for name, n, l in pieces if verdict(n, l) == FITS]", [T5]),
 "N9 unmeasured sewn-on not added": (SP, "            for name in _sewn_on(cir) if name not in measured]", "            for name in _sewn_on(cir) if False]", [T5]),
 "N10 blocking exception -> []": (SP, '        return [f"sewn-on pieces unmeasurable ({type(exc).__name__}): {UNKNOWN}"]', '        return []', ALL),
 "N11 hold not caught (generic error)": (R, "    except ChildrensDecisionRequired as exc:\n        return _childrens_hold(ctx, exc)", "    except ZeroDivisionError as exc:\n        return _childrens_hold(ctx, exc)", [T4]),
 "N12 owner action not deduped": (R, "        if not s.scalar(select(OwnerAction.id).where(OwnerAction.requirement_key == rk,", "        if True or not s.scalar(select(OwnerAction.id).where(OwnerAction.requirement_key == rk,", [T4]),
 "N13 not PermanentError": (P, "class ChildrensDecisionRequired(_PermanentError, ValueError):", "class ChildrensDecisionRequired(ValueError):", [T4]),
 "N14 listing raw decision": (LP, "        return (launch0.childrens_decision_for(CIR.from_dict(cir)) if cir", "        return (launch0.childrens_decision(slug_) if cir", [T6]),
 "N15 fold_title not shared": (FC, '    text = unicodedata.normalize("NFKC", fold(title or "")).replace', '    text = unicodedata.normalize("NFKC", title or "").replace', [T3]),
 "N16 CLOSURE_MAX_STITCHES=0": (L, "CLOSURE_MAX_STITCHES = 12", "CLOSURE_MAX_STITCHES = 0", [T1]),
 "N17 stuffed form not refused for undecided": (P, "    if not words and not stuffed:\n        return\n", "    if not words:\n        return\n", [T1, T4]),
 "N18 exemption accepted for any stuffed": (L, "    if closed_stuffed_form(cir) and state == NOT_FOR_CHILDREN \\", "    if False and closed_stuffed_form(cir) and state == NOT_FOR_CHILDREN \\", [T6]),
}
fns_all = ",".join([T1,T2,T3,T4,T5,T6])
sel = sys.argv[1].split("|") if len(sys.argv) > 1 else list(M)
for name in sel:
    f, old, new, fns = M[name]
    path = bl / f; src = path.read_text()
    assert src.count(old) == 1, (name, src.count(old))
    path.write_text(src.replace(old, new))
    try:
        r = subprocess.run(["/home/user/bl-runs/venv-integ4/bin/python", f"{S}/runsel.py", "test_a1r_child_safety_core", ",".join(fns) if fns else fns_all],
                           cwd=bl, capture_output=True, text=True, timeout=2400,
                           env={"PATH": "/usr/bin:/bin", "HOME": "/root", "PYTHONDONTWRITEBYTECODE": "1"})
        fails = [l[:160] for l in r.stdout.splitlines() if l.startswith("FAIL")]
        print(name, "KILLED" if r.returncode else "SURVIVED", fails[:2], (r.stderr[-200:] if r.returncode and not fails else ""), flush=True)
    finally:
        path.write_text(src)
print(subprocess.run(["git", "-C", str(bl), "status", "--short"], capture_output=True, text=True).stdout or "clean")
