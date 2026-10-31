"""Policy readings from the owner's phone (W4-LAUNCHFIX, Command Center `#/policy`).

Before this, the only intake for a person's reading of an Etsy policy page was
`POST /api/policy/snapshot` with the operator token -- unusable from a phone, and tied to a
token the owner is rotating. This is the same intake behind the owner's Command Center session
(passphrase + TOTP, CSRF, nonce) with a fresh step-up, because a reading is evidence that opens
gates. It records through the SAME path:

* `gates.platform_policy.record_page_reading` (digest only, `page` basis, the stale incident
  closed on a current reading, and -- since E3 -- a first page reading is the baseline while a
  later reading whose text differs is a material change that blocks until reviewed on the
  existing `policy_review` card in `#/approvals`);
* the same `policy.page_reading_recorded` audit row, with the same fields, that the
  `rendered_pages` gate reads as provenance.

`read_by` is the authenticated owner session, never a value from the body. The text is never
stored, logged or returned: only its SHA-256. The questions are guidance from
ETSY_POLICY_READINGS_PACKET.md (W4-LAUNCH1); nothing here pre-fills an answer.

What the owner personally confirms is recorded verbatim (`CONFIRMATIONS`), in a second audit
row (`policy.page_reading_attested`) beside the intake's row, with the session and where the
text came from. Two ways in, and neither is weaker than the operator intake:

* the five etsy.com/legal pages -- a person must read them (bot protection; software may not
  fetch them), so the owner pastes the page text (Select all -> Copy -> Paste) and confirms
  "I read this page myself";
* the two Help Center articles -- the server fetches the article text itself through Etsy's
  public Help Center article API (`gates.policy_reader`, the same reader production uses),
  and the owner confirms they reviewed that text and wrote the answers. The digest is of
  Etsy's own text, which is stronger evidence than a paste.

A replay of a request is refused by the Command Center gate (nonce + timestamp + CSRF, bound to
the session); a second identical reading of the same source by the same owner on the same day
is refused here as a duplicate rather than recorded twice.
"""
from __future__ import annotations

from datetime import date

