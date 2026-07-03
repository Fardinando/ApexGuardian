from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import bcrypt
import asyncio

from app.database import (
    get_errors_paginated, get_error_by_id, get_reports_for_error,
    get_fix_attempts_for_error, get_dashboard_stats, get_errors_by_day,
    get_top_errors, get_recent_activity, get_admin_list, create_admin,
    update_admin_role, toggle_admin_active, get_activity_log, get_user_stats,
    delete_error_complete, update_error_status, verify_admin_login,
    create_session, validate_session, delete_session, log_admin_activity,
    now_iso,
)
from app.auth import require_permission, get_current_admin, log_action
from app.services.pipeline import run_investigation_pipeline, run_manual_investigation
from app.services.git_ops import merge_to_main, rollback_fix
from app.services.vercel_logs import check_api_health as vercel_health
from app.services.ai_client import check_ai_health

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates" / "admin")


def _admin_context(request: Request) -> dict:
    admin = get_current_admin(request)
    return {"request": request, "admin": admin}


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", _admin_context(request))


@router.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    admin = verify_admin_login(username, password)
    if not admin:
        return templates.TemplateResponse("login.html", {
            **{"request": request, "admin": None},
            "error": "Credenciais inválidas",
        })

    token = create_session(admin["id"])
    log_admin_activity(admin["id"], "login", "system", None, {"username": username},
                       request.client.host if request.client else None)

    response = RedirectResponse("/admin", status_code=302)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    return response


@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        admin = validate_session(token)
        if admin:
            log_admin_activity(admin["id"], "logout", "system", None)
        delete_session(token)
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie("session_token")
    return response


@router.get("", response_class=HTMLResponse)
@require_permission("view_dashboard")
async def dashboard(request: Request):
    stats = get_dashboard_stats()
    errors_by_day = get_errors_by_day(30)
    top_errors = get_top_errors(5)
    recent = get_recent_activity(10)
    admin_info = get_current_admin(request)

    return templates.TemplateResponse("dashboard.html", {
        **{"request": request, "admin": admin_info},
        "stats": stats,
        "errors_by_day": errors_by_day,
        "top_errors": top_errors,
        "recent_activity": recent,
    })


@router.get("/api/stats")
@require_permission("view_dashboard")
async def stats_api(request: Request):
    stats = get_dashboard_stats()
    errors_by_day = get_errors_by_day(30)
    top_errors = get_top_errors(5)
    return {
        "stats": stats,
        "errors_by_day": errors_by_day,
        "top_errors": top_errors,
    }


@router.get("/api/activity")
@require_permission("view_dashboard")
async def activity_api(request: Request):
    return {"activity": get_recent_activity(10)}


@router.get("/errors", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_list(
    request: Request,
    page: int = 1,
    status: str = None,
    origin: str = None,
    search: str = None,
):
    errors, total = get_errors_paginated(page=page, status=status, origin=origin, search=search)
    total_pages = max(1, (total + 19) // 20)
    admin_info = get_current_admin(request)

    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "filter_status": status,
        "filter_origin": origin,
        "filter_search": search,
    })


@router.get("/errors/active", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_active(request: Request):
    errors, total = get_errors_paginated(
        status="new,analyzing,waiting_approval"
    )
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors,
        "page": 1, "total_pages": 1, "total": total,
        "section_title": "Ativos",
    })


@router.get("/errors/preview", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_preview(request: Request):
    errors, total = get_errors_paginated(status="preview")
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": total,
        "section_title": "Em Preview",
    })


@router.get("/errors/resolved", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_resolved(request: Request):
    errors, total = get_errors_paginated(status="production")
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": total,
        "section_title": "Resolvidos",
    })


@router.get("/errors/fully-archived", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_fully_archived(request: Request):
    errors, total = get_errors_paginated(status="archived_no_log")
    errors = [e for e in errors if e["total_reports"] == 1]
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": len(errors),
        "section_title": "Arquivados Completos",
    })


@router.get("/errors/partially-archived", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_partially_archived(request: Request):
    errors, total = get_errors_paginated(status="archived_no_log")
    errors = [e for e in errors if e["total_reports"] > 1]
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": len(errors),
        "section_title": "Arquivados Parciais",
    })


