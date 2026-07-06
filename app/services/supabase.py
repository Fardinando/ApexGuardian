from typing import Any
from app.config import settings


def get_supabase_client():
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_key)
    except Exception:
        return None


def supabase_available() -> bool:
    return bool(settings.supabase_url and settings.supabase_key)


def supabase_query(table: str, select: str = "*", eq: tuple | None = None,
                   limit: int = 100) -> list[dict[str, Any]]:
    if not supabase_available():
        return []
    client = get_supabase_client()
    if not client:
        return []
    try:
        query = client.table(table).select(select)
        if eq:
            query = query.eq(eq[0], eq[1])
        data = query.limit(limit).execute()
        return data.data if hasattr(data, 'data') else []
    except Exception:
        return []


def supabase_update(table: str, values: dict, eq: tuple) -> bool:
    if not supabase_available():
        return False
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(table).update(values).eq(eq[0], eq[1]).execute()
        return True
    except Exception:
        return False


def supabase_insert(table: str, values: dict) -> bool:
    if not supabase_available():
        return False
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(table).insert(values).execute()
        return True
    except Exception:
        return False


def supabase_delete(table: str, eq: tuple) -> bool:
    if not supabase_available():
        return False
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table(table).delete().eq(eq[0], eq[1]).execute()
        return True
    except Exception:
        return False