#: Per source: title and the questions the reading should answer (packet, 2026-10-27). Guidance
#: only -- the owner writes the answers in `summary`; nothing is pre-filled.
SOURCES: dict[str, dict] = {
    "seller_policy": {"title": "Etsy Seller Policy", "questions": [
        "Does it still require disclosing in the listing when an item is created with the use "
        "of AI? What wording or placement does it ask for?",
        "Does it still require listings to accurately represent the item?",
        "Digital downloads: still not returnable or cancellable by the buyer, and does "
        "Purchase Protection cover files not as described or never delivered?",
        "Are off-platform communication and sharing contact or payment details still "
        "prohibited, and unsolicited promotion treated as spam?",
        "Any new rule about digital patterns, AI-assisted designs or rendered (non-photograph) "
        "listing images?",
        "The page's 'last updated' date (put it in Version)."]},
    "creativity_standards": {"title": "Etsy Creativity Standards", "questions": [
        "If the link redirects, note the final URL.",
        "Is 'designed by a seller', including original designs sold as a digital download, "
        "still permitted? Does it still cover seller-prompted AI work?",
        "Is AI use still allowed where the seller plays a clear creative role and discloses it "
        "in the description? Has the disclosure wording or placement changed?",
        "Are packages of AI prompts still prohibited? Any new prohibition that could reach an "
        "AI-assisted crochet pattern (instructions, chart, PDF)?",
        "Do reselling and misrepresenting another maker's design remain removal reasons?",
        "The page's 'last updated' date (Version)."]},
    "listing_image_rules": {"title": "Requirements and Best Practices for Images", "questions": [
        "Does Etsy permit a digital pattern listing whose images, including the FIRST image, "
        "are clearly labelled digital renderings rather than photographs? Record exactly what "
        "the page says about renderings, mockups, illustrations and AI-generated images, and "
        "whether it distinguishes a digital download from a physical item.",
        "Must AI-generated or AI-assisted images be disclosed? Where?",
        "Technical rules: images per listing, formats, minimum and recommended size, "
        "thumbnail crop, file-size limit, first-image rules.",
        "What changed in the 2026-10-22 edit, if the page says?",
        "If the article links the legal listing-image page, read it too and answer here.",
        "The page's 'last updated' date (Version)."]},
    "advertising_rules": {"title": "Etsy Advertising and Promotion policy", "questions": [
        "Offsite Ads: current fee rates, per-order cap, attribution window, and when "
        "participation is optional or mandatory.",
        "Etsy Ads (onsite): any minimum daily budget; any rule that ads may not claim what the "
        "listing does not. Quote the page.",
        "Any rule about advertising AI-assisted or digital items.",
        "The page's 'last updated' date (Version)."]},
    "shilling_and_reviews": {"title": "Prohibited items and services (shilling / reviews)",
                             "questions": [
        "Is it still prohibited to have friends or family buy and review, or to compensate "
        "anyone (free items, samples, cash) for a review?",
        "Exactly when is a friend's or relative's review allowed?",
        "Does anything restrict pattern testers who receive a free pattern or a test fee? May "
        "a tester review at all?",
        "The page's 'last updated' date (Version)."]},
    "children_and_baby": {"title": "Children and Baby Products policy", "questions": [
        "Does Etsy still prohibit the patterns, designs or instructions for making prohibited "
        "children's items, not only the items?",
        "The current prohibited and restricted children's items. Do any cover a crochet baby "
        "blanket, a nursery basket or hanging ornaments? Note infant sleep accessories, crib "
        "blankets, small parts or choking hazards, drawstrings or cords.",
        "Current sleepwear and loungewear rules (sizes, flame resistance).",
        "Effective / last-updated date (Version)."]},
    "search_guidance": {"title": "How to Use Tags to Get Found in Search", "questions": [
        "Title character limit.",
        "Maximum tag count and characters per tag.",
        "May a tag start with a symbol?",
        "Do attributes act like tags?",
        "Does the Search Visibility page still exist?",
        "The page's 'last updated' date (Version)."]},
}

NEVER_READ, FRESH, STALE, CHANGED = "never_read", "fresh", "stale", "changed_unreviewed"
SUMMARY_MAX = 8000
HISTORY_MAX = 10
STEP_UP_ACTION = "policy.reading"
ATTESTED_AUDIT = "policy.page_reading_attested"

PASTE, FETCHED = "pasted_by_owner", "help_center_api"
#: The words the owner confirms, verbatim, per way in. Anything else is refused.
CONFIRMATIONS = {
    PASTE: "I read this page myself and pasted its full text",
    FETCHED: "I reviewed the article text the system fetched and wrote these answers",
}

#: `fetch(url) -> dict` for the Help Center article API; None uses `policy_reader._fetch`.
#: Injectable so tests never reach the network.
fetcher = None


class ReadingRefused(ValueError):
    """The reading was not recorded; the message says why (owner-facing)."""


class DuplicateReading(ReadingRefused):
    """The same reading by the same owner on the same day is already recorded."""


def _help_center() -> dict[str, str]:
    from ...gates import policy_reader

    return policy_reader.help_center_sources()


def _history(rows, attested: dict[int, dict]) -> list[dict]:
    out = []
    first_page = True
    for r in rows:
        d = r.detail or {}
        out.append({"snapshot_id": r.id, "checked_on": r.checked_on,
                    "read_by": d.get("read_by"), "basis": d.get("basis"),
                    "version": d.get("version") or r.version,
                    "digest": (r.digest or "")[:16],
                    "kind": ("baseline" if first_page and not r.material_change
                             else "change" if r.material_change else "same_as_before"),
                    "reviewed_at": d.get("reviewed_at"), "reviewed_by": d.get("reviewed_by"),
                    "attested": attested.get(r.id)})
        first_page = False
    return out[-HISTORY_MAX:][::-1]