@router.get("/errors/cooldown", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_cooldown(request: Request):
    import datetime
    now = datetime.datetime.utcnow().isoformat()
    errors, total = get_errors_paginated(status="cooldown")
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": total,
        "section_title": "Em Cooldown",
    })


@router.get("/errors/ignored", response_class=HTMLResponse)
@require_permission("view_errors")
async def errors_ignored(request: Request):
    errors, total = get_errors_paginated(status="ignored")
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("errors_list.html", {
        **{"request": request, "admin": admin_info},
        "errors": errors, "page": 1, "total_pages": 1, "total": total,
        "section_title": "Ignorados",
    })


@router.get("/errors/{error_id}", response_class=HTMLResponse)
@require_permission("view_error_detail")
async def error_detail(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404)
    reports = get_reports_for_error(error_id)
    fixes = get_fix_attempts_for_error(error_id)
    admin_info = get_current_admin(request)

    return templates.TemplateResponse("error_detail.html", {
        **{"request": request, "admin": admin_info},
        "error": error,
        "reports": reports,
        "fixes": fixes,
    })


@router.post("/errors/{error_id}/delete")
@require_permission("delete_any_error")
async def error_delete(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if error:
        await log_action(request, "delete_error", "error", error["hash"])
        delete_error_complete(error_id)
    return RedirectResponse("/admin/errors", status_code=302)


@router.post("/errors/{error_id}/archive")
@require_permission("archive_errors")
async def error_archive(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if error:
        update_error_status(error_id, "archived_no_log")
        await log_action(request, "archive_error", "error", error["hash"])
    return RedirectResponse(f"/admin/errors/{error_id}", status_code=302)


@router.post("/errors/{error_id}/reopen")
@require_permission("reopen_errors")
async def error_reopen(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if error:
        update_error_status(error_id, "new")
        await log_action(request, "reopen_error", "error", error["hash"])
    return RedirectResponse(f"/admin/errors/{error_id}", status_code=302)


@router.post("/errors/{error_id}/force-fix")
@require_permission("trigger_fix")
async def error_force_fix(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if error:
        update_error_status(error_id, "new")
        await log_action(request, "trigger_fix", "error", error["hash"])
        import asyncio
        asyncio.create_task(run_investigation_pipeline(error_id))
    return RedirectResponse(f"/admin/errors/{error_id}", status_code=302)


@router.post("/errors/{error_id}/approve-production")
@require_permission("approve_production")
async def error_approve_production(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404)

    fixes = get_fix_attempts_for_error(error_id)
    last_fix = fixes[-1] if fixes else None
    if last_fix and last_fix.get("branch_name"):
        await log_action(request, "approve_production", "error", error["hash"],
                         {"branch": last_fix["branch_name"]})
        result = await merge_to_main(last_fix["branch_name"])
        if result["success"]:
            update_error_status(error_id, "production")
            from app.services.telegram import send_simple_message
            await send_simple_message(
                f"🚀 *Erro #{error['hash']} publicado em produção!*\n\n"
                f"Correção mergeada para main e deploy realizado."
            )
        else:
            raise HTTPException(status_code=500, detail=result.get("error"))
    return RedirectResponse(f"/admin/errors/{error_id}", status_code=302)


@router.post("/errors/{error_id}/rollback")
@require_permission("rollback")
async def error_rollback(request: Request, error_id: int):
    error = get_error_by_id(error_id)
    if not error:
        raise HTTPException(status_code=404)

    fixes = get_fix_attempts_for_error(error_id)
    last_fix = fixes[-1] if fixes else None
    if last_fix and last_fix.get("branch_name"):
        await log_action(request, "rollback", "error", error["hash"],
                         {"branch": last_fix["branch_name"]})
        rollback_fix(last_fix["branch_name"])
        update_error_status(error_id, "new")
    return RedirectResponse(f"/admin/errors/{error_id}", status_code=302)


@router.get("/errors/add", response_class=HTMLResponse)
@require_permission("add_error_detection")
async def error_add_page(request: Request):
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("error_add.html", {
        **{"request": request, "admin": admin_info},
    })


@router.post("/errors/add")
@require_permission("add_error_detection")
async def error_add_action(
    request: Request,
    stack_trace: str = Form(...),
    url: str = Form(""),
    context: str = Form(""),
):
    await log_action(request, "add_error_manual", "error", None,
                     {"context_preview": context[:100]})
    result = await run_manual_investigation(stack_trace, context, url, context)
    admin_info = get_current_admin(request)

    return templates.TemplateResponse("error_add.html", {
        **{"request": request, "admin": admin_info},
        "result": result,
    })


@router.get("/admins", response_class=HTMLResponse)
@require_permission("add_admin")
async def admins_list(request: Request):
    admins = get_admin_list()
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("admins_list.html", {
        **{"request": request, "admin": admin_info},
        "admins": admins,
    })


@router.get("/admins/add", response_class=HTMLResponse)
@require_permission("add_admin")
async def admin_add_page(request: Request):
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("admin_add.html", {
        **{"request": request, "admin": admin_info},
    })


@router.post("/admins/add")
@require_permission("add_admin")
async def admin_add_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("basic"),
):
    current_admin = get_current_admin(request)
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        admin_id = create_admin(username, pw_hash, role, current_admin["id"])
        await log_action(request, "add_admin", "admin", username,
                         {"role": role, "new_admin_id": admin_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Username já existe")
    return RedirectResponse("/admin/admins", status_code=302)


@router.post("/admins/{admin_id}/change-role")
@require_permission("change_admin_role")
async def admin_change_role(request: Request, admin_id: int, role: str = Form(...)):
    if role not in ("supreme", "operator", "analyst", "basic"):
        raise HTTPException(status_code=400, detail="Role inválida")
    update_admin_role(admin_id, role)
    await log_action(request, "change_role", "admin", str(admin_id),
                     {"new_role": role})
    return RedirectResponse("/admin/admins", status_code=302)


@router.post("/admins/{admin_id}/ban")
@require_permission("remove_admin")
async def admin_ban(request: Request, admin_id: int):
    toggle_admin_active(admin_id, False)
    await log_action(request, "ban_admin", "admin", str(admin_id))
    return RedirectResponse("/admin/admins", status_code=302)


@router.post("/admins/{admin_id}/unban")
@require_permission("reactivate_admin")
async def admin_unban(request: Request, admin_id: int):
    toggle_admin_active(admin_id, True)
    await log_action(request, "reactivate_admin", "admin", str(admin_id))
    return RedirectResponse("/admin/admins", status_code=302)


@router.get("/activity", response_class=HTMLResponse)
@require_permission("view_admin_activity")
async def activity_log_page(request: Request, page: int = 1):
    activities, total = get_activity_log(page=page)
    total_pages = max(1, (total + 49) // 50)
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("activity_log.html", {
        **{"request": request, "admin": admin_info},
        "activities": activities,
        "page": page,
        "total_pages": total_pages,
    })


@router.get("/users", response_class=HTMLResponse)
@require_permission("view_user_stats")
async def users_page(request: Request):
    stats = get_user_stats()
    admin_info = get_current_admin(request)
    return templates.TemplateResponse("users.html", {
        **{"request": request, "admin": admin_info},
        "stats": stats,
    })


@router.get("/system", response_class=HTMLResponse)
@require_permission("check_integrations")
async def system_page(request: Request):
    vercel = await vercel_health()
    ai_status = await check_ai_health()
    admin_info = get_current_admin(request)

    from app.database import get_dashboard_stats, get_errors_by_day
    stats = get_dashboard_stats()

    return templates.TemplateResponse("system.html", {
        **{"request": request, "admin": admin_info},
        "vercel_status": vercel,
        "ai_status": ai_status,
        "stats": stats,
    })


@router.post("/system/force-poll")
@require_permission("force_workers")
async def system_force_poll(request: Request):
    await log_action(request, "force_poll", "system")
    from app.workers.log_poller import poll_logs_loop
    import asyncio
    asyncio.create_task(poll_logs_loop(1))
    return RedirectResponse("/admin/system", status_code=302)


@router.post("/system/force-volume")
@require_permission("force_workers")
async def system_force_volume(request: Request):
    await log_action(request, "force_volume", "system")
    from app.workers.volume_checker import check_volume_loop
    import asyncio
    asyncio.create_task(check_volume_loop(1))
    return RedirectResponse("/admin/system", status_code=302)
