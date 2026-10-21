"""`/api/cc/*` -- the Owner Command Center JSON API (contract: COMMAND_CENTER_API.md).

Authentication, CSRF, replay protection and rate limits are enforced *before* any handler runs,
by `security.operator_gate` -> `auth.gate` (default-deny for the whole prefix). Handlers here
add the per-action step-up check and turn authority refusals into audited 409s.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import approvals, ask as ask_mod, auth, emergency, notifications, providers, tabs
from . import company as company_mod
from . import private_context


def make_router(db) -> APIRouter:
    router = APIRouter(prefix="/api/cc")

    def actor(request) -> str:
        return f"owner:cc:{auth.current_public_id(request)}"

    async def body_of(request) -> dict:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "body must be JSON") from None
        if not isinstance(body, dict):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "body must be a JSON object")
        return body

    def ok(data: dict, status: int = 200) -> JSONResponse:
        return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})

    # ---- auth ------------------------------------------------------------------------

    @router.get("/auth/status")
    def auth_status(request: Request):
        row, why, token = auth.session_from_request(db, request)
        base = {"authenticated": False, "login_configured": auth.login_configured(),
                "totp_required": auth.totp_required(),
                # Re-audit L-1: plainly whether a second factor is configured (never the
                # secret), so the owner can see a passphrase-only production at a glance.
                "second_factor": auth.second_factor_status(),
                "csrf_token": None, "session": None,
                "stepup_valid_until": None,
                "stepup_window_seconds": int(auth.STEPUP_WINDOW.total_seconds()),
                "server_time": int(__import__("time").time())}
        if why is None:
            view = auth.session_view(db, row.public_id, current=row.public_id)
            until = auth.aware(row.stepup_until)
            base.update({"authenticated": True, "csrf_token": auth.csrf_for(token),
                         "session": view,
                         "stepup_valid_until": (until.isoformat() if until and
                                                until > auth._now() else None)})
        return ok(base)

    @router.post("/auth/login")
    async def login(request: Request):
        if not auth.login_configured():
            raise auth.refuse(db, request, 503, "LOGIN_NOT_CONFIGURED",
                              f"owner login is not configured ({auth.PASSPHRASE_VAR} unset)",
                              kind="login")
        if "application/json" not in (request.headers.get("content-type") or ""):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "JSON body required",
                              kind="login")
        body = await body_of(request)
        # Lockout resistance (audit ddf9c6e M1): a browser that signed in before is limited per
        # device, a valid operator-minted recovery code is not limited; everyone else per
        # client address, then globally. Only wrong credentials count toward any limit.
        device_id = await run_in_threadpool(auth.trusted_device, db, request)
        recovery = False
        if device_id is None and body.get("recovery_code") is not None:
            recovery = await run_in_threadpool(auth.consume_recovery_code, db,
                                               body.get("recovery_code"))
        # Re-audit L-2: the attempt is counted (reserved) atomically *before* the slow
        # PBKDF2 check, so a concurrent burst cannot all pass the limit; it is withdrawn on
        # success and becomes the wrong-credential record on failure.
        try:
            attempt_id, limited = await run_in_threadpool(
                lambda: auth.reserve_login_attempt(db, request, device_id=device_id,
                                                   recovery=recovery))
        except Exception:  # noqa: BLE001 - an uncountable attempt is not verified
            raise auth.refuse(db, request, 503, "AUTH_STORE_UNAVAILABLE",
                              "login attempts cannot be counted right now; try again",
                              kind="login") from None
        if limited:
            message = "too many failed logins; wait 15 minutes"
            if limited == "global":
                message += (" (a browser that has signed in before is not affected; the "
                            "operator can mint a one-time recovery code)")
            raise auth.refuse(db, request, 429, "RATE_LIMITED", message, kind="login",
                              session_public_id=device_id or "", detail={"limit": limited})
        try:
            good = await run_in_threadpool(auth.verify_owner, body.get("passphrase"),
                                           body.get("totp"), db=db)
        except Exception:  # noqa: BLE001 - fail closed; the reservation stays counted
            good = False
        if not good:
            message = "passphrase or code not accepted"
            await run_in_threadpool(
                lambda: auth.settle_login_attempt(
                    db, attempt_id, ok=False, message=message,
                    detail={"recovery_code": recovery} if recovery else None))
            # The reservation row is the audit record of this failure (not a second row).
            raise auth.CCRefused(401, message, auth.FAILED_LOGIN_CODE)
        await run_in_threadpool(auth.settle_login_attempt, db, attempt_id, ok=True)
        token, view = await run_in_threadpool(auth.create_session, db, request,
                                              device_label=str(body.get("device_label") or ""))
        auth.record(db, kind="login", outcome="ok", request=request,
                    session_public_id=view["session_id"],
                    detail={"trusted_device": bool(device_id), "recovery_code": recovery})
        resp = ok({"authenticated": True, "csrf_token": auth.csrf_for(token), "session": view,
                   "stepup_valid_until": view["stepup_valid_until"]})
        resp.set_cookie(auth.COOKIE, token, max_age=int(auth.SESSION_TTL.total_seconds()),
                        path="/", secure=True, httponly=True, samesite="strict")
        if device_id is None:
            dev_token, _dev_id = await run_in_threadpool(auth.issue_device, db)
            resp.set_cookie(auth.DEVICE_COOKIE, dev_token,
                            max_age=int(auth.DEVICE_TTL.total_seconds()), path="/",
                            secure=True, httponly=True, samesite="strict")
        return resp

    @router.post("/auth/logout")
    def logout(request: Request):
        pid = auth.current_public_id(request)
        auth.revoke_session(db, pid, "logged out")
        private_context.on_session_revoked(db, pid, "logged_out")
        auth.record(db, kind="logout", outcome="ok", request=request, session_public_id=pid)
        resp = ok({"logged_out": True})
        resp.delete_cookie(auth.COOKIE, path="/", secure=True, httponly=True,
                           samesite="strict")
        return resp

    @router.post("/auth/step-up")
    async def step_up(request: Request):
        body = await body_of(request)
        pid = auth.current_public_id(request)
        good = await run_in_threadpool(auth.verify_owner, body.get("passphrase"),
                                       body.get("totp"), db=db)
        if not good:
            revoked = auth.failed_stepup(db, pid)
            raise auth.refuse(db, request, 401, "BAD_CREDENTIALS",
                              "step-up not accepted" + ("; session revoked" if revoked else ""),
                              kind="stepup", session_public_id=pid)
        until = auth.grant_stepup(db, pid)
        auth.record(db, kind="stepup", outcome="ok", request=request, session_public_id=pid)
        return ok({"stepup_valid_until": until})

    # ---- tabs ------------------------------------------------------------------------

    @router.get("/home")
    def home(request: Request):
        return ok(tabs.home(db))

    @router.post("/home/seen")
    def home_seen(request: Request):
        return ok(tabs.mark_seen(db))

    @router.get("/brief/morning")
    def morning(request: Request, hours: float = 12):
        return ok(tabs.morning_brief(db, hours))

    @router.get("/approvals")
    def approvals_list(request: Request):
        box = approvals.inbox(db)
        return ok({"tab": "APPROVALS", "generated_at": tabs.now_iso(), **box})

    @router.get("/approvals/{card_id}")
    def approvals_one(card_id: str, request: Request):
        c = approvals.card(db, card_id)
        if c is None:
            return ok({"error": f"no open approval {card_id!r}", "code": "NOT_FOUND"}, 404)
        return ok(c)

    @router.get("/store")
    def store(request: Request):
        return ok(tabs.store(db))

    @router.get("/customers")
    def customers(request: Request):
        """W4-CCFM1 (F-619): customer aggregates only; content stays at /api/support."""
        return ok(tabs.customers(db))

    # ---- W4-STOREFRONT: owner Store area (read-only; owner session via the /api/cc/ gate) --

    @router.get("/store/catalogue")
    def store_catalogue(request: Request):
        from ...store_foundation import owner_store

        return ok(owner_store.catalogue(db))

    @router.get("/store/image/{build}")
    def store_image(build: str, request: Request):
        """The verified listing rendering of one collection product. A frame that does not
        verify is 404 -- never the unverified asset, never a substitute."""
        from fastapi.responses import Response

        from ...store_foundation import owner_store

        png = owner_store.image_png(str(build)[:60])
        if png is None:
            return ok({"error": "no verified image for this product", "code": "NOT_FOUND"}, 404)
        return Response(png, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "X-Image-Status": "VERIFIED; disclosed rendering, not a photograph"})

    @router.get("/store/pdf/{slug}")
    def store_pdf(slug: str, request: Request, terms: str = "US"):
        """The pattern PDF for one collection product, rendered now from its CIR (owner
        review copy; the sold file is the released, hashed PDF)."""
        from fastapi.responses import Response

        from ...store_foundation import owner_store

        try:
            out = owner_store.pattern_pdf(str(slug)[:80], str(terms)[:4])
        except Exception as exc:  # noqa: BLE001 - a refusal is reported, not a crash
            return ok({"error": f"pattern PDF refused: {type(exc).__name__}",
                       "code": "PDF_REFUSED"}, 409)
        if out is None:
            return ok({"error": "no such product or terminology", "code": "NOT_FOUND"}, 404)
        data, name = out
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "._-")[:80] or "pattern.pdf"
        return Response(data, media_type="application/pdf", headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "Content-Disposition": f'inline; filename="{safe}"',
            "X-Content-Type-Options": "nosniff"})

    @router.get("/money")
    def money(request: Request, period: str = "", window: str = ""):
        # F-914: a period (PWA `period`, or `window`) reaches the accounting summary.
        try:
            w = tabs.money_window((window or period)[:20])
        except ValueError as exc:
            return ok({"error": str(exc), "code": "BAD_PERIOD"}, 400)
        return ok(tabs.money(db, w))

    @router.get("/money/drill")
    def money_drill(request: Request, metric: str = "", period: str = "", window: str = ""):
        try:
            w = tabs.money_window((window or period)[:20])
        except ValueError as exc:
            return ok({"error": str(exc), "code": "BAD_PERIOD"}, 400)
        return ok(tabs.money_drill(db, metric, w))

    @router.get("/operations")
    def operations(request: Request):
        return ok(tabs.operations(db))

    @router.get("/truth")
    def truth(request: Request):
        # wave-3 K7: the ops-truth provider (owner inventory, tester roster, controls, ...).
        return ok(providers.call("ops_truth", db))

    @router.get("/drill")
    def drill(request: Request, provider: str = "", index: int = 0):
        # F-623 / F-665 (K7): any provider item -> source, timestamp, transformation,
        # confidence, reconciliation state and safe external ids.
        from ...ops import truth as ops_truth

        return ok(ops_truth.drill(db, provider, index))

    @router.get("/operations/drill")
    def operations_drill(request: Request, kind: str = "", id: str = ""):  # noqa: A002
        return ok(tabs.operations_drill(db, kind, id))

    @router.get("/autonomy")
    def autonomy(request: Request):
        return ok(tabs.autonomy(db))

    @router.get("/learn")
    def learn(request: Request):
        return ok(tabs.autonomy(db))

    # W4-CC: the company overview and the completion-effort board (read-only, owner session).
    @router.get("/company")
    def company_view(request: Request):
        return ok(company_mod.company(db))

    # W4-CCPACKET (F-878): the Launch-0 launch packet, read-only, owner session (the same
    # `/api/cc/*` default-deny gate as every route here; no new auth logic).
    @router.get("/launch/packet")
    def launch_packet_view(request: Request):
        from . import launch_packet

        return ok(launch_packet.view(db))

    # W4-FIRSTSALE: every first-sale gate per product and shop-wide, read-only, owner session.
    @router.get("/first-sale")
    def first_sale_view(request: Request):
        from . import first_sale

        return ok(first_sale.view(db))

    @router.get("/completion")
    def completion_view(request: Request):
        return ok({"tab": "COMPLETION", "generated_at": providers.now_iso(),
                   "sections": {"board": company_mod.completion(db),
                                "finish_line": company_mod.finish_line(),
                                "live_work": company_mod.live_company_work(db)}})

    @router.get("/insights")
    def insights(request: Request):
        return ok(tabs.insights(db))

    @router.get("/timeline")
    def timeline(request: Request, limit: int = 50):
        return ok(tabs.timeline(db, limit))

    @router.get("/notifications")
    def notifications_list(request: Request):
        return ok(tabs.notifications_tab(db))

    @router.post("/notifications/refresh")
    def notifications_refresh(request: Request):
        return ok(notifications.refresh(db))

    @router.post("/notifications/policy")
    async def notifications_policy(request: Request):
        body = await body_of(request)
        try:
            return ok(await run_in_threadpool(notifications.set_policy, db, body))
        except ValueError as exc:
            raise auth.refuse(db, request, 400, "BAD_REQUEST", str(exc)) from None

    @router.post("/notifications/{notification_id}/ack")
    def notifications_ack(notification_id: int, request: Request):
        if not notifications.ack(db, notification_id):
            return ok({"error": f"no notification {notification_id}", "code": "NOT_FOUND"},
                      404)
        return ok({"acked": notification_id})

    # ---- listing images (W-OWNERIMG) -----------------------------------------------------
    # Under /api/cc/, so `auth.gate` has already required a live owner session, plus CSRF, a
    # fresh nonce and a timestamp on every POST. The upload is the optional owner fallback
    # and runs the same gates as autonomous production. The approval re-checks every gate
    # and needs a step-up, because it is the owner's publication decision.

    @router.get("/images")
    def images_board(request: Request):
        from ...visual import image_production, outfits

        out = image_production.status_board(db)
        out["outfits"] = outfits.registry(db)
        return ok(out)

    @router.get("/images/plans")
    def images_plans(request: Request):
        from ...visual import shot_plans

        return ok(shot_plans.all_plans())

    @router.get("/images/{listing}")
    def images_listing(listing: str, request: Request):
        from ...products import launch0
        from ...visual import image_production

        if listing not in launch0.LAUNCH0_SLUGS:
            return ok({"error": f"no Launch-0 listing {listing!r}", "code": "NOT_FOUND"}, 404)
        return ok(image_production.readiness(db, listing))

    @router.post("/owner-images")
    async def owner_images_upload(request: Request):
        import base64
        import binascii

        from ...publish import owner_images

        body = await body_of(request)
        pid = auth.current_public_id(request)
        try:
            data = base64.b64decode(str(body.get("image_b64") or ""), validate=True)
        except (binascii.Error, ValueError):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "image_b64 must be base64",
                              session_public_id=pid) from None
        cost = body.get("cost_usd")
        try:
            cost = None if cost in (None, "") else float(cost)
            out = await run_in_threadpool(lambda: owner_images.intake(
                db, data=data, slug=str(body.get("slug") or ""),
                version=str(body.get("version") or ""), release=str(body.get("release") or ""),
                role=str(body.get("role") or ""), prompt=str(body.get("prompt") or "")[:8000],
                references=body.get("references") or "",
                provider=str(body.get("provider") or "")[:80],
                model=str(body.get("model") or "")[:120], cost_usd=cost,
                laura_present=bool(body.get("laura_present")),
                outfit_id=str(body.get("outfit_id") or "") or None,
                owner_visual_approval=(bool(body["owner_visual_approval"])
                                       if "owner_visual_approval" in body else None),
                submitted_by=actor(request)))
        except (owner_images.IntakeRefused, ValueError) as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "owner_images.intake", "sha256": out["sha256"],
                            "technical_status": out["technical_status"]})
        return ok(out)

    @router.post("/images/outfits")
    async def images_outfit(request: Request):
        from ...visual import outfits

        body = await body_of(request)
        pid = auth.current_public_id(request)
        try:
            out = outfits.register(db, outfit_id=str(body.get("outfit_id") or ""),
                                   garments=dict(body.get("garments") or {}),
                                   description=str(body.get("description") or ""),
                                   colours=[str(c) for c in body.get("colours") or []],
                                   reference_hashes=body.get("reference_hashes") or [],
                                   identity_changes=body.get("identity_changes"))
            if body.get("approve"):
                out = outfits.approve(db, out["outfit_id"], approved_by=actor(request))
        except outfits.OutfitRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        return ok(out)

    @router.post("/images/runs/approve")
    async def images_approve(request: Request):
        from ...visual import image_production

        body = await body_of(request)
        auth.require_stepup(db, request, "images.approve")
        out = await run_in_threadpool(lambda: image_production.approve(
            db, str(body.get("run_key") or ""), decided_by=actor(request)))
        auth.record(db, kind="action", outcome="ok" if out.get("approved") else "refused",
                    request=request, session_public_id=auth.current_public_id(request),
                    detail={"action": "images.approve", "run_key": body.get("run_key"),
                            "approved": out.get("approved")})
        return ok(out)

    # ---- gallery approval card, restart, wardrobe editor (W-VISNEXT) ----------------------
    # Three decisions kept apart on the card: the owner's look (recorded, no gate reads it),
    # technical certification (the stored verdicts; the owner cannot change them) and
    # publication authorization (`images/runs/approve`, step-up, every gate re-checked).

    @router.get("/images/runs/card")
    def images_card(request: Request, run_key: str = ""):
        from ...visual import image_production

        card = image_production.gallery_card(db, str(run_key)[:300])
        if card is None:
            return ok({"error": "no such run", "code": "NOT_FOUND"}, 404)
        return ok(card)

    @router.get("/images/candidates/{candidate_id}/image")
    def images_candidate_image(candidate_id: int, request: Request):
        """The stored bytes of one generated candidate, unchanged (sha256-addressed)."""
        from fastapi.responses import Response

        from ...core.artifacts import ArtifactStore
        from ...visual.image_records import ImageCandidate, ensure_tables

        ensure_tables(db)
        with db.session() as s:
            row = s.get(ImageCandidate, int(candidate_id))
            sha = row.sha256 if row is not None else ""
        data = None
        if sha:
            try:
                data = ArtifactStore().get(sha, db=db)
            except Exception:  # noqa: BLE001 - missing bytes are a 404, never a substitute
                data = None
        if not data:
            return ok({"error": "no stored image for this candidate", "code": "NOT_FOUND"}, 404)
        mime = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"
        return Response(data, media_type=mime, headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "X-Image-Status": "AI-generated candidate; never a photograph; not published"})

    @router.post("/images/runs/visual-approval")
    async def images_visual_approval(request: Request):
        from ...visual import image_production

        body = await body_of(request)
        out = await run_in_threadpool(lambda: image_production.record_visual_approval(
            db, str(body.get("run_key") or ""), decided_by=actor(request),
            approved=bool(body.get("approved")), note=str(body.get("note") or "")[:1000]))
        auth.record(db, kind="action", outcome="ok" if out.get("recorded") else "refused",
                    request=request, session_public_id=auth.current_public_id(request),
                    detail={"action": "images.visual_approval", "run_key": body.get("run_key"),
                            "approved": bool(body.get("approved"))})
        return ok(out)

    @router.post("/images/runs/restart")
    async def images_restart(request: Request):
        from ...queue.durable import DuplicateJob, JobQueue
        from ...visual import image_production

        # INTEG4 / security review of 7f6dbe8 (L1): a restart can resume paid generation, so
        # it needs step-up like authorize, run and approve.
        auth.require_stepup(db, request, "images.restart")
        body = await body_of(request)
        q = JobQueue(db)

        def follow(inputs, key):
            try:
                return q.enqueue(image_production.AGENT, image_production.JOB_TYPE, inputs,
                                 idempotency_key=key)
            except DuplicateJob:
                return None

        out = await run_in_threadpool(lambda: image_production.restart(
            db, str(body.get("run_key") or ""), follow=follow, by=actor(request),
            reason=str(body.get("reason") or "")[:500]))
        auth.record(db, kind="action", outcome="ok" if out.get("restarted") else "refused",
                    request=request, session_public_id=auth.current_public_id(request),
                    detail={"action": "images.restart", "run_key": body.get("run_key"),
                            "epoch": out.get("epoch")})
        return ok(out)

    @router.get("/wardrobe")
    def images_wardrobe(request: Request):
        from ...visual import outfits

        return ok(outfits.wardrobe_editor(db))

    @router.post("/images/outfits/action")
    async def images_outfit_action(request: Request):
        """Wardrobe editor actions: approve, reserve, release, replace, set_reference."""
        from ...visual import outfits

        body = await body_of(request)
        pid = auth.current_public_id(request)
        act = str(body.get("action") or "")
        oid = str(body.get("outfit_id") or "")
        listing = str(body.get("listing") or "")
        try:
            if act == "approve":
                out = outfits.approve(db, oid, approved_by=actor(request))
            elif act == "reserve":
                out = outfits.reserve(db, oid, listing)
            elif act == "release":
                out = outfits.release(db, oid, listing,
                                      why=str(body.get("why") or "owner, wardrobe editor"))
            elif act == "replace":
                out = outfits.replace(db, oid, str(body.get("new_outfit_id") or ""), listing)
            elif act == "set_reference":
                out = outfits.set_approved_reference(db, oid, str(body.get("image_sha256") or ""),
                                                     by=actor(request))
            else:
                return ok({"error": f"unknown action {act!r}", "code": "BAD_REQUEST"}, 400)
        except outfits.OutfitRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": f"images.outfit.{act}", "outfit_id": oid,
                            "listing": listing})
        return ok(out)

    # ---- controlled visual experiments (W-VISNEXT) -----------------------------------------
    # Owner session for everything (auth.gate), step-up for authorize and run. No query-string
    # secrets and no ops-token route: the provider key is read by the job from the process
    # environment and never crosses this API.

    @router.get("/experiments")
    def experiments_board(request: Request):
        from ...experiments import controlled

        return ok({"experiments": controlled.board(db)})

    @router.post("/experiments/{definition_id}/authorize")
    async def experiments_authorize(definition_id: str, request: Request):
        from ...experiments import controlled

        body = await body_of(request)
        auth.require_stepup(db, request, "experiments.authorize")
        pid = auth.current_public_id(request)

        def cap(name):
            v = body.get(name)
            return None if v in (None, "") else float(v)
        try:
            out = await run_in_threadpool(lambda: controlled.authorize(
                db, str(definition_id)[:80], by=actor(request), stepped_up=True,
                generation_cap_cad=cap("generation_cap_cad"),
                vision_cap_cad=cap("vision_cap_cad")))
        except (controlled.ControlledRefused, ValueError) as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "experiments.authorize", **out})
        return ok(out)

    @router.post("/experiments/{definition_id}/run")
    async def experiments_run(definition_id: str, request: Request):
        from ...experiments import controlled
        from ...queue.durable import DuplicateJob, JobQueue

        await body_of(request)
        auth.require_stepup(db, request, "experiments.run")
        pid = auth.current_public_id(request)
        q = JobQueue(db)

        def enqueue(inputs, key):
            try:
                # W4-CREDHEALTH: a reclaimed job re-runs once so the run resumes or settles
                # (run_job never pays twice: paid-call replay, billing-unknown never resent).
                return q.enqueue(controlled.AGENT, controlled.JOB_TYPE, inputs,
                                 idempotency_key=key, max_attempts=2)
            except DuplicateJob as exc:
                return exc.existing_id
        try:
            out = await run_in_threadpool(lambda: controlled.submit(
                db, str(definition_id)[:80], by=actor(request), enqueue=enqueue,
                stepped_up=True))
        except controlled.ControlledRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "experiments.run", **out})
        return ok(out)

    # ---- the owner's dated Shop Manager readings (W4-LISTREADY, review F7) -----------------
    # Owner session + step-up. The owner-attested pages (messages, legal_and_tax) are accepted
    # only here; `recorded_by` is the authenticated owner, not a claim in the body.

    @router.post("/etsy/shop-observation")
    async def shop_observation_owner(request: Request):
        from ...commerce import shop_observations

        body = await body_of(request)
        auth.require_stepup(db, request, "etsy.shop_observation")
        pid = auth.current_public_id(request)
        try:
            out = await run_in_threadpool(lambda: shop_observations.record(
                db, page=str(body.get("page") or "")[:40], observed_at=body.get("observed_at"),
                complete=body.get("complete"), values=body.get("values"),
                statement=str(body.get("statement") or ""), recorded_by=actor(request)))
        except shop_observations.ObservationRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:300], kind="action",
                              session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "etsy.shop_observation",
                            "page": str(body.get("page") or "")[:40]})
        return ok(out)

    # ---- the owner's Launch-0 image-review batch (W4-LISTREADY, D-W4-LAUNCH-VISION-BATCH) ----
    # Owner session for both; step-up to activate. Activation fixes the frame scope from the
    # stored Launch-0 frames, then enqueues the one batch run. Nothing else raises a ceiling.

    @router.get("/launch-review")
    def launch_review_state(request: Request):
        from ...finance import launch_review

        out = launch_review.state(db)
        if out.get("status") in ("not_activated", launch_review.UNUSED):
            # Read-only, for the card: whether activation's own checks would pass now.
            scope = launch_review.frame_scope(db)
            out["frames_ready"] = bool(scope["frames"]) and not scope["missing"]
            out["missing_releases"] = scope["missing"]
            out["vision_open"] = launch_review.vision_open(db) is True
        return ok(out)

    @router.post("/launch-review/activate")
    async def launch_review_activate(request: Request):
        from ...finance import launch_review
        from ...queue.durable import DuplicateJob, JobQueue

        await body_of(request)
        auth.require_stepup(db, request, "launch_review.activate")
        pid = auth.current_public_id(request)
        try:
            out = await run_in_threadpool(lambda: launch_review.activate(
                db, by=actor(request), stepped_up=True))
        except launch_review.LaunchReviewRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=pid) from None
        try:
            job = JobQueue(db).enqueue(launch_review.AGENT, launch_review.JOB_TYPE, {},
                                       idempotency_key=launch_review.resume_key(db),
                                       max_attempts=1)
            out["run_job_id"] = job.id
        except DuplicateJob as exc:
            out["run_job_id"] = exc.existing_id
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "launch_review.activate",
                            **{k: out.get(k) for k in ("batch_id", "status", "frames",
                                                       "total_cap_cad", "daily_cap_cad",
                                                       "expires_at", "run_job_id")}})
        return ok(out)

    @router.post("/launch-review/resume")
    async def launch_review_resume(request: Request):
        """Delta review N2: queue one more run of the open batch (pending releases only),
        under the same caps and expiry. Step-up."""
        from ...finance import launch_review
        from ...queue.durable import JobQueue

        await body_of(request)
        auth.require_stepup(db, request, "launch_review.resume")
        pid = auth.current_public_id(request)
        st = launch_review.state(db)
        if st.get("status") != launch_review.OPEN:
            raise auth.refuse(db, request, 400, "REFUSED",
                              f"the batch is {st.get('status')}; only an open batch resumes",
                              kind="action", session_public_id=pid)
        job = JobQueue(db).enqueue(launch_review.AGENT, launch_review.JOB_TYPE, {},
                                   idempotency_key=launch_review.resume_key(db),
                                   max_attempts=1)
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "launch_review.resume", "run_job_id": job.id})
        return ok({**st, "run_job_id": job.id})

    @router.get("/experiments/runs/{run_id}/card")
    def experiments_card(run_id: int, request: Request):
        from ...experiments import controlled

        out = controlled.card(db, int(run_id))
        if out is None:
            return ok({"error": "no such experiment run", "code": "NOT_FOUND"}, 404)
        return ok(out)

    @router.get("/experiments/runs/{run_id}/image")
    def experiments_image(run_id: int, request: Request):
        from fastapi.responses import Response

        from ...core.artifacts import ArtifactStore
        from ...experiments import controlled

        r = controlled.get_run(db, int(run_id))
        data = None
        if r and r.get("image_sha256"):
            try:
                data = ArtifactStore().get(r["image_sha256"], db=db)
            except Exception:  # noqa: BLE001 - missing bytes are a 404
                data = None
        if not data:
            return ok({"error": "no stored image for this run", "code": "NOT_FOUND"}, 404)
        return Response(data, media_type="image/png", headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "X-Image-Status": "EXPERIMENT; AI-generated; never a photograph; never published"})

    @router.get("/account")
    def account(request: Request):
        return ok(tabs.account(db, auth.current_public_id(request)))

    @router.get("/account/sessions")
    def sessions(request: Request):
        return ok({"sessions": auth.list_sessions(db, auth.current_public_id(request))})

    @router.post("/account/sessions/revoke-others")
    def revoke_others(request: Request):
        me = auth.current_public_id(request)
        n = 0
        for s_ in auth.list_sessions(db, me, limit=500):
            if not s_["current"] and s_["revoked_at"] is None:
                n += int(auth.revoke_session(db, s_["session_id"], f"revoked by {me}"))
                private_context.on_session_revoked(db, s_["session_id"])
        auth.record(db, kind="session_revoke", outcome="ok", request=request,
                    session_public_id=me, detail={"revoked": n})
        return ok({"revoked": n})

    @router.post("/account/sessions/{session_id}/revoke")
    def revoke_one(session_id: str, request: Request):
        me = auth.current_public_id(request)
        if not auth.revoke_session(db, session_id, f"revoked by {me}"):
            return ok({"error": f"no live session {session_id!r}", "code": "NOT_FOUND"}, 404)
        private_context.on_session_revoked(db, session_id)
        auth.record(db, kind="session_revoke", outcome="ok", request=request,
                    session_public_id=me, detail={"revoked": session_id})
        return ok({"revoked": session_id})

    # ---- owner actions ---------------------------------------------------------------

    @router.post("/actions/{action}")
    async def run_action(action: str, request: Request):
        if action not in approvals.ACTIONS:
            raise auth.refuse(db, request, 404, "NOT_FOUND", f"unknown action {action!r}",
                              kind="action", session_public_id=auth.current_public_id(request))
        body = await body_of(request)
        if approvals.ACTIONS[action][0]:
            auth.require_stepup(db, request, action)
        try:
            out = await run_in_threadpool(approvals.execute, db, action, body,
                                          actor=actor(request))
        except approvals.ActionNotFound as exc:
            raise auth.refuse(db, request, 404, "NOT_FOUND", str(exc), kind="action",
                              session_public_id=auth.current_public_id(request)) from None
        except approvals.ActionRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc),
                              kind="action",
                              session_public_id=auth.current_public_id(request),
                              detail=exc.detail) from None
        return ok({"ok": True, "action": action, **out})

    # ---- W4-SHOPSYNC: live shop settings, CONFIRMED-LIVE / OWNER-CONFIRMED / UNVERIFIED --
    # Session + CSRF + nonce are enforced by the gate. A confirmation is the owner's dated
    # statement about their own shop (no authority is granted), so it needs no step-up.
    # Re-reading queues the daily store.live_drift job, which makes read-only api_key GETs.

    @router.get("/store/settings")
    def store_settings(request: Request):
        from ...store_foundation import shop_sync

        return ok(shop_sync.status(db))

    @router.post("/store/settings/sync")
    async def store_settings_sync(request: Request):
        from datetime import datetime, timezone

        from ...queue.durable import DuplicateJob, JobQueue

        await body_of(request)
        key = f"store.live_drift:cc:{datetime.now(timezone.utc):%Y%m%dT%H%M}"
        try:
            job = JobQueue(db).enqueue("orchestrator", "store.live_drift", {},
                                       idempotency_key=key)
        except DuplicateJob:
            job = None
        auth.record(db, kind="action", outcome="ok", request=request,
                    session_public_id=auth.current_public_id(request),
                    detail={"action": "store.settings_sync", "enqueued": job is not None})
        return ok({"ok": True, "enqueued": job is not None,
                   "job_id": getattr(job, "id", None)})

    @router.post("/store/settings/{key}/confirm")
    async def store_settings_confirm(key: str, request: Request):
        from ...store_foundation import shop_sync

        body = await body_of(request)
        # Final review R2: a confirmation is evidence (the banner check and the payout
        # requirement close on it), so it needs the owner's step-up.
        auth.require_stepup(db, request, "store.settings.confirm")
        try:
            out = await run_in_threadpool(
                lambda: shop_sync.confirm(db, key, actor=actor(request),
                                          statement=str(body.get("statement") or "")))
        except shop_sync.ConfirmRefused as exc:
            raise auth.refuse(db, request, 409, "NOT_OWNER_CONFIRMABLE", str(exc),
                              kind="action",
                              session_public_id=auth.current_public_id(request)) from None
        return ok({"ok": True, **out})

    # ---- W4-ETSYCOMM: the Etsy connection, from the owner's phone ----------------------
    # Session + CSRF + nonce are enforced by the gate before these run. Re-check is a
    # read-only ping (no step-up); Connect starts a grant of shop authority (step-up).

    @router.get("/etsy")
    def etsy_status(request: Request):
        from . import etsy_connect

        return ok(etsy_connect.status(db))

    @router.post("/etsy/recheck")
    async def etsy_recheck(request: Request):
        from . import etsy_connect

        await body_of(request)
        out = await run_in_threadpool(etsy_connect.recheck, db, actor=actor(request))
        return ok({"ok": True, **out})

    @router.post("/etsy/connect")
    async def etsy_connect_start(request: Request):
        from . import etsy_connect

        await body_of(request)
        auth.require_stepup(db, request, "etsy.connect")
        try:
            out = await run_in_threadpool(etsy_connect.connect, db, actor=actor(request))
        except etsy_connect.ConnectRefused as exc:
            raise auth.refuse(db, request, 409, exc.code, str(exc), kind="action",
                              session_public_id=auth.current_public_id(request),
                              detail=exc.detail) from None
        return ok({"ok": True, **out})

    # ---- W4-ONDEMAND: "Run checks now" -------------------------------------------------
    # Session + CSRF + nonce + timestamp are enforced by the gate before these run. A check
    # that calls a third party (model, Etsy, bucket) also needs a fresh step-up. Each run only
    # enqueues the existing scheduled job type; the worker re-authorises and budget-checks it.

    # ---- W4-CREDHEALTH: provider credential health (owner view) ------------------------
    # The latest reading per provider plus the live key fingerprint (last 4 + sha256 prefix),
    # which only this owner-authenticated view returns. "Check now" is
    # POST /api/cc/checks/credentials/run (the existing on-demand path).

    @router.get("/credentials")
    def credentials_status(request: Request):
        from ...gateway import credentials

        return ok({"providers": credentials.state(db, owner=True),
                   "run_now": "/api/cc/checks/credentials/run",
                   "rotation_doc": "research/final_build/w4/KEY_ROTATION.md"})

    @router.get("/checks")
    def checks_status(request: Request):
        from ...ops import on_demand

        return ok(on_demand.status(db))

    @router.post("/checks/{key}/run")
    async def checks_run(key: str, request: Request):
        from ...ops import on_demand

        await body_of(request)
        pid = auth.current_public_id(request)
        check = on_demand.CHECKS.get(key)
        if check is None:
            raise auth.refuse(db, request, 404, "NOT_FOUND", f"unknown check {key!r}",
                              kind="action", session_public_id=pid)
        if check.external:
            auth.require_stepup(db, request, f"checks.{key}")
        try:
            out = await run_in_threadpool(on_demand.run_check, db, key, actor=actor(request))
        except on_demand.CheckRefused as exc:
            status = 429 if exc.code == "RATE_LIMITED" else 409
            raise auth.refuse(db, request, status, exc.code, str(exc), kind="action",
                              session_public_id=pid,
                              detail={"retry_after_s": exc.retry_after_s}) from None
        return ok({"ok": True, **out})

    # ---- emergency -------------------------------------------------------------------

    @router.get("/emergency")
    def emergency_status(request: Request):
        return ok(emergency.status(db))

    async def _emergency(request, fn, *, stepup: bool, **fixed):
        body = await body_of(request)
        if stepup:
            auth.require_stepup(db, request, "resume")
        kwargs = {"reason": body.get("reason"), "actor": actor(request), **fixed}
        if "scope" not in fixed and fn is not emergency.kill_to_shadow:
            kwargs.update(scope=body.get("scope"), department=body.get("department"))
        try:
            return ok(await run_in_threadpool(lambda: fn(db, **kwargs)))
        except emergency.EmergencyRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc),
                              kind="emergency",
                              session_public_id=auth.current_public_id(request)) from None

    @router.post("/emergency/pause")
    async def emergency_pause(request: Request):
        return await _emergency(request, emergency.pause, stepup=False)

    @router.post("/emergency/resume")
    async def emergency_resume(request: Request):
        return await _emergency(request, emergency.resume, stepup=True)

    @router.post("/emergency/kill")
    async def emergency_kill(request: Request):
        return await _emergency(request, emergency.kill_to_shadow, stepup=False)

    # ---- v1.1 integrator wiring: operations recovery and department blocks --------------
    # All of these sit under /api/cc/, so `security.operator_gate` -> `auth.gate` has
    # already required a live owner session (and CSRF + freshness for every POST) before a
    # handler runs. Step-up is added for the actions that *restore* activity or re-run work;
    # blocking a department only makes the company more restrictive, so it does not need it.

    def _str(body: dict, key: str, limit: int = 200) -> str:
        return str(body.get(key) or "").strip()[:limit]

    async def _recovery(request: Request, action: str, call):
        from ...ops import recovery

        body = await body_of(request)
        auth.require_stepup(db, request, f"recovery.{action}")
        try:
            out = await run_in_threadpool(call, recovery, body, actor(request))
        except recovery.RecoveryRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc),
                              kind="action",
                              session_public_id=auth.current_public_id(request)) from None
        if isinstance(out, dict) and out.get("refused"):
            # ops.recovery audits a refusal and returns it; the owner sees it as a refusal.
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(out["refused"]),
                              kind="action",
                              session_public_id=auth.current_public_id(request))
        return ok({"ok": True, "action": action, "result": out})

    @router.get("/operations/recovery")
    def recovery_recent(request: Request, limit: int = 50):
        from ...ops import recovery

        return ok({"recent": recovery.recent(db, limit=max(1, min(int(limit), 200)))})

    @router.post("/operations/recovery/restart-job")
    async def recovery_restart_job(request: Request):
        def call(rec, body, who):
            try:
                job_id = int(body.get("job_id"))
            except (TypeError, ValueError):
                raise rec.RecoveryRefused("job_id must be an integer") from None
            return rec.restart_stuck_job(db, job_id, actor=who,
                                         request_id=_str(body, "request_id", 120),
                                         reason=_str(body, "reason"))
        return await _recovery(request, "restart_stuck_job", call)

    @router.post("/operations/recovery/release-lease")
    async def recovery_release_lease(request: Request):
        def call(rec, body, who):
            return rec.release_stale_lease(db, _str(body, "name", 120), actor=who,
                                           request_id=_str(body, "request_id", 120))
        return await _recovery(request, "release_stale_lease", call)

    @router.post("/operations/recovery/rerun-cycle")
    async def recovery_rerun_cycle(request: Request):
        def call(rec, body, who):
            return rec.rerun_department_cycle(db, _str(body, "cadence", 120), actor=who,
                                              request_id=_str(body, "request_id", 120))
        return await _recovery(request, "rerun_department_cycle", call)

    @router.get("/operations/soak")
    def operations_soak(request: Request, start: str = ""):
        from datetime import datetime, timezone

        from ...ops import slo

        try:
            when = datetime.fromisoformat(start)
        except ValueError:
            return ok({"error": "start must be an ISO 8601 timestamp", "code": "BAD_REQUEST"},
                      400)
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        return ok(slo.soak_report(db, start=when))

    def _department(request, department: str) -> str:
        from ...autonomy import charters

        if department not in charters.BY_KEY:
            raise auth.refuse(db, request, 404, "NOT_FOUND",
                              f"unknown department {department!r}", kind="action",
                              session_public_id=auth.current_public_id(request))
        return department

    def _audit_department(who: str, action: str, department: str, detail: dict) -> None:
        from ...core.models import AuditLog

        with db.session() as s:
            s.add(AuditLog(actor=who[:64], action=action, artifact=f"department:{department}",
                           detail=detail))

    @router.post("/departments/{department}/block")
    async def department_block(department: str, request: Request):
        from ...autonomy import memory

        dept = _department(request, department)
        body = await body_of(request)
        never = emergency.never_paused_refusal(dept)
        if never:
            # Same rule as emergency pause (F-889): blocking these would blind the company.
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", never, kind="action",
                              session_public_id=auth.current_public_id(request))
        reason = _str(body, "reason") or "blocked by the owner from the command center"
        who = actor(request)
        await run_in_threadpool(lambda: memory.block_department(db, dept,
                                                                reason=f"{reason} ({who})"))
        _audit_department(who, "cc.department.block", dept, {"reason": reason})
        return ok({"ok": True, "department": dept, "blocked": True})

    @router.post("/departments/{department}/unblock")
    async def department_unblock(department: str, request: Request):
        from ...autonomy import memory

        dept = _department(request, department)
        await body_of(request)
        auth.require_stepup(db, request, "department.unblock")
        who = actor(request)
        await run_in_threadpool(lambda: memory.unblock_department(db, dept))
        _audit_department(who, "cc.department.unblock", dept, {})
        return ok({"ok": True, "department": dept, "blocked": False})

    # ---- ask -------------------------------------------------------------------------

    @router.post("/ask")
    async def ask(request: Request):
        body = await body_of(request)
        return ok(await run_in_threadpool(ask_mod.ask, db, str(body.get("question") or "")))

    # ---- listing outcomes intake (W3 lane K3 wiring) -------------------------------------

    @router.post("/listing-outcomes")
    async def listing_outcomes_intake(request: Request, period_start: str = "",
                                      period_end: str = ""):
        """Owner uploads an Etsy listing-level Stats export (CSV body). Session + CSRF + nonce
        are already enforced by `auth.gate`; refusals are 400 with the exact reason."""
        from ...commerce import listing_outcomes

        text = (await request.body()).decode("utf-8", errors="replace")
        try:
            out = await run_in_threadpool(lambda: listing_outcomes.submit_export(
                db, text, period_start=period_start, period_end=period_end,
                submitted_by=actor(request)))
        except listing_outcomes.OutcomeRefused as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=auth.current_public_id(request)) from None
        return ok(out)

    # ---- authority (W3 K11, wired by W3-WIRE4) -------------------------------------------
    # Under /api/cc/, so `auth.gate` has already required a live owner session, CSRF and a
    # fresh nonce. Both are consequential owner decisions, so each also needs a fresh step-up
    # before the domain call, which itself refuses anything but owner + step_up_verified.

    @router.post("/authority/approve/{key}")
    async def authority_approve(key: str, request: Request):
        from ...authority import dag

        body = await body_of(request)
        pid = auth.current_public_id(request)
        auth.require_stepup(db, request, "authority.approve")
        ref = str(body.get("approval_ref") or body.get("owner_action_id") or "")[:120]
        try:
            out = await run_in_threadpool(lambda: dag.approve(
                db, key, approved_by="owner", step_up_verified=True,
                approval_ref=ref or f"cc:{pid}"))
        except dag.WorkRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc)[:500],
                              kind="action", session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "authority.approve", "key": key, "ref": ref})
        return ok({"ok": True, "work_item": out})

    @router.post("/authority/grant")
    async def authority_grant(request: Request):
        from ...authority import policy

        body = await body_of(request)
        pid = auth.current_public_id(request)
        auth.require_stepup(db, request, "authority.grant")
        try:
            max_per_day = int(body.get("max_per_day") or 0)
            max_cost = float(body.get("max_cost_cad") or 0.0)
        except (TypeError, ValueError):
            raise auth.refuse(db, request, 400, "BAD_REQUEST",
                              "max_per_day must be an integer and max_cost_cad a number",
                              kind="action", session_public_id=pid) from None
        kwargs = {"agent": str(body.get("agent") or "")[:64],
                  "action_class": str(body.get("action_class") or "")[:32],
                  "job_type": str(body.get("job_type") or "")[:80],
                  "level": str(body.get("level") or "owner_each")[:20],
                  "max_per_day": max_per_day, "max_cost_cad": max_cost,
                  "owner_decision_id": str(body.get("owner_decision_id") or "")[:64],
                  "reason": str(body.get("reason") or "")[:2000]}
        try:
            pid_row = await run_in_threadpool(lambda: policy.grant(
                db, granted_by="owner", step_up_verified=True, **kwargs))
        except policy.AuthorityRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc)[:500],
                              kind="action", session_public_id=pid) from None
        auth.record(db, kind="action", outcome="ok", request=request, session_public_id=pid,
                    detail={"action": "authority.grant", "policy_id": pid_row,
                            **{k: kwargs[k] for k in ("agent", "action_class", "job_type",
                                                      "level", "owner_decision_id")}})
        return ok({"ok": True, "policy_id": pid_row})

    # ---- Talk to Laura (W3 lane F; D-FB-13, spec/07 item 9) ------------------------------
    # Under /api/cc/, so `auth.gate` has already required a live owner session, and for the
    # POSTs CSRF + a fresh nonce + timestamp. A protected follow-on additionally needs
    # step-up. Business register only.

    @router.get("/laura")
    def laura_overview(request: Request):
        from ...laura.agency import talk

        return ok(talk.overview(db))

    @router.get("/laura/conversation")
    def laura_conversation(request: Request, limit: int = 20):
        from ...laura.agency import talk

        return ok({"register": "business", "turns": talk.history(db, limit)})

    @router.post("/laura/ask")
    async def laura_ask(request: Request):
        from ...laura.agency import talk

        body = await body_of(request)
        question = body.get("question")
        if not isinstance(question, str):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "question must be a string")
        from ...laura.agency import presence

        modes = body.get("modes")
        modes = [str(m) for m in modes][:3] if isinstance(modes, list) else None
        pid = auth.current_public_id(request)
        turn = await run_in_threadpool(
            lambda: talk.converse(db, question, session_public_id=pid))
        # Phase 1 delivers text; a richer mode requested degrades with its reason (D-FB-16).
        return ok({**turn, "delivery": presence.negotiate(modes)})

    @router.post("/laura/follow-on")
    async def laura_follow_on(request: Request):
        from ...laura.agency import followon

        body = await body_of(request)
        pid = auth.current_public_id(request)
        if body.get("confirm") is not True:
            raise auth.refuse(db, request, 400, "CONFIRMATION_REQUIRED",
                              "confirm the follow-on explicitly ({\"confirm\": true})",
                              kind="action", session_public_id=pid)
        try:
            turn_id = int(body.get("turn_id"))
        except (TypeError, ValueError):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "turn_id must be an integer",
                              kind="action", session_public_id=pid) from None
        key = str(body.get("proposal_key") or "")[:120]
        prop = await run_in_threadpool(_laura_proposal, turn_id, key)
        if prop is None:
            raise auth.refuse(db, request, 404, "NOT_FOUND",
                              f"turn {turn_id} has no proposal {key!r}", kind="action",
                              session_public_id=pid)
        protected = followon.protected(str(prop.get("job_type") or ""))
        if protected:
            auth.require_stepup(db, request, f"laura.follow_on.{prop.get('job_type')}")
        try:
            out = await run_in_threadpool(lambda: followon.create(
                db, turn_id, key, confirmed_by=actor(request), stepped_up=protected))
        except followon.FollowOnNotFound as exc:
            raise auth.refuse(db, request, 404, "NOT_FOUND", str(exc), kind="action",
                              session_public_id=pid) from None
        except followon.FollowOnRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc),
                              kind="action", session_public_id=pid) from None
        return ok({"ok": True, **out})

    def _laura_proposal(turn_id: int, key: str):
        from ...laura.agency.models import LauraTurn, ensure_tables

        ensure_tables(db)
        with db.session() as s:
            turn = s.get(LauraTurn, turn_id)
            if turn is None:
                return None
            return next((dict(p) for p in turn.proposals or []
                         if isinstance(p, dict) and p.get("key") == key), None)

    @router.get("/laura/portrait")
    def laura_portrait(request: Request):
        """Laura's canonical portrait, for the owner's Laura view only. Internal: it is a
        canonical reference, not publication-approved (D-FB-11 / directive item 7)."""
        from fastapi.responses import Response

        from ...laura.agency import identity_view

        try:
            p = identity_view.portrait()
        except Exception:  # noqa: BLE001 - no portrait is shown rather than a substitute
            return ok({"error": "canonical portrait unavailable", "code": "NOT_FOUND"}, 404)
        return Response(p["bytes"], media_type="image/jpeg", headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "X-Laura-Identity": p["identity_id"],
            "X-Laura-Image-Status": f"{p['status']}; internal; not publication-approved"})

    # ---- Laura presence: visible identity, voice spec, modes (D-FB-16 items 7-10) ---------

    @router.get("/laura/presence")
    def laura_presence(request: Request):
        from ...laura.agency import identity_view, presence, roadmap, voice_selection

        return ok({"capabilities": presence.capabilities(),
                   "visible_identity": identity_view.visible_identity(),
                   "voice": voice_selection.status(db),
                   "roadmap": roadmap.rows(),
                   "improvement_domain": roadmap.IMPROVEMENT_DOMAIN})

    @router.get("/laura/voice-spec")
    def laura_voice_spec(request: Request):
        from ...laura.agency import voice_spec

        return ok(voice_spec.public_view())

    @router.get("/laura/frame/{frame}")
    def laura_frame(frame: str, request: Request):
        """One owner-approved canonical reference frame (D-FB-14), verified by bytes,
        internal only. Anything else is 404 -- never a substitute image."""
        from fastapi.responses import Response

        from ...laura.agency import identity_view

        try:
            f = identity_view.frame_bytes(frame)
        except Exception:  # noqa: BLE001
            return ok({"error": "no such canonical frame", "code": "NOT_FOUND"}, 404)
        return Response(f["bytes"], media_type=f["mime"], headers={
            "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "X-Laura-Identity": f["identity_id"],
            "X-Laura-Image-Status": f"{f['status']}; internal; not publication-approved"})

    @router.post("/laura/voice")
    async def laura_voice(request: Request):
        """Phase 2 entry point (speech in). GATED until an STT provider is configured: the
        request is refused with the exact needs; nothing is guessed from audio."""
        import base64
        import binascii

        from ...laura.agency import presence

        body = await body_of(request)
        pid = auth.current_public_id(request)
        try:
            audio = base64.b64decode(str(body.get("audio_b64") or ""), validate=True)
        except (binascii.Error, ValueError):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "audio_b64 must be base64",
                              session_public_id=pid) from None
        if not audio or len(audio) > 2_000_000:
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "audio must be 1 B .. 2 MB",
                              session_public_id=pid)
        out = await run_in_threadpool(lambda: presence.respond(
            db, audio=audio, audio_mime=str(body.get("mime") or "")[:60],
            modes=[presence.VOICE, presence.TEXT], session_public_id=pid))
        if out["status"] == "REFUSED":
            return ok({"error": out["error"], "code": "VOICE_GATED",
                       "capabilities": presence.capabilities()}, 503)
        return ok(out)

    # ---- owner-private context (PRIV contract; private_context is the only gateway) -------
    # Under /api/cc/, so a live owner session + CSRF + nonce + timestamp are already enforced.
    # Every private route is POST (no GET cache anywhere) and answers `no-store`.

    def _private(request: Request, fn):
        pid = auth.current_public_id(request)
        try:
            return ok(fn(pid))
        except private_context.PrivateUnavailable as exc:
            raise auth.refuse(db, request, exc.status, exc.code,
                              f"private context unavailable ({exc.exc_name})",
                              kind="private_context", session_public_id=pid) from None

    @router.get("/private/status")
    def private_status(request: Request):
        return ok(private_context.status(db, auth.current_public_id(request)))

    @router.post("/private/open")
    def private_open(request: Request):
        auth.require_stepup(db, request, "private.open")
        return _private(request, lambda pid: private_context.open_(db, pid))

    @router.post("/private/close")
    def private_close(request: Request):
        return _private(request, lambda pid: private_context.close(db, pid))

    @router.post("/private/view")
    def private_view(request: Request):
        return _private(request, lambda pid: private_context.view(db, pid))

    @router.post("/private/remember")
    async def private_remember(request: Request):
        body = await body_of(request)
        return _private(request, lambda pid: private_context.remember(
            db, pid, body.get("key"), body.get("text")))

    @router.post("/private/turn")
    async def private_turn(request: Request):
        body = await body_of(request)
        return _private(request, lambda pid: private_context.owner_turn(
            db, pid, body.get("text")))

    @router.post("/private/forget")
    async def private_forget(request: Request):
        body = await body_of(request)
        return _private(request, lambda pid: private_context.forget(
            db, pid, body.get("id")))

    return router


STORE_PREVIEW_PATH = "/cc/store-preview"
LOGIN_RECOVERY_PATH = "/api/owner/cc/login-recovery"
#: W4-STORE wiring: the owner records what the live Etsy storefront shows (owner session).
LIVE_OBSERVATION_PATH = "/api/store/live_observation"


def login_recovery_handler(db):
    """Owner lockout recovery (audit ddf9c6e M1): a single-use, 15-minute login code.

    Mounted by `install` at `/api/owner/cc/login-recovery` (POST). It is *not* under
    `/api/cc/`, so the application-wide `security.operator_gate` requires the operator bearer
    credential (default-deny for every non-GET route). The code lets one login from a new
    device past the per-client and global failure limits; the passphrase (and TOTP) is still
    required, and the code is spent on first use.
    """

    def mint_login_recovery(request: Request):
        out = auth.mint_recovery_code(db)
        auth.record(db, kind="login_recovery", outcome="ok", request=request,
                    detail={"expires_at": out["expires_at"]})
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    return mint_login_recovery


def store_preview_handler(db):
    """F-926 Owner Store Preview (lane F): a not-live, script-free rendering of the whole shop.

    Mounted by `install` at `/cc/store-preview` (the path lane F's summary links to), ahead of
    the public `/cc/` static shell. `security.owner_session_route` names this exact path, so
    `operator_gate` -> `auth.gate` requires a live owner session before it renders.
    """
    from fastapi.responses import HTMLResponse

    def owner_store_preview(request: Request, viewport: str = "mobile",
                            variant: str = ""):
        from ...store_foundation import preview as store_preview_mod

        # W4-STOREFRONT: with no variant named, the owner sees the customer storefront view
        # (customer page + folded owner evidence panel); every earlier variant stays reachable.
        variant = variant or getattr(store_preview_mod, "DEFAULT_OWNER_VARIANT", "standard")
        # `variant` is passed through; the preview module validates it against its own
        # VARIANTS (an unknown name renders the standard variant), so lane B owns the names.
        variant = str(variant or "standard")[:40]
        try:
            html = store_preview_mod.render_preview(db, viewport, variant=variant)
        except TypeError:  # a preview module without variants
            html = store_preview_mod.render_preview(db, viewport)
        return HTMLResponse(html,
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow"})

    return owner_store_preview


IMAGE_REVIEW_PATH = "/cc/image-review"


def image_review_handler(db):
    """W4-IMAGES: the owner-only internal image review (`store_foundation.image_review`).

    Every candidate listing image, shown with its status and limitations, including frames
    withheld from the customer preview. `security.owner_session_route` names this exact path,
    so `operator_gate` -> `auth.gate` requires a live owner session. It is never a customer
    surface: no-store, noindex, and nothing on it grants publication.
    """
    from fastapi.responses import HTMLResponse

    def owner_image_review(request: Request):
        from ...store_foundation import image_review

        html = image_review.render_page(db)
        return HTMLResponse(html, headers={"Cache-Control": "no-store",
                                           "X-Robots-Tag": "noindex, nofollow"})

    return owner_image_review


def live_observation_handler(db):
    """W4-STORE: `POST /api/store/live_observation` -- the owner's dated reading of the live shop.

    `security.owner_session_route` names this path, so `operator_gate` -> `auth.gate` has
    already required a live owner session, a same-origin request, the CSRF token and a fresh
    nonce. The body is `{observed_at, fields: {field: live value}, statement}`; the domain
    call (`store_foundation.live_state.record_observation`) validates it and appends one
    `store.live_observation` audit row. Nothing here writes to Etsy: the drift job reads the
    observation and can only propose ADOPT_LIVE_INTO_REPO or owner instructions.
    """
    async def record_live_observation(request: Request):
        from ...store_foundation import live_state

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = None
        sid = auth.current_public_id(request)
        if not isinstance(body, dict):
            raise auth.refuse(db, request, 400, "BAD_REQUEST", "body must be a JSON object",
                              kind="action", session_public_id=sid)
        try:
            out = await run_in_threadpool(lambda: live_state.record_observation(
                db, observed_at=body.get("observed_at"), fields=body.get("fields"),
                statement=str(body.get("statement") or ""), recorded_by=f"owner:cc:{sid}"))
        except (live_state.ObservationRefused, live_state.OwnerFieldProtected) as exc:
            raise auth.refuse(db, request, 400, "REFUSED", str(exc)[:500], kind="action",
                              session_public_id=sid) from None
        drift = await run_in_threadpool(lambda: live_state.drift(db))
        return JSONResponse({"ok": True, "observation": out, "drift_counts": drift["counts"],
                             "writes_performed": drift.get("writes_performed", 0)},
                            status_code=201, headers={"Cache-Control": "no-store"})

    return record_live_observation
