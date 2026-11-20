"""Launch planning (Master Plan section 5).

The flagship timeline in section 5 counts backwards from a launch: T-90 thesis, T-75 concept,
T-60 CIR, T-45 QA, T-30 assets, T-21 SEO indexing, T-14 teasers, launch, then post-launch.

The thing that makes it a plan rather than a calendar is what it counts back *from*. Not the
holiday -- the day the buying window opens, which for a sixty-hour blanket is three months
earlier. Anchoring on the holiday produces a launch that is technically on time and
commercially useless.

When a window is already open, the plan says so and compresses rather than pretending there
are ninety days. A plan that quietly invents time is worse than no plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# (days before launch, stage, what must be true by then)
TIMELINE: list[tuple[int, str, str]] = [
    (90, "market thesis", "demand evidence, competitor read and the price band are recorded"),
    (75, "concept", "concept selected from the scored pool and the originality check passed"),
    (60, "CIR", "the pattern exists as a compiled CIR, not a sketch"),
    (45, "QA", "reverse compilation and adversarial QA pass; physical test if Class B/C"),
    (30, "assets", "PDF, charts and listing imagery are final and Asset Truth has cleared"),
    (21, "SEO", "listing published to indexing; Etsy needs weeks to rank a new listing"),
    (14, "teasers", "email, Pinterest and social teasers are live"),
    (0, "launch", "listing is live and the buying window is open"),
    (-14, "amplify", "tutorial content, cross-sell and review follow-up are running"),
    (-30, "optimise", "first performance read: impressions, CTR, conversion, refunds"),
]


@dataclass
class LaunchStep:
    stage: str
    on: date
    requirement: str
    late: bool = False

    def to_dict(self) -> dict:
        return {"stage": self.stage, "on": self.on.isoformat(),
                "requirement": self.requirement, "late": self.late}


@dataclass
class LaunchPlan:
    slug: str
    launch_on: date
    window_opens: date | None
    window_closes: date | None
    steps: list[LaunchStep] = field(default_factory=list)
    compressed: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"slug": self.slug, "launch_on": self.launch_on.isoformat(),
                "window_opens": self.window_opens.isoformat() if self.window_opens else None,
                "window_closes": (self.window_closes.isoformat()
                                  if self.window_closes else None),
                "compressed": self.compressed, "warnings": list(self.warnings),
                "steps": [s.to_dict() for s in self.steps]}


def plan_launch(slug: str, *, today: date, window: tuple[date, date] | None,
                build_lead_days: int) -> LaunchPlan:
    """Build the timeline for one product.

    `window` is the buying window from the radar, or None for an evergreen product. Evergreen
    products launch as soon as they are ready: there is nothing to be early or late for, and
    waiting only costs indexing time.
    """
    warnings: list[str] = []
    ready = today + timedelta(days=build_lead_days)

    if window is None:
        launch_on = ready
        opens = closes = None
    else:
        opens, closes = window
        # Launch at the window's opening, or as soon as we can if it has already opened.
        launch_on = max(ready, opens)
        if launch_on > closes:
            warnings.append(
                f"the buying window closed on {closes.isoformat()} and we cannot be ready "
                f"before {ready.isoformat()}; this is next year's product, not this year's")
            launch_on = closes
        elif opens < today:
            warnings.append(
                f"the window opened on {opens.isoformat()}, so the full 90-day timeline does "
                f"not exist. Stages before today are compressed, not skipped -- each one "
                f"still has to happen, just faster.")

    steps: list[LaunchStep] = []
    for offset, stage, requirement in TIMELINE:
        on = launch_on - timedelta(days=offset)
        steps.append(LaunchStep(stage=stage, on=on, requirement=requirement,
                                late=on < today))

    compressed = any(s.late and s.stage != "launch" for s in steps)
    if compressed and not warnings:
        warnings.append("some stages are already past their ideal date; they are compressed "
                        "into the time that actually remains")

    # Etsy needs real time to index a new listing; launching the same week it is published
    # means launching into no search traffic.
    seo = next(s for s in steps if s.stage == "SEO")
    if (launch_on - seo.on).days < 14:  # pragma: no cover - fixed by the timeline above
        warnings.append("fewer than 14 days between publication and launch: the listing will "
                        "not be indexed in time to carry search traffic")

    return LaunchPlan(slug=slug, launch_on=launch_on, window_opens=opens,
                      window_closes=closes, steps=steps, compressed=compressed,
                      warnings=warnings)
