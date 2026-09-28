"""Vacuous-test detector (F-123): a test must not pass by looping over nothing.

THE DEFECT. `for row in rows: assert row.ok` passes when `rows` is empty, and an empty `rows` is
exactly what a broken producer returns. The suite has met this before: a certification loop
(C-5) passed for a whole session because the eligible set it iterated was empty, and the
suite-level guard in run_tests.sh ("SUITE REPORTED NO PASSES") only catches a whole file that
proves nothing, not one test inside a green file that does.

THE RULE, AS AN AST SCAN OF EVERY tests/test_*.py. A `for` loop whose body asserts (an `assert`
statement, or a call to `check(...)` / `assert_*` / `self.assert*`) is VACUOUS-RISK unless the
test establishes, somewhere in the same function, that the loop had something to iterate:

  * the iterable is a non-empty literal (list/tuple/set/dict/string), `range(<positive const>)`,
    or `enumerate`/`zip`/`sorted`/`reversed`/`.items()`/`.values()`/`.keys()` over one;
  * the iterable is a module constant bound to a non-empty literal;
  * an assertion anywhere in the function mentions the iterable's root name, or a name the
    loop body writes (a counter / a collected list that is asserted afterwards);
  * the loop has an `else:` or `break`-free body followed by an assert on the loop variable.

Deliberately syntactic and conservative. It proves the test *looked* at emptiness, not that it
looked correctly -- a named limit.

EMPTINESS UNDER TEST is legitimate (F-123 says so): a loop annotated on its `for` line with
`# vacuity-ok: <reason>` is exempt, and the reason is required.

THE BASELINE. When this detector was introduced (2026-09-28) it found the loops listed in
`BASELINE` below, in files owned by other build clusters that this change may not edit. They
are grandfathered as a RATCHET: each is keyed by (file, function, iterable source), a new
finding anywhere fails, and a baseline entry that no longer fires must be deleted (so the list
only shrinks). Fixing one means adding the non-emptiness assertion and removing its key.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
PRAGMA = "# vacuity-ok:"

_WRAPPERS = {"enumerate", "zip", "sorted", "reversed", "list", "tuple", "set", "iter"}
_VIEWS = {"items", "values", "keys"}


def _asserts(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name == "check" or name.startswith("assert"):
                return True
    return False


def _nonempty_literal(node: ast.AST, consts: dict[str, ast.AST]) -> bool:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) > 0 and not any(isinstance(e, ast.Starred) for e in node.elts)
    if isinstance(node, ast.Dict):
        return len(node.keys) > 0
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return len(node.value) > 0
    if isinstance(node, ast.Name) and node.id in consts:
        return _nonempty_literal(consts[node.id], {})
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id == "range" and node.args:
            stop = node.args[-1] if len(node.args) == 1 else node.args[1]
            start = node.args[0] if len(node.args) > 1 else ast.Constant(0)
            if isinstance(stop, ast.Constant) and isinstance(start, ast.Constant):
                return isinstance(stop.value, int) and stop.value > start.value
            return False
        if isinstance(f, ast.Name) and f.id in _WRAPPERS and node.args:
            return all(_nonempty_literal(a, consts) for a in node.args)
        if isinstance(f, ast.Attribute) and f.attr in _VIEWS:
            return _nonempty_literal(f.value, consts)
    return False


def _code_constant(node: ast.AST) -> bool:
    """An UPPER_CASE table defined in code (`B.SIZES`, `GARMENTS[2:]`, `TILT_FOR.items()`).

    Exempt as a named limit: these are fixed data in the diff, not a producer's eligible set,
    and F-123 is about the latter. An empty code table is caught by that module's own tests.
    """
    while True:
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _VIEWS:
                node = f.value
                continue
            if isinstance(f, ast.Name) and f.id in _WRAPPERS and len(node.args) == 1:
                node = node.args[0]
                continue
            return False
        if isinstance(node, ast.Subscript):
            node = node.value
            continue
        name = node.attr if isinstance(node, ast.Attribute) else \
            node.id if isinstance(node, ast.Name) else ""
        return bool(name) and name.isupper() and len(name) > 1


def _root_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _written_names(loop: ast.For) -> set[str]:
    out = set()
    for n in ast.walk(loop):
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                    out.add(t.value.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                n.func.attr in {"append", "add", "extend", "update", "setdefault"} and \
                isinstance(n.func.value, ast.Name):
            out.add(n.func.value.id)
    return out - _loop_targets(loop)


def _loop_targets(loop: ast.For) -> set[str]:
    return {x.id for x in ast.walk(loop.target) if isinstance(x, ast.Name)}


def _assert_mentions(scope: ast.AST, names: set[str], exclude: ast.For) -> bool:
    """Does any assertion in `scope`, outside `exclude`'s body, mention one of `names`?"""
    inside = {id(n) for n in ast.walk(exclude)}
    for n in ast.walk(scope):
        if id(n) in inside:
            continue
        test = None
        if isinstance(n, ast.Assert):
            test = n.test
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name == "check" or name.startswith("assert"):
                test = ast.Tuple(elts=list(n.args), ctx=ast.Load())
        if test is not None and _root_names(test) & names:
            return True
    return False


