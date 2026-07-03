from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from functools import wraps
from typing import Callable
import secrets

from app.database import validate_session, log_admin_activity

PERMISSIONS = {
    "supreme": {
        "view_dashboard": True,
        "view_errors": True,
        "view_error_detail": True,
        "view_screenshots": True,
        "view_stacktraces": True,
        "view_user_stats": True,
        "view_correction_history": True,
        "view_admin_activity": True,
        "view_worker_status": True,
        "add_error_detection": True,
        "view_investigation_result": True,
        "trigger_fix": True,
        "deploy_preview": True,
        "approve_production": True,
        "rollback": True,
        "delete_any_error": True,
        "archive_errors": True,
        "reopen_errors": True,
        "add_admin": True,
        "remove_admin": True,
        "change_admin_role": True,
        "reactivate_admin": True,
        "view_system_logs": True,
        "force_workers": True,
        "export_data": True,
        "maintenance_mode": True,
        "check_integrations": True,
    },
    "operator": {
        "view_dashboard": True,
        "view_errors": True,
        "view_error_detail": True,
        "view_screenshots": True,
        "view_stacktraces": True,
        "view_user_stats": True,
        "view_correction_history": True,
        "view_worker_status": True,
        "trigger_fix": True,
        "deploy_preview": True,
        "approve_production": True,
        "rollback": True,
        "export_data": True,
        "check_integrations": True,
    },
    "analyst": {
        "view_dashboard": True,
        "view_errors": True,
        "view_error_detail": True,
        "view_screenshots": True,
        "view_stacktraces": True,
        "view_user_stats": True,
        "view_correction_history": True,
        "view_admin_activity": True,
        "add_error_detection": True,
        "view_investigation_result": True,
        "export_data": True,
        "check_integrations": True,
    },
    "basic": {
        "view_dashboard": True,
        "view_errors": True,
        "view_error_detail": True,
        "view_screenshots": True,
        "view_stacktraces": True,
    },
}


def get_current_admin(request: Request) -> dict | None:
    token = request.cookies.get("session_token")
    if not token:
        token = request.headers.get("X-Session-Token")
    if token:
        return validate_session(token)
    return None


def has_permission(admin: dict, permission: str) -> bool:
    if not admin:
        return False
    role = admin.get("role", "basic")
    return PERMISSIONS.get(role, {}).get(permission, False)


def require_permission(permission: str):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                for _, v in kwargs.items():
                    if isinstance(v, Request):
                        request = v
                        break
            if not request:
                raise HTTPException(status_code=500, detail="Request object not found")

            admin = get_current_admin(request)
            if not admin:
                accept = request.headers.get("accept", "")
                if "text/html" in accept:
                    return RedirectResponse(url="/admin/login", status_code=302)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            if not has_permission(admin, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission}",
                )

            request.state.admin = admin
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def log_action(request: Request, action: str, target_type: str = None,
                     target_id: str = None, details: dict = None):
    admin = getattr(request.state, "admin", None)
    if admin:
        log_admin_activity(
            admin_id=admin["id"],
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip=request.client.host if request.client else None,
        )
