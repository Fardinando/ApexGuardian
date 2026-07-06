import httpx
from typing import Any
from app.config import settings


def _headers() -> dict[str, str]:
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base_url() -> str:
    return f"{settings.supabase_url.rstrip('/')}/rest/v1"


def supabase_available() -> bool:
    return bool(settings.supabase_url and settings.supabase_key)


def supabase_query(table: str, select: str = "*", eq: tuple | None = None,
                   limit: int = 100) -> list[dict[str, Any]]:
    if not supabase_available():
        return []
    try:
        params = {"select": select, "limit": limit}
        if eq:
            params[f"{eq[0]}"] = f"eq.{eq[1]}"
        resp = httpx.get(
            f"{_base_url()}/{table}",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def supabase_update(table: str, values: dict, eq: tuple) -> bool:
    if not supabase_available():
        return False
    try:
        resp = httpx.patch(
            f"{_base_url()}/{table}?{eq[0]}=eq.{eq[1]}",
            headers=_headers(),
            json=values,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def supabase_insert(table: str, values: dict) -> bool:
    if not supabase_available():
        return False
    try:
        resp = httpx.post(
            f"{_base_url()}/{table}",
            headers=_headers(),
            json=values,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def supabase_delete(table: str, eq: tuple) -> bool:
    if not supabase_available():
        return False
    try:
        resp = httpx.delete(
            f"{_base_url()}/{table}?{eq[0]}=eq.{eq[1]}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False
