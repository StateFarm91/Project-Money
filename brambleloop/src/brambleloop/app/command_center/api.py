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
                "totp_required": auth.totp_required(), "csrf_token": None, "session": None,
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
        limited = await run_in_threadpool(
            lambda: auth.login_throttle(db, request, device_id=device_id, recovery=recovery))
        if limited:
            message = "too many failed logins; wait 15 minutes"
            if limited == "global":
                message += (" (a browser that has signed in before is not affected; the "
                            "operator can mint a one-time recovery code)")
            raise auth.refuse(db, request, 429, "RATE_LIMITED", message, kind="login",
                              session_public_id=device_id or "", detail={"limit": limited})
        good = await run_in_threadpool(auth.verify_owner, body.get("passphrase"),
                                       body.get("totp"))
        if not good:
            raise auth.refuse(db, request, 401, auth.FAILED_LOGIN_CODE,
                              "passphrase or code not accepted", kind="login",
                              session_public_id=device_id or "",
                              detail={"recovery_code": recovery} if recovery else None)
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
                                       body.get("totp"))
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

    @router.get("/money")
    def money(request: Request):
        return ok(tabs.money(db))

    @router.get("/money/drill")
    def money_drill(request: Request, metric: str = ""):
        return ok(tabs.money_drill(db, metric))

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
                            variant: str = "standard"):
        from ...store_foundation import preview as store_preview_mod

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
