"""Offline, persistent tests for release-specific visual anchor selection."""
from brambleloop.core.db import Database
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.visual import candidate_gates, fidelity, image_production
from brambleloop.visual.image_records import ImageCandidate


FINGERPRINT = "c" * 64


def _anchor(db, cand, release):
    return candidate_gates._anchor_of(db, cand, release, expected_cir_fingerprint=FINGERPRINT)


def _row(db, digest, release, *, slug="item", version="1", run=None, method="autonomous",
         fidelity_override=None):
    with db.session() as session:
        session.add(ImageCandidate(
            sha256=digest, run_key=(image_production.run_key("item", "1", release)
                                    if run is None else run),
            method=method, provenance_kind="ai_generated_autonomous",
            slug=slug, version=version, release=release, listing="same-listing",
            role=image_production.ANCHOR_ROLE, technical_status="PASS", publishable=True,
            checks={"product_truth": {"fidelity": fidelity_override if fidelity_override is not None
                                      else {"status": "PASS", "kind": "anchor", "checker": fidelity.CHECKER,
                                            "checks": [{"check": name, "status": "PASS"}
                                                       for name in ("isolation", "piece_count", "craft_texture")],
                                            "image_sha256": digest,
                                            "slug": slug, "version": version,
                                            "cir_fingerprint": FINGERPRINT}}},
        ))


def test_anchor_selection_binds_full_release_slug_version_and_bytes(tmp_path, monkeypatch):
    from brambleloop.core import artifacts

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "test.db"), scratch=True)
    db.create_all()
    release = "1" * 64
    other_release = "1" * 12 + "2" * 52
    data = b"stored synthetic anchor"
    digest = ArtifactStore().put("test", data, "image/png", db=db).sha256
    cand = {"slug": "item", "version": "1", "listing": "same-listing"}

    # A candidate with the same listing and 12-digit prefix is not the same release.
    _row(db, digest, other_release, slug="item", version="1")
    assert _anchor(db, cand, release) == (None, None)
    # A previously stored abbreviated release cannot prove exact identity either.
    _row(db, digest, release[:12], slug="item", version="1")
    assert _anchor(db, cand, release) == (None, None)
    # Even an exact release is not evidence for a different product or version.
    _row(db, digest, release, slug="another-item", version="1")
    assert _anchor(db, cand, release) == (None, None)
    _row(db, digest, release, slug="item", version="2")
    assert _anchor(db, cand, release) == (None, None)

    _row(db, digest, release)
    anchor, got = _anchor(db, cand, release)
    assert anchor["sha256"] == digest and anchor["status"] == "PASS"
    assert got == data
    # A later high-ranked candidate for a different version must not hide the valid one.
    _row(db, digest, release, slug="item", version="2")
    assert _anchor(db, cand, release)[1] == data
    # Lost/corrupt artifacts are never returned as a validated anchor.
    path = tmp_path / "artifacts" / digest[:2] / digest
    path.write_bytes(b"different bytes")
    assert _anchor(db, cand, release)[1] is None


def test_release_comparison_requires_two_complete_matching_digests():
    release = "a" * 64
    assert fidelity.same_release(release, release)
    assert not fidelity.same_release(release, release[:12])
    assert not fidelity.same_release(release, "a" * 12 + "b" * 52)
    assert not fidelity.same_release(release, "a")
    assert not fidelity.same_release(release, "a" * 12 + "not-a-digest")


def test_pass_label_without_matching_fidelity_evidence_is_held(tmp_path, monkeypatch):
    from sqlalchemy import select
    from brambleloop.core import artifacts

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "evidence.db"), scratch=True)
    db.create_all()
    release = "b" * 64
    data = b"synthetic evidence"
    digest = ArtifactStore().put("test", data, "image/png", db=db).sha256
    _row(db, digest, release, fidelity_override={})
    cand = {"slug": "item", "version": "1", "listing": "same-listing"}
    assert _anchor(db, cand, release) == (None, None)
    valid = {"status": "PASS", "kind": "anchor", "checker": fidelity.CHECKER,
             "checks": [{"check": name, "status": "PASS"}
                        for name in ("isolation", "piece_count", "craft_texture")],
             "image_sha256": digest,
             "slug": "item", "version": "1", "cir_fingerprint": FINGERPRINT}
    for changed in ({"image_sha256": "d" * 64}, {"cir_fingerprint": "e" * 64},
                    {"kind": "lifestyle"}, {"status": "UNKNOWN"}, {"checker": "old"},
                    {"checks": [{"status": "UNKNOWN"}]},
                    {"checks": [{"check": "isolation", "status": "PASS"}]},
                    {"unknown": ["piece_count"]}):
        with db.session() as session:
            row = session.scalar(select(ImageCandidate))
            row.checks = {"product_truth": {"fidelity": {**valid, **changed}}}
        assert _anchor(db, cand, release) == (None, None)
    with db.session() as session:
        row = session.scalar(select(ImageCandidate))
        row.checks = {"product_truth": {"fidelity": valid}}
    assert _anchor(db, cand, release)[1] == data


