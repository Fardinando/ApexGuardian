import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.database import (
    db, now_iso, update_error_status,
    is_maintenance_mode,
)
from app.services.pipeline import run_investigation_pipeline
from app.services.telegram import send_simple_message

logger = logging.getLogger("apexguardian.volume_checker")

_running = False


async def check_volume_loop(interval_seconds: int = 3600):
    global _running
    if _running:
        return
    _running = True

    logger.info("Iniciando verificação de volume (intervalo: %ds)", interval_seconds)

    while _running:
        try:
            if is_maintenance_mode():
                await asyncio.sleep(60)
                continue

            now = datetime.now(timezone.utc)
            two_weeks_ago = (now - timedelta(days=14)).isoformat()
            two_months_ago = (now - timedelta(days=60)).isoformat()

            with db() as conn:
                rows = conn.execute(
                    """SELECT r.error_sig_id, COUNT(DISTINCT r.user_id_anon) as user_count,
                              e.hash, e.status, e.description
                       FROM user_reports r
                       JOIN error_signatures e ON r.error_sig_id = e.id
                       WHERE e.status = 'archived_no_log'
                       GROUP BY r.error_sig_id
                       HAVING user_count >= 3"""
                ).fetchall()

                for row in rows:
                    sig_id = row["error_sig_id"]
                    user_count = row["user_count"]
                    error_hash = row["hash"]
                    status = row["status"]

                    if status == "archived_no_log" and user_count >= 10:
                        update_error_status(sig_id, "new")
                        logger.info("Volume trigger (10+ users): %s (%d usuários)", error_hash, user_count)
                        await send_simple_message(
                            f"📊 *Gatilho de Volume Ativado*\n\n"
                            f"Erro #{error_hash} atingiu *{user_count} usuários*\n"
                            f"Reabrindo investigação automaticamente..."
                        )
                        asyncio.create_task(run_investigation_pipeline(sig_id))
                        continue

                    recent_reports = conn.execute(
                        """SELECT COUNT(DISTINCT r.user_id_anon) as recent_count
                           FROM user_reports r
                           JOIN error_signatures e ON r.error_sig_id = e.id
                           WHERE r.error_sig_id = ? AND r.created_at >= ?""",
                        (sig_id, two_weeks_ago)
                    ).fetchone()[0]

                    if recent_reports >= 10:
                        update_error_status(sig_id, "new")
                        logger.info("Volume trigger (10+ em 14d): %s", error_hash)
                        asyncio.create_task(run_investigation_pipeline(sig_id))

                    all_reports = conn.execute(
                        """SELECT COUNT(DISTINCT r.user_id_anon) as total_count
                           FROM user_reports r
                           WHERE r.error_sig_id = ? AND r.created_at >= ?""",
                        (sig_id, two_months_ago)
                    ).fetchone()[0]

                    if all_reports >= 30:
                        update_error_status(sig_id, "new")
                        logger.info("Volume trigger (30+ em 60d): %s", error_hash)
                        asyncio.create_task(run_investigation_pipeline(sig_id))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Erro na verificação de volume: %s", str(e))

        await asyncio.sleep(interval_seconds)


def stop_volume_check():
    global _running
    _running = False