def status(db, *, today: date | None = None) -> dict:
    """Every watched source, its URL, its state from a person's page readings, the history of
    those readings and the questions. Reads only."""
    from sqlalchemy import select

    from ...core.models import AuditLog, PolicySnapshot
    from ...gates import platform_policy as pp

    today = today or date.today()
    changed = {c["source"]: c for c in pp.unreviewed_changes(db)}
    hc = _help_center()
    with db.session() as s:
        rows = list(s.scalars(select(PolicySnapshot).order_by(PolicySnapshot.id)))
        attested = {}
        for a in s.scalars(select(AuditLog).where(AuditLog.action == ATTESTED_AUDIT)):
            d = a.detail or {}
            if isinstance(d.get("snapshot_id"), int):
                attested[d["snapshot_id"]] = {"confirmed": d.get("confirmed"),
                                              "text_source": d.get("text_source"),
                                              "at": a.at.isoformat() if a.at else None}
    page_rows: dict[str, list] = {}
    newest_any: dict[str, PolicySnapshot] = {}
    for r in rows:
        newest_any[r.source] = r
        if (r.detail or {}).get("basis") == pp.PAGE_BASIS:
            page_rows.setdefault(r.source, []).append(r)
    out = []
    for key, (url, affects) in pp.POLICY_SOURCES.items():
        meta = SOURCES.get(key, {"title": key, "questions": []})
        mine = page_rows.get(key) or []
        row = mine[-1] if mine else None
        way = FETCHED if key in hc else PASTE
        entry = {"source": key, "title": meta["title"], "url": url, "affects": list(affects),
                 "questions": list(meta["questions"]), "checked_on": None, "read_by": None,
                 "version": None, "age_days": None, "way_in": way,
                 "confirm_with": CONFIRMATIONS[way],
                 "history": _history(mine, attested)}
        if row is not None:
            try:
                age = (today - date.fromisoformat(row.checked_on)).days
            except (TypeError, ValueError):
                age = None
            entry.update(checked_on=row.checked_on, read_by=(row.detail or {}).get("read_by"),
                         version=pp.version_of(row), age_days=age,
                         state=FRESH if age is not None and 0 <= age <= pp.MAX_AGE_DAYS
                         else STALE)
            if entry["state"] == STALE:
                entry["note"] = (f"expired: read {age} days ago; a reading is current for "
                                 f"{pp.MAX_AGE_DAYS} days" if age is not None and age >= 0
                                 else "the recorded date is unreadable or in the future")
        else:
            other = newest_any.get(key)
            entry["state"] = NEVER_READ
            entry["note"] = ("missing: no person's page reading is recorded" + (
                f"; the newest reading on file is a {(other.detail or {}).get('basis') or 'seed'}"
                f" reading of {other.checked_on}" if other is not None else ""))
        if key in changed:
            entry["state"] = CHANGED
            entry["review"] = {"card": f"policy:{key}", "where": "#/approvals",
                               "changed_on": changed[key]["checked_on"]}
        out.append(entry)
    return {"sources": out, "max_age_days": pp.MAX_AGE_DAYS, "version_max": pp.VERSION_MAX,
            "summary_max": SUMMARY_MAX, "states": [NEVER_READ, FRESH, STALE, CHANGED],
            "stores": "the SHA-256 of the page text only; the text is never stored",
            "baseline_rule": ("your first reading of a page is its baseline; a later reading "
                              "whose text differs is a change and blocks publishing until you "
                              "review it in Approvals"),
            "generated_at": today.isoformat()}


