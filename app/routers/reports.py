from fastapi import APIRouter, HTTPException
import base64
import json
import asyncio

from app.schemas import ReportIn
from app.database import (
    hash_error, upsert_error_signature, add_user_report, add_log_event,
    now_iso, get_error_by_hash, get_reports_for_error, update_error_status,
    is_maintenance_mode,
)
from app.services.vercel_logs import fetch_logs_in_window
from app.services.telegram import send_telegram_message
from app.services.pipeline import run_investigation_pipeline

router = APIRouter(prefix="/webhook", tags=["reports"])

_pending_investigations: dict[int, str] = {}


def get_pending_investigation(error_id: int) -> str | None:
    return _pending_investigations.get(error_id)


def remove_pending_investigation(error_id: int):
    _pending_investigations.pop(error_id, None)


@router.post("/report")
async def receive_report(payload: ReportIn):
    hash_val = hash_error(description=payload.description)
    error_sig_id = upsert_error_signature(
        hash_val=hash_val,
        stack_trace="",
        description=payload.description,
        origin="user_report",
        user_id_anon=payload.user_id_anon,
    )
    matched_log = False
    try:
        logs = await fetch_logs_in_window(
            payload.timestamp_frontend - 600,
            payload.timestamp_frontend,
        )
        if logs:
            matched_log = True
            for log in logs[:3]:
                add_log_event(error_sig_id, log.get("deploymentId", ""),
                              json.dumps(log), log.get("timestamp", now_iso()))
    except Exception:
        pass

    add_user_report(
        error_sig_id, payload.user_id_anon, payload.description,
        payload.screenshot_base64, payload.timestamp_frontend, matched_log
    )

    error = get_error_by_hash(hash_val)
    if not matched_log and error and error["total_reports"] == 1:
        update_error_status(error["id"], "archived_no_log")
        return {
            "status": "archived",
            "message": "Erro registrado. Não encontrado nos logs. O time foi avisado.",
            "error_id": error["id"],
        }

    if matched_log and not is_maintenance_mode():
        error_id = error_sig_id
        update_error_status(error_id, "new")
        asyncio.create_task(ask_to_investigate(error_id, payload.description, hash_val))

    return {
        "status": "received",
        "message": "Denúncia recebida com sucesso.",
        "error_id": error_sig_id,
        "log_matched": matched_log,
    }


async def ask_to_investigate(error_id: int, description: str, hash_val: str = "",
                              stack_trace: str = ""):
    if not hash_val:
        from app.database import get_error_by_id
        err = get_error_by_id(error_id)
        hash_val = err["hash"] if err else str(error_id)
    await asyncio.sleep(1)

    from app.services.ai_client import diagnose_error
    from app.services.search import search_error
    query = f"{stack_trace[:300] or description[:200]} Next.js React Vercel"
    search_results = await search_error(query)
    diagnosis = await diagnose_error(stack_trace or "", description, search_results)
    explanation = diagnosis or "Não foi possível analisar automaticamente."

    _pending_investigations[error_id] = hash_val
    msg = (
        f"⚠️ *Alerta de Warning — ERROR_ID:{error_id}*\n\n"
        f"`{description[:300]}`\n\n"
        f"🧠 *Explicação:*\n{explanation[:1500]}\n\n"
        f"Deseja que eu investigue?\n\n"
        f"✅ \"Sim\" / \"Investigar\" → Iniciar investigação\n"
        f"❌ \"Não\" / \"Ignorar\" → Arquivar sem investigar"
    )
    await send_telegram_message(msg)
