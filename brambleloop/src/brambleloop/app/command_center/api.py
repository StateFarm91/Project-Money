"""`/api/cc/*` -- the Owner Command Center JSON API (contract: COMMAND_CENTER_API.md).

Authentication, CSRF, replay protection and rate limits are enforced *before* any handler runs,
by `security.operator_gate` -> `auth.gate` (default-deny for the whole prefix). Handlers here
add the per-action step-up check and turn authority refusals into audited 409s.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import approvals, ask as ask_mod, auth, emergency, notifications, tabs


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
        if await run_in_threadpool(auth.login_rate_limited, db, request):
            raise auth.refuse(db, request, 429, "RATE_LIMITED",
                              "too many failed logins; wait 15 minutes", kind="login")
        body = await body_of(request)
        good = await run_in_threadpool(auth.verify_owner, body.get("passphrase"),
                                       body.get("totp"))
        if not good:
            raise auth.refuse(db, request, 401, "BAD_CREDENTIALS",
                              "passphrase or code not accepted", kind="login")
        token, view = await run_in_threadpool(auth.create_session, db, request,
                                              device_label=str(body.get("device_label") or ""))
        auth.record(db, kind="login", outcome="ok", request=request,
                    session_public_id=view["session_id"])
        resp = ok({"authenticated": True, "csrf_token": auth.csrf_for(token), "session": view,
                   "stepup_valid_until": view["stepup_valid_until"]})
        resp.set_cookie(auth.COOKIE, token, max_age=int(auth.SESSION_TTL.total_seconds()),
                        path="/", secure=True, httponly=True, samesite="strict")
        return resp

    @router.post("/auth/logout")
    def logout(request: Request):
        pid = auth.current_public_id(request)
        auth.revoke_session(db, pid, "logged out")
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
        auth.record(db, kind="session_revoke", outcome="ok", request=request,
                    session_public_id=me, detail={"revoked": n})
        return ok({"revoked": n})

    @router.post("/account/sessions/{session_id}/revoke")
    def revoke_one(session_id: str, request: Request):
        me = auth.current_public_id(request)
        if not auth.revoke_session(db, session_id, f"revoked by {me}"):
            return ok({"error": f"no live session {session_id!r}", "code": "NOT_FOUND"}, 404)
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
        except approvals.ActionRefused as exc:
            raise auth.refuse(db, request, 409, "REFUSED_BY_AUTHORITY", str(exc),
                              kind="action",
                              session_public_id=auth.current_public_id(request)) from None
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

    return router


STORE_PREVIEW_PATH = "/cc/store-preview"


def store_preview_handler(db):
    """F-926 Owner Store Preview (lane F): a not-live, script-free rendering of the whole shop.

    Mounted by `install` at `/cc/store-preview` (the path lane F's summary links to), ahead of
    the public `/cc/` static shell. `security.owner_session_route` names this exact path, so
    `operator_gate` -> `auth.gate` requires a live owner session before it renders.
    """
    from fastapi.responses import HTMLResponse

    def owner_store_preview(request: Request, viewport: str = "mobile"):
        from ...store_foundation import preview as store_preview_mod

        return HTMLResponse(store_preview_mod.render_preview(db, viewport),
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow"})

    return owner_store_preview