def findings_in(path: Path) -> list[tuple[str, int, str, str]]:
    """[(function, line, iterable source, file)] for every vacuous-risk loop in one file."""
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    consts = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
              for t in node.targets if isinstance(t, ast.Name)}
    out = []

    def visit(scope: ast.AST, fname: str) -> None:
        for node in ast.iter_child_nodes(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(node, node.name)
                continue
            if isinstance(node, ast.ClassDef):
                visit(node, fname)
                continue
            for loop in [n for n in ast.walk(node) if isinstance(n, (ast.For, ast.AsyncFor))]:
                if not _asserts(ast.Module(body=loop.body, type_ignores=[])):
                    continue
                line = lines[loop.lineno - 1]
                if PRAGMA in line and line.split(PRAGMA, 1)[1].strip():
                    continue
                if _nonempty_literal(loop.iter, consts):
                    continue
                if _code_constant(loop.iter):
                    continue
                roots = _root_names(loop.iter) - _WRAPPERS - _VIEWS - {"range", "len"}
                if _assert_mentions(scope, roots | _written_names(loop), loop):
                    continue
                out.append((fname, loop.lineno, ast.unparse(loop.iter), path.name))
            # nested defs inside compound statements
            for inner in ast.walk(node):
                if inner is not node and isinstance(inner, (ast.FunctionDef,
                                                            ast.AsyncFunctionDef)):
                    visit(inner, inner.name)

    visit(tree, "<module>")
    # Helpers (`_scrubbed_env`, fixtures) are not tests: a loop there is only vacuous through
    # the test that calls it, which is where the finding belongs.
    out = [f for f in out if f[0] == "<module>" or f[0].startswith("test")]
    # a loop can be reached from both the module walk and a nested-def walk; keep one
    return sorted(set(out), key=lambda f: (f[3], f[1]))


def all_findings() -> list[tuple[str, int, str, str]]:
    out = []
    for p in sorted(TESTS.glob("test_*.py")):
        out += findings_in(p)
    return out


def key(f: tuple[str, int, str, str]) -> tuple[str, str, str]:
    return (f[3], f[0], f[2])


BASELINE: set[tuple[str, str, str]] = {
    ('test_assembly.py', 'test_unobservable_characteristics_are_never_counted_as_agreement', 'res.characteristics'),
    ('test_asset_manifest.py', 'test_every_manifest_hash_is_the_hash_of_the_file_on_disk', 'brief.asset_manifest()'),
    ('test_asset_manifest.py', 'test_every_role_is_one_of_the_three_and_every_entry_is_dated', 'brief.asset_manifest()'),
    ('test_blinded.py', 'test_the_grid_is_judged_by_an_independent_panel_blinded_to_side', 'judge.calls'),
    ('test_brand.py', 'test_the_fabric_render_cannot_invent_a_colour', 'used'),
    ('test_build2.py', 'test_every_requirement_carries_its_spec_text_and_a_reason', 'R.load()'),
    ('test_cert_claude_independence.py', 'test_production_start_command_runs_kills_and_resumes_without_this_session', 'before.items()'),
    ('test_cert_claude_independence.py', 'test_production_start_command_runs_kills_and_resumes_without_this_session', 'cadence_keys_a'),
    ('test_cert_competitive_weakness.py', 'test_with_no_capture_every_occasion_stays_unmeasured', "out['engine']['unscored']"),
    ('test_cert_dashboard.py', 'test_dashboard_cards_equal_sql', 'cl.items()'),
    ('test_cert_design.py', 'test_drop_shoulder_from_concept_assembles_at_every_size', 'design.build_all().items()'),
    ('test_cert_grading.py', 'test_cyc_sources_are_recorded', 'designs().items()'),
    ('test_cert_grading.py', 'test_size_counts_and_boundaries', 'designs().items()'),
    ('test_cert_hero_title_safe.py', 'test_no_hero_puts_ink_in_the_title_safe_band_and_every_thumbnail_still_passes', '_heroes()'),
    ('test_cert_identity.py', 'test_manifest_hashes_equal_committed_bytes_computed_independently', "_manifest()['assets']"),
    ('test_cert_wiring.py', 'test_scheduler_tick_calls_priority_for_and_bands_every_cadence_job', "_jobs(st['db'])"),
    ('test_childrens.py', 'test_a_complete_pattern_produces_no_findings_at_all', 'sub.audiences'),
    ('test_childrens.py', 'test_every_children_pattern_points_at_the_maker_who_sells', 'sub.audiences'),
    ('test_childrens.py', 'test_every_marker_is_a_phrase_that_survives_into_the_rendered_text', 'sub.audiences'),
    ('test_childrens.py', 'test_every_named_statement_exists_and_is_explained', 'sub.statements'),
    ('test_childrens.py', 'test_sizes_increase_monotonically_within_each_chart', 'chart'),
    ('test_commerce.py', 'test_the_listing_prints_the_statements_own_words_rather_than_a_paraphrase', 'seo.childrens_listing_statements(rendered)'),
    ('test_commerce.py', 'test_the_tag_set_is_not_one_concept_restated', 'tags'),
    ('test_compression.py', 'test_a_bundle_is_only_proposed_where_its_members_share_a_lane', "_at(97)['bundles']"),
    ('test_compression.py', 'test_a_retirement_is_scoped_to_one_class_and_one_occasion', "_at(97)['retired_classes']"),
    ('test_deliverable_qa.py', 'test_a_childrens_pattern_carries_every_statement_its_audience_requires', 'rendered.text.items()'),
    ('test_deliverable_qa.py', 'test_a_childrens_pattern_carries_every_statement_its_audience_requires', "text.split('\\n')"),
    ('test_deliverable_qa.py', 'test_a_uk_document_states_its_gauge_in_uk_terms_everywhere_it_states_it', '_designs()'),
    ('test_deliverable_qa.py', 'test_both_terminologies_render_for_every_shippable_design', '_designs()'),
    ('test_deliverable_qa.py', 'test_every_abbreviation_in_the_instructions_is_defined_in_the_document', '_designs()'),
    ('test_deliverable_qa.py', 'test_every_place_that_renders_the_customer_pdf_pins_its_date', 'enumerate(source.splitlines(), 1)'),
    ('test_deliverable_qa.py', 'test_every_statement_in_the_block_shows_its_source_or_says_it_has_none', 'ch.unsourced_statements()'),
    ('test_deliverable_qa.py', 'test_every_tool_the_instructions_require_is_on_the_materials_list', '_designs()'),
    ('test_deliverable_qa.py', 'test_the_chart_and_its_legend_are_pictures_and_the_document_says_where_the_text_is', "pdf_mod._chart_symbols(cir, twin, 'US')"),
    ('test_deliverable_qa.py', 'test_the_colour_key_describes_the_chart_that_was_actually_printed', "art['cues'].items()"),
    ('test_deliverable_qa.py', 'test_the_key_completeness_check_is_measured_on_the_whole_document', '_designs()'),
    ('test_deliverable_qa.py', 'test_the_key_does_not_contradict_the_instructions_about_joining_the_rounds', 'spiral_claims'),
    ('test_deliverable_qa.py', 'test_the_listing_chart_shows_what_the_document_shows', '_round_designs()'),
    ('test_departments.py', 'test_every_message_reaches_the_right_desk', 'cases'),
    ('test_etsy_exercise.py', 'test_no_credential_value_reaches_the_report_the_ledger_or_the_owner_queue', 'proof_secrets'),
    ('test_etsy_exercise.py', 'test_the_rotation_proof_reports_fingerprints_and_never_a_token', "proof['fingerprint_chain']"),
    ('test_etsy_oauth_callback.py', 'test_no_malformed_callback_causes_a_single_outbound_request', 'cases.items()'),
    ('test_etsy_oauth_callback.py', 'test_nothing_in_the_page_the_log_or_the_audit_row_carries_a_secret', 'leakable'),
    ('test_etsy_oauth_callback.py', 'test_the_redirect_uri_rules_etsy_publishes_are_enforced_before_the_owner_sees_a_browser', 'bad.items()'),
    ('test_etsy_surfaces.py', 'test_every_surface_the_brief_named_is_classified_exactly_once', 'es.surfaces()'),
    ('test_etsy_surfaces.py', 'test_every_unsupported_verdict_names_a_counted_absence', 'es.by_verdict(es.UNSUPPORTED)'),
    ('test_etsy_surfaces.py', 'test_every_verdict_rests_on_at_least_one_document_this_build_read', 'es.surfaces()'),
    ('test_etsy_surfaces.py', 'test_no_owner_action_pretends_software_could_have_done_it', 'es.owner_queue()'),
    ('test_etsy_surfaces.py', 'test_no_surface_claims_a_scope_etsy_does_not_publish', 'es.surfaces()'),
    ('test_etsy_surfaces.py', 'test_no_surface_claims_a_scope_etsy_does_not_publish', 's.scopes'),
    ('test_etsy_surfaces.py', 'test_the_first_sale_blockers_are_the_ones_a_shop_cannot_open_without', 'es.first_sale_blockers()'),
    ('test_etsy_transport.py', 'test_the_run_never_activates_anything_whatever_goes_wrong', 'cases'),
    ('test_family.py', 'test_a_family_member_is_never_the_hero_in_another_palette', "report['viable_roles']"),
    ('test_final_closure_matrix.py', 'test_exercised_rows_cite_a_committed_production_artefact', "_matrix()['matrix']"),
    ('test_final_closure_matrix.py', 'test_integrated_rows_have_a_producer_reached_from_a_live_root', "_matrix()['matrix']"),
    ('test_final_master_registry.py', 'test_no_requirement_swallows_a_section_heading_or_version_note', "_parser().parse()['requirements']"),
    ('test_first_customer_gate.py', 'test_the_download_is_a_first_customer_failure_while_the_store_is_ephemeral', "_launch0()['products']"),
    ('test_first_customer_gate.py', 'test_the_four_areas_that_pass_pass_on_measured_evidence', "_launch0()['products']"),
    ('test_garments.py', 'test_built_length_never_falls_between_sizes', '_raglan_matrix() + [G.harbour_pullover()]'),
    ('test_garments.py', 'test_every_size_of_every_design_passes_the_whole_chain', '_designs()'),
    ('test_garments.py', 'test_no_garment_matches_a_benchmark_and_each_states_its_provenance', '_designs()'),
    ('test_garments.py', 'test_no_garment_matches_a_benchmark_and_each_states_its_provenance', 'design.build_all().items()'),
    ('test_garments.py', 'test_raglan_increases_follow_the_standard_eight_per_unit', 'd.build_all().items()'),
    ('test_garments.py', 'test_raglan_neck_fits_the_body_at_every_size', '_raglan_matrix()'),
    ('test_garments.py', 'test_raglan_neck_fits_the_body_at_every_size', 'd.build_all().items()'),
    ('test_garments.py', 'test_sizes_grow_monotonically_and_hit_their_intended_chest', '_designs()'),
    ('test_garments.py', 'test_the_neckband_join_is_placed_at_the_neck_row_and_the_gates_agree', 'd.build_all().items()'),
    ('test_garments.py', 'test_the_sleeve_top_meets_the_body_side_it_is_sewn_to', 'G.harbour_pullover().build_all().items()'),
    ('test_gateway.py', 'test_no_prompt_asks_a_model_for_pattern_instructions', 'banned'),
    ('test_gateway.py', 'test_no_prompt_asks_a_model_for_pattern_instructions', 'prompt_registry.all_prompts()'),
    ('test_geometry.py', 'test_a_coaster_set_needs_yarn_for_the_whole_set', 'one.yarn_metres_by_color.items()'),
    ('test_graded.py', 'test_what_the_source_does_not_publish_is_unsourced_and_grading_to_it_refuses', 'table.sizes'),
    ('test_grading.py', 'test_a_graded_component_compiles_at_every_size', 'g.grade(_run(), stitches_per_10cm=16, rows_per_10cm=18, motif_width=8)'),
    ('test_grading.py', 'test_ease_is_declared_per_size_rather_than_scaled', 'sizes'),
    ('test_image_bench.py', 'test_every_rubric_line_cites_a_requirement', 'B.RUBRIC + (B.IDENTITY_DIMENSION,)'),
    ('test_intel.py', 'test_the_remaining_count_is_counted_rather_than_computed_to_fall', 'ast.walk(fn)'),
    ('test_lanes.py', 'test_the_requirements_own_examples_reach_the_lane_it_names', 'fast'),
    ('test_lanes.py', 'test_the_requirements_own_examples_reach_the_lane_it_names', 'flagship'),
    ('test_lanes.py', 'test_the_two_lanes_cannot_both_admit_the_same_product', 'cases'),
    ('test_launch.py', 'test_nothing_blocked_on_build_is_ever_sent_to_the_owner', 'readiness.buildable'),
    ('test_launch.py', 'test_the_owner_queue_carries_everything_the_directive_asks_for', "assess(db, phase='shadow').owner_requests()"),
    ('test_launch0.py', 'test_a_childrens_title_with_no_audience_assignment_is_reported', 'rows'),
    ('test_launch0.py', 'test_every_launch0_product_reports_finished_measurements_and_admits_they_are_arithmetic', 'l0.launch0()'),
    ('test_launch0.py', 'test_no_pipeline_entry_claims_a_cir', 'l0.pipeline_plan(today=TODAY)'),
    ('test_launch0.py', 'test_the_audience_assignment_is_computed_from_the_candidates_not_listed_twice', 'cand.variants'),
    ('test_launch0.py', 'test_the_report_carries_no_demand_or_velocity_score_for_a_product', 'names'),
    ('test_launch0.py', 'test_the_subjects_we_never_publish_are_enumerated_from_the_constraint_module', 'never'),
    ('test_listing_schema.py', 'test_every_gap_states_its_evidential_status_and_cannot_invent_a_claim', 'S.gaps()'),
    ('test_moat.py', 'test_an_asset_nobody_has_built_is_not_counted_as_a_moat', 'keys'),
    ('test_model_photography.py', 'test_a_frame_with_any_failed_floor_is_never_kept', "first['frames']"),
    ('test_owned_photography.py', 'test_the_prompt_is_derived_from_the_certified_pattern', 'cir.colors'),
    ('test_physical.py', 'test_the_factor_reaches_the_yardage_the_customer_reads', 'twin.yarn_metres_by_color.items()'),
    ('test_product_run.py', 'test_the_detected_repeat_is_the_real_one_not_a_convenient_one', 'enumerate(grid)'),
    ('test_product_run.py', 'test_the_detected_repeat_is_the_real_one_not_a_convenient_one', 'enumerate(row)'),
    ('test_prospecting.py', 'test_generated_variety_is_still_checked_rather_than_assumed', 'P._crosses_for(slot, 40)'),
    ('test_provenance_write_path.py', 'test_a_file_artefact_carries_the_hash_of_the_file_it_is', 'rows'),
    ('test_provenance_write_path.py', 'test_the_pdfs_and_charts_in_the_job_outputs_are_counted', "build.outputs['pdf_sha256_by_terminology'].items()"),
    ('test_quality.py', 'test_every_dimension_section_three_names_is_tracked', 'conf.Dimension'),
    ('test_reference_pack.py', 'test_a_clean_run_is_ready_for_approval_and_still_frozen_by_nobody', 'ast.walk(tree)'),
    ('test_render.py', 'test_the_yarn_runs_on_through_the_joins_and_ends_only_at_the_hops', 'ends'),
    ('test_render.py', 'test_the_yarn_runs_on_through_the_joins_and_ends_only_at_the_hops', 'strands'),
    ('test_repeat.py', 'test_a_recommendation_never_points_at_what_the_buyer_owns', '[s for s in POOL if not s.is_bundle][:12]'),
    ('test_rollforward.py', 'test_a_roll_forward_prefers_the_soonest_occasion_that_can_repay_it', "plan['capacities'][A.ENGINEERING]['moves']"),
    ('test_rowcycle.py', 'test_a_cycle_is_never_claimed_where_the_rows_differ', 'range(cycle.period)'),
    ('test_rowcycle.py', 'test_a_cycle_is_never_claimed_where_the_rows_differ', 'range(cycle.repeats)'),
    ('test_teardown.py', 'test_intake_never_opens_a_file_it_only_hashes_it', 'result.files'),
    ('test_teardown_readiness.py', 'test_every_capability_the_owner_listed_is_covered', "out['capabilities']"),
    ('test_tiers.py', 'test_the_ceilings_get_tighter_as_the_surface_gets_riskier', 'zip(ranks, ranks[1:])'),
    ('test_vacuity.py', 'test_a_non_emptiness_assertion_or_a_literal_clears_the_loop', 'clean'),
    ('test_video.py', 'test_every_planned_module_is_on_a_platform_its_shape_fits', "out['modules']"),
}


# --- the gate --------------------------------------------------------------------------------------
def test_no_new_vacuous_risk_loop_anywhere_in_the_suite():
    found = all_findings()
    new = [f for f in found if key(f) not in BASELINE]
    assert not new, "loops that assert over a possibly empty iterable (add a non-emptiness " \
        "assertion, or `# vacuity-ok: <reason>` if emptiness is the behaviour):\n  " + \
        "\n  ".join(f"{f[3]}:{f[1]} in {f[0]}: for ... in {f[2]}" for f in new)


def test_the_baseline_only_shrinks():
    live = {key(f) for f in all_findings()}
    dead = sorted(BASELINE - live)
    assert not dead, f"baseline entries that no longer fire -- delete them: {dead}"


def test_the_scan_sees_the_suite():
    files = list(TESTS.glob("test_*.py"))
    assert len(files) > 100, len(files)


# --- the detector detects (fixtures are parsed, never executed) --------------------------------------
def _scan(src: str) -> list:
    tmp = Path(__import__("tempfile").mkdtemp()) / "test_fixture.py"
    tmp.write_text(src)
    return findings_in(tmp)


def test_a_loop_asserting_over_an_unchecked_iterable_is_flagged():
    got = _scan("def test_x():\n    rows = load()\n    for r in rows:\n        assert r.ok\n")
    assert [(f[0], f[2]) for f in got] == [("test_x", "rows")], got
    got = _scan("def test_y():\n    for r in db.query():\n        check('ok', r.ok)\n")
    assert len(got) == 1, got


def test_a_non_emptiness_assertion_or_a_literal_clears_the_loop():
    clean = [
        "def test_a():\n    rows = load()\n    assert rows\n    for r in rows:\n        assert r\n",
        "def test_b():\n    rows = load()\n    assert len(rows) == 3\n    for r in rows:\n"
        "        assert r\n",
        "def test_c():\n    for r in (1, 2):\n        assert r\n",
        "def test_d():\n    for i in range(5):\n        assert i >= 0\n",
        "CASES = ['a', 'b']\ndef test_e():\n    for c in CASES:\n        assert c\n",
        "def test_f():\n    n = 0\n    for r in load():\n        assert r\n        n += 1\n"
        "    assert n > 0\n",
        "def test_g():\n    for k, v in {'a': 1}.items():\n        assert v\n",
        "def test_h():\n    for r in load():  # vacuity-ok: empty is the refusal under test\n"
        "        assert r\n",
    ]
    for src in clean:
        assert _scan(src) == [], src


def test_a_pragma_without_a_reason_does_not_exempt():
    got = _scan("def test_x():\n    for r in load():  # vacuity-ok:\n        assert r\n")
    assert len(got) == 1, "a bare pragma exempted a loop without saying why"


def test_a_constant_table_is_exempt_but_a_computed_view_of_it_is_not():
    assert _scan("def test_a():\n    for s in B.SIZES:\n        assert s\n") == []
    assert len(_scan("def test_b():\n    for s in B.eligible(B.SIZES):\n        assert s\n")) == 1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