def test_real_synthetic_fidelity_verdict_can_be_selected(tmp_path, monkeypatch):
    from brambleloop.core import artifacts
    from brambleloop.creative.pattern_refs import release_hash_of
    from test_w4_fidelity import CLOUD, PASSING_BANDS_JUDGE, _cir, flat_lay

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "real-verdict.db"), scratch=True)
    db.create_all()
    cir = _cir(CLOUD)
    release = release_hash_of(cir)
    data = flat_lay(cir)
    measured = fidelity.verify_anchor(data, cir, judge=PASSING_BANDS_JUDGE)
    assert measured["status"] == "PASS"
    digest = ArtifactStore().put("test", data, "image/png", db=db).sha256
    run = image_production.run_key(cir.slug, cir.version, release)
    _row(db, digest, release, slug=cir.slug, version=cir.version, run=run,
         fidelity_override=measured)
    cand = {"slug": cir.slug, "version": cir.version, "listing": "same-listing"}
    anchor, selected = candidate_gates._anchor_of(
        db, cand, release, expected_cir_fingerprint=cir.fingerprint)
    assert anchor["status"] == "PASS" and selected == data


def test_anchor_selection_keeps_production_and_experiment_runs_separate(tmp_path, monkeypatch):
    from brambleloop.core import artifacts

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "runs.db"), scratch=True)
    db.create_all()
    release = "a" * 64
    run = image_production.run_key("item", "1", release)
    exp_a, exp_b = run + "#experiment-a", run + "#experiment-b"
    data = b"experiment-only synthetic anchor"
    digest = ArtifactStore().put("test", data, "image/png", db=db).sha256
    _row(db, digest, release, run=exp_a)
    base = {"slug": "item", "version": "1", "listing": "same-listing"}
    assert _anchor(db, base, release) == (None, None)
    assert _anchor(db, {**base, "run_key": exp_b}, release) == (None, None)
    assert _anchor(db, {**base, "run_key": exp_a}, release)[1] == data
    assert _anchor(db, {**base, "run_key": "unrelated"}, release) == (None, None)
    # Unscoped owner submissions remain available to production, never experiments.
    _row(db, digest, release, run="", method="owner_submitted")
    assert _anchor(db, base, release)[1] == data
    assert _anchor(db, {**base, "run_key": exp_b}, release) == (None, None)


def test_reverify_uses_persisted_candidate_run_not_another_run(tmp_path, monkeypatch):
    from brambleloop.core import artifacts

    monkeypatch.setattr(artifacts, "DEFAULT_DIR", str(tmp_path / "artifacts"))
    db = Database("sqlite:///" + str(tmp_path / "reverify.db"), scratch=True)
    db.create_all()
    release = "a" * 64
    run = image_production.run_key("item", "1", release)
    data = b"synthetic image"
    digest = ArtifactStore().put("test", data, "image/png", db=db).sha256
    _row(db, digest, release, run=run + "#a")
    with db.session() as session:
        row = ImageCandidate(sha256=digest, run_key=run + "#b", method="autonomous",
                             provenance_kind="ai_generated_autonomous", slug="item",
                             version="1", release=release, listing="same-listing",
                             role="lifestyle", technical_status="UNKNOWN")
        session.add(row)
        session.flush()
        candidate_id = row.id

    def evaluate(db_, cand, **_kwargs):
        selected, _ = _anchor(db_, cand, release)
        return {"checks": {}, "technical_status": "UNKNOWN" if selected is None else "PASS",
                "publishable": False}

    monkeypatch.setattr(candidate_gates, "evaluate", evaluate)
    result = image_production.reverify(db, candidate_id, judges=None)
    assert result["reverified"] and result["technical_status"] == "UNKNOWN"


def test_lifestyle_handler_does_not_bind_a_different_full_release():
    from brambleloop.visual.render_verification import authoritative_cir

    cir = authoritative_cir("cloudline-baby-blanket")
    release = "a" * 64
    other = "a" * 12 + "b" * 52
    result = fidelity.verify_lifestyle(
        b"not-an-image", cir, release_hash=release,
        anchor={"status": "PASS", "release_hash": other},
    )
    anchor = next(check for check in result["checks"] if check["check"] == "anchor")
    assert anchor["status"] == "UNKNOWN"
