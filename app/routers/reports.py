from fastapi import APIRouter, HTTPException
import base64
import json

from app.schemas import ReportIn
from app.database import (
    hash_error, upsert_error_signature, add_user_report, add_log_event,
    now_iso, get_error_by_hash, get_reports_for_error, update_error_status
)
from app.services.vercel_logs import fetch_logs_in_window
from app.services.telegram import send_telegram_message
from app.services.pipeline import run_investigation_pipeline

router = APIRouter(prefix="/webhook", tags=["reports"])


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

    if matched_log:
        update_error_status(error_sig_id, "new")
        import asyncio
        asyncio.create_task(run_investigation_pipeline(error_sig_id))

    return {
        "status": "received",
        "message": "Denúncia recebida com sucesso.",
        "error_id": error_sig_id,
        "log_matched": matched_log,
    }
