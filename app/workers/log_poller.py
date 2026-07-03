import asyncio
import json
import logging

from app.database import (
    hash_error, upsert_error_signature, add_log_event, get_error_by_hash,
    update_error_status, now_iso, is_maintenance_mode,
)
from app.services.vercel_logs import fetch_recent_deployments, fetch_deployment_logs
from app.services.pipeline import run_investigation_pipeline

logger = logging.getLogger("apexguardian.log_poller")

_last_poll_time: float = 0
_running = False


async def poll_logs_loop(interval_seconds: int = 180):
    global _running
    if _running:
        return
    _running = True

    logger.info("Iniciando polling de logs da Vercel (intervalo: %ds)", interval_seconds)

    while _running:
        try:
            if is_maintenance_mode():
                await asyncio.sleep(60)
                continue

            global _last_poll_time
            from datetime import datetime, timezone
            current_time = datetime.now(timezone.utc).timestamp()

            deployments = await fetch_recent_deployments(5)
            for dep in deployments:
                dep_id = dep.get("uid") or dep.get("id")
                if not dep_id:
                    continue

                logs = await fetch_deployment_logs(dep_id, limit=50)
                for log in logs:
                    if log.get("type") != "error" and log.get("level") != "error":
                        continue

                    log_text = log.get("text") or log.get("message", "")
                    if not log_text:
                        continue

                    hash_val = hash_error(stack_trace=log_text)
                    existing = get_error_by_hash(hash_val)
                    if existing:
                        continue

                    error_id = upsert_error_signature(
                        hash_val=hash_val,
                        stack_trace=log_text,
                        description=f"Log detectado: {log_text[:200]}",
                        origin="vercel_log",
                    )

                    log_ts = log.get("created") or log.get("timestamp") or now_iso()
                    add_log_event(error_id, dep_id, json.dumps(log), str(log_ts))

                    logger.info("Novo erro detectado via log polling: %s", hash_val)
                    asyncio.create_task(run_investigation_pipeline(error_id))

            _last_poll_time = current_time

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Erro no polling de logs: %s", str(e))

        await asyncio.sleep(interval_seconds)


def stop_polling():
    global _running
    _running = False
