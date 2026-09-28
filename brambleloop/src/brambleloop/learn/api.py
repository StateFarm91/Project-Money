"""Public read-only Learn surface. Review writing is deliberately not a public endpoint."""
from fastapi import APIRouter, HTTPException
from .service import approved_lesson


def router(db):
    routes = APIRouter()

    @routes.get("/learn/{slug}")
    def read_lesson(slug: str, revision: str | None = None):
        lesson = approved_lesson(db, slug)
        if lesson is None or (revision is not None and lesson["revision"] != revision):
            raise HTTPException(404, "No approved lesson for this revision")
        # JSON data, never interpolate lesson prose into HTML or executable markup.
        # Provenance is retained privately; public responses expose teaching fields only.
        spec = lesson["spec"]
        return {"slug": slug, "revision": lesson["revision"],
                "learner_problem": spec["learner_problem"], "topics": spec["topics"],
                "terminology": spec["terminology"], "assumptions": spec["assumptions"],
                "steps": spec["steps"]}

    return routes
