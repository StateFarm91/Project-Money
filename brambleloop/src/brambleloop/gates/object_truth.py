"""Conservative object-name checks against the computed digital twin."""
import re

from ..products.text_fold import fold


def dishcloth_dimension_findings(cir, twin, *, texts=()) -> list[str]:
    """Refuse a named cloth whose computed shape cannot support that name.

    This design band is a guardrail, not a physical sample or a heat-safety claim.
    """
    for value in (getattr(cir, "title", ""), *texts):
        # Collapse punctuation and invisible characters between parts of the object name.
        text = re.sub(r"[^a-z0-9]+", " ", fold(value or ""))
        if re.search(r"\b(?:dish|wash|face)\s*cloths?\b", text):
            width, height = twin.width_cm, twin.height_cm
            if (len(cir.components) != 1 or width is None or height is None
                    or not (15 <= width <= 35 and 15 <= height <= 35)
                    or max(width, height) > 1.5 * min(width, height)):
                return ["The named dishcloth must be a single approximately square cloth "
                        "with computed sides between 15 and 35 cm."]
    return []
