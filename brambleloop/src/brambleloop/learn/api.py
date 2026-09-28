"""Authenticated Learn workflow; public read only serves exact approved revisions.

Reviewer credentials are distinct from the operator/editor. Review is supplied human
attestation, not an automatically measured fact; missing reviewer configuration is closed.
"""
import hmac
import os
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select
from ..core import opsauth
from .models import LearnGap, Lesson
from .service import approved_lesson, save_lesson, review_lesson

EDITOR = "learn-operator-editor"


def _editor(authorization):
    try:
        opsauth.check(authorization)
    except opsauth.OpsAuthUnavailable:
        raise HTTPException(503, "Learn editor credential unavailable")
    except opsauth.OpsAuthRefused:
        raise HTTPException(401, "Learn editor credential refused")


def _reviewer(authorization):
    expected = os.environ.get("BRAMBLELOOP_LEARN_REVIEW_TOKEN", "").strip()
    identity = os.environ.get("BRAMBLELOOP_LEARN_REVIEWER_ID", "").strip()
    editor_token = os.environ.get(opsauth.TOKEN_VAR, "").strip()
    if (len(expected) < opsauth.MIN_TOKEN_LENGTH or not identity or identity == EDITOR
            or hmac.compare_digest(expected, editor_token)):
        raise HTTPException(503, "Distinct Learn reviewer credential and identity required")
    supplied = (authorization or "").strip()
    if supplied.lower().startswith("bearer "):
        supplied = supplied[7:].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Learn reviewer credential refused")
    return identity


def router(db):
    routes = APIRouter()

    @routes.get("/api/learn/queue")
    def queue(authorization: str | None = Header(default=None)):
        _editor(authorization)
        with db.session() as s:
            return [{"topic": g.topic, "state": g.state, "owner": g.owner,
                     "evidence": g.evidence} for g in s.scalars(select(LearnGap)).all()]

    @routes.put("/api/learn/lessons/{slug}")
    def draft(slug: str, spec: dict, authorization: str | None = Header(default=None)):
        _editor(authorization)
        spec = {**spec, "author": EDITOR}
        with db.session() as s:
            requested = spec.get("topics")
            if not isinstance(requested, list) or not requested or any(
                    not isinstance(t, str) or s.get(LearnGap, t) is None for t in requested):
                raise HTTPException(422, "Lesson needs a source-backed content gap")
        try:
            revision = save_lesson(db, slug, spec)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc))
        return {"slug": slug, "revision": revision, "state": "DRAFT"}

    @routes.get("/api/learn/lessons/{slug}")
    def review_draft(slug: str, authorization: str | None = Header(default=None)):
        _reviewer(authorization)
        with db.session() as s:
            row = s.get(Lesson, slug)
            if row is None:
                raise HTTPException(404, "Lesson not found")
            return {"slug": row.slug, "revision": row.revision, "spec": row.spec}

    @routes.post("/api/learn/lessons/{slug}/review")
    def review(slug: str, record: dict, authorization: str | None = Header(default=None)):
        identity = _reviewer(authorization)
        # Store the supplied evidence description hash, not an invented independent test run.
        if record.get("evidence_class") != "human_attestation" or not record.get("evidence_ref"):
            raise HTTPException(422, "Explicit human_attestation and evidence_ref required")
        try:
            review_lesson(db, slug, record["revision"], identity,
                          record["verdicts"], record["evidence_ref"])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc))
        lesson = approved_lesson(db, slug)
        return {"slug": slug, "state": "APPROVED" if lesson else "WITHHELD",
                "evidence_class": "human_attestation", "automated_truth_proof": False}

    @routes.get("/learn/{slug}")
    def read_lesson(slug: str, revision: str | None = None):
        lesson = approved_lesson(db, slug)
        if lesson is None or (revision is not None and lesson["revision"] != revision):
            raise HTTPException(404, "No approved lesson for this revision")
        spec = lesson["spec"]
        return {"slug": slug, "revision": lesson["revision"],
                "learner_problem": spec["learner_problem"], "topics": spec["topics"],
                "terminology": spec["terminology"], "assumptions": spec["assumptions"],
                "steps": spec["steps"]}

    return routes