def _fetch_article(source: str) -> str:
    """The article's text from Etsy's public Help Center article API, or a refusal."""
    from ...gates import policy_reader as pr

    article_id = _help_center().get(source)
    if not article_id:
        raise ReadingRefused(f"{source} is not a Help Center article; paste the page text")
    try:
        payload = (fetcher or pr._fetch)(pr.HELP_API.format(id=article_id))
    except Exception as exc:  # noqa: BLE001 - an unreadable article is not a reading
        raise ReadingRefused(f"the article could not be fetched ({type(exc).__name__}); "
                             f"nothing was recorded") from None
    article = (payload or {}).get("article") or {}
    if str(article.get("id")) != str(article_id) or article.get("draft"):
        raise ReadingRefused("the article API did not return the published article")
    text = pr._text_of(article.get("body") or "")
    if len(text) < pr.MIN_TEXT_CHARS:
        raise ReadingRefused("the fetched article is too short to be the policy text")
    return text


def record(db, body: dict, *, actor: str, today: date | None = None) -> dict:
    """Record one reading through `record_page_reading`, write the intake's audit row and the
    owner's attestation row. Refuses incomplete, unconfirmed or duplicate readings."""
    from sqlalchemy import select

    from ...agents.registry import Registry
    from ...core.models import PolicySnapshot
    from ...gates import platform_policy as pp

    body = body if isinstance(body, dict) else {}
    source = str(body.get("source") or "").strip()
    if source not in pp.POLICY_SOURCES:
        raise ReadingRefused(f"unknown policy source {source!r}")
    if not actor or not str(actor).strip():
        raise ReadingRefused("no authenticated owner to name as the reader")
    summary = str(body.get("summary") or "").strip()
    if not summary:
        raise ReadingRefused("write your answers to the questions: a reading without them is "
                             "incomplete")
    if len(summary) > SUMMARY_MAX:
        raise ReadingRefused(f"summary is {len(summary)} characters; at most {SUMMARY_MAX}")
    way = FETCHED if body.get("fetch_article") is True else PASTE
    if str(body.get("confirm") or "").strip() != CONFIRMATIONS[way]:
        raise ReadingRefused(f"confirm must be exactly {CONFIRMATIONS[way]!r}")
    if way == FETCHED:
        if str(body.get("text") or "").strip():
            raise ReadingRefused("send either pasted text or fetch_article, not both")
        text = _fetch_article(source)
    else:
        text = str(body.get("text") or "")
    checked_on = str(body.get("checked_on") or "") or (today or date.today()).isoformat()
    digest = pp.digest_of(text)
    reader = str(actor).strip()
    with db.session() as s:
        same = s.scalars(select(PolicySnapshot).where(
            PolicySnapshot.source == source, PolicySnapshot.digest == digest,
            PolicySnapshot.checked_on == checked_on).order_by(PolicySnapshot.id.desc())).first()
        if same is not None and (same.detail or {}).get("basis") == pp.PAGE_BASIS and (
                same.detail or {}).get("read_by") == reader:
            raise DuplicateReading(f"this reading of {source} is already recorded (snapshot "
                                   f"{same.id}); nothing was added")
    try:
        result = pp.record_page_reading(
            db, source=source, text=text, version=str(body.get("version") or ""),
            summary=summary, read_by=reader, checked_on=checked_on, today=today,
            owner_attested=True)
    except pp.PolicyRefused as exc:
        raise ReadingRefused(str(exc)[:300]) from None
    reg = Registry(db)
    # Exactly the row POST /api/policy/snapshot writes (app.main.api_policy_snapshot): the
    # digest and the outcome, never the text.
    reg.audit("orchestrator", pp.PAGE_READING_AUDIT, detail={
        k: result[k] for k in ("id", "source", "digest", "material_change", "checked_on",
                               "current", "incidents_resolved", "basis")})
    reg.audit(reader[:64], ATTESTED_AUDIT, artifact=f"policy:{source}", detail={
        "snapshot_id": result["id"], "source": source, "digest": result["digest"],
        "confirmed": CONFIRMATIONS[way], "text_source": way, "session": reader,
        "kind": ("baseline" if result.get("first_reading")
                 else "change" if result["material_change"] else "same_as_before")})
    return {**result, "text_source": way,
            "kind": ("baseline" if result.get("first_reading")
                     else "change" if result["material_change"] else "same_as_before")}
